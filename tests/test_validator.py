import pytest

from analytics_engine.validator import SQLValidationError, validate_sql


ALLOWED = {"sales_data", "targets"}


def test_allows_simple_select():
    validate_sql("SELECT region, SUM(amount) FROM sales_data GROUP BY region", ALLOWED)


def test_allows_cte_and_join():
    validate_sql(
        """
        WITH x AS (SELECT region, SUM(amount) AS actual FROM sales_data GROUP BY region)
        SELECT x.region, x.actual, t.target FROM x JOIN targets t ON x.region = t.region
        """,
        ALLOWED,
    )


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE sales_data",
        "DELETE FROM sales_data",
        "COPY sales_data TO '/tmp/x.csv'",
        "SELECT * FROM read_csv_auto('/etc/passwd')",
        "PRAGMA database_list",
        "SELECT 1; SELECT 2",
    ],
)
def test_blocks_unsafe_sql(sql):
    with pytest.raises(SQLValidationError):
        validate_sql(sql, ALLOWED)


def test_blocks_unknown_table():
    with pytest.raises(SQLValidationError):
        validate_sql("SELECT * FROM secret_table", ALLOWED)


def test_semicolon_inside_literal_is_not_treated_as_second_statement():
    validate_sql("SELECT 'a;b' AS text FROM sales_data LIMIT 1", ALLOWED)
