# RAG-VU refactoring plan: hexagonal architecture and an event-driven ingestion pipeline

Status: implemented (see "Implementation steps" for what each step produced).

## 1. Goals

1. Restructure the code base along SOLID principles and the Hexagonal (Ports and Adapters)
   architecture. The previous code is used only as an approximate specification of behaviour.
2. Replace Celery task chaining (`apply_async` from inside tasks, routed through Redis) with an
   event-driven pipeline built on the transactional outbox and inbox patterns.
3. Keep every event in PostgreSQL. Redis is no longer used to emit or store events; it remains
   only as the Celery job transport (the broker that wakes a worker up), and a job message
   carries nothing but the id of an inbox row.
4. Split ingestion into four explicit stages, each a Celery job on its own queue:
   **upload → parsing → chunking → embedding**.
5. Make inbox processing idempotent: an event is processed at most once per consumer, no matter
   how many times it is relayed or how many times Celery delivers the job.
6. Split the test suite into `tests/unit` (no external services) and `tests/integration`
   (real PostgreSQL), and rewrite the tests for the new code.

## 2. Problems in the previous design

| Problem | Consequence |
| --- | --- |
| Tasks chained each other with `apply_async` after committing (`_parse_document` enqueues `chunk_document_task`). | A crash between commit and enqueue silently stalls a pipeline; Redis is the source of truth for "what happens next". |
| The API committed the document and then called `enqueue_pipeline`; a dispatch failure had to be compensated by hand (`dispatch_pipeline` → 503). | Two-phase write without a transaction (dual write). |
| No deduplication of task deliveries (`acks_late` + redelivery could run a stage twice). | Duplicate work; races between two runs of the same stage. |
| Chunking and embedding were one step. | A failed embedding call re-chunked the document; embeddings could not be rebuilt on their own. |
| Business rules, SQLAlchemy, FastAPI `HTTPException`, Docling, httpx and environment lookups were mixed in the same functions. | Hard to test without stubbing half the world; impossible to swap a provider without editing services. |
| Three settings classes (`app/config.py`, `app/settings.py`, query settings) and hard-coded DB URLs in CLI modules. | Configuration drift. |

## 3. Target architecture

```
app/
├── domain/                 Pure Python: entities, value objects, enums, domain events. No I/O.
├── application/            Use cases and ports (abstract interfaces). Depends only on domain.
│   ├── ports/              One ABC per file: repositories, unit of work, storage, parser, …
│   ├── dto/                Plain data passed across ports (staged file, inbox message, …)
│   └── use_cases/          documents/, stages/, events/, query/
├── adapters/
│   ├── inbound/            Drive the application: http (FastAPI), celery (jobs),
│   │                       event_processor, chainlit, cli
│   └── outbound/           Implement ports: persistence (SQLAlchemy/PostgreSQL), storage,
│                           parsing (Docling, pravo.gov.ru), chunking, embeddings, llm,
│                           rerank, retrieval, rendering, messaging (Celery dispatcher)
├── bootstrap/              Composition root: builds adapters and injects them into use cases
└── config/                 One pydantic settings class
```

Dependency rule: `domain` ← `application` ← `adapters` ← `bootstrap`. Inner layers never import
outer ones. Use cases receive ports through their constructor (Dependency Inversion); each port is
small and focused (Interface Segregation); providers (Ollama/OpenRouter, Docling/plain splitter)
are interchangeable implementations of the same port (Liskov, Open/Closed); every class has one
reason to change (Single Responsibility).

The coding rules from `AGENTS.md` still apply: module-scope imports, functions ≤ 30 lines, one
class per file named after the class, type annotations, Ruff (100 columns, double quotes).

## 4. Pipeline stages and events

### 4.1 Event envelope

Every event has at least these fields (stored as columns in both event tables):

| Field | Type | Meaning |
| --- | --- | --- |
| `event_id` | UUID | Unique id, generated when the event is created |
| `event_type` | string | Class name of the event, e.g. `FileUploadedEvent` |
| `producer` | string | Component that emitted it: `api`, `upload`, `parsing`, `chunking`, `embedding`, `law-import` |
| `occurred_at` | timestamptz | When the fact happened (UTC) |
| `payload` | JSONB | Event-specific fields |

All pipeline events also carry `document_id` and `pipeline_id` in the payload.

### 4.2 Event flow

