# Task: Hybrid RAG Document Deduplication & Versioning (`pgvector` + MinHash)

## Goal
Deduplicate and version documents on upload using a two-step check in PostgreSQL: fast semantic search via L2-normalized average embeddings (`pgvector` HNSW), followed by lexical/structural verification using pre-stored MinHash signatures. Support both latest-only and multi-version retrieval.

## 1. Database Schema

**Done** in migration `alembic/versions/20261124_0001_document_versioning.py`, with
`DocumentModel`, `ChunkModel`, the `Document` entity and `SqlAlchemyDocumentRepository`
updated to match.

`documents` already had `version INT NOT NULL` (the entity defaults it to 1) and a unique
`sha256`. The migration reuses `version` as the version number instead of adding a second
one, and adds:

| Column | Type | Notes |
|---|---|---|
| `cluster_id` | `UUID NOT NULL` | Shared by every version of one document. Ids are UUIDs, so this is not `INT`. A new document starts its own cluster (`cluster_id = id`, set by `Document.__post_init__`); existing rows are backfilled the same way |
| `is_latest` | `BOOLEAN NOT NULL DEFAULT TRUE` | |
| `avg_embedding` | `vector(768)`, nullable | The size `qwen3-embedding:0.6b` is configured to return (`OLLAMA_EMBEDDING_DIMENSIONS`), the same as `chunks.embedding_small`. Only this embedder is supported for now. Fingerprinting fails fast if `embedder.dimensions != 768`; the column itself rejects other sizes. Nullable because it is computed after the embedding stage |
| `minhash_sig` | `BIGINT[]`, nullable | 128 values; `BIGINT` avoids signed overflow from 32/64-bit hashes |

Constraints and indexes on `documents`:

- `uq_documents_one_latest_per_cluster`: unique `(cluster_id) WHERE is_latest`. It enforces
  exactly one latest version per cluster and serves the `is_latest` filter. This replaces a
  plain B-tree on the boolean `is_latest`, which the planner would rarely use.
- `uq_documents_cluster_version`: unique `(cluster_id, version)`.
- **Follow-up for `force_upload=replace_latest` (§2.1):** both unique indexes above must become
  partial on `deleted_at IS NULL`, so a soft-deleted replaced row doesn't block its
  replacement. Not in `20261124_0001` yet; add a second migration with §2.
- `ix_documents_cluster_id`: B-tree on `cluster_id`.
- `ix_documents_avg_embedding_hnsw`: HNSW `(avg_embedding vector_cosine_ops)`.
- `ck_documents_minhash_length`: `minhash_sig IS NULL OR cardinality(minhash_sig) = 128`.
- `ck_documents_version_positive`: `version >= 1`.

`chunks` gets `content_hash VARCHAR(32) NOT NULL`, a **stored generated column**:
`md5(lower(btrim(regexp_replace(normalize(text, NFKC), '\s+', ' ', 'g'))))`. Postgres
computes it on every insert and update, so no application code sets it and it can't drift
from `text`. It uses `md5` because `sha256()` would need `convert_to()`, which isn't
immutable and so isn't allowed in a generated column. md5 is used only for equality within
a cluster, not for security.

**Exact duplicates** are already caught by `uq_documents_sha256` before any embedding is
done. Check the file's sha256 first in §2 and skip the fingerprint search on a match.

**Creating a new version** must happen in one transaction: set the previous latest row's
`is_latest = FALSE`, then insert the new row with `version = previous + 1` and
`is_latest = TRUE`. Lock the cluster's latest row (`SELECT … FOR UPDATE`) first. Two
concurrent uploads of a new version then serialise, and the unique indexes turn any
remaining race into an `IntegrityError` (`ConcurrencyConflictError` via
`flush_or_conflict`) instead of two "latest" rows.

## 2. Ingestion Pipeline

A cluster is built incrementally: each new document either joins an existing cluster as
its next version or starts a cluster of its own. There is no batch clustering job. The
decision runs in two places, in this order: the upload request (exact duplicates and the
`force_upload` override), then a **versioning step after the embedding stage** (identity and
fingerprints), because `avg_embedding` needs the chunk embeddings.

