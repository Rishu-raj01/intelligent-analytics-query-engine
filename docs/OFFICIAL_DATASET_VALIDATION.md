# Official Dataset Validation Notes

This repository includes the assignment dataset in `dataset/` and validates the important edge cases before the GenAI layer is allowed to execute analytics.

## 1. `NA` is a real business value

The supplied data uses `NA` as the region code for North America. Pandas normally interprets `NA` as a missing value, which would silently break region grouping and target joins. The loader therefore uses `keep_default_na=False` and treats only genuinely empty cells as null.

## 2. Transport-wrapped files

The supplied files can arrive with each original CSV/JSON line wrapped as a single quoted field. `read_csv_compat()` and `read_json_compat()` detect this representation and reverse only the transport wrapping before parsing. Normal CSV/JSON files continue to work unchanged.

## 3. No evaluation leakage

`nl_queries.json` contains both a natural-language `query` and an `expected_logic` field. Runtime intentionally extracts only the natural-language question. `expected_logic` is never sent to the LLM planner and is never used to generate answers.

This is deliberate: the assignment requires unseen-query support and forbids hardcoded answers.

## 4. Physical schema vs. data dictionary

The dictionary defines business metrics and synonyms, but its dimension list does not enumerate every valid physical column. For example, `customer_id` and `product_name` exist in `sales_data.csv` and are required by two supplied queries.

The engine therefore treats the profiled physical schema as authoritative for field existence and the data dictionary as semantic guidance for definitions and synonyms.

## 5. YoY limitation

The sales data contains only 2024 dates. A genuine year-over-year growth calculation needs a previous year. The correct behavior is to return the available 2024 revenue with `previous_year_revenue = NULL` and `yoy_growth_pct = NULL`, while explaining the missing comparison period instead of inventing history.

## 6. Golden checks

`tests/test_official_dataset.py` validates ingestion plus the expected analytical behavior for all eight supplied query types:

- filtered revenue aggregation,
- top-N ranking,
- average order value,
- target comparison,
- contribution percentage,
- top product within each region,
- YoY with missing prior-year data,
- nested top-3-customer revenue by region.

These checks are test-only. The runtime engine does not read golden outputs or use them as a fallback answer cache.
