# RAG Evaluation with Ragas

## Goal

Build an **opt-in evaluation suite** that runs the real RAG-VU query pipeline
(`embed → SqlAlchemyHybridRetriever → Reranker → ChatModel`, i.e. `AnswerQuestion`) against
the Russian Consumer Protection Law (`Закон РФ от 07.02.1992 N 2300-1 «О защите прав
потребителей»`) and scores it with Ragas. Regressions in retrieval or generation should then
show up as failing tests with a per-sample report.

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

- **One code path.** The pre-refactor code (`app/services`, `app/api`, `app/models`,
  `app/db`, `app/config.py`, `app/settings.py`, the old `tests/test_*.py`) has been removed.
  What remains is the hexagonal solution only:
  - **Settings**: `AppSettings` (`app/config/app_settings.py`) is the only settings class.
    Every model, URL and key the eval suite needs comes from it; nothing else is read.
  - **Query**: `AnswerQuestion` (`app/application/use_cases/query/answer_question.py`), wired
    by `QueryContainer` (`app/bootstrap/query_container.py`), is the only query
    implementation. The Chainlit UI (`app/adapters/inbound/chat_ui/chat.py`) and the search
    endpoint both go through it, so evaluating `AnswerQuestion` evaluates what users get.
  - **Ingestion**: the stage jobs wired by `WorkerContainer` (`DoclingDocumentParser`,
    `DoclingHybridChunker`, `infrastructure.embedder`) are the only ingestion path.
- **Tracing is in place.** `AnswerQuestion.execute(question, history, session_id=None)` runs
  inside a `rag.query` span, and the embedder, retriever, reranker and chat model are wrapped
  in `Traced*` decorators. `ChatModel.complete()` returns a `ChatCompletion` (`text`, `model`,
  `usage`, `finish_reason`). `Infrastructure.tracer` is a `NullTracer` unless
  `TRACING_ENABLED=true`.
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
]
```

No PDF library and no separate embeddings client: Docling is already a dependency (§3.2),
and Ragas embeddings are an adapter over the app's own `Embedder` (§4.2). Run `uv lock` and
commit the updated `uv.lock`.

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

1.4. Add `tests/eval/reports/` and `tests/eval/.cache/` to `.gitignore`.

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
```

2.2. In `AnswerQuestion`:

- Add `async def trace(question, history, session_id=None) -> AnswerTrace`. It opens the
  same `rag.query` span `execute()` opens today (input, session, attributes, output), so
  eval runs are traced exactly like chat runs.
- Make `_answer` build and return the `AnswerTrace`. `_final_answer` returns the
  `ChatCompletion`'s text, model and usage instead of only the text.
- `execute()` becomes `return (await self.trace(question, history, session_id)).answer_with_sources`,
  so its signature, output and spans are unchanged for the chat UI.
- Keep each method at 30 lines or fewer.

2.3. Unit tests in `tests/unit/application/test_answer_question.py`. Check that `trace()`
returns the reranked matches, an answer without the `**Источники:**` block, and the chat
model's `model`/`usage`, and that `execute()` output is unchanged.

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
  article-hit-rate check (§4.5) compare against the identifiers retrieval uses.
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
- `testset_size`: **30** by default (`--size`). Use `--seed` and `RunConfig(max_workers=2,
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
  "reviewed": false
}
```

### 3.5. Human review (required before merge)

- Read every sample. Fix or delete hallucinated references, questions answerable without the
  law, and duplicates. Then set `"reviewed": true`.
