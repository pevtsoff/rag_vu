# A question: retrieval and answer

The chat UI calls `AnswerQuestion`; `POST /documents/search` uses the same retriever with an
explicit `latest_only`. Soft-deleted documents and duplicates are never searched.

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant Chat as Chainlit UI
    participant AQ as AnswerQuestion
    participant Emb as Embedder
    participant Ret as SqlAlchemyHybridRetriever
    participant DB as PostgreSQL
    participant Rr as Reranker
    participant LLM as Chat model

    User->>Chat: question
    Chat->>AQ: execute(question, history)
    AQ->>AQ: retrieval query (follow-ups get the previous question)
    AQ->>AQ: latest_only = not asks_about_versions(question)
    AQ->>Emb: embed(query)
    AQ->>Ret: retrieve(vector, query, latest_only)

    par three searches, each over live, non-duplicate documents
        Ret->>DB: vector: nearest chunks (pgvector)
    and
        Ret->>DB: BM25: node text (pg_textsearch)
    and
        Ret->>DB: article: exact "Статья N", if named
    end
    Note over Ret,DB: latest_only: only is_latest documents<br/>every version: 4x over-fetch
    Ret->>Ret: reciprocal rank fusion (+ whole article for list questions)
    Ret->>DB: version rows of the candidates (document, cluster, version, redaction)

    opt every version (question about changes)
        Note over Ret: at most 2 passages per version<br/>drop versions below 0.6 x best score<br/>at most 4 versions per document:<br/>named in the question, then latest, then best
    end
    Ret-->>AQ: candidates (with version info)

    alt latest_only
        AQ->>Rr: rerank(query, candidates), top_k
    else every version
        AQ->>Rr: rerank(query, candidates, limit = 10)
        AQ->>AQ: collapse identical passages across versions,<br/>order by version, oldest first
    end
    AQ->>AQ: label each passage [Doc: file | v2 | ред. от ...]
    opt two or more versions of one document in the context
        AQ->>AQ: add the instruction to compare versions
    end
    AQ->>LLM: system prompt + context + history + question
    LLM-->>AQ: answer
    AQ->>AQ: remove reasoning leaks, append source links
    AQ-->>Chat: answer with sources
    Chat-->>User: answer
```
