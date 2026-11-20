# RAG-VU

RAG-VU is a document ingestion and retrieval-augmented question answering (RAG) application. It accepts files supported by [Docling](https://docling-project.github.io/docling/), converts them into structured text, splits that text into searchable chunks, and stores vector embeddings in PostgreSQL with pgvector. Users can search the indexed material and ask questions through a chat interface that retrieves relevant passages and cites their source context.

The project is document-type agnostic. Laws remain supported, including a dedicated importer for Russian laws published on pravo.gov.ru; when legal article nodes are present, chunking uses article parts instead of repeating the whole article.

## What it includes

- A FastAPI API for uploading documents, tracking pipelines, searching, and viewing source nodes.
- An **event-driven ingestion pipeline** with four stages — **upload → parsing → chunking → embedding** — each a Celery job on its own queue, connected by events stored in PostgreSQL (transactional outbox + idempotent inbox).
- PostgreSQL storage for documents, structured nodes, chunks, vectors, and the event tables.
- A Chainlit chat interface with vector + BM25 + exact-article retrieval, reranking, and source-grounded answers.
- Configurable embedding, chat, and reranking providers: Ollama and OpenRouter.

## Architecture

The code follows Hexagonal (Ports and Adapters) architecture. See [docs/architecture/refactoring_plan.md](docs/architecture/refactoring_plan.md) for the full design.

```
app/
├── domain/        entities (Document, Pipeline, Node, Chunk), stages, domain events
├── application/   ports (interfaces) and use cases; depends only on the domain
├── adapters/
│   ├── inbound/   http (FastAPI), celery_jobs, event_processor, chat_ui (Chainlit), cli
│   └── outbound/  persistence (SQLAlchemy), storage, parsing (Docling), law_sources,
│                  chunking, embeddings, llm, rerank, retrieval, rendering, messaging
├── bootstrap/     composition root (wires adapters into use cases)
└── config/        settings
```

### Event flow

```
POST /upload ─► FileReceivedEvent ─► [upload]    move file to storage, verify size/sha256
             ─► FileUploadedEvent ─► [parsing]   Docling → nodes, structure JSON, image OCR
             ─► DocumentParsedEvent ─► [chunking] hybrid chunker or text splitter
             ─► DocumentChunkedEvent ─► [embedding] vectors in batches → pipeline SUCCEEDED
             ─► DocumentEmbeddedEvent
```

Every event has `event_id`, `event_type`, `producer`, `occurred_at` and a JSON payload (always with `document_id` and `pipeline_id`).

- **Outbox** (`outbox_events`): a use case writes its state change and the next event in one transaction. Nothing is sent to a broker from request handlers or jobs.
- **Event processor** (`event-processor` service): polls the outbox in batches with `FOR UPDATE SKIP LOCKED`, inserts one `inbox_events` row per (event, consumer) with `ON CONFLICT DO NOTHING`, then dispatches a Celery job — carrying only the inbox id — to the consumer's queue. It also redelivers jobs that were lost or abandoned.
- **Inbox** (`inbox_events`): a job first *claims* its row (with a lock token), does the work, and marks the row `PROCESSED` in the same transaction that stores the result and the next event. A duplicate or redelivered job finds the row already processed and does nothing.

Redis is only the Celery transport; events are never stored or emitted through it.

## Run with Docker Compose

Prerequisites: Docker with the Compose plugin.

1. Configure `.env` in the repository root (see `.env.example`). Keep API keys private.
2. Build and start the services with `make build` (later: `make up`).
3. Apply database migrations: `make migrate-up`.
4. Open the API health check at [http://localhost:8080/health](http://localhost:8080/health), the API docs at [http://localhost:8080/docs](http://localhost:8080/docs), and the chat UI at [http://localhost:8000](http://localhost:8000).

Services: `postgres`, `redis`, `api`, `event-processor`, `worker-upload`, `worker-parsing`, `worker-chunking`, `worker-embedding`, `query` (Chainlit).

The default `PORT_PREFIX=8` exposes the API on port `8080` and chat on `8000`; other prefixes give `${PORT_PREFIX}080` and `${PORT_PREFIX}000`. Set `RAG_VU_API_BASE_URL` if the API is hosted elsewhere.

Event processing settings (all optional): `EVENT_BATCH_SIZE` (100), `EVENT_POLL_INTERVAL_SECONDS` (1), `INBOX_LOCK_TIMEOUT_SECONDS` (3600, must exceed the slowest stage), `INBOX_REDELIVERY_AFTER_SECONDS` (300), `EMBEDDING_BATCH_SIZE` (32).

## API endpoints

The interactive schema is at `/docs`, `/redoc` and `/openapi.json`.

- `GET /health` — `{"status":"healthy"}`.
- `POST /api/v1/documents/upload` — multipart `file`. An identical upload returns its active pipeline (`duplicate: true`); `force_run=true` cancels it and starts a new one.
- `GET /api/v1/documents/{doc_id}` — document metadata and status.
- `GET /api/v1/documents/{doc_id}/pipelines` — pipeline history, newest first.
- `GET /api/v1/documents/{doc_id}/rerun/{stage}?force_run=true` — restart from `uploading`, `parsing`, `chunking` or `embedding` (cancels any active run). Without `force_run=true` it returns the active pipeline, or `409` if none is running.
- `POST /api/v1/documents/search` — `{"query": "...", "top_k": 5}` (`top_k` 1–100); hybrid search returning `id`, `content`, `score`, `node_ids`.
- `GET /api/v1/nodes/{node_id}/html` — rendered source node; `404` if missing or not renderable.
- `GET /api/v2/documents/{doc_id}`, `POST /api/v2/documents/search` — same as v1.

Useful Makefile targets: `make ps`, `make logs`, `make restart`, `make down`, `make migrate-history`, `make migrate-down`, `make help`. `make down-v` and `make flush` erase stored data.

## Configure models

Provider settings are read from `.env`. Set `OPENROUTER_API_KEY` when using an OpenRouter feature. You can choose providers independently for chat, embeddings, and reranking.

### Embeddings

Chunking uses `EMBEDDING_PROVIDER` and a matching tokenizer. Defaults are `OLLAMA_EMBEDDING_TOKENIZER=Qwen/Qwen3-Embedding-0.6B`, `OPENROUTER_EMBEDDING_TOKENIZER=nvidia/Nemotron-3-Embed-1B-BF16`, and `EMBEDDING_CHUNK_MAX_TOKENS=512`. If you change the embedding model, configure its matching Hugging Face tokenizer too. The worker caches tokenizer files in the `rag_vu-hf-cache` Docker volume.

OpenRouter embeddings use `nvidia/nemotron-3-embed-1b:free` in the application. Ollama embeddings use the configured `OLLAMA_EMBEDDING_MODEL` (default `qwen3-embedding:0.6b`). To use Ollama, install and start [Ollama](https://ollama.com), then pull the models you configure:

```bash
ollama pull gpt-oss:20b
ollama pull qwen3-embedding:0.6b
```

Example `.env` settings for Ollama:

```dotenv
QUERY_LLM_PROVIDER=ollama
OLLAMA_MODEL=gpt-oss:20b
RERANK_PROVIDER=ollama
OLLAMA_RERANK_MODEL=gpt-oss:20b
EMBEDDING_PROVIDER=ollama
OLLAMA_EMBEDDING_MODEL=qwen3-embedding:0.6b
OLLAMA_BASE_URL=http://localhost:11434
```

For OpenRouter, configure `QUERY_LLM_PROVIDER`, `EMBEDDING_PROVIDER`, and `RERANK_PROVIDER` as `openrouter`. Chat settings include `OPENROUTER_CHAT_MODEL` and `OPENROUTER_CHAT_FALLBACK_MODELS`; reranking uses `OPENROUTER_RERANK_MODEL`. The query service currently permits only free OpenRouter chat model IDs (ending in `:free` or using `openrouter/free`).

Compose sets the query container's Ollama URL from `OLLAMA_DOCKER_BASE_URL`, which defaults to `http://host.docker.internal:11434`; Compose maps that hostname to the host gateway. If Ollama runs on another host or port, set `OLLAMA_DOCKER_BASE_URL` accordingly. Local maintenance scripts run outside Docker and should use an appropriate host-reachable `OLLAMA_BASE_URL`, commonly `http://localhost:11434`.

## Ingest documents

Upload a Docling-supported file to `POST /api/v1/documents/upload`. The API streams it to `media/documents/.incoming`, records the document, its pipeline and a `FileReceivedEvent` in one transaction, and returns immediately. The four stage workers then move the file to `media/documents/<document_id>/`, parse it with Docling (Russian and English OCR for scanned PDFs; LibreOffice for RTF), create chunks, and embed them. Pipeline status shows the current stage and any stage error.

To restart from a stage, use the rerun endpoint or the CLI:

```bash
uv run python -m app.adapters.inbound.cli.rerun_document DOCUMENT_UUID --stage embedding
```

## Query and Search in DB

### Query with the Chainlit UI

Start the Compose services with `make up` (or `make build` on first run), then open [http://localhost:8000](http://localhost:8000) in a browser. The Chainlit UI is exposed on host port `8000` by default. If you change `PORT_PREFIX` from its default `8`, use `http://localhost:${PORT_PREFIX}000` instead. Submit a question in the chat; the service embeds it, retrieves candidates with vector and BM25 search, reranks the results, and asks the configured chat model to answer using the selected passages and their source context. Answers include links to source node HTML at `GET /api/v1/nodes/{node_id}/html`.

### Search directly in PostgreSQL

For a direct full-text BM25 search, connect to the Compose PostgreSQL service and run a query such as the following. Replace the Russian example phrase with your search terms:

```sql
WITH search AS (
    SELECT to_bm25query(
        'воинская обязанность',
        'idx_nodes_text_bm25'
    ) AS query
)
SELECT
    n.id AS node_id,
    n.node_type,
    n.title AS node_title,
    n.breadcrumbs,
    n.text AS node_text,
    d.id AS document_id,
    d.file_name,
    n.text <@> search.query AS bm25_distance
FROM nodes AS n
JOIN documents AS d ON d.id = n.document_id
CROSS JOIN search
WHERE n.text IS NOT NULL
ORDER BY bm25_distance
LIMIT 5;
```

This query uses the `pg_textsearch` BM25 index configured for `nodes.text`; lower distance ranks first. The API also exposes document search through `POST /api/v1/documents/search` (see [API endpoints](#api-endpoints)).

## Law support

Russian laws can be imported from pravo.gov.ru-style pages. The importer stores the law's section/article/part hierarchy as nodes and emits `DocumentParsedEvent`, so chunking and embedding run through the same pipeline:

```bash
uv run python -m app.adapters.inbound.cli.import_law URL [URL ...] [--nodes-json out/]
```

Law documents uploaded as files go through the Docling pipeline instead.

## Tests

```
tests/unit/         no services needed (in-memory fakes for every port)
tests/integration/  real PostgreSQL with pgvector, ltree and pg_textsearch
```

```bash
make test-unit          # local: uv run --extra dev pytest tests/unit
make test-integration   # in Docker against the Compose PostgreSQL (database rag_vu_test)
```

Integration tests need `TEST_DATABASE_URL` (an asyncpg URL); the database is created and migrated automatically, and the tests are skipped when the variable is unset.

## Example database data

The CSV files below show representative rows from the ingestion workflow:

- [Documents](docs/data_examples/documents.csv) — document metadata and ingestion status.
- [Nodes](docs/data_examples/nodes.csv) — parsed content and its source structure.
- [Chunks](docs/data_examples/chunks.csv) — chunk text and embedding columns.

These are illustrative snapshots. Depending on the embedding provider, vectors are stored in `embedding_big`, `embedding_mid`, or `embedding_small`.