- Eval tests load **only** `reviewed: true` samples and fail if fewer than 20 exist.
- Add 3–5 **hand-written** "trap" questions that the law doesn't answer
  (`"reference": "В законе нет ответа…"`). They exercise the prompt rule "If it does not
  contain the answer, say so".

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
├── eval_run.py                    # runs AnswerQuestion.trace() over the testset (cached)
├── metric_runner.py               # scores one metric over all samples, writes report
├── thresholds.toml                # per-metric gates
├── test_context_precision.py
├── test_context_recall.py
├── test_context_entities_recall.py
├── test_noise_sensitivity.py
├── test_response_relevancy.py
├── test_faithfulness.py
└── test_article_hit_rate.py
```

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
| `RAGAS_REINGEST` | `false` | Force re-ingestion of the PDF |
| `RAGAS_MAX_CONCURRENCY` | `2` | Semaphore around `ascore` calls |

**Which models to reuse from `AppSettings`:**

- **Embeddings: reuse the app's embedder, with no new setting.** Response Relevancy (and
  testset generation) only need a reasonable embedding space, and staying on
  `EMBEDDING_PROVIDER` keeps eval in step with retrieval automatically. Implement
  `RagasEmbedderAdapter` as a thin implementation of the Ragas embeddings interface over
  `infrastructure.embedder` (`Embedder.embed(texts, EmbeddingTask.QUERY)`; questions and
  answers are compared as queries). Verify which embeddings base class `AnswerRelevancy` and
  `TestsetGenerator` accept in 0.4.3. If they differ, write two thin adapters over the same
  `Embedder`.
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
  2. `eval_infrastructure`: `Infrastructure(AppSettings(database_url=...), null_pool=True)`.
     Tracing follows `TRACING_ENABLED` (off by default; see §5.5).
  3. `eval_corpus`: ingest `consumer_law.pdf` through the **real** stage jobs. Generalise
     `PipelineRunner` to accept `parser`, `chunker` and `embedder` (defaults keep today's
     fakes), and pass the real ones built like `WorkerContainer` does
     (`DoclingDocumentParser`, `DoclingHybridChunker`, `infrastructure.embedder`). It's
     idempotent: if a document with the PDF's sha256 is already `SUCCEEDED` and
     `RAGAS_REINGEST` is false, reuse it. Assert that the pipeline succeeded and that chunks
     have embeddings.
  4. `eval_run`: load the reviewed testset. For each sample (bounded concurrency), call
     `QueryContainer(eval_infrastructure).answer_question.trace(q, [], session_id=run_id)` and
     return `list[EvalSample]`. Persist the result to
     `tests/eval/reports/<run_id>/answers.jsonl`, so the metric tests share **one** pipeline
     run and a failed metric can be debugged without re-querying.
  5. `ragas_llm`: built once in `judge_factory.py` with `llm_factory(RAGAS_JUDGE_MODEL,
     client=AsyncOpenAI(base_url=..., api_key=...))`. The base URL and key come from the
     `AppSettings` connection named by `RAGAS_JUDGE_PROVIDER` (`{ollama_base_url}/v1`, or
     `openrouter_url` + `openrouter_api_key`).
  6. `ragas_embeddings`: `RagasEmbedderAdapter(eval_infrastructure.embedder)`.

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
  10% of samples errored.
- `MetricReport` holds `name`, `mean`, `median`, `min`, `per_sample: list[(id, score, error)]`,
  plus the pipeline and model config. Write it to `tests/eval/reports/<run_id>/<metric>.json`,
  and add a combined `summary.md` table at session end (via a `pytest_sessionfinish` hook).
- Gate on the **mean** over samples, not on every sample. LLM judges are noisy.

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

`test_article_hit_rate.py` holds cheap checks that need no judge:

- **Article hit rate**: the share of samples where any `reference_articles` value appears in
  the `Breadcrumbs:` of the retrieved contexts. It catches retrieval regressions instantly.
- **Trap questions**: for samples whose reference says the law has no answer, the answer must
  say so instead of inventing a rule.

### 4.6. Thresholds (`thresholds.toml`)

These starting values are **placeholders**. Calibrate them after the first baseline run:
set each gate to roughly *baseline − 0.05* and commit the baseline report alongside.

```toml
context_precision       = 0.60
context_recall          = 0.60
context_entities_recall = 0.40   # Russian morphology + English prompts make this metric strict
noise_sensitivity_max   = 0.35
response_relevancy      = 0.70
faithfulness            = 0.75
article_hit_rate        = 0.80
min_reviewed_samples    = 20
max_error_ratio         = 0.10
```

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
	uv run --extra eval python -m tests.eval.generate_testset --size 30

eval: ## Run Ragas evaluation (needs TEST_EVAL_DATABASE_URL, judge LLM, embedder)
	uv run --extra dev --extra eval pytest tests/eval -m eval -v

eval-smoke: ## Quick eval on 5 samples
	RAGAS_MAX_SAMPLES=5 $(MAKE) eval
```

