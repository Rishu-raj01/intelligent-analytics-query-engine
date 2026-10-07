# Intelligent Analytics Query Engine

A GenAI-powered analytics engine that converts natural-language business questions into **validated DuckDB SQL**, executes the SQL against the supplied dataset, and returns results with an explanation and confidence score.

> **Design principle:** the LLM interprets the question; the database computes the truth.

## Why this design

The assignment requires correctness, GenAI usage, unseen-query support, confidence, explanations, complex analytics, and an optional feedback loop. A direct “ask an LLM for the final number” approach is flexible but unreliable. A fully rule-based parser is deterministic but brittle on unseen wording.

This implementation uses a hybrid architecture:

```text
Natural-language query
        |
        v
Schema profiler + data dictionary + relevant feedback
        |
        v
GenAI semantic planner (strict structured output)
        |
        v
Read-only DuckDB SQL
        |
        v
SQL safety / grounding validation
        |
        v
DuckDB deterministic execution
        |
        +---- execution error ---> one error-guided GenAI repair
        |
        v
Post-result verification
        |
        v
Result + confidence + explanation
```

## Requirement coverage

| Requirement | Implementation |
|---|---|
| Understand natural language | GenAI planner receives the question, physical schema profile and data dictionary |
| Map business terms to fields | Dictionary metrics/synonyms + real schema samples |
| Executable logic | DuckDB SQL |
| Aggregation/grouping/filtering | Native SQL |
| Ranking | Window functions |
| Top N within groups | `ROW_NUMBER` / `DENSE_RANK` partitioned by parent group |
| Contribution percentages | CTE/window denominator logic with `NULLIF` protection |
| Nested logic | Explicit CTEs |
| Comparisons with targets | Actuals aggregated to target grain before join |
| Time-based queries | Date profiling + DuckDB date functions |
| Meaningful GenAI | Semantic planning, structured output, error-guided repair, feedback retrieval |
| Confidence score | Semantic + schema + execution + verification + feedback evidence |
| Explanation | Understanding, assumptions, generated logic and result reasoning |
| Feedback loop | Relevant `feedback_log.csv` examples retrieved into planner context |
| Unseen queries | No exact-query fallback rules or hardcoded answers |

## Project structure

```text
.
├── analytics_engine/
│   ├── config.py
│   ├── data_loader.py
│   ├── llm_planner.py
│   ├── validator.py
│   ├── executor.py
│   ├── feedback.py
│   ├── verifier.py
│   ├── confidence.py
│   ├── models.py
│   └── engine.py
├── dataset/                       # official assignment files
├── tests/                         # exact-result + safety tests
├── sample_outputs/
│   └── official_reference.json
├── docs/
│   ├── ARCHITECTURE.md
│   ├── EVALUATION_MAPPING.md
│   ├── DEMO_SCRIPT.md
│   └── OFFICIAL_DATASET_VALIDATION.md
├── main.py                        # CLI
├── api.py                         # FastAPI endpoint
├── benchmark.py                   # batch evaluation summary
├── Dockerfile
└── .github/workflows/ci.yml
```

## Official dataset

The assignment files are included in `dataset/`:

```text
dataset/
├── sales_data.csv
├── targets.csv
├── data_dictionary.json
└── nl_queries.json
```

`feedback_log.csv` is optional and is auto-detected when present.

### Important data-quality handling

The supplied data contains several evaluation traps that are handled explicitly:

1. **`NA` is a real region value.** Pandas normally treats `NA` as a missing value. The loader preserves it with `keep_default_na=False`, preventing silent corruption of North America groupings and target joins.
2. **Transport-wrapped files are supported.** If every original CSV/JSON line arrives wrapped as one quoted field, the compatibility loader reverses only that wrapping before parsing.
3. **The physical schema is authoritative.** The data dictionary provides business semantics, but it does not list every physical field. Valid columns such as `customer_id` and `product_name` can still be used when present in the CSV.
4. **No evaluation leakage.** `nl_queries.json` contains `expected_logic`, but runtime deliberately extracts only the natural-language `query`. `expected_logic` is never passed to the planner and is never used as a fallback answer.
5. **Missing comparison periods are not fabricated.** The supplied sales data contains only 2024. For YoY, the engine is instructed to return a `NULL` previous-year value/growth and explain the data limitation.

More detail: [`docs/OFFICIAL_DATASET_VALIDATION.md`](docs/OFFICIAL_DATASET_VALIDATION.md).

## GenAI planner

The planner uses the OpenAI **Responses API** with a strict JSON-schema contract. It must return:

- interpretation (`understanding`),
- one read-only DuckDB SQL query,
- tables and columns used,
- assumptions,
- complexity,
- analytical features,
- expected output shape,
- semantic confidence,
- explanation.

The prompt explicitly tells the model **not to compute final numbers** and **not to hardcode evaluation questions**.

### Why SQL instead of generated Python?

SQL is easier to audit, validate and sandbox. DuckDB supports all operations required by the task: joins, grouping, window functions, CTEs, ranking, percentages and time logic.

