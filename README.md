# Intelligent Analytics Query Engine

A production-oriented natural-language analytics system that converts business questions into validated DuckDB SQL, executes the query deterministically, and returns the result with an explanation and evidence-based confidence score.

> **Design principle:** the LLM understands the question; the database computes the truth.

## What makes this implementation different

This is intentionally **not** a collection of hardcoded query patterns and it does not ask an LLM to invent final numbers.

- GenAI performs semantic mapping from business language to the provided schema/data dictionary.
- The model returns a **strict structured plan**: interpretation, SQL, tables/columns used, assumptions, complexity, analytical features and expected output shape.
- A local safety layer rejects non-read-only SQL, external file/network readers and unknown tables.
- DuckDB performs all arithmetic, grouping, ranking, joins and time logic.
- Failed SQL can be repaired once using the actual validator/database error.
- `feedback_log.csv` is used as a small **feedback-RAG** layer: embedding + lexical retrieval when available, lexical fallback otherwise.
- Confidence combines model confidence with deterministic evidence instead of trusting a single LLM score.
- Tests assert exact analytics for Top-N-per-group, contribution percentages and target comparisons.
- A CLI, FastAPI endpoint, Dockerfile and CI workflow are included.

## Architecture

```text
                      CSV files + data_dictionary.json
                                 |
                                 v
                    +--------------------------+
                    | Schema/Data Profiler     |
                    | types, samples, nulls,   |
                    | candidate relationships  |
                    +------------+-------------+
                                 |
Natural-language query           |          optional feedback_log.csv
        |                        |                    |
        +------------------------+                    v
                                 |          +-----------------------+
                                 |          | Feedback Retriever    |
                                 |          | embeddings + lexical  |
                                 |          +-----------+-----------+
                                 |                      |
                                 v                      |
                       +--------------------+<-----------+
                       | GenAI Planner      |
                       | Structured Output  |
                       +---------+----------+
                                 |
                         QueryPlan + SQL
                                 |
                                 v
                       +--------------------+
                       | SQL Safety Layer   |
                       | read-only + schema |
                       +---------+----------+
                                 |
                                 v
                       +--------------------+
                       | DuckDB Executor    |
                       +----+----------+----+
                            |          |
                         error       result
                            |          |
                            v          v
                       GenAI repair  deterministic
                            |        verification
                            +----+-----+
                                 |
                                 v
                    +--------------------------+
                    | Confidence + Explanation |
                    +------------+-------------+
                                 |
                                 v
                         Required JSON output
```

## Requirement coverage

| Assignment requirement | Implementation |
|---|---|
| Understand natural language | GenAI planner receives schema profiles + data dictionary |
| Map business terms to fields | Data dictionary + schema samples are grounded into the prompt |
| Executable logic | Read-only DuckDB SQL |
| Aggregation/grouping/filtering | Native SQL operations |
| Ranking | Window functions |
| Top N within groups | `ROW_NUMBER`/`DENSE_RANK` partitioned by parent group |
| Contribution percentages | Window/CTE denominator logic with divide-by-zero protection |
| Nested logic | Explicit CTEs |
| Target comparisons | Aggregate actuals to target grain, then join on supported keys |
| Time-based queries | Date profiling + DuckDB date functions |
| Meaningful GenAI | Semantic planning + error-guided repair + feedback retrieval |
| Confidence score | Hybrid semantic + deterministic evidence score |
| Explanation | Planner interpretation + generated SQL + assumptions + metadata |
| Feedback loop | Relevant historical corrections retrieved into planner context |
| Unseen queries | No exact-query fallback rules or hardcoded answers |

A more detailed evaluator mapping is in [`docs/EVALUATION_MAPPING.md`](docs/EVALUATION_MAPPING.md).

## Project structure

