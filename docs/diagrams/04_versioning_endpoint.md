# Fixing a decision: `POST /documents/{id}/versioning`

For a wrong automatic decision found after ingestion, whatever the file names. It is recorded
as `source: manual`, so a rerun of the versioning stage keeps it.

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant API as API
    participant UC as ChangeDocumentVersioning
    participant Members as ClusterMembership
    participant DB as PostgreSQL

    User->>API: POST /documents/{id}/versioning {mode, cluster_id}
    alt mode = join without cluster_id
        API-->>User: 422
    end
    API->>UC: execute(document_id, mode, cluster_id)
    UC->>DB: BEGIN, get(document) FOR UPDATE
    alt missing or soft-deleted
        UC-->>User: 404 Document not found
    end

    alt mode = create_new (split)
        UC->>Members: leave(document)
        Members->>DB: document: own cluster, v1, latest
        opt it was the latest of its old cluster
            Members->>DB: highest remaining version: latest again
        end
        UC->>UC: clear duplicate_of, if any
    else mode = join (cluster_id)
        UC->>Members: join_as_latest(document, cluster_id)
        Members->>DB: latest_in_cluster(cluster_id) FOR UPDATE
        alt cluster has no latest version
            Members-->>User: 404 Cluster has no latest version
        end
        Members->>Members: leave the old cluster (as above)
        Members->>DB: previous latest: is_latest = false
        Members->>DB: document: cluster_id, version = max + 1, latest
    end
    UC->>DB: doc_metadata.versioning = {source: manual, mode, cluster_id, version}, COMMIT
    API-->>User: 200 document (cluster_id, version, is_latest)
```

Which tool for which situation:

| Situation | Use |
|---|---|
| A corrected copy of the same file | upload with `force_upload=replace_latest` |
| Same file name, different document | upload with `force_upload=create_new` |
| A new redaction of a law | plain upload (automatic) |
| Two different documents were merged | `versioning` `create_new` |
| A version was missed | `versioning` `join` |
| A document was wrongly marked a duplicate | `versioning` `create_new` |
