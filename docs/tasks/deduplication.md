# Task: Hybrid RAG Document Deduplication & Versioning (`pgvector` + MinHash)

## Goal
Deduplicate and version documents on upload using a two-step check in PostgreSQL: fast semantic search via L2-normalized average embeddings (`pgvector` HNSW), followed by lexical/structural verification using pre-stored MinHash signatures. Support both latest-only and multi-version retrieval.

## 1. Database Schema
- Add columns to `documents`:
  - `cluster_id INT`
  - `version_num INT DEFAULT 1`
  - `is_latest BOOLEAN DEFAULT TRUE`
  - `avg_embedding vector(1536)`
  - `minhash_sig BIGINT[]` (128-integer array; use `BIGINT[]` to avoid 32-bit signed overflow from 32-bit/64-bit hashes)
- Add indexes:
  - HNSW index on `documents(avg_embedding vector_cosine_ops)`
  - Standard B-tree indexes on `cluster_id` and `is_latest`

## 2. Ingestion Pipeline
- **Compute document fingerprints on upload (once per incoming file):**
  - `avg_embedding`: Token-weighted mean of chunk embeddings, L2-normalized (`vec / norm(vec)`).
  - `minhash_sig`: 128-integer MinHash signature computed from normalized 3-to-5 word shingles (e.g., via `datasketch`).
- **Query top 5 semantic candidates** before inserting (index-friendly cosine distance `<=>`):
  ```sql
  SELECT id, cluster_id, version_num,
         1 - ((avg_embedding <=> \$1) / 2.0) AS sem_sim,
         minhash_sig
  FROM documents
  WHERE avg_embedding <=> \$1 <= 0.08  -- >= 0.96 semantic similarity on 0-to-1 scale
  ORDER BY avg_embedding <=> \$1 ASC
  LIMIT 5;
  ```
- **Evaluate candidates using pre-stored `minhash_sig`:**
  - Compute lexical overlap for each candidate: `lex_sim = sum(a == b for a, b in zip(new_sig, row.minhash_sig)) / 128.0`.
  - **Branching logic (check against top match):**
    1. **Exact Duplicate (`sem_sim >= 0.995` AND `lex_sim >= 0.99`):** Skip ingestion and return existing document ID.
    2. **New Version (`sem_sim >= 0.96` AND `lex_sim < 0.99`):** Inherit `cluster_id`, set previous `is_latest = FALSE`, insert new doc with `version_num + 1`, `is_latest = TRUE`, and save both `avg_embedding` and `minhash_sig`.
    3. **New Document (`sem_sim < 0.96` or no match):** Insert with `version_num = 1`, `is_latest = TRUE`, `cluster_id = id`, and save both fingerprints.

## 3. Backfill Existing Docs
- Write an idempotent migration script to compute and store `avg_embedding` and `minhash_sig` for existing documents, group pairs with `sem_sim >= 0.96` via connected components into a shared `cluster_id`, and assign `version_num` and `is_latest` ordered by `created_at`.

## 4. Retrieval & Prompting
- **Default search (`latest_only=True`):** Filter chunks where `is_latest = TRUE`.
- **Multi-version search (`latest_only=False`):** Over-fetch chunks and apply MMR (or cap at 1–2 chunks per `document_id`) to surface distinct versions without duplicate boilerplate.
- **Prompting:** Prefix chunks with `[Doc: {title} | v{version_num} | {created_at}]` and instruct the LLM to explicitly highlight differences across versions when multiple versions appear.

## 5. Tests
- Verify `avg_embedding` has L2 norm `1.0` and `minhash_sig` has length `128` regardless of document length.
- Test upload flows:
  - Identical file → skipped.
  - Single-sentence/number edit → saved as `v2` (caught by `lex_sim < 0.99`).
  - Heavy rewrite of same topic → saved as `v2` (caught by `sem_sim >= 0.96`).
  - Unrelated file → new `cluster_id`.
- Confirm HNSW index usage via `EXPLAIN ANALYZE`.
