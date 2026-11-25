# The whole process

One upload from the file to an answer, at a high level. Each box links to its detailed
diagram: [upload and pipeline](01_upload_and_pipeline.md), [force_upload](02_force_upload.md),
[versioning stage](03_versioning_stage.md), [versioning endpoint](04_versioning_endpoint.md),
[query and retrieval](05_query_and_retrieval.md).

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant API as API (FastAPI)
    participant DB as PostgreSQL<br/>(documents, outbox, inbox)
    participant EP as Event processor
    participant W as Stage workers (Celery)
    participant Q as Chat (AnswerQuestion)
    participant M as Models<br/>(embedder, reranker, LLM)

    rect rgb(235, 245, 255)
    Note over User,DB: 1. Upload (01, 02)
    User->>API: POST /documents/upload (file, optional force_upload)
    API->>DB: identical file (sha256)? reuse it
    alt force_upload=replace_latest
        API->>DB: soft-delete the latest "law.pdf", new row takes its cluster and version
    else force_upload=create_new
        API->>DB: new cluster v1, renamed law_2.pdf
    else no force_upload
        API->>DB: new cluster v1 (decided later by the versioning stage)
    end
    API->>DB: document + pipeline + FileReceivedEvent, one transaction
    API-->>User: id, pipeline_id, cluster_id, version
    end

    rect rgb(240, 250, 240)
    Note over DB,M: 2. Ingestion pipeline (01): event → inbox → job → next event
    loop upload → parsing → chunking → embedding
        EP->>DB: outbox events to inbox rows
        EP->>W: job(inbox_id)
        W->>W: store file / Docling parse / chunk
        W->>M: embed chunks (embedding stage)
        W->>DB: result + next event, one transaction
    end
    end

    rect rgb(255, 248, 235)
    Note over DB,W: 3. Versioning stage (03)
    EP->>W: job(versioning)
    W->>W: fingerprint: MinHash, law identifier, average embedding
    alt decided by force_upload or manually
        W->>DB: keep the assignment, store the fingerprint
    else same legal identifier as another document
        W->>DB: next version of its cluster (or duplicate)
    else similar fingerprint to a cluster's latest version
        W->>DB: new version / duplicate / new document by thresholds
    end
    W->>DB: DocumentVersionedEvent, pipeline SUCCEEDED
    end

    opt 4. The decision was wrong (04)
        User->>API: POST /documents/{id}/versioning (create_new | join)
        API->>DB: split into own cluster, or join another as latest
        API-->>User: document with new cluster and version
    end

    rect rgb(245, 240, 255)
    Note over User,M: 5. Question (05)
    User->>Q: question
    Q->>Q: about changes between versions? → search every version
    Q->>M: embed the question
    Q->>DB: vector + BM25 + article search (latest versions, or all versions)
    Q->>Q: fuse (RRF), pick versions, label passages [Doc | vN | ред.]
    Q->>M: rerank, then answer from the passages
    Q-->>User: answer with source links
    end
```