```text
.
├── analytics_engine/
│   ├── config.py          # Environment/configuration
│   ├── data_loader.py     # CSV loading, profiling, relationships
│   ├── llm_planner.py     # Structured GenAI planning + repair
│   ├── validator.py       # SQL safety + grounding checks
│   ├── executor.py        # Deterministic DuckDB execution
│   ├── feedback.py        # Feedback-RAG retrieval
│   ├── verifier.py        # Post-execution consistency checks
│   ├── confidence.py      # Evidence-based confidence score
│   ├── models.py          # Typed internal contracts
│   └── engine.py          # End-to-end orchestration
├── tests/                 # Exact-result + safety tests
├── examples/demo_dataset/ # Small reproducible demo data
├── sample_outputs/        # Reference output format/demo
├── docs/
├── main.py                # CLI
├── api.py                 # FastAPI service
├── benchmark.py           # Batch evaluation summary
├── Dockerfile
└── .github/workflows/ci.yml
```

## GenAI design

The planner uses the OpenAI Responses API with a strict JSON Schema output contract. The model must return:

- `understanding`
- `sql`
- `used_tables`
- `referenced_columns`
- `assumptions`
- `semantic_confidence`
- `complexity`
- `query_features`
- `expected_output`
- `explanation`

The prompt explicitly prohibits query-specific hardcoding and prohibits the model from calculating final metric values itself.

### Why SQL instead of generated Python?

Generated arbitrary Python is difficult to sandbox and audit. SQL is easier to display, validate and test, while DuckDB supports the analytical operations required by the assignment: joins, CTEs, windows, date logic and nested aggregations.

## Feedback loop / RAG

When `feedback_log.csv` is present, the engine finds corrections relevant to the current question.

1. If embeddings are enabled and available, semantic similarity is combined with token-set similarity.
2. If embedding retrieval fails for any reason, the engine automatically falls back to lexical retrieval.
3. Up to three relevant examples are inserted into the GenAI planning context.
4. Positive/negative retrieved evidence contributes a small amount to confidence.

This keeps feedback useful without making it a single point of failure.

## Confidence score

Confidence is **not just the model saying “I am confident.”** It combines:

- 34% semantic interpretation confidence
- 22% schema grounding
- 10% assumption clarity
- 14% successful execution signal
- 12% deterministic result verification
- 8% relevant feedback evidence

A repaired query receives an additional penalty. The full score breakdown and reasons are returned in `metadata`.

## Safety and robustness

Before execution, the engine:

- allows only a single `SELECT` / `WITH ... SELECT` query,
- blocks DDL/DML and sensitive DuckDB commands,
- blocks external readers such as `read_csv`, `read_parquet`, scanners and `glob`,
- rejects unknown tables,
- executes only against preloaded in-memory tables,
- treats the user query, data dictionary, sample values and feedback as untrusted prompt data.

The batch runner is fault tolerant: one failed/ambiguous query returns a `confidence_score` of `0.0` without aborting the remaining evaluation queries.

## Setup

Python 3.11+ recommended.

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

macOS/Linux:

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Create `.env` from `.env.example`:

```env
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-6-luna
MAX_REPAIR_ATTEMPTS=1
MAX_RESULT_ROWS=5000
ENABLE_FEEDBACK_EMBEDDINGS=true
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
```

`OPENAI_MODEL` and the embedding model are configurable, so the project is not tied to a single deployment.

## Dataset

Place the official assignment files in `dataset/`:

```text
dataset/
├── sales_data.csv
├── targets.csv
├── data_dictionary.json
├── nl_queries.json
└── feedback_log.csv       # optional
```

Additional CSV files are auto-loaded. The filename stem becomes the SQL table name.

A tiny reproducible dataset is included in `examples/demo_dataset/` for demonstration and tests.

## Run

### One query

```bash
python main.py --dataset dataset --query "Top 3 products by revenue within each region"
```

### All queries from `nl_queries.json`

```bash
python main.py --dataset dataset --all --output results.json
```

### Benchmark summary

