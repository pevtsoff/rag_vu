# RAG Evaluation with Ragas

## Goal

Build an **opt-in evaluation suite** that runs the real RAG-VU query pipeline
(`embed → SqlAlchemyHybridRetriever → Reranker → ChatModel`, i.e. `AnswerQuestion`) against
the Russian Consumer Protection Law (`Закон РФ от 07.02.1992 N 2300-1 «О защите прав
потребителей»`) and scores it with Ragas. Regressions in retrieval or generation should then
show up as failing tests with a per-sample report.

**Work from the Ragas skill.** The repo carries the `ragas` agent skill at
`.claude/skills/ragas/SKILL.md` (§1.5). Load it before writing any Ragas code. It lists the
current 0.4 API names and the old 0.1-era names that most online snippets still use
(`Dataset.from_dict`, `question`/`contexts`/`ground_truth` columns, lowercase metric
singletons, `TestsetGenerator.from_langchain`, `test_size=`). **Don't write those.** Where
this task and the skill seem to differ, the skill's API names win and the task's design wins.

Metrics in scope (Ragas "Retrieval Augmented Generation" group):

| Metric | What it tells us | Ragas inputs | Direction |
|---|---|---|---|
| Context Precision | Are relevant passages ranked high after rerank? | `user_input`, `reference`, `retrieved_contexts` | higher is better |
| Context Recall | Did retrieval bring everything the reference needs? | `user_input`, `reference`, `retrieved_contexts` | higher is better |
| Context Entities Recall | Are the reference's entities (article numbers, terms, deadlines, amounts) present in the contexts? | `reference`, `retrieved_contexts` | higher is better |
| Noise Sensitivity | How often irrelevant passages push the answer into wrong claims | `user_input`, `response`, `reference`, `retrieved_contexts` | **lower is better** |
| Response Relevancy | Does the answer address the question? (LLM + embeddings) | `user_input`, `response` | higher is better |
| Faithfulness | Is every claim in the answer supported by the contexts? | `user_input`, `response`, `retrieved_contexts` | higher is better |

---

## Current state (what the task builds on)

- **Architecture**: hexagonal.
  - **Settings**: `AppSettings` (`app/config/app_settings.py`). Every model, URL and key the
    eval suite needs comes from it.
  - **Query**: `AnswerQuestion` (`app/application/use_cases/query/answer_question.py`), wired
    by `QueryContainer` (`app/bootstrap/query_container.py`). The Chainlit UI
    (`app/adapters/inbound/chat_ui/chat.py`) and the search endpoint both go through it, so
    evaluating `AnswerQuestion` evaluates what users get.
  - **Ingestion**: the stage jobs wired by `WorkerContainer` (`DoclingDocumentParser`,
    `DoclingHybridChunker`, `infrastructure.embedder`).
- **Arize Phoenix tracing is in place** (README, "Tracing with Arize Phoenix"):
  - Every question produces a `rag.query` trace with `embedding.query`, `retrieval.vector` /
    `retrieval.bm25` / `retrieval.article`, `retrieval.hybrid`, `rerank` and `llm.answer`
    (full prompt, answer, model, token usage) children.
  - Every ingestion stage produces a `pipeline.<stage> [<pipeline id>]` trace, plus a
    closing `pipeline [<pipeline id>]` trace. All of them share `session.id` = pipeline id.
  - Use cases depend only on the `Tracer` / `TraceSpan` ports. `OpenInferenceTracer` exports
    to Phoenix (`PHOENIX_COLLECTOR_ENDPOINT`, `PHOENIX_PROJECT_NAME`) with a batch exporter,
    and `HTTPXClientInstrumentor` turns every outgoing `httpx` call in the process into a
    child HTTP span. With `TRACING_ENABLED=false` a `NullTracer` is used.
  - `AnswerQuestion.execute(question, history, session_id=None)` opens the `rag.query` span.
    `ChatModel.complete()` returns a `ChatCompletion` (`text`, `model`, `usage`,
    `finish_reason`).

  Phoenix already shows *what* the pipeline did for a question. The eval suite adds *how good*
  it was, and links the two (§4.7).
- **Problem 1: the pipeline hides its contexts.** `AnswerQuestion.execute()` returns only the
  final string, with the `**Источники:**` source links already appended by
  `append_source_links`. Ragas needs `retrieved_contexts` (the reranked `RetrievedMatch.text`
  list sent to the LLM) and the raw answer **without** the source-links block. Otherwise the
  links lower Faithfulness and Response Relevancy.
- **Problem 2: the integration harness uses fakes.** `tests/integration/pipeline_runner.py`
  uses `FakeParser`, `TextChunker` and `FakeEmbedder`, and `tests/integration/conftest.py`
  truncates every table before each test (function scope). Evaluation needs the real Docling
  parser, chunker and embedder, and a corpus that is ingested once per session.
- **Test data**: the PDF is at **`tests/eval/test_data/consumer_law.pdf`** (not
  `tests/test_data/`). It has 45 pages and about 136k characters, with articles 1–46
  including 16.1, 23.1, 26.1, 26.2, 39.1 and 42.1–42.3. Every page carries a
  КонсультантПлюс header/footer. **Load it with the project's own Docling parser**, not a
  second PDF library, so the testset's article boundaries match what retrieval indexes
  (§3.2).
- **pytest config**: `testpaths = ["tests/unit", "tests/integration"]`, so a bare `pytest`
  excludes `tests/eval`. **But** the Compose `tests` service runs `pytest tests`, which
  ignores `testpaths` and would collect `tests/eval` (§5.3 fixes this).
  `asyncio_default_fixture_loop_scope = "function"`, so session-scoped async fixtures need an
  explicit `loop_scope="session"`.
- **Providers**: Ollama (`gpt-oss:20b`, `qwen3-embedding:0.6b`) or OpenRouter free models
  (`free_model_policy` rejects paid IDs). Both expose OpenAI-compatible APIs
  (`{OLLAMA_BASE_URL}/v1`, `OPENROUTER_URL`), so Ragas can use either through an
  `AsyncOpenAI` client.
- **Coding standards**: `AGENTS.md` applies to eval code too. One class per file, functions
  of 30 lines or fewer, type annotations, Ruff (100 cols, double quotes), and no silently
  swallowed errors.

---

## 1. Add Ragas to the project

1.1. Add an **optional `eval` extra** so the runtime images don't grow:

```toml
[project.optional-dependencies]
eval = [
    "ragas==0.4.3",          # latest release; collections API (ragas.metrics.collections)
    "openai>=1.50",          # AsyncOpenAI client for llm_factory
    "langchain-openai",      # ChatOpenAI wrapper used by TestsetGenerator
    "langchain-core",
    "pandas",
    "pytest-timeout",        # RAGAS_RUN_TIMEOUT
    "pytest-order",          # judge sanity check runs first (§4.8)
    "arize-phoenix-client>=2.7",  # writes Ragas scores onto traces (§4.7); needs Phoenix server >= 13.15
]
```

