# Sequence diagrams

Mermaid sequence diagrams of the ingestion, versioning and query flows. GitHub and most IDEs
render them in place.

| Diagram | Covers |
|---|---|
| [00_whole_process.md](00_whole_process.md) | The whole flow on one page: upload, pipeline, versioning, fixes, questions |
| [01_upload_and_pipeline.md](01_upload_and_pipeline.md) | Plain upload, outbox → inbox → Celery, the five pipeline stages |
| [02_force_upload.md](02_force_upload.md) | `force_upload=replace_latest` and `create_new`, and their errors |
| [03_versioning_stage.md](03_versioning_stage.md) | How the versioning stage assigns a cluster and version |
| [04_versioning_endpoint.md](04_versioning_endpoint.md) | Fixing a decision with `POST /documents/{id}/versioning` |
| [05_query_and_retrieval.md](05_query_and_retrieval.md) | A chat question: hybrid search, latest-only vs every version, rerank, answer |

How they fit together:

1. A file enters through `POST /documents/upload` (01), optionally with `force_upload` (02).
2. The pipeline ends with the versioning stage (03), which decides automatically unless
   `force_upload` already decided.
3. A wrong decision is fixed later with the versioning endpoint (04).
4. Questions only see live, non-duplicate documents, by default only their latest versions (05).