```bash
python benchmark.py --dataset dataset --output benchmark_results.json
```

This reports success rate, average confidence, median latency and repair count.

## API

Start the FastAPI service:

```bash
uvicorn api:app --host 0.0.0.0 --port 8000
```

Example request:

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query":"Top 3 products by revenue within each region"}'
```

Health endpoint:

```text
GET /health
```

## Docker

```bash
docker build -t intelligent-analytics-engine .
docker run --rm -p 8000:8000 --env-file .env intelligent-analytics-engine
```

Mount the official dataset when required by your runtime/deployment environment.

## Output contract

The required fields are preserved, with additional explainability metadata:

```json
{
  "query": "Top 3 products by revenue within each region",
  "generated_logic": "WITH ... SELECT ...",
  "result": [],
  "confidence_score": 0.92,
  "explanation": "Revenue is aggregated by region and product, then products are ranked within each region.",
  "understood_as": "Rank products independently inside every region by revenue and keep three.",
  "assumptions": [],
  "metadata": {
    "complexity": "complex",
    "query_features": {"ranking": true},
    "confidence_breakdown": {},
    "verification_warnings": [],
    "latency_ms": 0
  }
}
```

## Tests

```bash
pytest -q
```

The tests are deliberately stronger than “the result is non-empty.” They verify:

- exact Top-N-within-group output,
- contribution percentages summing to 100%,
- exact actual-vs-target variance values,
- end-to-end orchestration with a deterministic fake planner (no network required),
- feedback retrieval,
- SQL safety and prompt-injection boundary cases.

The repository also includes a GitHub Actions CI workflow that installs dependencies and runs the suite on every push/pull request.

## Sample output

`sample_outputs/reference_demo.json` demonstrates the result contract against the included demo data. It is clearly marked as a **reference demo**; before final submission, generate `results.json` using the official dataset and configured GenAI model rather than presenting fabricated assignment results.

## Tradeoffs

### LLM-generated SQL vs fixed rule parser

A fixed parser is predictable but brittle on unseen wording. An LLM planner generalizes better to business language; the validator and database provide the deterministic boundary.

### One model call vs planner + critic

This implementation uses one planning call and only performs another call when repair is needed. That keeps latency/cost lower than always using a second critic model. Deterministic post-execution verification provides a cheap additional signal.

### Feedback embeddings vs vector database

The assignment scope does not need a separate vector service. Small feedback logs can be embedded and scored in memory. For large production histories, the retriever would move to a vector store with persisted embeddings.

### Confidence calibration

The score is interpretable but heuristic. With labeled evaluation history, the next step would be empirical calibration (for example logistic/isotonic calibration) against actual correctness.

## Edge cases handled

- null values,
- empty result sets,
- divide-by-zero in percentages,
- text-formatted dates,
- multi-table joins,
- Top-N ties/order stability,
- target-grain joins,
- SQL validation failures,
- execution failures with error-guided repair,
- prompt-injection-style requests for unsafe SQL,
- unknown tables,
- oversized result sets with truncation metadata.

## If I had more time

1. Add dataset-level golden answers for every official `nl_queries.json` item once expected outputs are available.
2. Add AST-level SQL lineage/type validation.
3. Calibrate confidence against labeled evaluation data.
4. Cache plans/results using query + dataset fingerprint.
5. Add execution resource/time limits for very large datasets.
6. Add an Azure OpenAI provider adapter and Azure deployment manifests.
7. Persist feedback embeddings in a vector store when feedback volume becomes large.

## Design summary

The main separation of responsibilities is deliberate:

- **GenAI** understands business language and creates the analytical plan.
- **Validation** enforces the execution boundary.
- **DuckDB** computes the answer.
- **Feedback-RAG** improves future plans.
- **Verification + confidence** make uncertainty visible instead of hiding it.

That makes the system flexible enough for unseen questions while remaining auditable, testable and deployable.
