#!/usr/bin/env bash
# Remove the pre-refactor ("old") solution, keeping only the hexagonal rewrite.
#
# Deletes 76 legacy .py files that are unchanged since master and not imported by any new
# code, plus their non-.py leftovers and the now-empty app/routers, app/schemas, app/mcp
# folders. Tracked files are removed with `git rm`, so the result is a set of staged
# deletions you can review (`git status`, `git diff --cached --stat`) and undo
# (`git restore --staged --worktree <path>`) before committing.
#
# Kept on purpose: alembic/versions/* (migration history), app/__init__.py,
# tests/conftest.py.
#
# Usage, from the repository root:  bash remove_legacy_code.sh

set -euo pipefail

if [[ ! -f pyproject.toml || ! -d app/adapters ]]; then
    echo "Run this from the rag_vu repository root." >&2
    exit 1
fi

LEGACY_PY=(
    app/config.py
    app/settings.py

    app/api/__init__.py
    app/api/v1/__init__.py
    app/api/v1/documents.py
    app/api/v1/nodes.py
    app/api/v2/__init__.py
    app/api/v2/documents.py

    app/db/__init__.py
    app/db/db_enums/__init__.py
    app/db/db_enums/node_types.py
    app/db/model_base.py
    app/db/session.py

    app/models/__init__.py
    app/models/api/__init__.py
    app/models/api/document/__init__.py
    app/models/api/document/document_create.py
    app/models/api/document/document_response.py
    app/models/api/document/pipeline_response.py
    app/models/api/document/rerun_pipeline.py
    app/models/api/document/run_document_pipeline.py
    app/models/api/document/search_request.py
    app/models/api/document/search_response.py
    app/models/api/document/upload_document.py
    app/models/db/__init__.py
    app/models/db/chunk.py
    app/models/db/document.py
    app/models/db/node.py
    app/models/db/pipeline.py
    app/models/services/__init__.py
    app/models/services/chunk_data.py
    app/models/services/parsed_node.py
    app/models/services/retrieved_match.py

    app/services/__init__.py
    app/services/embeddings.py
    app/services/api/__init__.py
    app/services/api/nodes_search.py
    app/services/api/documents/__init__.py
    app/services/api/documents/common.py
    app/services/api/documents/pipelines.py
    app/services/api/documents/rerun_stage.py
    app/services/api/documents/upload_document.py
    app/services/background_jobs/__init__.py
    app/services/background_jobs/celery_app.py
    app/services/background_jobs/dispatch.py
    app/services/background_jobs/exceptions.py
    app/services/background_jobs/tasks.py
    app/services/chunking/__init__.py
    app/services/chunking/builders.py
    app/services/chunking/chunking.py
    app/services/chunking/connection.py
    app/services/chunking/docling.py
    app/services/chunking/persistence.py
    app/services/chunking/processing.py
    app/services/chunking/text.py
    app/services/parser/__init__.py
    app/services/parser/parser.py
    app/services/parser/pravo_parser.py
    app/services/query/__init__.py
    app/services/query/answer.py
    app/services/query/bootstrap.py
    app/services/query/chat.py
    app/services/query/exceptions.py
    app/services/query/providers.py
    app/services/query/query.py
    app/services/query/rerank.py
    app/services/query/retrieve_context.py
    app/services/query/search_chunks.py
    app/services/query/settings.py
    app/services/query/types.py

    tests/test_chunking.py
    tests/test_document_pipelines_endpoint.py
    tests/test_ingestion.py
    tests/test_nodes_endpoint.py
    tests/test_pravo_parser.py
    tests/test_query_services.py
)

LEGACY_OTHER=(
    app/services/api/templates/node.html
    app/services/query/chainlit.md
    app/services/query/.chainlit
)

LEGACY_DIRS=(app/api app/db app/models app/services app/routers app/schemas app/mcp)

remove_path() {
    local path="$1"
    [[ -e "$path" ]] || return 0
    if git ls-files --error-unmatch "$path" >/dev/null 2>&1 \
        || [[ -n "$(git ls-files -- "$path")" ]]; then
        git rm -r -q -- "$path"
    else
        rm -rf -- "$path"
    fi
    echo "removed $path"
}

echo "Removing ${#LEGACY_PY[@]} legacy .py files..."
for path in "${LEGACY_PY[@]}"; do remove_path "$path"; done

echo "Removing non-.py leftovers..."
for path in "${LEGACY_OTHER[@]}"; do remove_path "$path"; done

echo "Cleaning stale __pycache__ and empty folders in legacy directories..."
for dir in "${LEGACY_DIRS[@]}"; do
    [[ -d "$dir" ]] || continue
    find "$dir" -type d -name __pycache__ -prune -exec rm -rf {} +
    find "$dir" -depth -type d -empty -delete
done
rm -f app/__pycache__/config.cpython-*.pyc app/__pycache__/settings.cpython-*.pyc

leftover=0
for dir in "${LEGACY_DIRS[@]}"; do
    if [[ -d "$dir" ]]; then
        echo "WARNING: $dir still contains files not on the legacy list (left untouched):" >&2
        find "$dir" -type f >&2
        leftover=1
    fi
done

echo "Checking that no remaining code imports the removed modules..."
if grep -rnE "^\s*(from|import)\s+app\.(services|api|models|db|routers|schemas|mcp|settings)\b|^\s*from\s+app\s+import\s+(config|settings)\b" \
    --include='*.py' app tests alembic; then
    echo "ERROR: the imports above still point at removed code." >&2
    exit 1
fi

echo
echo "Done. Review with:  git status && git diff --cached --stat"
echo "Then verify with:   make lint && uv run --extra dev pytest tests/unit"
echo "Delete this script when finished:  rm remove_legacy_code.sh"
exit "$leftover"
