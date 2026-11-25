# Upload with `force_upload`

`force_upload` lets a person decide the version at upload time. It only applies when a latest
document with the same file name exists. All errors happen before anything is stored, and the
staged file is discarded.

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant API as API
    participant Upload as UploadDocument
    participant DB as PostgreSQL
    participant Storage as LocalFileStorage

    User->>API: POST /documents/upload?force_upload=...&cluster_id=...
    API->>Upload: execute(..., override)
    Upload->>Storage: stage(stream)
    Upload->>DB: BEGIN, get_by_sha256 FOR UPDATE
    Upload->>DB: latest_with_file_name(file_name) FOR UPDATE

    alt no latest document has this name
        Upload->>Storage: discard(staged file)
        Upload-->>User: 422 no latest document is called ...
    else replace_latest and several clusters match, no cluster_id
        Upload->>Storage: discard(staged file)
        Upload-->>User: 409 resend with cluster_id (lists the cluster ids)
    else identical content already stored
        alt create_new, or replace_latest of another document
            Upload->>Storage: discard(staged file)
            Upload-->>User: 409 an identical file is already stored
        else replace_latest of that same document
            Upload-->>User: 200 duplicate=true (no change)
        end
    else replace_latest
        Upload->>DB: cancel the target's active pipeline, if any
        Upload->>DB: soft-delete the target (deleted_at, is_latest=false, sha256 freed)
        Upload->>DB: insert new document (same cluster, same version, latest)
        Note right of DB: partial unique indexes ignore deleted rows
        Upload->>DB: insert pipeline + FileReceivedEvent, COMMIT
        Upload-->>User: 200 {cluster_id = target's, version = target's}
    else create_new
        Upload->>DB: exists_with_file_name(law.pdf), (law_2.pdf), ...
        Note right of Upload: first free name: law_2.pdf, law_3.pdf, ...
        Upload->>DB: insert document (v1, own cluster, renamed, original_file_name kept)
        Upload->>DB: insert pipeline + FileReceivedEvent, COMMIT
        Upload-->>User: 200 {filename = law_2.pdf, version = 1}
    end
    Note over DB: doc_metadata.versioning.source = "force_upload":<br/>the versioning stage keeps this assignment
```
