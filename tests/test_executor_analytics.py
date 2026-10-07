import math

import pandas as pd

from analytics_engine.executor import DuckDBExecutor


def sample_tables():
    sales = pd.DataFrame(
        [
            [1, "2026-01-03", "North", "Alice", "A", 2, 100.0, 0.0],
            [2, "2026-01-04", "North", "Bob", "B", 1, 300.0, 0.1],
            [3, "2026-01-05", "South", "Alice", "A", 4, 50.0, 0.0],
            [4, "2026-01-06", "South", "Cara", "C", 1, 500.0, 0.0],
            [5, "2026-01-07", "North", "Alice", "C", 1, 400.0, 0.0],
        ],
        columns=[
            "order_id", "order_date", "region", "customer", "product",
            "quantity", "unit_price", "discount",
        ],
    )
    targets = pd.DataFrame(
        [["2026-01", "North", 800.0], ["2026-01", "South", 750.0]],
        columns=["month", "region", "target_revenue"],
    )
    return {"sales_data": sales, "targets": targets}


def test_top_n_within_group_exact_result():
    executor = DuckDBExecutor(sample_tables())
    sql = """
    WITH customer_revenue AS (
      SELECT region, customer,
             SUM(quantity * unit_price * (1 - discount)) AS revenue
      FROM sales_data
      GROUP BY region, customer
    ), ranked AS (
      SELECT *, ROW_NUMBER() OVER (PARTITION BY region ORDER BY revenue DESC, customer) AS rank
      FROM customer_revenue
    )
    SELECT region, customer, revenue, rank
    FROM ranked WHERE rank <= 2
    ORDER BY region, rank
    """
    result = executor.execute(sql)
    assert result.rows == [
        {"region": "North", "customer": "Alice", "revenue": 600.0, "rank": 1},
        {"region": "North", "customer": "Bob", "revenue": 270.0, "rank": 2},
        {"region": "South", "customer": "Cara", "revenue": 500.0, "rank": 1},
        {"region": "South", "customer": "Alice", "revenue": 200.0, "rank": 2},
    ]


def test_contribution_percentage_exact_total():
    executor = DuckDBExecutor(sample_tables())
    sql = """
    WITH p AS (
      SELECT product, SUM(quantity * unit_price * (1 - discount)) AS revenue
      FROM sales_data GROUP BY product
    )
    SELECT product, revenue,
           100.0 * revenue / NULLIF(SUM(revenue) OVER (), 0) AS contribution_pct
    FROM p ORDER BY product
    """
    result = executor.execute(sql)
    shares = [row["contribution_pct"] for row in result.rows]
    assert math.isclose(sum(shares), 100.0, rel_tol=1e-9, abs_tol=1e-9)
    assert [row["revenue"] for row in result.rows] == [400.0, 270.0, 900.0]


def test_target_comparison_join():
    executor = DuckDBExecutor(sample_tables())
    sql = """
    WITH actual AS (
      SELECT strftime(TRY_CAST(order_date AS DATE), '%Y-%m') AS month,
             region,
             SUM(quantity * unit_price * (1 - discount)) AS actual_revenue
      FROM sales_data
      GROUP BY 1, 2
    )
    SELECT a.region, a.actual_revenue, t.target_revenue,
           a.actual_revenue - t.target_revenue AS variance
    FROM actual a
    JOIN targets t USING (month, region)
    ORDER BY a.region
    """
    result = executor.execute(sql)
    assert result.rows == [
        {"region": "North", "actual_revenue": 870.0, "target_revenue": 800.0, "variance": 70.0},
        {"region": "South", "actual_revenue": 700.0, "target_revenue": 750.0, "variance": -50.0},
    ]
