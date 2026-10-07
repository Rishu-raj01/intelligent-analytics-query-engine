from __future__ import annotations

from typing import Any

import duckdb
import numpy as np
import pandas as pd

from .models import ExecutionResult


def _json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        if np.isnan(value):
            return None
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if pd.isna(value):
        return None
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    return value


class DuckDBExecutor:
    def __init__(self, tables: dict[str, pd.DataFrame], max_rows: int = 5000):
        self.tables = tables
        self.max_rows = max_rows
        self.con = duckdb.connect(database=":memory:")
        for name, df in tables.items():
            self.con.register(name, df)

    def execute(self, sql: str) -> ExecutionResult:
        df = self.con.execute(sql).fetchdf()
        row_count = len(df)
        truncated = row_count > self.max_rows
        visible = df.head(self.max_rows) if truncated else df

        rows: list[dict[str, Any]] = []
        for record in visible.to_dict(orient="records"):
            rows.append({str(k): _json_value(v) for k, v in record.items()})

        return ExecutionResult(
            columns=[str(c) for c in df.columns],
            rows=rows,
            row_count=row_count,
            truncated=truncated,
        )