### 2.1. At upload (`UploadDocument`)

1. **Exact duplicate.** The existing `get_by_sha256` check stays as it is: an identical
   file reuses its document (and `force_run` still re-runs its pipeline). No fingerprints
   are needed.
2. **`force_upload` override, for a file name that already exists.** `POST /documents/upload`
   gets an optional `force_upload` parameter, `enum VersioningOverride { replace_latest,
   create_new }`, so a person can always override the similarity rules below. It applies
   when a **latest** document (`is_latest = TRUE`, not deleted) has the same `file_name`:
   - `replace_latest`: the upload **replaces** that cluster's latest version. In one
     transaction, lock the latest row (`SELECT … FOR UPDATE`), soft-delete it (set
     `deleted_at`, `is_latest = FALSE`; its chunks are excluded from retrieval and removed
     by the flush/cleanup job), and insert the new document in the same cluster with the
     **same** `version` number and `is_latest = TRUE`. Use for a wrong or broken file that
     should not stay in the history. Because the replaced row is soft-deleted, the
     `(cluster_id, version)` unique index must become partial, `WHERE deleted_at IS NULL`
     (and the same for the one-latest-per-cluster index): add that to the schema
     migration.
   - `create_new`: the upload **starts a new cluster** (`version = 1`, `cluster_id = id`),
     even if the identity or fingerprint rules would make it a version. Use when two
     different documents happen to share a file name, or a wrong merge must be avoided.
   - In both cases the versioning step (§2.2) **doesn't change the assignment**. It still
     computes and stores the fingerprints, so later uploads can match against them.
   - Errors, all returned before anything is stored:
     - `force_upload` given but no latest document has that `file_name` → `422`, so a typo in
       the name isn't silently ignored.
     - Several clusters' latest versions have that `file_name` → `409` listing their
       `cluster_id`s. The caller resends with `cluster_id=<uuid>` to pick one.
     - `create_new` with a file whose sha256 already exists → `409`: `uq_documents_sha256`
       allows one document per identical file. `replace_latest` with an identical file is
       a no-op that returns the existing document.
   - The decision is recorded on the document (`doc_metadata.versioning = {"source":
     "force_upload", "mode": ...}`) and as a span attribute on the upload trace, so overrides are
     visible later.
   - `force_upload` is unrelated to the existing `force_run` flag (re-run the pipeline for an
     identical file). Keep both, and document the difference in the OpenAPI description.
3. Otherwise the document is stored as a **new cluster** (`version = 1`, `is_latest = TRUE`)
   and the versioning step decides after embedding whether it is really a new version.

### 2.2. Versioning step (after the embedding stage)

A new pipeline stage (`versioning`, after `embedding`) emits its event like the other
stage jobs. Skip it when the document was assigned by `force_upload`.

1. **Compute fingerprints once per document:**
   - `avg_embedding`: token-weighted mean of the document's chunk embeddings, L2-normalised
     (`vec / norm(vec)`). Only 768-dimension embeddings are supported (§1).
   - `minhash_sig`: 128-value MinHash (`datasketch`) of normalised 3-to-5-word shingles of
     the full text.
2. **Identity first (legal documents).** If parsing found a document identifier (for a
   Russian law: type, date and number, e.g. `Закон РФ от 07.02.1992 N 2300-1`), store it
   in `doc_metadata.identifier` and look for a latest document with the same identifier.
   Same identifier with different content means a **new version** of that cluster; a
   different identifier means it is **not** a version, whatever the fingerprints say.
   This is deterministic and isn't fooled by two laws on similar topics.
