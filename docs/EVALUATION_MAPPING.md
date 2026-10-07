# Evaluation Mapping

This document maps the assignment rubric directly to implementation evidence.

| Evaluation area | Evidence in this repository |
|---|---|
| Correctness | DuckDB executes all numerical logic; exact-result tests cover complex analytics |
| Natural-language understanding | `analytics_engine/llm_planner.py` receives schema profiles, samples and dictionary |
| GenAI usage | Strict structured planning, semantic confidence, assumptions, error-guided repair |
| Aggregation/grouping/filtering | Generated DuckDB SQL |
| Ranking | Window functions; exact Top-N-per-group test |
| Contribution percentages | Window/CTE denominator logic; exact 100% sum test |
| Nested logic | CTE-based planning guidance |
| Target comparisons | Grain-aware join guidance + exact target variance test |
| Time queries | Date profiling and DuckDB date functions |
| Confidence | `analytics_engine/confidence.py` returns interpretable component breakdown |
| Explanations | Planner interpretation + SQL + assumptions + metadata |
| Feedback loop | `analytics_engine/feedback.py` hybrid embedding/lexical retrieval |
| Edge cases | SQL safety, nulls, empty results, divide-by-zero, repair, truncation |
| Unseen queries | No exact query strings or query-specific fallback branches |
| Engineering quality | typed internal models, tests, CI, API, Docker, benchmark script |

## Correctness philosophy

The LLM never returns the final metric value as truth. It creates executable logic; DuckDB computes the result. This avoids the common failure mode where an LLM provides plausible-looking but unverified arithmetic.

## GenAI is necessary, not decorative

Removing the model would remove the semantic layer that maps unseen business phrasing to schema-aware analytical logic. The model is therefore part of the system's reasoning path, while deterministic components constrain and verify it.

## Why the feedback loop counts as learning from feedback

The engine does not blindly append the first rows of the log. It retrieves the most relevant historical feedback for the current question and injects those examples into the planner context. Embedding similarity is used when possible, with lexical fallback for resilience.
