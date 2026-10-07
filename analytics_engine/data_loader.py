from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


def safe_table_name(path: Path) -> str:
    name = re.sub(r"[^a-zA-Z0-9_]+", "_", path.stem.strip())
    if not name:
        raise ValueError(f"Could not derive a SQL table name from {path.name}")
    if name[0].isdigit():
        name = f"t_{name}"
    return name.lower()


def _jsonable(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value


@dataclass
class DatasetBundle:
    tables: dict[str, pd.DataFrame]
    data_dictionary: Any
    nl_queries: list[str]
    feedback_path: Path | None
    profiles: dict[str, Any]
    relationship_hints: list[dict[str, Any]]


class DatasetLoader:
    def __init__(self, dataset_dir: Path):
        self.dataset_dir = dataset_dir

    def load(self) -> DatasetBundle:
        if not self.dataset_dir.exists():
            raise FileNotFoundError(
                f"Dataset directory not found: {self.dataset_dir.resolve()}"
            )

        tables: dict[str, pd.DataFrame] = {}
        feedback_path: Path | None = None
        for csv_path in sorted(self.dataset_dir.glob("*.csv")):
            if csv_path.name.lower() == "feedback_log.csv":
                feedback_path = csv_path
                continue
            table_name = safe_table_name(csv_path)
            tables[table_name] = pd.read_csv(csv_path)

        if not tables:
            raise FileNotFoundError(
                f"No CSV data tables found in {self.dataset_dir.resolve()}"
            )

        dictionary_path = self.dataset_dir / "data_dictionary.json"
        data_dictionary: Any = {}
        if dictionary_path.exists():
            with dictionary_path.open("r", encoding="utf-8") as f:
                data_dictionary = json.load(f)

        query_path = self.dataset_dir / "nl_queries.json"
        nl_queries = self._load_queries(query_path) if query_path.exists() else []

        profiles = {name: self._profile_table(name, df) for name, df in tables.items()}
        relationship_hints = self._infer_relationships(tables)

        return DatasetBundle(
            tables=tables,
            data_dictionary=data_dictionary,
            nl_queries=nl_queries,
            feedback_path=feedback_path,
            profiles=profiles,
            relationship_hints=relationship_hints,
        )

    @staticmethod
    def _load_queries(path: Path) -> list[str]:
        with path.open("r", encoding="utf-8") as f:
            raw = json.load(f)

        if isinstance(raw, list):
            output: list[str] = []
            for item in raw:
                if isinstance(item, str):
                    output.append(item)
                elif isinstance(item, dict):
                    for key in ("query", "question", "nl_query", "text"):
                        if key in item:
                            output.append(str(item[key]))
                            break
            return output

        if isinstance(raw, dict):
            for key in ("queries", "nl_queries", "questions"):
                if isinstance(raw.get(key), list):
                    return DatasetLoader._normalize_query_list(raw[key])

        raise ValueError(f"Unsupported nl_queries.json structure in {path}")

    @staticmethod
    def _normalize_query_list(items: list[Any]) -> list[str]:
        result: list[str] = []
        for item in items:
            if isinstance(item, str):
                result.append(item)
            elif isinstance(item, dict):
                for key in ("query", "question", "nl_query", "text"):
                    if key in item:
                        result.append(str(item[key]))
                        break
        return result

    @staticmethod
    def _profile_table(name: str, df: pd.DataFrame) -> dict[str, Any]:
        columns: list[dict[str, Any]] = []
        for col in df.columns:
            series = df[col]
            non_null = series.dropna()
            samples = [_jsonable(v) for v in non_null.head(3).tolist()]
            unique_count = int(non_null.nunique(dropna=True)) if len(non_null) else 0

            date_like = False
            if len(non_null) and (
                "date" in str(col).lower()
                or "month" in str(col).lower()
                or "year" in str(col).lower()
                or "time" in str(col).lower()
            ):
                try:
                    parsed = pd.to_datetime(non_null.head(100), errors="coerce")
                    date_like = float(parsed.notna().mean()) >= 0.8
                except Exception:
                    date_like = False

            columns.append(
                {
                    "name": str(col),
                    "dtype": str(series.dtype),
                    "null_count": int(series.isna().sum()),
                    "unique_count": unique_count,
                    "sample_values": samples,
                    "date_like": date_like,
                }
            )
        return {"table": name, "rows": int(len(df)), "columns": columns}

    @staticmethod
    def _infer_relationships(tables: dict[str, pd.DataFrame]) -> list[dict[str, Any]]:
        names = list(tables)
        hints: list[dict[str, Any]] = []
        for i, left_name in enumerate(names):
            left = tables[left_name]
            for right_name in names[i + 1 :]:
                right = tables[right_name]
                shared = [c for c in left.columns if c in set(right.columns)]
                if shared:
                    hints.append(
                        {
                            "tables": [left_name, right_name],
                            "shared_columns": [str(c) for c in shared],
                            "note": "Candidate join keys only; use business meaning and data dictionary to decide.",
                        }
                    )
        return hints
