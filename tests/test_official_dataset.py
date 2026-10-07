import math
from pathlib import Path

from analytics_engine.data_loader import DatasetLoader
from analytics_engine.executor import DuckDBExecutor


DATASET = Path(__file__).resolve().parents[1] / "dataset"


def load_bundle():
    return DatasetLoader(DATASET).load()


def test_official_files_load_and_preserve_na_region():
    bundle = load_bundle()
    sales = bundle.tables["sales_data"]
    targets = bundle.tables["targets"]
    assert sales.shape == (10, 15)
    assert targets.shape == (9, 3)
    assert set(sales["region"].unique()) == {"APAC", "EMEA", "NA"}
    assert sales["region"].isna().sum() == 0
    assert targets["region"].isna().sum() == 0
    assert len(bundle.nl_queries) == 8


def test_dictionary_and_physical_schema_are_both_available():
    bundle = load_bundle()
    assert bundle.data_dictionary["synonyms"]["sales"] == "revenue"
    assert bundle.data_dictionary["metrics"]["revenue"] == "quantity * unit_price * (1 - discount)"
    assert "customer_id" in bundle.tables["sales_data"].columns
    assert "product_name" in bundle.tables["sales_data"].columns


def test_date_profile_exposes_single_year_for_yoy_reasoning():
    bundle = load_bundle()
    order_date = next(c for c in bundle.profiles["sales_data"]["columns"] if c["name"] == "order_date")
    assert order_date["date_like"] is True
    assert order_date["date_coverage"]["years"] == [2024]


def test_total_sales_india_march():
    result = DuckDBExecutor(load_bundle().tables).execute("""
        SELECT SUM(quantity * unit_price * (1 - discount)) AS total_sales
        FROM sales_data
        WHERE country = 'India'
          AND strftime(TRY_CAST(order_date AS DATE), '%Y-%m') = '2024-03'
    """)
    assert math.isclose(result.rows[0]["total_sales"], 108.0)


def test_top_2_cities_by_profit():
    result = DuckDBExecutor(load_bundle().tables).execute("""
        SELECT city, SUM(profit) AS total_profit
        FROM sales_data
        GROUP BY city
        ORDER BY total_profit DESC, city ASC
        LIMIT 2
    """)
    assert result.rows == [
        {"city": "New York", "total_profit": 200.0},
        {"city": "San Francisco", "total_profit": 180.0},
    ]


def test_average_order_value_by_region():
    result = DuckDBExecutor(load_bundle().tables).execute("""
        SELECT region,
               SUM(quantity * unit_price * (1 - discount)) / NULLIF(COUNT(order_id), 0) AS avg_order_value
        FROM sales_data
        GROUP BY region
        ORDER BY region
    """)
    expected = {"APAC": 118.5, "EMEA": 2398.0 / 3.0, "NA": 3262.4 / 3.0}
    for row in result.rows:
        assert math.isclose(row["avg_order_value"], expected[row["region"]], rel_tol=1e-9)


def test_regions_missing_feb_target():
    result = DuckDBExecutor(load_bundle().tables).execute("""
        WITH actual AS (
            SELECT region,
                   strftime(TRY_CAST(order_date AS DATE), '%Y-%m') AS month,
                   SUM(quantity * unit_price * (1 - discount)) AS actual_revenue
            FROM sales_data
            GROUP BY region, month
        )
        SELECT a.region, a.actual_revenue, t.target_revenue,
               a.actual_revenue - t.target_revenue AS variance
        FROM actual a
        JOIN targets t ON a.region = t.region AND a.month = t.month
        WHERE a.month = '2024-02' AND a.actual_revenue < t.target_revenue
        ORDER BY a.region
    """)
    assert result.rows == [
        {"region": "APAC", "actual_revenue": 75.0, "target_revenue": 6000.0, "variance": -5925.0},
        {"region": "EMEA", "actual_revenue": 255.0, "target_revenue": 7500.0, "variance": -7245.0},
        {"region": "NA", "actual_revenue": 1116.0, "target_revenue": 9500.0, "variance": -8384.0},
    ]


