# Upload and the ingestion pipeline

A plain upload (no `force_upload`). Every stage commits its result, the next event and the
inbox acknowledgement in one transaction; Redis only carries inbox ids.

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant API as API (FastAPI)
    participant Upload as UploadDocument
    participant Storage as LocalFileStorage
    participant DB as PostgreSQL
    participant EP as Event processor
    participant Celery as Celery (Redis)
    participant Workers as Stage workers

    User->>API: POST /documents/upload (file)
    API->>Upload: execute(stream, file_name, mime_type)
    Upload->>Storage: stage(stream) to .incoming, sha256
    Upload->>DB: get_by_sha256(sha256) FOR UPDATE
    alt identical file already stored
        DB-->>Upload: existing document
        Upload->>Storage: discard(staged file)
        Upload-->>API: existing document and active pipeline (duplicate=true)
    else new content
        Upload->>DB: BEGIN, insert document (v1, own cluster, latest)
        Upload->>DB: insert pipeline (stage=uploading)
        Upload->>DB: insert FileReceivedEvent into outbox, COMMIT
        Upload-->>API: document, pipeline (duplicate=false)
    end
    API-->>User: 200 {id, pipeline_id, cluster_id, version, is_latest}

    loop for each stage: upload, parsing, chunking, embedding, versioning
        EP->>DB: lock pending outbox events (SKIP LOCKED)
        EP->>DB: insert inbox row per consumer (ON CONFLICT DO NOTHING)
        EP->>Celery: send job with inbox id (queue = stage)
        Celery->>Workers: run job(inbox_id)
        Workers->>DB: claim inbox row (lock token)
        Workers->>DB: prepare: load the stage input
        Note over Workers: compute: slow work outside a transaction
        Workers->>DB: persist: result + next event + complete inbox row, COMMIT
    end
    Note over DB: pipeline SUCCEEDED, document SUCCEEDED
```

What each stage does and emits:

| Stage | Consumes | Work | Emits |
|---|---|---|---|
| upload | `FileReceivedEvent` | move the file to `media/documents/<id>/`, verify size and sha256 | `FileUploadedEvent` |
| parsing | `FileUploadedEvent` | Docling: nodes, structure JSON, OCR | `DocumentParsedEvent` |
| chunking | `DocumentParsedEvent` | hybrid chunker / text splitter | `DocumentChunkedEvent` |
| embedding | `DocumentChunkedEvent` | chunk vectors in batches | `DocumentEmbeddedEvent` |
| versioning | `DocumentEmbeddedEvent` | fingerprint, assign cluster and version ([03](03_versioning_stage.md)) | `DocumentVersionedEvent` |