5.2. Docker:

- Add `ARG UV_EXTRAS="--extra dev"` to `docker/Dockerfile` and use it in
  `uv sync --frozen --no-install-project $UV_EXTRAS`.
- Add an `eval` compose service (profile `eval`), modelled on `tests`:
  - built with `UV_EXTRAS="--extra dev --extra eval"` as a separate image tag;
  - mounts `tests/` and `media/rapidocr-models`;
  - sets `TEST_EVAL_DATABASE_URL=.../rag_vu_eval` and
    `OLLAMA_BASE_URL=${OLLAMA_DOCKER_BASE_URL}`;
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
which judge model to configure.

5.5. Optional, with Phoenix: run eval with `TRACING_ENABLED=true`. Every sample then appears
in Phoenix as a `rag.query` trace, grouped under the session `run_id`, so a low-scoring
sample can be opened straight from `summary.md` (include the session id there).

---

## 6. Risks & notes

- **Language**: metric prompts are English while the data is Russian. Faithfulness and
  Recall cope well, but Entity Recall is sensitive to inflection. Optionally adapt metric
  prompts to Russian (`adapt_prompts("russian", llm)`) and compare baselines before choosing.
- **Judge = generator bias**: §4.2 enforces a judge model different from the answering
  model. If `RAGAS_ALLOW_SELF_JUDGE` is used, the report must say so and the scores
  shouldn't be compared with other runs.
- **Free-tier limits** (OpenRouter `:free`): 30 samples × 6 metrics is several hundred judge
  calls on top of the pipeline's own calls. Keep concurrency at 2, enable retries, and use
  `RAGAS_MAX_SAMPLES` for smoke runs.
- **Context formatting**: `retrieved_contexts` include the `Документ:` / `Breadcrumbs:`
  header added by `build_retrieved_context`. That's intended, because it's exactly what the
  LLM sees. Note it in the README.
- **Non-determinism**: report mean ± spread. Don't tighten thresholds based on one run.

---

## Definition of done

- [ ] `ragas==0.4.3` and its deps are in the `eval` extra; `uv.lock` is updated; the `eval`
      marker is registered.
- [ ] `AnswerQuestion.trace()` + `AnswerTrace` (including `model` and `usage`) are added with
      unit tests. `execute()` keeps its signature, output and `rag.query` span.
- [ ] `python -m tests.eval.generate_testset` uses the app's Docling parser on a temporary
      copy of `tests/eval/test_data/consumer_law.pdf` and produces a Russian JSONL testset,
      with ≥ 20 human-reviewed samples plus trap questions committed.
- [ ] `tests/eval` holds the six metric tests (Context Precision, Context Recall, Context
      Entities Recall, Noise Sensitivity, Response Relevancy, Faithfulness) and the
      article-hit-rate / trap-question checks.
- [ ] All model and connection settings come from `AppSettings` plus `RAGAS_*`. Embeddings go
      through the app's `Embedder`. The judge model differs from the answering model.
- [ ] Ingestion uses the real parser, chunker and embedder, runs once per session, and is
      reused across runs.
- [ ] The pipeline runs once per session and all metrics share its answers.
- [ ] Per-metric JSON reports and `summary.md` are written to `tests/eval/reports/<run_id>/`.
- [ ] Thresholds are calibrated from a committed baseline run.
- [ ] `make test-unit`, `make test-integration`, `make eval`, `make eval-smoke` and
      `make eval-testset` work; the Docker `eval` profile works.
- [ ] Default `pytest`, `make test-unit`, `make test-integration` and the Compose `tests`
      service don't collect `tests/eval`.
- [ ] `make lint` passes; the code follows `AGENTS.md`.
- [ ] The README has an Evaluation section.