def test_category_contribution_sums_to_100():
    result = DuckDBExecutor(load_bundle().tables).execute("""
        WITH category_revenue AS (
            SELECT product_category,
                   SUM(quantity * unit_price * (1 - discount)) AS revenue
            FROM sales_data
            GROUP BY product_category
        )
        SELECT product_category, revenue,
               100.0 * revenue / NULLIF(SUM(revenue) OVER (), 0) AS contribution_pct
        FROM category_revenue
        ORDER BY contribution_pct DESC, product_category
    """)
    assert math.isclose(sum(r["contribution_pct"] for r in result.rows), 100.0, rel_tol=1e-9)
    assert [r["product_category"] for r in result.rows] == ["Technology", "Furniture", "Office Supplies"]


def test_top_product_in_each_region():
    result = DuckDBExecutor(load_bundle().tables).execute("""
        WITH product_revenue AS (
            SELECT region, product_name,
                   SUM(quantity * unit_price * (1 - discount)) AS revenue
            FROM sales_data
            GROUP BY region, product_name
        ), ranked AS (
            SELECT *, DENSE_RANK() OVER (PARTITION BY region ORDER BY revenue DESC) AS rank
            FROM product_revenue
        )
        SELECT region, product_name, revenue
        FROM ranked
        WHERE rank = 1
        ORDER BY region, product_name
    """)
    assert result.rows == [
        {"region": "APAC", "product_name": "Ergo Chair", "revenue": 324.0},
        {"region": "EMEA", "product_name": "Samsung Galaxy", "revenue": 1288.0},
        {"region": "NA", "product_name": "Dell XPS", "revenue": 2068.0},
    ]


def test_yoy_is_null_without_previous_year():
    result = DuckDBExecutor(load_bundle().tables).execute("""
        WITH yearly AS (
            SELECT EXTRACT(YEAR FROM TRY_CAST(order_date AS DATE))::INTEGER AS year,
                   SUM(quantity * unit_price * (1 - discount)) AS current_year_revenue
            FROM sales_data GROUP BY year
        ), lagged AS (
            SELECT year, current_year_revenue,
                   LAG(current_year_revenue) OVER (ORDER BY year) AS previous_year_revenue
            FROM yearly
        )
        SELECT year, current_year_revenue, previous_year_revenue,
               100.0 * (current_year_revenue - previous_year_revenue)
               / NULLIF(previous_year_revenue, 0) AS yoy_growth_pct
        FROM lagged ORDER BY year
    """)
    assert len(result.rows) == 1
    assert result.rows[0]["year"] == 2024
    assert math.isclose(result.rows[0]["current_year_revenue"], 6134.4)
    assert result.rows[0]["previous_year_revenue"] is None
    assert result.rows[0]["yoy_growth_pct"] is None


def test_revenue_of_top_3_customers_per_region():
    result = DuckDBExecutor(load_bundle().tables).execute("""
        WITH customer_revenue AS (
            SELECT region, customer_id,
                   SUM(quantity * unit_price * (1 - discount)) AS revenue
            FROM sales_data
            GROUP BY region, customer_id
        ), ranked AS (
            SELECT *, ROW_NUMBER() OVER (
                PARTITION BY region ORDER BY revenue DESC, customer_id ASC
            ) AS rank
            FROM customer_revenue
        )
        SELECT region, SUM(revenue) AS top_3_customers_revenue
        FROM ranked
        WHERE rank <= 3
        GROUP BY region
        ORDER BY region
    """)
    assert result.rows == [
        {"region": "APAC", "top_3_customers_revenue": 474.0},
        {"region": "EMEA", "top_3_customers_revenue": 2398.0},
        {"region": "NA", "top_3_customers_revenue": 3262.4},
    ]
