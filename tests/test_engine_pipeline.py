import json
from pathlib import Path

import pandas as pd

from analytics_engine.config import Settings
from analytics_engine.engine import AnalyticsQueryEngine
from analytics_engine.models import ExpectedOutput, QueryFeatures, QueryPlan


class FakePlanner:
    def plan(self, **kwargs):
        return QueryPlan(
            understanding="Rank customers by computed revenue within each region and keep the top two.",
            sql="""
            WITH x AS (
              SELECT region, customer,
                     SUM(quantity * unit_price * (1 - discount)) AS revenue
              FROM sales_data GROUP BY region, customer
            ), r AS (
              SELECT *, ROW_NUMBER() OVER (PARTITION BY region ORDER BY revenue DESC, customer) AS rank
              FROM x
            )
            SELECT region, customer, revenue, rank FROM r WHERE rank <= 2 ORDER BY region, rank
            """,
            used_tables=["sales_data"],
            referenced_columns=["region", "customer", "quantity", "unit_price", "discount"],
            assumptions=[],
            explanation="Revenue is computed from quantity, unit price and discount, then customers are ranked independently inside each region.",
            semantic_confidence=0.96,
            complexity="complex",
            query_features=QueryFeatures(aggregation=True, grouping=True, ranking=True, nested_logic=True),
            expected_output=ExpectedOutput(
                grain="top two customers within each region",
                columns=["region", "customer", "revenue", "rank"],
            ),
        )

    def repair(self, **kwargs):
        raise AssertionError("Repair should not be needed in this test")


def build_dataset(path: Path):
    pd.DataFrame(
        [
            [1, "North", "Alice", 2, 100.0, 0.0],
            [2, "North", "Bob", 1, 300.0, 0.1],
            [3, "South", "Alice", 4, 50.0, 0.0],
            [4, "South", "Cara", 1, 500.0, 0.0],
            [5, "North", "Alice", 1, 400.0, 0.0],
        ],
        columns=["order_id", "region", "customer", "quantity", "unit_price", "discount"],
    ).to_csv(path / "sales_data.csv", index=False)
    (path / "data_dictionary.json").write_text(
        json.dumps({"revenue": "quantity * unit_price * (1 - discount)"}),
        encoding="utf-8",
    )


def test_end_to_end_pipeline_without_network(tmp_path: Path):
    build_dataset(tmp_path)
    settings = Settings(
        dataset_dir=tmp_path,
        model="test-model",
        max_repair_attempts=0,
        max_result_rows=100,
        enable_feedback_embeddings=False,
        embedding_model="unused",
    )
    engine = AnalyticsQueryEngine(settings)
    engine.planner = FakePlanner()

    output = engine.answer("Top 2 customers by revenue within each region").to_dict()

    assert output["result"][0] == {
        "region": "North", "customer": "Alice", "revenue": 600.0, "rank": 1
    }
    assert output["metadata"]["repaired"] is False
    assert output["metadata"]["query_features"]["ranking"] is True
    assert output["confidence_score"] > 0.8
    assert output["generated_logic"].strip().upper().startswith("WITH")