```
HTTP upload ──► FileReceivedEvent ──► [upload queue]    UploadStageJob
                                         moves the staged file to permanent storage,
                                         verifies size + sha256
                └─► FileUploadedEvent (path, file_name, size, sha256, mime_type)
                                   ──► [parsing queue]  ParseStageJob
                                         Docling → nodes, structure JSON, image OCR
                └─► DocumentParsedEvent (structure_path, node_count)
                                   ──► [chunking queue] ChunkStageJob
                                         Docling hybrid chunker or text splitter → chunks
                └─► DocumentChunkedEvent (chunk_count)
                                   ──► [embedding queue] EmbedStageJob
                                         embeds chunks in batches, pipeline SUCCEEDED
                └─► DocumentEmbeddedEvent (chunk_count, dimensions)   (no consumer; audit)

Any stage failure ──► PipelineFailedEvent (stage, error)              (no consumer; audit)
```

Reruns are just events emitted by the API: rerun from `uploading` emits `FileReceivedEvent`,
from `parsing` emits `FileUploadedEvent`, from `chunking` emits `DocumentParsedEvent`, from
`embedding` emits `DocumentChunkedEvent`. The law importer (`pravo.gov.ru`) stores parsed nodes
and emits `DocumentParsedEvent`, so imported laws are chunked and embedded by the same pipeline.

### 4.3 Event routing map

`application/use_cases/events/default_event_routes.py`

| Event type | Consumer | Celery queue | Celery task |
| --- | --- | --- | --- |
| `FileReceivedEvent` | `upload` | `upload` | `jobs.upload` |
| `FileUploadedEvent` | `parsing` | `parsing` | `jobs.parsing` |
| `DocumentParsedEvent` | `chunking` | `chunking` | `jobs.chunking` |
| `DocumentChunkedEvent` | `embedding` | `embedding` | `jobs.embedding` |

An event type can have several consumers; adding one is a one-line change to the map.

## 5. Transactional outbox and inbox

### 5.1 Tables (migration `20261119_0001`)

`outbox_events`: `event_id` (PK), `event_type`, `producer`, `occurred_at`, `aggregate_id`,
`payload`, `status` (`PENDING` / `PUBLISHED`), `published_at`, `created_at`.
Partial index on `occurred_at WHERE status = 'PENDING'`.

`inbox_events`: `id` (PK), `event_id`, `consumer`, `event_type`, `producer`, `occurred_at`,
`payload`, `status` (`RECEIVED` / `PROCESSING` / `PROCESSED` / `FAILED`), `attempts`,
`received_at`, `dispatched_at`, `locked_until`, `lock_token`, `processed_at`, `last_error`.
**Unique constraint `(event_id, consumer)`** — the core of idempotency.

### 5.2 Writing events (outbox)

A use case changes domain state and appends its events to `outbox_events` **in the same
database transaction**. Either both are committed or neither is. Nothing is sent to Celery from
request handlers or stage jobs.

### 5.3 Event processor (relay)

A separate long-running process (`python -m app.adapters.inbound.event_processor`, Compose
service `event-processor`) loops:

1. **Relay a batch** — in one transaction: `SELECT … FROM outbox_events WHERE status='PENDING'
   ORDER BY occurred_at LIMIT :batch FOR UPDATE SKIP LOCKED`; for each event and each route in
   the map, `INSERT INTO inbox_events … ON CONFLICT (event_id, consumer) DO NOTHING RETURNING id`;
   mark the outbox rows `PUBLISHED`; commit.
2. **Dispatch** — after the commit, send one Celery job per *newly inserted* inbox row to the
   route's queue (message = inbox id) and stamp `dispatched_at`.
3. **Redeliver** — rows still `RECEIVED` whose dispatch is older than
   `INBOX_REDELIVERY_AFTER_SECONDS` (dispatch failed, broker lost the message), and rows stuck in
   `PROCESSING` whose `locked_until` has passed (worker died), are dispatched again.
4. Sleep `EVENT_POLL_INTERVAL_SECONDS` when there was nothing to do.

`SKIP LOCKED` lets several processors run side by side without double-relaying.

### 5.4 Running a job (inbox)

`InboxJobRunner` (application layer) wraps every stage job with the template:

1. **Claim** (own transaction): `UPDATE inbox_events SET status='PROCESSING', lock_token=:new,
   locked_until=now()+timeout, attempts=attempts+1 WHERE id=:id AND (status='RECEIVED' OR
   (status='PROCESSING' AND locked_until < now()))`. If no row is updated the event was already
   processed, failed, or is being processed by someone else → the job returns without work.