3. **Fingerprints when there is no identifier.** Compare **only against the latest
   version of each cluster**, so a cluster is matched by its current text and doesn't drift
   through old versions:
   ```sql
   SELECT id, cluster_id, version,
          1 - ((avg_embedding <=> :vec) / 2.0) AS sem_sim,
          minhash_sig
   FROM documents
   WHERE is_latest AND deleted_at IS NULL AND id <> :new_id
     AND avg_embedding <=> :vec <= 0.08  -- >= 0.96 semantic similarity on 0-to-1 scale
   ORDER BY avg_embedding <=> :vec
   LIMIT 5;
   ```
   For each candidate, `lex_sim = sum(a == b for a, b in zip(new_sig, row.minhash_sig)) /
   128.0`. Pick the candidate with the highest `lex_sim` (not just the nearest vector):
   - **Near-identical** (`sem_sim >= 0.995` and `lex_sim >= 0.99`): the same content in a
     different file (re-export, other format). Mark the new document a duplicate of that
     one (`doc_metadata.duplicate_of`), set it `is_latest = FALSE` and drop its chunks from
     retrieval. Don't create a version.
   - **New version** (`sem_sim >= 0.96` and `0.5 <= lex_sim < 0.99`): the lower bound is
     required. Averaged embeddings of two different documents on one topic easily reach
     0.96 while sharing little text; a real new version shares most of its wording.
   - **New document** otherwise: it keeps the cluster assigned at upload.
4. **Moving a document into a cluster as a new version** is one transaction: lock the
   cluster's latest row (`SELECT … FOR UPDATE`), set it `is_latest = FALSE`, and update the
   new document to `cluster_id = <cluster>`, `version = previous + 1`, `is_latest = TRUE`.
   The unique indexes turn a concurrent race into a `ConcurrencyConflictError`; retry the
   step once.
5. **Record why** in `doc_metadata.versioning` (`source`: `identifier` / `fingerprint` /
   `new`, matched document id, `sem_sim`, `lex_sim`) and on the stage's trace span.
   Thresholds (`VERSIONING_SEM_SIM`, `VERSIONING_DUPLICATE_SEM_SIM`,
   `VERSIONING_LEX_SIM_MIN`, `VERSIONING_DUPLICATE_LEX_SIM`) go into `AppSettings`.
