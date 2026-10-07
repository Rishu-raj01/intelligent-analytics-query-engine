from __future__ import annotations

import re

from .models import QueryPlan


class SQLValidationError(ValueError):
    pass


BLOCKED_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "REPLACE",
    "COPY", "ATTACH", "DETACH", "INSTALL", "LOAD", "CALL", "PRAGMA",
    "EXPORT", "IMPORT", "TRUNCATE", "MERGE", "GRANT", "REVOKE", "VACUUM",
}

BLOCKED_EXTERNAL_FUNCTIONS = {
    "read_csv", "read_csv_auto", "read_parquet", "read_json", "read_json_auto",
    "read_text", "read_blob", "csv_scan", "parquet_scan", "json_scan",
    "sqlite_scan", "postgres_scan", "mysql_scan", "iceberg_scan", "delta_scan",
    "httpfs", "glob",
}


def _strip_sql_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return re.sub(r"--[^\n\r]*", " ", sql)


def _strip_string_literals(sql: str) -> str:
    return re.sub(r"'(?:''|[^'])*'", "''", sql)


def _cte_names(sql: str) -> set[str]:
    return {
        m.group(1).lower()
        for m in re.finditer(
            r"(?:\bWITH\b|,)\s*([A-Za-z_][A-Za-z0-9_]*)\s+AS\s*\(",
            sql,
            flags=re.IGNORECASE,
        )
    }


def _referenced_relations(sql: str) -> set[str]:
    refs: set[str] = set()
    pattern = re.compile(
        r"\b(?:FROM|JOIN)\s+((?:\"[^\"]+\")|(?:[A-Za-z_][A-Za-z0-9_]*))",
        flags=re.IGNORECASE,
    )
    for match in pattern.finditer(sql):
        token = match.group(1).strip().strip('"')
        if token:
            refs.add(token.lower())
    return refs


def validate_sql(sql: str, allowed_tables: set[str]) -> None:
    clean = _strip_sql_comments(sql).strip().rstrip(";").strip()
    if not clean:
        raise SQLValidationError("Generated SQL is empty.")

    if not re.match(r"^(SELECT|WITH)\b", clean, flags=re.IGNORECASE):
        raise SQLValidationError("Only read-only SELECT/WITH queries are allowed.")

    structure_only = _strip_string_literals(clean)
    if ";" in structure_only:
        raise SQLValidationError("Exactly one SQL statement is allowed.")

    upper = structure_only.upper()
    for keyword in BLOCKED_KEYWORDS:
        if re.search(rf"\b{keyword}\b", upper):
            raise SQLValidationError(f"Blocked SQL keyword: {keyword}")

    lowered = structure_only.lower()
    for function_name in BLOCKED_EXTERNAL_FUNCTIONS:
        if re.search(rf"\b{re.escape(function_name)}\s*\(", lowered):
            raise SQLValidationError(
                f"External-source function is not allowed: {function_name}"
            )

    ctes = _cte_names(clean)
    refs = _referenced_relations(clean)
    allowed = {t.lower() for t in allowed_tables}
    unknown = refs - allowed - ctes
    if unknown:
        raise SQLValidationError(
            "Query references unknown/unapproved tables: " + ", ".join(sorted(unknown))
        )


def validate_plan_metadata(
    plan: QueryPlan,
    allowed_tables: set[str],
    table_columns: dict[str, set[str]],
) -> list[str]:
    warnings: list[str] = []
    allowed_lower = {t.lower() for t in allowed_tables}
    planned_tables = {t.lower() for t in plan.used_tables}
    unknown_tables = planned_tables - allowed_lower
    if unknown_tables:
        warnings.append("Planner metadata names unknown table(s): " + ", ".join(sorted(unknown_tables)))

    all_columns = {c.lower() for cols in table_columns.values() for c in cols}
    unknown_columns: list[str] = []
    for ref in plan.referenced_columns:
        col = ref.split(".")[-1].strip('"`[]').lower()
        if col and col not in all_columns:
            unknown_columns.append(ref)
    if unknown_columns:
        warnings.append(
            "Planner metadata names unknown column(s): " + ", ".join(sorted(set(unknown_columns)))
        )
    return warnings