No PDF library and no separate embeddings client: Docling is already a dependency (§3.2),
and Ragas embeddings are an adapter over the app's own `Embedder` (§4.2). The OpenTelemetry /
Phoenix exporter packages are already runtime dependencies. Run `uv lock` and commit the
updated `uv.lock`.

1.2. Register a new pytest marker in `pyproject.toml`:

```toml
markers = [
    "integration: requires PostgreSQL (TEST_DATABASE_URL)",
    "eval: Ragas evaluation; requires PostgreSQL, embedder and judge LLM (slow, costs tokens)",
]
```

1.3. Use the **collections API** (`from ragas.metrics.collections import ...`), not the
deprecated `ragas.metrics` singletons. Note: in the collections API, *Response Relevancy* is
exported as **`AnswerRelevancy`**. Metrics take the judge in the constructor and are scored
with `await metric.ascore(**kwargs)`, which returns a `MetricResult` with `.value`. Pin
exactly `0.4.3`, because the Ragas API has broken between minor versions.

Single-sample field names (the skill's data format), used by every metric call and by the
JSONL testset: `user_input` (question), `retrieved_contexts` (list of strings), `response`
(pipeline answer), `reference` (ground-truth answer). Don't use the old `question` /
`contexts` / `ground_truth` names. Note that `evaluate()` accepts only the classic
`ragas.metrics` objects and **rejects collections metrics**, so this suite scores per sample
with `ascore()` (§4.4) and never calls `evaluate()`.

**Import check.** The skill reports that a fresh 0.4.3 install with LangChain 1.x fails on
`import ragas` (`No module named 'langchain_community.chat_models.vertexai'`). After
`uv lock`, run `uv run --extra eval python -c "import ragas"`. If it fails, pin
`langchain<1`, `langchain-core<1`, `langchain-community<0.4` and `langchain-openai<1` in the
`eval` extra, and check the Ragas release notes first, since a newer release may fix it.

1.4. Add `tests/eval/reports/` and `tests/eval/.cache/` to `.gitignore`.

1.5. **Commit the Ragas skill.** Add `.claude/skills/ragas/SKILL.md` (the skill, Apache-2.0,
unchanged). Anyone implementing or extending the eval suite, human or agent, loads it first.
Keep it in step with the pinned version: if `ragas` is bumped, re-check the skill's API
examples against the new release.

1.6. **Privacy switch.** Ragas sends anonymous usage analytics by default. Set
`RAGAS_DO_NOT_TRACK=true` in the `eval` compose service, in `tests/eval/conftest.py`
(`os.environ.setdefault`) and in the README's eval instructions. The law is public text, but
the same setup must stay safe if someone evaluates private documents later; the README also
notes that the judge provider sees the retrieved contexts.

---

## 2. Production-code seam: expose retrieved contexts (small, non-breaking)

Let `AnswerQuestion` return what it already computes, so evaluation runs **exactly** the code
the chat UI runs and doesn't re-implement retrieval in tests.

2.1. New DTO `app/application/dto/answer_trace.py`:

```python
@dataclass(frozen=True)
class AnswerTrace:
    question: str
    retrieval_query: str
    matches: tuple[RetrievedMatch, ...]   # reranked passages sent to the LLM
    answer: str                           # after remove_reasoning_leak, before source links
    answer_with_sources: str              # what the user sees
    model: str                            # ChatCompletion.model that produced the answer
    usage: TokenUsage                     # ChatCompletion.usage
    trace_ids: TraceIds | None            # trace/span id of the rag.query span; None when untraced
```

2.2. Expose the span's ids through the tracing port, so the use case can hand them back
without depending on OpenTelemetry:

- New DTO `app/application/dto/trace_ids.py`:
  `@dataclass(frozen=True) class TraceIds: trace_id: str; span_id: str`, both lowercase hex
  as Phoenix shows them (32 and 16 characters).
- `TraceSpan` gets `@property @abstractmethod def ids(self) -> TraceIds | None`.
  `OpenInferenceSpan` returns them from `otel_span.get_span_context()`
  (`format(ctx.trace_id, "032x")`, `format(ctx.span_id, "016x")`); `NullSpan` returns `None`.
- Unit-test both implementations.

2.3. In `AnswerQuestion`:

- Add `async def trace(question, history, session_id=None) -> AnswerTrace`. It opens the
  same `rag.query` span `execute()` opens today (input, session, attributes, output), so
  eval runs are traced exactly like chat runs.
- Make `_answer` build and return the `AnswerTrace`. `_final_answer` returns the
  `ChatCompletion`'s text, model and usage instead of only the text. `trace_ids` is
  `span.ids` of the `rag.query` span.
- `execute()` becomes `return (await self.trace(question, history, session_id)).answer_with_sources`,
  so its signature, output and spans are unchanged for the chat UI.
- Keep each method at 30 lines or fewer.

2.4. Unit tests in `tests/unit/application/test_answer_question.py`. Check that `trace()`
returns the reranked matches, an answer without the `**Источники:**` block, the chat model's
`model`/`usage`, and `trace_ids` from the span (`None` with `NullTracer`). Check that
`execute()` output is unchanged.

---

## 3. Generate the Ragas test set from `consumer_law.pdf`

Testset generation is a **separate, manually run script**, not a test. Its output is
reviewed and committed, so each eval run is deterministic and doesn't pay for generation.

### 3.1. Files

```
tests/eval/
├── generate_testset.py            # CLI: python -m tests.eval.generate_testset
├── testset/
│   ├── law_article_loader.py      # PDF → one langchain Document per article (via Docling)
│   ├── testset_generator_factory.py
│   └── testset_writer.py
└── test_data/
    ├── consumer_law.pdf
    ├── consumer_law_testset.jsonl # committed, human-reviewed
    └── consumer_law_kg.json       # optional cached KnowledgeGraph (gitignored)
```

### 3.2. Loading the PDF (`LawArticleLoader`)

- **Reuse the app's Docling parser**, built the way `WorkerContainer._parser` builds it:
  `DoclingDocumentParser(create_document_converter, DoclingNodeBuilder(),
  DoclingImageExtractor(TesseractTextRecognizer()))`, then
  `await parser.parse(path, "consumer_law")`. It strips the КонсультантПлюс header/footer
  and splits the law into heading-keyed `ParsedNode`s, so article boundaries are identical to
  what gets indexed. There's no second regex splitter to keep in sync.
- **Parse a temporary copy.** `DoclingDocumentParser` writes `<file>.docling.json` (and
  extracted images) next to its input. Copy the PDF into a `tempfile.TemporaryDirectory()`
  and parse that, so `tests/eval/test_data/` stays clean.
- Map nodes whose title starts with `Статья` into one `langchain_core.documents.Document` per
  article: `page_content = node.text`, `metadata = {"article": <number from the title>,
  "title": node.title, "chapter": <nearest ancestor breadcrumb>}`. This gives
  `reference_contexts` that line up with how the app chunks law articles, and lets the
  retrieval hit-rate checks (§4.5) compare against the identifiers retrieval uses.
- Skip non-article nodes: image nodes, the preamble, the "Список изменяющих документов"
  amendment list, and section-only nodes with no article number.

### 3.3. Generator setup (`TestsetGeneratorFactory`)

- LLM: `LangchainLLMWrapper(ChatOpenAI(base_url=..., api_key=..., model=RAGAS_GENERATOR_MODEL))`.
  The connection comes from `AppSettings` for `RAGAS_JUDGE_PROVIDER` (§4.2).
  `RAGAS_GENERATOR_MODEL` defaults to `RAGAS_JUDGE_MODEL`.
- Embeddings: the same `RagasEmbedderAdapter` over `infrastructure.embedder` used for scoring
  (§4.2). There's no separate embeddings model or client.
- Build the KnowledgeGraph explicitly (`default_transforms` + `apply_transforms`), then
  `kg.save(...)`, so a re-run with a different size or distribution skips the expensive
  transform step.
- **Russian output**: adapt the synthesizer prompts before generating, otherwise questions
  come out in English:
  `prompts = await synth.adapt_prompts("russian", llm=generator_llm); synth.set_prompts(**prompts)`.
- **Personas** (pass `persona_list`): *потребитель, вернувший некачественный товар*;
  *юрист по защите прав потребителей*; *продавец / владелец интернет-магазина*.
- Query distribution: the default is 50% single-hop specific, 25% multi-hop abstract and
  25% multi-hop specific. Keep it, but make sure about 30% of questions name an article
  number ("Что говорит статья 18…"), because the retriever has a dedicated exact-article
  path (`retrieval.article`).
- **Reference example:** the Ragas docs page
  [Testset Generation for RAG](https://docs.ragas.io/en/stable/concepts/test_data_generation/rag/#example_4)
  describes the model this factory follows. Queries are classified as single-hop vs
  multi-hop and specific vs abstract. A `KnowledgeGraph` is built from nodes (the splitter),
  extractors (for example named entities stored as node properties) and relationship
  builders (for example Jaccard overlap of shared entities), chained with
  `apply_transforms`, with `Parallel` for components that can run together. Scenarios are
  then drawn from the graph. Its fourth example shows a custom `QuerySynthesizer` subclass
  with two methods: generate scenarios from related node pairs in the graph, then turn each
  scenario into a sample (query, reference contexts, reference answer). The page's code is a
  skeleton with placeholder bodies, so read it for structure, not as working logic.
  Use it to add a **custom synthesizer** only if the default ones can't produce the
  "name an article number" questions (below); otherwise stay with the built-in synthesizers.
- The skill's basic call is `generator.generate_with_langchain_docs(docs, testset_size=N)`
  with `output` columns `user_input`, `reference`, `reference_contexts`, `synthesizer_name`.
  Our factory builds the `KnowledgeGraph` explicitly, but the output must match those
  columns, so the JSONL below only adds fields. Pass `query_distribution=` built from
  `ragas.testset.synthesizers` to change the mix.
- `testset_size`: **50** by default (`--size`). The skill recommends averaging over 40 or
  more samples and treating differences of about 0.02 as noise, and some generated samples
  are dropped in review. Use `--seed` and `RunConfig(max_workers=2,
  timeout=180, max_retries=5)` so free-tier rate limits don't kill the run.

### 3.4. Output format (`consumer_law_testset.jsonl`)

One JSON object per line:

```json
{
  "id": "cl-001",
  "user_input": "В какой срок продавец обязан заменить товар ненадлежащего качества?",
  "reference": "…",
  "reference_contexts": ["Статья 21. …"],
  "reference_articles": ["21"],
  "synthesizer_name": "single_hop_specific_query_synthesizer",
  "persona": "потребитель",
  "kind": "rag",
  "reviewed": false
}
```

### 3.5. Human review (required before merge)

- Read every sample. Fix or delete hallucinated references, questions answerable without the
  law, and duplicates. Then set `"reviewed": true`.
- Synthetic test sets are a start, not ground truth. Also mix in **5–10 real user
  questions**: pull them from the `rag_vu` Phoenix project (chat `rag.query` traces), write
  the reference answer by hand from the law, and mark them `"synthesizer_name": "manual"`.
- Eval tests load **only** `reviewed: true` samples and fail if fewer than 40 exist, so the
  means are meaningful.
- Add 3–5 **hand-written** "trap" questions that the law doesn't answer
  (`"reference": "В законе нет ответа…"`). They exercise the prompt rule "If it does not
  contain the answer, say so". Give them `"kind": "trap"`, `"reference_articles": []`.

### 3.6. Testset contract

The testset is a versioned input, like a migration. A loose JSONL file silently drifts, so
it is validated on every load.

- `tests/eval/testset/testset_row.py`: a pydantic model for one row with `extra="forbid"`.
  `kind` is `"rag"` or `"trap"`; `id` matches `^cl-\d{3}$`; `user_input` and `reference` are
  non-empty; `kind="rag"` requires at least one `reference_contexts` entry and one
  `reference_articles` entry.
- The loader fails (not skips) on: a schema error, duplicate `id`s, duplicate `user_input`s
  after whitespace/case normalisation, a `reference_articles` value that isn't an article
  number in the parsed law (checked against the `LawArticleLoader` output), or fewer than
  `min_reviewed_samples` reviewed `rag` rows or `min_trap_samples` reviewed `trap` rows.
- **Ids are stable.** Never renumber or reuse an id. Deleting a bad sample retires its id.
  Per-sample baseline comparison (§4.6) depends on it.
- The run manifest (§4.9) records the testset's sha256 and row count. A changed testset
  means a new baseline.
- **Split by kind.** `kind="rag"` rows feed the six Ragas metrics and the retrieval checks.
  `kind="trap"` rows feed **only** the refusal check. A trap's reference ("В законе нет
  ответа…") would score near 0 on Context Recall / Precision and distort every mean.

---

## 4. Evaluation test suite in `tests/eval`

### 4.1. Layout

```
tests/eval/
├── __init__.py
├── conftest.py                    # skip logic, session fixtures
├── eval_settings.py               # EvalSettings (pydantic-settings, prefix RAGAS_)
├── judge_factory.py               # ragas llm_factory over AppSettings connections
├── ragas_embedder_adapter.py      # Ragas embeddings interface over the app's Embedder port
├── eval_corpus.py                 # ingest consumer_law.pdf once with REAL adapters
├── eval_sample.py                 # dataclass: testset row + AnswerTrace
├── eval_run.py                    # runs AnswerQuestion.trace() over the testset
├── corpus_fingerprint.py          # what ingestion reuse is keyed on (§4.3)
├── metric_catalog.py              # the ONE place Ragas metric classes are imported/built
├── metric_runner.py               # scores one metric over all samples, writes report
├── gate.py                        # absolute + baseline-regression gates (§4.6)
├── bootstrap_interval.py          # 95% bootstrap CI of a mean
├── run_manifest.py                # reproducibility record of a run (§4.9)
├── report_writer.py               # per-metric JSON, summary.json, summary.md
├── promote_baseline.py            # CLI behind `make eval-baseline`
├── phoenix_annotator.py           # writes per-sample scores onto rag.query spans (§4.7)
├── untraced_http_client.py        # httpx client for judge calls, excluded from tracing
├── thresholds.toml                # per-metric gates
├── baseline/
│   └── summary.json               # committed baseline run (§4.6)
├── judge_calibration.jsonl        # hand-labelled samples for the judge check (§4.8)
├── test_judge_sanity.py           # runs first; aborts the session if the judge is broken
├── test_context_precision.py
├── test_context_recall.py
├── test_context_entities_recall.py
├── test_noise_sensitivity.py
├── test_response_relevancy.py
├── test_faithfulness.py
├── test_retrieval_hit_rate.py     # deterministic: article hit@k, MRR (no judge)
└── test_trap_refusal.py           # DiscreteMetric on kind="trap" rows
```

Pure-logic tests for the harness live in `tests/unit/eval/` (§4.10).

### 4.2. Models and `EvalSettings`

The pipeline under test is configured by `AppSettings` alone (`QUERY_LLM_PROVIDER`,
`EMBEDDING_PROVIDER`, `RERANK_PROVIDER`, `TOP_K`, …), exactly as in production. The eval
suite adds only what `AppSettings` doesn't have:

| Variable | Default | Purpose |
|---|---|---|
| `TEST_EVAL_DATABASE_URL` | none (suite skips if unset) | asyncpg URL of a **dedicated** DB, e.g. `rag_vu_eval`. Never the integration DB, which is truncated per test |
| `RAGAS_JUDGE_PROVIDER` | `openrouter` | Which `AppSettings` connection the judge uses: `ollama_base_url`, or `openrouter_url` + `openrouter_api_key` |
| `RAGAS_JUDGE_MODEL` | none (required) | Judge model name. Must differ from the answering model (see below) |
| `RAGAS_GENERATOR_MODEL` | `RAGAS_JUDGE_MODEL` | Model for testset generation (§3.3) |
| `RAGAS_ALLOW_SELF_JUDGE` | `false` | Escape hatch to judge with the answering model; marked in the report |
| `RAGAS_MAX_SAMPLES` | `0` (all) | Quick smoke runs |
| `RAGAS_REINGEST` | `false` | Force re-ingestion even when the corpus fingerprint matches |
| `RAGAS_REUSE_ANSWERS` | none | A previous `run_id`: re-score its `answers.jsonl` instead of re-querying the pipeline (for judge or threshold work only; the manifest marks it) |
| `RAGAS_JUDGE_TIMEOUT` | `120` | Seconds per judge call, passed to the untraced `httpx` client |
| `RAGAS_JUDGE_MAX_RETRIES` | `5` | Retries with exponential backoff on 429/5xx/timeout |
| `RAGAS_RUN_TIMEOUT` | `3600` | Hard cap for the whole session (`pytest-timeout`), so a stuck free-tier queue can't hang CI |
| `RAGAS_MAX_CONCURRENCY` | `2` | Semaphore around `ascore` calls |
| `RAGAS_PHOENIX_PROJECT` | `rag_vu_eval` | Phoenix project for eval traces; overrides `PHOENIX_PROJECT_NAME` for the eval run only |
| `RAGAS_PHOENIX_URL` | `PHOENIX_COLLECTOR_ENDPOINT` without `/v1/traces` | Phoenix HTTP API for annotations; `PHOENIX_API_KEY` is passed through when set |

Phoenix traceability is on when `TRACING_ENABLED=true`, read from `AppSettings` as
everywhere else. With it off, the suite still scores and gates, but writes no annotations
(§4.7).

**Which models to reuse from `AppSettings`:**

- **Embeddings: reuse the app's embedder, with no new setting.** Response Relevancy (and
  testset generation) only need a reasonable embedding space, and staying on
  `EMBEDDING_PROVIDER` keeps eval in step with retrieval automatically. Implement
  `RagasEmbedderAdapter` as a thin implementation of the Ragas embeddings interface over
  `infrastructure.embedder` (`Embedder.embed(texts, EmbeddingTask.QUERY)`; questions and
  answers are compared as queries). Verify which embeddings base class `AnswerRelevancy` and
  `TestsetGenerator` accept in 0.4.3. If they differ, write two thin adapters over the same
  `Embedder`.
- **Judge temperature is 0** (pass it through `llm_factory`'s model args) and the judge model
  is pinned to an exact ID, never an alias such as `:latest`, so a provider-side model swap
  can't move the scores. The answering pipeline runs with production settings unchanged:
  the suite measures what users get, and §4.6's interval absorbs its variance.
- **Judge capability.** Ragas judge prompts need reliable structured (JSON) output. Small
  local or free models often fail at it, which shows up as NaN rows. `test_judge_sanity.py`
  (§4.8) rejects a judge that can't do the job before any tokens are spent on the run.
- **Judge LLM: same connection settings, a different model.** If the model that answered also
  grades the answer, it tends to rubber-stamp its own output (self-grading bias), which hides
  exactly the regressions this suite exists to catch. So the judge reuses `AppSettings`
  connections but has its own model name.
  - The answering model is `ollama_model` when `QUERY_LLM_PROVIDER=ollama`, otherwise
    `openrouter_chat_model`.
  - `judge_factory.py` fails fast if `RAGAS_JUDGE_MODEL` equals the answering model, unless
    `RAGAS_ALLOW_SELF_JUDGE=true`.
  - This follows the same pattern the app already uses for `ollama_rerank_model` vs
    `ollama_model`.

The report records the pipeline settings, the answering model (`AnswerTrace.model`) and the
judge model, so runs can be compared.

### 4.3. Fixtures (`conftest.py`)

- `pytest_collection_modifyitems`: mark every item in `tests/eval` with `eval`. Skip with a
  clear reason when `TEST_EVAL_DATABASE_URL` is unset or `ragas` isn't installed. Import
  `ragas` only inside fixtures and helpers, never at the top of a test module, so a run
  without the `eval` extra skips instead of erroring at collection.
- Extract `sync_url`, `alembic_config` and `_create_database` from
  `tests/integration/conftest.py` into `tests/support/postgres.py` and reuse them from both
  conftests. Don't import one conftest from another.
- **Session-scoped, `loop_scope="session"`** fixtures (`@pytest_asyncio.fixture(scope="session",
  loop_scope="session")`; tests use `pytestmark = pytest.mark.asyncio(loop_scope="session")`):
  1. `eval_database`: create and migrate `rag_vu_eval`. **No truncation.**
  2. `eval_infrastructure`: `Infrastructure(AppSettings(database_url=...,
     phoenix_project_name=RAGAS_PHOENIX_PROJECT), null_pool=True)`. Tracing follows
     `TRACING_ENABLED`. Teardown calls `infrastructure.dispose()`, which shuts the tracer
     provider down and flushes any spans still in the batch exporter.
  3. `eval_corpus`: ingest `consumer_law.pdf` through the **real** stage jobs. Generalise
     `PipelineRunner` to accept `parser`, `chunker` and `embedder` (defaults keep today's
     fakes), and pass the real ones built like `WorkerContainer` does
     (`DoclingDocumentParser`, `DoclingHybridChunker`, `infrastructure.embedder`). It's
     idempotent, keyed on a **corpus fingerprint**, not just the PDF hash: sha256 of the PDF
     + embedding provider, model and dimension + chunker settings (max tokens, tokenizer) +
     Docling version. Store the fingerprint in a small `eval_corpus_state` row (or the
     document's metadata). If it matches a `SUCCEEDED` document and `RAGAS_REINGEST` is
     false, reuse it; otherwise delete the old document's chunks and re-ingest. Keying on the
     PDF alone would silently evaluate stale vectors after an embedder change. Assert that the pipeline succeeded and that chunks
     have embeddings. Return the pipeline id: with tracing on, the ingestion of the law is
     the Phoenix session `<pipeline id>` (`pipeline.parsing [...]` shows the node count and
     node types Docling produced), and the report links to it.
  4. `eval_run`: load and validate the reviewed testset (§3.6). For each sample (bounded
     concurrency), call
     `QueryContainer(eval_infrastructure).answer_question.trace(q, [], session_id=run_id)` and
     return `list[EvalSample]`. Persist the result to
     `tests/eval/reports/<run_id>/answers.jsonl`, including each sample's `trace_ids`, so the
     metric tests share **one** pipeline run and a failed metric can be debugged without
     re-querying. A pipeline exception for a sample is recorded as that sample's error (same
     10% budget as judge errors, §4.4), never dropped. Answers are **not** reused across
     sessions unless `RAGAS_REUSE_ANSWERS` names a run.
  5. `ragas_llm`: built once in `judge_factory.py` with `llm_factory(RAGAS_JUDGE_MODEL,
     client=AsyncOpenAI(base_url=..., api_key=..., http_client=untraced_http_client()))`.
     The base URL and key come from the `AppSettings` connection named by
     `RAGAS_JUDGE_PROVIDER` (`{ollama_base_url}/v1`, or `openrouter_url` +
     `openrouter_api_key`). The untraced client is explained in §4.7.
  6. `ragas_embeddings`: `RagasEmbedderAdapter(eval_infrastructure.embedder)`.
  7. `phoenix_annotator`: a `PhoenixAnnotator` when tracing is on, otherwise a no-op
     annotator with the same interface.

Mapping `EvalSample` to Ragas inputs:

```python
user_input         = sample.user_input
response           = trace.answer                     # no source links
retrieved_contexts = [m.text for m in trace.matches]  # includes "Документ:/Breadcrumbs:" header
reference          = sample.reference
```

### 4.4. `MetricRunner`

- `async def score(metric, samples, inputs_of) -> MetricReport` calls `metric.ascore(...)`
  per sample under a semaphore and records the value. If a judge call fails, it records
  `error` for that sample and **doesn't swallow it silently**: the test fails if more than
  10% of samples errored. A `NaN` or `None` value counts as an error too. The skill warns that
  Ragas can quietly record NaN for failed rows, which would otherwise distort a mean. Check
  the error count (the equivalent of `df.isna().sum()`) before trusting any mean.
- `MetricReport` holds `name`, `mean`, `median`, `min`, `per_sample: list[(id, score, error)]`,
  plus the pipeline and model config. Write it to `tests/eval/reports/<run_id>/<metric>.json`,
  and add a combined `summary.md` table at session end (via a `pytest_sessionfinish` hook).
- Each metric is built in `metric_catalog.py` and nowhere else. In 0.4.3 verify the exact
  collections class names and constructor arguments (`dir(ragas.metrics.collections)` and
  the skill). For example, check whether reference-based precision is `ContextPrecision` or
  `ContextPrecisionWithReference`, and how `NoiseSensitivity` takes its mode. A Ragas bump
  then touches one file.
- Record the judge's token usage and call count per metric in the report, so cost per run is
  visible and a jump in calls (retries) is noticed.
- Never log or write API keys; the manifest stores provider and model names only.
- Gate on the **mean** over samples, not on every sample. LLM judges are noisy.
- After scoring, hand the per-sample results to `phoenix_annotator` **before** asserting,
  so scores reach Phoenix even when the gate fails.

### 4.5. The tests

Each test file is short: build the metric, score it, and compare it to its threshold. On
failure, show the 5 worst samples (id, question, score) in the assertion message.

| Test file | Metric class (`ragas.metrics.collections`) | Assertion |
|---|---|---|
| `test_context_precision.py` | `ContextPrecision` (with reference) | `mean >= thresholds.context_precision` |
| `test_context_recall.py` | `ContextRecall` | `mean >= thresholds.context_recall` |
| `test_context_entities_recall.py` | `ContextEntityRecall` | `mean >= thresholds.context_entities_recall` |
| `test_noise_sensitivity.py` | `NoiseSensitivity` (mode `relevant`) | `mean <= thresholds.noise_sensitivity_max` |
| `test_response_relevancy.py` | `AnswerRelevancy(llm=..., embeddings=...)` | `mean >= thresholds.response_relevancy` |
| `test_faithfulness.py` | `Faithfulness` | `mean >= thresholds.faithfulness` |

Group the report as the skill suggests: **retriever** metrics (Context Precision, Context
Recall, Context Entities Recall) use only `user_input`, `retrieved_contexts` and `reference`,
and **generator** metrics (Faithfulness, Response Relevancy, Noise Sensitivity) are
evaluated on the retrieval the pipeline actually produced. A failing retriever group with a
healthy generator group points at chunking, hybrid retrieval or rerank, not at the prompt.
Context Recall and Entities Recall need `reference`: a sample without one is a testset bug,
and the loader rejects it.

All six run on `kind="rag"` rows only (§3.6).

**`test_retrieval_hit_rate.py`: deterministic, no judge, no tokens.** These are the most
trustworthy signals in the suite, so they gate first and can run on every PR (§5.6):

- **Article hit@k**: the share of `rag` samples where any `reference_articles` value appears
  in the `Breadcrumbs:` of the retrieved contexts. Parse the article number from the
  breadcrumb with one shared helper, also used by `LawArticleLoader`, so both sides agree.
- **MRR**: mean reciprocal rank of the first context from a reference article (0 if none).
  It shows rerank regressions that hit@k misses.
- **Article-question hit rate**: hit@k restricted to questions that name an article, which
  exercises the `retrieval.article` path. It should be close to 1.0.

**`test_trap_refusal.py`**, the trap questions (custom metric): for samples whose reference says the law has no answer,
  the answer must say so instead of inventing a rule. Implement this as a Ragas
  `DiscreteMetric` (`name="correct_refusal"`, `allowed_values=["pass", "fail"]`, prompt
  placeholders `{question}` and `{response}`), scored with the same judge. Gate on the share
  of `pass`. This is the skill's custom-metric pattern, so don't hand-roll a regex or a
  second judging client. The trap set is small, so this is an absolute gate (every trap must
  pass by default: `trap_refusal_min = 1.0`), not a baseline-relative one.

### 4.6. Thresholds (`thresholds.toml`)

Each metric has **two gates**, implemented in `gate.py`. Both must pass:

1. **Absolute floor** (`thresholds.toml`): the quality the product must never go below.
   These starting values are placeholders. After the first baseline run, set each to about
   *baseline − 0.10*.
2. **Regression vs baseline** (`baseline/summary.json`): catches a real drop long before the
   floor does. For each metric, compute the **paired** per-sample difference
   (current − baseline) over sample ids present in both runs, and a 95% bootstrap interval of
   its mean (`bootstrap_interval.py`, 2,000 resamples, fixed seed). The gate fails when the
   whole interval is below `-noise_tolerance` (above `+noise_tolerance` for Noise
   Sensitivity). Pairing by id removes most between-question variance, so 50 samples can
   detect a drop of a few points instead of needing hundreds.

If the baseline was made with a different judge model, testset sha256 or Ragas version
(compare manifests, §4.9), the regression gate is **skipped with a loud warning** in the
report, and only the floors apply. Comparing across judges is meaningless.

**Updating the baseline** is a reviewed change, never automatic:
`make eval-baseline` copies the current run's `summary.json` (with per-sample scores and
manifest) into `tests/eval/baseline/`. The PR that changes it says why (intended
improvement, new judge, new testset) and links the Phoenix eval session. Take the first
baseline **before** changing prompts, chunking or retrievers.

```toml
context_precision       = 0.60
context_recall          = 0.60
context_entities_recall = 0.40   # Russian morphology + English prompts make this metric strict
noise_sensitivity_max   = 0.35
response_relevancy      = 0.70
faithfulness            = 0.75
article_hit_rate        = 0.80
retrieval_mrr           = 0.60
article_question_hit    = 0.95
trap_refusal_min        = 1.0
min_reviewed_samples    = 40
min_trap_samples        = 3
max_error_ratio         = 0.10
noise_tolerance         = 0.02   # differences below this are noise (skill guideline)
bootstrap_resamples     = 2000
bootstrap_seed          = 1234
```

### 4.7. Traceability in Arize Phoenix

Each eval sample is a real `rag.query` trace in Phoenix. The suite groups those traces by
run, writes each metric's score onto them, and keeps its own LLM calls out of them.

- **Own project and session.** Eval traffic goes to the Phoenix project
  `RAGAS_PHOENIX_PROJECT` (`rag_vu_eval`), so it never mixes with chat traffic in `rag_vu`.
  Every sample is answered with `session_id=run_id`, so the Sessions tab shows one eval run
  as one session.
- **Scores on the traces.** `PhoenixAnnotator` uses `phoenix.client.Client(base_url=
  RAGAS_PHOENIX_URL)` and `client.spans.log_span_annotations(...)` to attach one annotation
  per metric to each sample's `rag.query` span (`trace_ids.span_id`):
  - `name`: the metric (`faithfulness`, `context_precision`, …, `article_hit`);
  - `annotator_kind`: `"LLM"` for Ragas metrics, `"CODE"` for the article-hit and trap
    checks;
  - `result`: the `score`, a `label` (`pass` / `fail` against the threshold) and an
    `explanation` (the Ragas reason when the metric gives one, else the error);
  - `identifier`: `run_id`, so re-annotating a run updates it instead of duplicating;
  - `metadata`: sample id, judge model, answering model, threshold.

  Phoenix then shows the scores next to each trace and aggregates them per project. A
  low-scoring sample opens straight onto its retrieval, rerank and LLM spans, so you can see
  *why* it scored low.
- **Flush before annotating.** Spans leave through a batch exporter, so call
  `infrastructure.tracer_provider.force_flush()` once `eval_run` finishes, before the first
  annotation is logged. If Phoenix rejects annotations for spans it hasn't ingested yet,
  retry with a short backoff, then record the failure in the report. Annotation failures
  never fail the eval.
- **Keep judge calls out of the traces.** `HTTPXClientInstrumentor` instruments `httpx`
  process-wide, and `AsyncOpenAI` / `ChatOpenAI` use `httpx`. Without care, several hundred
  judge requests would appear as stray HTTP spans in the eval project.
  - `untraced_http_client()` builds an `httpx.AsyncClient` and calls
    `HTTPXClientInstrumentor.uninstrument_client(client)` on it.
  - The judge LLM and the testset generator are built with that client; verify that the
    instance is excluded once instrumentation is active.
  - The pipeline's own calls (embedder, reranker, answering model) stay traced, because
    they're what is being evaluated.
- **Links in the report.** `summary.md` names the Phoenix project, the eval session
  (`run_id`) and the ingestion session (pipeline id). It also lists the trace id of each of
  the 5 worst samples per metric, so each failing sample can be found by trace id in
  Phoenix.
- **Without tracing.** With `TRACING_ENABLED=false` the tracer is a `NullTracer`,
  `trace_ids` is `None`, annotation is skipped, and the report says "not traced". The gates
  behave the same.

### 4.8. Judge sanity check (`test_judge_sanity.py`)

A broken judge produces confident-looking numbers. Before the run is scored, check the judge
on a small hand-labelled set whose answers are known:

- `judge_calibration.jsonl` has about 8 fixed samples written from the law (no pipeline
  involved): a faithful answer and an answer with an invented deadline for the same
  contexts; a relevant and an off-topic answer; contexts that do and don't contain the
  reference; a correct refusal and an invented rule for a trap.
- The test scores each pair with the real metric objects from `metric_catalog.py` and
  asserts the **ordering**: the good item scores higher than the bad one, by at least 0.3
  (refusal: `pass` vs `fail`). It also asserts that no value is NaN.
- It runs first (`pytest-order`), and only when a judge-based test is selected, so
  `make eval-retrieval` never needs a judge. If it fails, the
  session stops with "judge model `<id>` failed calibration", instead of 300 judge calls
  producing noise.
- This is also the test to rerun when picking a judge model: try candidates on the
  calibration set and keep one that passes reliably.

### 4.9. Run manifest and reproducibility

Every run writes `tests/eval/reports/<run_id>/manifest.json`, and `summary.json` embeds it:

- `run_id` (UTC timestamp + short git sha), git sha and dirty flag, start/end time;
- `ragas`, `docling` and Python versions;
- testset path, sha256 and row counts by kind;
- corpus fingerprint and ingestion pipeline id;
- pipeline settings that affect answers (`QUERY_LLM_PROVIDER`, answering model, embedding
  provider/model, rerank provider/model, `TOP_K`, …) read from `AppSettings`, never secrets;
- judge provider, model, temperature, and the self-judge flag;
- `RAGAS_REUSE_ANSWERS` source run, if any; Phoenix project and session.

`summary.json` is the machine-readable result: per metric, the mean, the 95% interval, the
error count, the gate outcomes, and per-sample `(id, score, error)`. It is what the baseline
gate reads and what `make eval-baseline` copies. `summary.md` is rendered from it for
people, with a column for the delta vs baseline.

### 4.10. Unit tests for the harness (`tests/unit/eval/`)

The eval suite is code that decides whether a change ships, so its own logic is unit-tested
and runs in the normal `make test-unit` (no DB, no LLM). Modules that import `ragas` use
`pytest.importorskip("ragas")`.

- `TestsetRow` and the loader: schema errors, duplicates, unknown article numbers and the
  minimum counts all fail.
- `corpus_fingerprint`: changes when any of its inputs change.
- `judge_factory`: refuses a judge equal to the answering model unless the escape hatch is set.
- `MetricRunner` with a fake metric: errors and NaN are counted, the error-ratio limit
  fails, values are aggregated correctly.
- `gate.py` and `bootstrap_interval.py`: pass/fail on constructed paired data, the
  direction flip for Noise Sensitivity, and the skip when manifests are incompatible.
- The breadcrumb article-number parser and hit@k / MRR on hand-built matches.
- `RagasEmbedderAdapter` over a fake `Embedder`.

---

## 5. Running it

5.1. Makefile targets. The README and the Compose `tests` service comment already document
`make test-unit` / `make test-integration`, but the Makefile still lacks them, so add them
here too:

```make
test-unit: ## Unit tests (local)
	uv run --extra dev pytest tests/unit

test-integration: ## Integration tests in Docker against the Compose PostgreSQL
	docker compose -f docker/docker-compose.yml --profile test run --rm tests pytest tests/integration

eval-testset: ## Generate the Ragas testset from consumer_law.pdf (manual, then review)
	uv run --extra eval python -m tests.eval.generate_testset --size 50

eval: ## Run Ragas evaluation (needs TEST_EVAL_DATABASE_URL, judge LLM, embedder)
	uv run --extra dev --extra eval pytest tests/eval -m eval -v

eval-smoke: ## Quick eval on 5 samples (no regression gate: too few samples)
	RAGAS_MAX_SAMPLES=5 $(MAKE) eval

eval-retrieval: ## Deterministic retrieval checks only (no judge, no tokens)
	uv run --extra dev --extra eval pytest tests/eval/test_retrieval_hit_rate.py -m eval -v

eval-baseline: ## Promote the latest run to tests/eval/baseline/ (commit with a reason)
	uv run --extra eval python -m tests.eval.promote_baseline
```

5.2. Docker:

- Add `ARG UV_EXTRAS="--extra dev"` to `docker/Dockerfile` and use it in
  `uv sync --frozen --no-install-project $UV_EXTRAS`.
- Add an `eval` compose service (profile `eval`), modelled on `tests`:
  - built with `UV_EXTRAS="--extra dev --extra eval"` as a separate image tag;
  - mounts `tests/` and `media/rapidocr-models`;
  - sets `TEST_EVAL_DATABASE_URL=.../rag_vu_eval` and
    `OLLAMA_BASE_URL=${OLLAMA_DOCKER_BASE_URL}`;
  - sets `RAGAS_DO_NOT_TRACK=true` (§1.6);
  - sets `TRACING_ENABLED=true`, `PHOENIX_COLLECTOR_ENDPOINT=http://phoenix:6006/v1/traces`
    and `RAGAS_PHOENIX_URL=http://phoenix:6006`, and depends on the `phoenix` service;
  - runs `pytest tests/eval -m eval`.
- The image already includes Docling and Tesseract, which ingestion needs.

5.3. Default runs must **not** collect `tests/eval`:

- Change the Compose `tests` service command from `pytest tests` to `pytest`, so
  `testpaths` applies.
- Keep the conftest skip (§4.3) as a second guard.
- Verify that `make test-unit`, `make test-integration` and a bare `pytest` all leave
  `tests/eval` alone.

5.4. README: add an "Evaluation" section covering what each metric means, how to generate and
review the testset, how to run, where reports are written, how to update thresholds, and
which judge model to configure. Also cover where eval runs appear in Phoenix: the
`rag_vu_eval` project, one session per run, metric annotations on each `rag.query` span. Add
a row for the eval annotations to the README's tracing table.

5.5. Locally (`make eval`), Phoenix traceability needs the Compose `phoenix` service running,
with `TRACING_ENABLED=true`, `PHOENIX_COLLECTOR_ENDPOINT=http://localhost:${PORT_PREFIX}006/v1/traces`
and `RAGAS_PHOENIX_URL=http://localhost:${PORT_PREFIX}006` in `.env`.

5.6. **When it runs (CI).** The full eval is too slow and costly for every push, and LLM
scores are too noisy to block every PR on. Split it:

- **Every PR touching `app/` or `tests/eval/`**: harness unit tests (in `make test-unit`)
  and `make eval-retrieval`. They're deterministic and need only Postgres and the embedder,
  so they are a hard gate. If the CI runner can't reach the production embedder (Ollama),
  run them on a self-hosted runner or nightly only. Don't swap in a fake embedder, since
  that would measure nothing.
- **Nightly on the main branch, and manually on a PR (label `run-eval` or
  `workflow_dispatch`)**: the full `make eval`. On a PR it reports and is required before
  merging changes to the prompt, chunker, retriever, reranker or models.
- CI uploads `tests/eval/reports/<run_id>/` as a build artifact and posts `summary.md` to
  the PR or job summary.
- Judge and provider keys come from CI secrets. The job sets `RAGAS_DO_NOT_TRACK=true`.
- Set `RAGAS_MAX_SAMPLES=0` in CI. With a smaller sample, the regression gate is skipped,
  so the smoke target never stands in for the real run.

---

## 6. Risks & notes

- **Language**: metric prompts are English while the data is Russian. Faithfulness and
  Recall cope well, but Entity Recall is sensitive to inflection. Optionally adapt metric
  prompts to Russian (`adapt_prompts("russian", llm)`) and compare baselines before choosing.
- **Judge = generator bias**: §4.2 enforces a judge model different from the answering
  model. If `RAGAS_ALLOW_SELF_JUDGE` is used, the report must say so and the scores
  shouldn't be compared with other runs.
- **Judge noise**: per the skill, metrics are LLM-judged, cost tokens, vary between runs and
  depend on the judge model. That's why the gate is on a mean over 40 or more samples, with
  a pinned judge.
- **Hosted judge sees the data**: the retrieved contexts go to the judge provider. Fine for
  a public law; use an Ollama judge for anything confidential.
- **LangChain / Ragas import break**: see the import check in §1.3.
- **Free-tier limits** (OpenRouter `:free`): 50 samples × 6 metrics is several hundred judge
  calls on top of the pipeline's own calls. Keep concurrency at 2, enable retries, and use
  `RAGAS_MAX_SAMPLES` for smoke runs.
- **Context formatting**: `retrieved_contexts` include the `Документ:` / `Breadcrumbs:`
  header added by `build_retrieved_context`. That's intended, because it's exactly what the
  LLM sees. Note it in the README.
- **Non-determinism**: report mean with its 95% interval (§4.6). Don't tighten thresholds
  based on one run. Before the first real baseline, run the suite twice on the same commit:
  if the paired interval of the difference isn't within `±noise_tolerance`, the judge or
  the sample is too noisy, so fix that first.
- **Single-turn only**: every sample is asked with empty history. Follow-up questions that
  rely on chat history are out of scope for this task.
- **Single document**: the corpus is one law, so cross-document retrieval confusion isn't
  measured. Adding a second law as a distractor corpus is a natural next step.
- **Phoenix versions**: `arize-phoenix-client` needs Phoenix server ≥ 13.15. Compose uses
  `arizephoenix/phoenix:latest`. Pin the image once annotations work, so a Phoenix upgrade
  doesn't silently break them.
- **Trace volume**: each eval run adds about 50 `rag.query` traces, plus one ingestion
  session when re-ingesting. Delete old eval runs in the `rag_vu_eval` project, or the
  `rag_vu-phoenix-data` volume, when it grows.

---

## Definition of done

- [ ] `ragas==0.4.3` and its deps are in the `eval` extra; `uv.lock` is updated; the `eval`
      marker is registered; `import ragas` works.
- [ ] `.claude/skills/ragas/SKILL.md` is committed, and no code uses the old Ragas API names
      listed in it.
- [ ] `AnswerQuestion.trace()` + `AnswerTrace` (including `model`, `usage` and `trace_ids`)
      are added with unit tests. `execute()` keeps its signature, output and `rag.query`
      span. `TraceSpan.ids` is implemented by `OpenInferenceSpan` and `NullSpan`.
- [ ] `python -m tests.eval.generate_testset` uses the app's Docling parser on a temporary
      copy of `tests/eval/test_data/consumer_law.pdf` and produces a Russian JSONL testset,
      with ≥ 40 human-reviewed samples (including real user questions and trap questions)
      committed.
- [ ] `tests/eval` holds the six metric tests (Context Precision, Context Recall, Context
      Entities Recall, Noise Sensitivity, Response Relevancy, Faithfulness) and the
      retrieval hit-rate and trap-refusal (`DiscreteMetric`) checks. NaN scores count as errors.
- [ ] All model and connection settings come from `AppSettings` plus `RAGAS_*`. Embeddings go
      through the app's `Embedder`. The judge model differs from the answering model.
- [ ] Ingestion uses the real parser, chunker and embedder, runs once per session, and is
      reused across runs.
- [ ] The pipeline runs once per session and all metrics share its answers.
- [ ] Per-metric JSON reports and `summary.md` are written to `tests/eval/reports/<run_id>/`.
- [ ] With tracing on, an eval run appears in Phoenix project `rag_vu_eval` as one session.
      Every `rag.query` span carries one annotation per metric. Judge calls don't appear as
      spans. `summary.md` names the eval and ingestion sessions and the trace ids of the
      worst samples.
- [ ] With tracing off, the suite runs and gates the same and writes no annotations.
- [ ] The testset is schema-validated on load (§3.6), with stable ids. Trap rows are kept
      out of the six Ragas metrics.
- [ ] Corpus reuse is keyed on the corpus fingerprint, not the PDF hash alone.
- [ ] `test_judge_sanity.py` passes on the calibration set and aborts the session when it
      fails.
- [ ] Deterministic hit@k / MRR / article-question checks exist and run in PR CI.
- [ ] Each metric has an absolute floor and a paired-bootstrap regression gate against
      `tests/eval/baseline/summary.json`. The gate is skipped (with a warning) when the
      manifests aren't comparable.
- [ ] `manifest.json` and `summary.json` are written for every run, with no secrets.
- [ ] Harness unit tests in `tests/unit/eval/` pass in `make test-unit`.
- [ ] Thresholds and the baseline are calibrated from two runs on the same commit and
      committed.
- [ ] CI runs `eval-retrieval` on PRs and the full eval nightly and on demand, and uploads
      the reports.
- [ ] `make test-unit`, `make test-integration`, `make eval`, `make eval-smoke`,
      `make eval-retrieval`, `make eval-baseline` and `make eval-testset` work; the Docker `eval` profile works.
- [ ] Default `pytest`, `make test-unit`, `make test-integration` and the Compose `tests`
      service don't collect `tests/eval`.
- [ ] `make lint` passes; the code follows `AGENTS.md`.
- [ ] The README has an Evaluation section.
