from __future__ import annotations

import csv
import io
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


def _unwrap_line_encoded_text(text: str) -> str:
    """Repair files where every logical line was exported as one quoted CSV field.

    Some spreadsheet/download pipelines wrap each original CSV/JSON line in quotes and
    double the quotes inside it. This helper reverses that transport encoding without
    changing the actual values.
    """
    repaired: list[str] = []
    for line in text.splitlines():
        if line.startswith('"'):
            try:
                parsed = next(csv.reader([line]))
                if len(parsed) == 1:
                    repaired.append(parsed[0])
                    continue
            except csv.Error:
                pass
        repaired.append(line)
    return "\n".join(repaired)


def read_csv_compat(path: Path) -> pd.DataFrame:
    """Read normal CSVs and line-wrapped CSV exports while preserving literal 'NA'."""
    kwargs = {
        "encoding": "utf-8-sig",
        # Critical: the assignment uses region='NA' (North America). Pandas normally
        # treats 'NA' as a missing value, which would silently corrupt analytics/joins.
        "keep_default_na": False,
        # Still represent genuinely empty fields as missing values.
        "na_values": [""],
    }
    df = pd.read_csv(path, **kwargs)

    # The supplied assignment CSVs may arrive with each full row quoted as one field.
    if len(df.columns) == 1 and "," in str(df.columns[0]):
        raw = path.read_text(encoding="utf-8-sig")
        repaired = _unwrap_line_encoded_text(raw)
        df = pd.read_csv(io.StringIO(repaired), keep_default_na=False, na_values=[""])

    # Defensive cleanup for BOMs/whitespace that occasionally survive exports.
    df.columns = [str(c).lstrip("\ufeff").strip() for c in df.columns]
    return df


def read_json_compat(path: Path) -> Any:
    """Read standard JSON plus line-wrapped JSON exports without semantic changes."""
    text = path.read_text(encoding="utf-8-sig")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = json.loads(_unwrap_line_encoded_text(text))

    # Also tolerate a file whose entire JSON document was serialized as a JSON string.
    if isinstance(parsed, str):
        parsed = json.loads(parsed)
    return parsed


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
            tables[table_name] = read_csv_compat(csv_path)

        if not tables:
            raise FileNotFoundError(
                f"No CSV data tables found in {self.dataset_dir.resolve()}"
            )

        dictionary_path = self.dataset_dir / "data_dictionary.json"
        data_dictionary: Any = {}
        if dictionary_path.exists():
            data_dictionary = read_json_compat(dictionary_path)

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
        raw = read_json_compat(path)

        # Intentionally extract only the natural-language question. If the assignment
        # ships evaluator/reference metadata such as `expected_logic`, it is NOT exposed
        # to the LLM planner. This avoids answer leakage and query-specific hardcoding.
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
            parsed_dates: pd.Series | None = None
            if len(non_null) and (
                "date" in str(col).lower()
                or "month" in str(col).lower()
                or "year" in str(col).lower()
                or "time" in str(col).lower()
            ):
                try:
                    parsed_dates = pd.to_datetime(non_null.head(1000), errors="coerce")
                    date_like = float(parsed_dates.notna().mean()) >= 0.8
                except Exception:
                    date_like = False

            profile: dict[str, Any] = {
                "name": str(col),
                "dtype": str(series.dtype),
                "null_count": int(series.isna().sum()),
                "unique_count": unique_count,
                "sample_values": samples,
                "date_like": date_like,
            }
            if date_like and parsed_dates is not None:
                valid_dates = parsed_dates.dropna()
                if len(valid_dates):
                    profile["date_coverage"] = {
                        "min": valid_dates.min().isoformat(),
                        "max": valid_dates.max().isoformat(),
                        "years": sorted({int(x) for x in valid_dates.dt.year.tolist()}),
                    }
            columns.append(profile)
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