6. **Fixing a wrong decision** after the fact: the same overrides as `force_upload`, as an
   endpoint on an existing document, `POST /documents/{id}/versioning` with
   `{"mode": "create_new"}` (split it into its own cluster; the remaining versions keep
   their numbers) or `{"mode": "join", "cluster_id": ...}` (make it that
   cluster's latest version).

## 3. Backfill Existing Docs
No need to backfill the existing docs, rather flush the db completely and apply the new changes

## 4. Retrieval & Prompting

Each version is its own `documents` row, and the versions of one document share
`cluster_id`. So "per version" below means per `document_id`, grouped under `cluster_id`.

### 4.1. Default search (`latest_only=True`)
Join chunks to `documents` and filter `documents.is_latest = TRUE` in **every** retrieval
branch (vector, BM25 and exact-article), before fusion. A filter applied after `LIMIT` would
return fewer than `top_k` chunks.

### 4.2. Multi-version search (`latest_only=False`)
The LLM must see **the same passage from each relevant version**, side by side, to compare
them. Don't use MMR here: it treats the v2 and v3 copies of the same clause as redundant and
drops one of them, which is exactly the pair the user wants compared.

Pipeline, in order:

1. **Over-fetch** from each branch (`top_k × multi_version_overfetch`, default 4) without the
   `is_latest` filter, then fuse with RRF as today.
2. **Per-version cap:** keep at most `k_per_version` (default 2) chunks per `document_id`,
   ranked by fused score:
   ```sql
   SELECT * FROM (
     SELECT f.*, ROW_NUMBER() OVER (
              PARTITION BY f.document_id ORDER BY f.fused_score DESC) AS rn
     FROM fused f
   ) t
   WHERE rn <= :k_per_version
   ```
   This is a **ceiling, not a quota**: a version with fewer matching chunks contributes fewer.
3. **Relevance floor:** drop a version whose best chunk scores below
   `version_relevance_floor` (default 0.6) × the best fused score overall. Versions that
   don't really match the question drop out instead of filling slots with noise.
4. **Version cap:** keep at most `max_versions` (default 4) versions per `cluster_id`. Prefer,
   in order: versions the question names (by version number or date, e.g. "в редакции
   2019 года"), the latest version, then the highest-scoring rest.
5. **Rerank** the survivors. The cap runs before rerank, so rerank cost is bounded by
   `max_versions × k_per_version` per cluster.
6. **Collapse unchanged passages:** chunks of one cluster with the same `content_hash` are
   sent once, labelled with the version range they appear in (step 7). The LLM then sees
   outright what did *not* change, instead of re-reading identical text.
7. **Budget:** cut to `multi_version_chunk_budget` (default 10) after collapsing, keeping
   whole version groups where possible. Order the context by cluster, then by
   `version` ascending, so versions read in chronological order.

All defaults go into `AppSettings` (`MULTI_VERSION_OVERFETCH`, `K_PER_VERSION`,
`VERSION_RELEVANCE_FLOOR`, `MAX_VERSIONS`, `MULTI_VERSION_CHUNK_BUDGET`) and are recorded on
the `retrieval.hybrid` span.

### 4.3. Prompting
- Prefix each chunk with `[Doc: {title} | v{version} | {created_at}]`. A collapsed
  passage gets `[Doc: {title} | v1–v3 (без изменений) | {created_at of the first}]`.
- When more than one version of a document is in the context, the instruction says:
  compare the versions; name for each difference which version it comes from; say plainly
  when a passage is unchanged; when the user didn't ask about history, answer from the
  latest version and mention earlier versions only where they differ.
- With a single version in the context, no comparison instruction is added.

## 5. Tests
- Verify `avg_embedding` has L2 norm `1.0` and `minhash_sig` has length `128` regardless of document length.
- Test `force_upload` (§2.1):
  - `replace_latest` on an existing file name: the old latest is soft-deleted, the new
    document has the same cluster and version and is the only latest one.
  - `create_new` on an existing file name: a new cluster with `version = 1`; the old
    cluster is unchanged; the versioning step doesn't move it, even when it would match.
  - Errors: `force_upload` with an unknown file name → 422; a name shared by two clusters without
    `cluster_id` → 409; `create_new` with identical content → 409.
- Test identity: same law identifier with changed text → new version; a different
  identifier with near-identical fingerprints → not merged.
- Test the `lex_sim` floor: two different documents with `sem_sim >= 0.96` and
  `lex_sim < 0.5` stay in separate clusters.
- Test upload flows:
  - Identical file → skipped.
  - Single-sentence/number edit → saved as `v2` (caught by `lex_sim < 0.99`).
  - Heavy rewrite of the same law → `v2` when the identifier matches. Without an identifier it
    becomes a new cluster (its `lex_sim` is below the 0.5 floor); use `force_upload` or the
    versioning endpoint to join it.
  - Unrelated file → new `cluster_id`.
- Confirm HNSW index usage via `EXPLAIN ANALYZE`.
- Schema (done, `tests/integration/test_migrations.py`): the migrated schema matches the
  ORM; a second latest version, a repeated version number, version 0 and a MinHash of the
  wrong length are all rejected; `content_hash` is equal for chunks that differ only in
  case or whitespace and differs otherwise. `tests/unit/domain/test_document.py` covers the
  `cluster_id` default.
- Retrieval (`latest_only=True`): only `is_latest` chunks are returned, and still `top_k`
  of them when older versions match better.
- Retrieval (`latest_only=False`), on a cluster with 6 versions:
  - no version contributes more than `k_per_version` chunks;
  - a version without relevant chunks is dropped by the relevance floor;
  - at most `max_versions` versions appear, and a version named in the question is always
    kept;
  - an unchanged clause appears once, labelled with its version range;
  - a clause changed in v3 appears as two chunks (v1–v2 and v3+), in version order;
  - the context never exceeds `multi_version_chunk_budget`.
- Prompt builder: the comparison instruction is present only when two or more versions of
  one document are in the context.
- Ragas: add 5 multi-version questions ("что изменилось в статье … между редакциями") to the
  eval testset and compare Context Precision and Noise Sensitivity against plain MMR before
  fixing the defaults.