## SQL safety

Before execution the validator:

- permits only one `SELECT` / `WITH ... SELECT` statement,
- blocks DDL/DML and sensitive commands,
- blocks external file/network readers such as `read_csv`, `read_parquet`, scanners and `glob`,
- rejects unknown/unapproved tables,
- executes only against preloaded in-memory tables.

If valid SQL fails during execution, one repair attempt can be made using the concrete database error while preserving the original business intent.

## Feedback loop

When `feedback_log.csv` exists, the engine retrieves feedback relevant to the new question. It can combine embeddings with lexical similarity, and automatically falls back to lexical retrieval if embeddings are unavailable. Only a few relevant examples are added to the planner context.

This keeps feedback useful without turning historical answers into hardcoded rules.

## Confidence score

The confidence score is an **evidence-based heuristic**, not a claim that `0.92` means “92% statistically guaranteed correct.” It combines:

- semantic interpretation confidence,
- schema grounding,
- explicit assumptions,
- successful execution,
- deterministic result verification,
- relevant feedback evidence.

Repairs, missing evidence and verification warnings reduce the score. The detailed breakdown is returned in `metadata`.

## Setup

Python 3.11+ is recommended.

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

Create `.env` from `.env.example` and add your API key:

```env
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-6-luna
MAX_REPAIR_ATTEMPTS=1
MAX_RESULT_ROWS=5000
ENABLE_FEEDBACK_EMBEDDINGS=true
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
```

The model name is configurable through `OPENAI_MODEL`.

## Run

Run one query:

```bash
python main.py --dataset dataset --query "Top product in each region"
```

Run all supplied queries:

```bash
python main.py --dataset dataset --all --output results.json
```

Run the benchmark summary:

```bash
python benchmark.py --dataset dataset --output benchmark_results.json
```

Start the API:

```bash
uvicorn api:app --host 0.0.0.0 --port 8000
```

Docker:

```bash
docker build -t intelligent-analytics-engine .
docker run --rm -p 8000:8000 --env-file .env intelligent-analytics-engine
```

## Required output contract

The five assignment fields are always present; additional metadata is included for auditability.

```json
{
  "query": "Top product in each region",
  "generated_logic": "WITH ... SELECT ...",
  "result": [],
  "confidence_score": 0.94,
  "explanation": "Revenue is aggregated by region and product and ranked within each region.",
  "understood_as": "Find the highest-revenue product independently in each region.",
  "assumptions": [],
  "metadata": {
    "complexity": "complex",
    "confidence_breakdown": {},
    "verification_warnings": []
  }
}
```

## Official reference outputs

[`sample_outputs/official_reference.json`](sample_outputs/official_reference.json) contains independently checked reference results for all eight supplied assignment questions. It is **not read by runtime code** and cannot act as an answer cache.

The numerical results and canonical SQL were validated against the supplied dataset. The committed reference confidence values are representative only because no API key is stored in the repository. Generate an actual live-model run with:

```bash
python main.py --dataset dataset --all --output sample_outputs/model_run.json
```

## Tests

```bash
pytest -q
```

The test suite verifies more than “a result was returned.” It includes:

- official-file ingestion and literal `NA` preservation,
- schema/dictionary grounding,
- date coverage detection,
- exact India/March revenue,
- exact top-2 city profit ranking,
- exact AOV by region,
- exact February target misses and variances,
- contribution percentages summing to 100%,
- top product per region,
- YoY behavior when the previous year is absent,
- nested top-3-customer revenue per region,
- SQL safety,
- feedback retrieval,
- end-to-end orchestration with a deterministic fake planner.

GitHub Actions installs dependencies and runs the suite on pushes and pull requests.

## Tradeoffs

**LLM planner vs. fixed parser:** a fixed parser is predictable but brittle on unseen wording. The LLM generalizes better, while validation and DuckDB provide deterministic boundaries.

**One planner call vs. planner + critic:** a second model call is used only when repair is needed. This reduces latency/cost; deterministic verification provides an additional signal.

**In-memory feedback retrieval vs. vector database:** appropriate for the small assignment scope. A production version with large feedback history would persist embeddings in a vector store.

**Heuristic confidence:** interpretable and useful for this assignment, but not statistically calibrated. With labeled production data, the score should be calibrated against actual correctness.

## If I had more time

- AST-level SQL lineage and type validation,
- empirical confidence calibration,
- query/result caching keyed by dataset fingerprint,
- execution time/resource limits for large data,
- provider adapters for Azure OpenAI,
- persisted feedback embeddings/vector retrieval,
- a larger adversarial unseen-query evaluation suite.

## Summary

The system separates responsibilities intentionally:

- **GenAI** understands business language and creates a structured analytical plan.
- **Validation** enforces a safe execution boundary.
- **DuckDB** computes the result.
- **Feedback retrieval** improves future planning.
- **Verification + confidence** expose uncertainty instead of hiding it.

This keeps the engine flexible enough for unseen questions while remaining auditable, testable and deterministic where correctness matters.
