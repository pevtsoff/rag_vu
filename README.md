# RAG-VU

RAG-VU is a document ingestion and retrieval-augmented question answering (RAG) application. It accepts files supported by [Docling](https://docling-project.github.io/docling/), converts them into structured text, splits that text into searchable chunks, and stores vector embeddings in PostgreSQL with pgvector. Users can search the indexed material and ask questions through a chat interface that retrieves relevant passages and cites their source context.

The project is document-type agnostic: it is no longer limited to legal text or law-specific chunking. Laws remain supported, including a dedicated parser for Russian laws published on pravo.gov.ru. For ordinary uploads, the pipeline uses Docling's document structure and hybrid chunking; when legal article nodes are present, chunking prioritizes article and article-part text.

## What it includes

- A FastAPI API for uploading documents, tracking ingestion pipelines, and viewing source nodes.
- Asynchronous ingestion with Celery and Redis: upload, parse with Docling, create chunks, and generate embeddings.
- PostgreSQL storage for documents, structured nodes, chunks, and vector embeddings.
- A Chainlit chat interface with vector and BM25 retrieval, reranking, and source-grounded answers.
- Configurable embedding, chat, and reranking providers: Ollama and OpenRouter.

## Run with Docker Compose

Prerequisites: Docker with the Compose plugin. A local Python 3.12 environment is needed only for running maintenance scripts outside Docker.

1. Configure `.env` in the repository root. The checked-in file has local development defaults. Set database credentials and any model provider settings you need; keep API keys private.
2. Build and start the services:

   ```bash
   make build
   ```

   For subsequent starts without rebuilding, use `make up`.
3. Apply database migrations:

   ```bash
   make migrate-up
   ```

4. Open the API health check at [http://localhost:8080/health](http://localhost:8080/health), the interactive API docs at [http://localhost:8080/docs](http://localhost:8080/docs), and the chat UI at [http://localhost:8000](http://localhost:8000).

The default `PORT_PREFIX=8` exposes the API on port `8080` and chat on port `8000`. If you change the prefix, the ports are `${PORT_PREFIX}080` and `${PORT_PREFIX}000`. The chat service defaults to `http://localhost:8080` for the API; set `RAG_VU_API_BASE_URL` if it is hosted elsewhere.

## API endpoints

The complete interactive schema is available at `/docs` (Swagger UI), `/redoc` (ReDoc), and `/openapi.json` (OpenAPI JSON), using the API host and port shown above. The application routes currently registered are:

### Health

- `GET /health` — returns `{"status":"healthy"}` when the API is running.

### Documents, API v1

- `POST /api/v1/documents/upload` — upload a file as multipart form data using the required `file` field. An identical upload returns its active pipeline; pass `force_run=true` to cancel the active pipeline and start a new one. A new document always gets its initial pipeline.
- `GET /api/v1/documents/{doc_id}` — retrieve document metadata and processing status.
- `GET /api/v1/documents/{doc_id}/rerun/{stage}?force_run=true` — force a pipeline rerun from a stage, cancelling any active run first. Without `force_run=true`, the endpoint returns the active pipeline or responds with `409` if none is running. The accepted `PipelineStages` values are `uploading`, `parsing`, and `chunking`. Parsing continues through chunking and embedding; chunking recreates embeddings from the existing parse.
- `POST /api/v1/documents/search` — submit JSON `{"query": "...", "top_k": 5}` to search documents; `top_k` must be between 1 and 100. Returns a list of matches with IDs, content, and scores.
- `GET /api/v1/nodes/{node_id}/html` — return the rendered HTML for a source node. `node_id` must be a UUID; returns 404 if the node is not found.

### Documents, API v2

- `GET /api/v2/documents/{doc_id}` — retrieve document metadata and processing status.
- `POST /api/v2/documents/search` — accepts the same search request shape as v1. The current handler is a stub and returns an empty list.

## MCP server

The MCP server exposes document upload, pipeline rerun, and document lookup tools. Start the API and workers first, then run the MCP server from the repository root:

```bash
uv run python -m app.mcp.mcp_app
```

By default it serves Streamable HTTP at `http://127.0.0.1:8001/mcp`. The server calls the RAG-VU HTTP API at `RAG_VU_API_BASE_URL` (default `http://localhost:8080`). Set `MCP_HOST` and `MCP_PORT` to change the bind address and port.

The Docker Compose stack includes an `mcp` service at `http://localhost:${PORT_PREFIX}001/mcp` (for example, `http://localhost:8001/mcp` when `PORT_PREFIX=8`). It calls the API through the internal `api:8000` address.

ChatGPT connects to remote MCP endpoints, so it cannot connect to this loopback URL directly. To use it from ChatGPT, expose it through a Secure MCP Tunnel, or host it at a public HTTPS endpoint, then add that HTTPS MCP endpoint in ChatGPT under **Plugins → Add custom MCP server** (or the Apps setup shown for your account). ChatGPT's available MCP features and setup permissions depend on the plan and workspace. See [OpenAI's connection instructions](https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt).

For clients that launch local MCP processes over stdio, set `MCP_TRANSPORT=stdio` and configure the command as `uv run --directory /path/to/rag_vu python -m app.mcp.mcp_app`. `upload_a_file` accepts a path readable by the MCP server process, plus an optional `force_run` flag. `rerun_pipeline` accepts a document UUID, a stage (`uploading`, `parsing`, or `chunking`), and an optional `force_run` flag. `get_document` accepts a document UUID.

The Makefile includes these useful commands:

```bash
make ps              # list running containers
make logs            # follow service logs
make restart         # restart services
make down            # stop and remove containers
make migrate-history # show Alembic migration history
make migrate-down    # roll back one migration
make help            # list documented Makefile targets
```

`make migrate-create MSG="describe schema change"` creates a migration. `make down-v` removes the PostgreSQL data volume. `make flush` drops and recreates the database schema and migration files; both commands erase stored data.

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

Upload a Docling-supported file to `POST /api/v1/documents/upload`. The API stores the original file under `media/documents`, creates document and pipeline records, then dispatches processing to the Celery worker. Docling converts the file into a structured document; RAG-VU builds source nodes, chunks their text, generates embeddings, and persists the results. Redis is used as the Celery broker and is started by Compose. Pipeline status records progress and stage errors.

The API provides stage reruns at:

- `GET /api/v1/documents/{document_id}/rerun/parsing` — parse again, then continue through chunking and embedding.
- `GET /api/v1/documents/{document_id}/rerun/chunking` — recreate chunks and embeddings from the existing parse.

For PDF files, the worker enables Russian and English OCR for scanned pages. The worker image includes LibreOffice for RTF conversion. Supported input formats depend on the installed Docling version and its configured backends.

After application or schema updates, apply migrations with `make migrate-up`.

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

Russian laws remain a supported source type. The dedicated parser can fetch a law from pravo.gov.ru and save its document record and legal hierarchy to PostgreSQL. Its built-in example can be run with:

```bash
uv run python -m app.services.parser.pravo_parser
```

Law documents uploaded through the general API also go through the Docling ingestion pipeline. The chunker uses article and article-part nodes when the parser provides them, preserving legal hierarchy for retrieval.

## Manual processing

The chunking script can be used for stored documents during maintenance or debugging. Configure the database and embedding provider first:

```bash
uv run python -m app.services.chunking.chunking
```

To process one document by UUID:

```bash
uv run python -m app.services.chunking.chunking --document-id DOCUMENT_UUID
```

OpenRouter embeddings require `OPENROUTER_API_KEY`. Ollama embeddings require a reachable Ollama service and configured embedding model.

## Example database data

The CSV files below show representative rows from the ingestion workflow:

- [Documents](docs/data_examples/documents.csv) — document metadata and ingestion status.
- [Nodes](docs/data_examples/nodes.csv) — parsed content and its source structure.
- [Chunks](docs/data_examples/chunks.csv) — chunk text and embedding columns.

These are illustrative snapshots. Depending on the embedding provider, vectors are stored in `embedding_big`, `embedding_mid`, or `embedding_small`.