2. **Prepare** (short read transaction): load the pipeline; if it is no longer `IN_PROGRESS`
   (cancelled by a newer run) the message is completed as *skipped*.
3. **Compute** (no transaction): the slow work — moving files, Docling, tokenising, HTTP calls to
   the embedding provider.
4. **Persist** (one transaction): re-check the pipeline under `SELECT … FOR UPDATE`, write the
   results, append the next event to the outbox, and mark the inbox row `PROCESSED`
   **only if `lock_token` still matches**. Results, the next event and the inbox acknowledgement
   commit atomically, so a redelivered job always finds `PROCESSED` and does nothing.
5. **Failure**: roll back, then in a new transaction mark the inbox row `FAILED`, mark the
   pipeline/document `FAILED` with the stage and error, and emit `PipelineFailedEvent`.

File-system side effects in *compute* are idempotent (moves tolerate an already-moved file,
Docling output is overwritten), so a retry after a crash is safe.

### 5.5 Guarantees

* No event is lost: it is in PostgreSQL before anyone acts on it.
* Each `(event, consumer)` pair is stored once and its result committed once.
* A pipeline cannot advance from a stale run: every stage re-checks `IN_PROGRESS` under a row lock.
* Celery/Redis may lose or duplicate messages without affecting correctness.

## 6. Data model changes

* `pipelines`: `stage` accepts `uploading | parsing | chunking | embedding`; new `embedded`,
  `embedded_at`; the duplicated `last_uploaded/last_parsed/last_chunked` columns are folded into
  `*_at` and dropped. Existing chunked pipelines are marked embedded (they were embedded by the
  old combined step).
* `chunks`: written by the chunking stage without vectors; the embedding stage fills
  `embedding_small` (768, Ollama) or `embedding_big` (2048, OpenRouter) by vector dimension.
* New `outbox_events` and `inbox_events` tables.

## 7. API changes

* `GET /api/v1/documents/{id}/rerun/{stage}` accepts `uploading | parsing | chunking | embedding`.
* `PipelineResponse` exposes `embedded`/`embedded_at` instead of the removed `last_*` fields.
* `POST /api/v1/documents/search` performs a real hybrid search (it was a stub returning `[]`);
  v2 reuses the same use case.
* An upload no longer fails with 503 when the broker is down: the event is durable and will be
  relayed when Celery is reachable.

## 8. Tests

```
tests/
├── unit/          no network, no database; in-memory fakes for every port
│   ├── domain/ application/ adapters/ fakes/
└── integration/   real PostgreSQL (TEST_DATABASE_URL), migrations applied with Alembic
```

Integration tests cover: Alembic upgrade/downgrade, repositories, outbox `SKIP LOCKED`
batching, inbox `ON CONFLICT` idempotency and lock tokens, a full upload→embedding run through
the real database with fake parser/embedder, and the HTTP API against the database.
They are skipped when `TEST_DATABASE_URL` is unset. `make test-unit`, `make test-integration`.

## 9. Implementation steps

1. Domain layer: entities (`Document`, `Pipeline` with stage transitions, `Node`, `Chunk`),
   enums, value objects, events, `EventEnvelope` and `EventRegistry`.
2. Application ports and use cases: documents (upload, rerun, get, list pipelines, render node,
   search, import law), stage jobs (upload, parse, chunk, embed), events (outbox relay,
   redelivery, inbox job runner, routes), query (answer question, prompt helpers, source links).
3. Persistence adapter: SQLAlchemy models, repositories, unit of work, Alembic migration for the
   event tables and pipeline columns; `alembic/env.py` reads the URL from settings.
4. Other outbound adapters: local file storage, Docling parser/node builder/image OCR, pravo.gov.ru
   law source, Docling and text chunkers, Ollama/OpenRouter embedders, chat models and rerankers,
   hybrid retriever (vector + BM25 + exact article + RRF), Jinja renderer, Celery dispatcher.
5. Inbound adapters: FastAPI app factory and routers, one Celery job per queue, event processor
   loop, Chainlit chat, CLIs (`import_law`, `rerun`), composition root.
6. Docker Compose: `worker-upload`, `worker-parsing`, `worker-chunking`, `worker-embedding`,
   `event-processor`; Makefile test targets; README.
7. Tests: unit and integration suites as described above.
8. Verification: Ruff, unit tests, integration tests and migrations against PostgreSQL 17 with
   pgvector and pg_textsearch.
