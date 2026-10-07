from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from rapidfuzz import fuzz


@dataclass
class FeedbackExample:
    query: str
    corrected_logic: str
    feedback: str
    score: float
    is_positive: bool | None
    retrieval_method: str = "lexical"


class FeedbackStore:
    """Small feedback-RAG layer with embedding retrieval and safe lexical fallback."""

    def __init__(
        self,
        path: Path | None,
        enable_embeddings: bool = True,
        embedding_model: str = "text-embedding-3-small",
    ):
        self.path = path
        self.df = self._load(path)
        self.enable_embeddings = enable_embeddings
        self.embedding_model = embedding_model
        self._embedding_client = None
        self._row_embeddings: np.ndarray | None = None
        self._row_texts: list[str] = []

    @staticmethod
    def _load(path: Path | None) -> pd.DataFrame:
        if path is None or not path.exists():
            return pd.DataFrame()
        try:
            return pd.read_csv(path)
        except Exception:
            return pd.DataFrame()

    def relevant_examples(self, query: str, limit: int = 3) -> list[FeedbackExample]:
        if self.df.empty:
            return []

        q_col = self._find_col(["query", "nl_query", "question", "input"])
        if q_col is None:
            return []

        logic_col = self._find_col(
            ["corrected_logic", "correct_sql", "expected_sql", "generated_logic", "sql"]
        )
        feedback_col = self._find_col(["feedback", "notes", "comment", "reason"])
        correct_col = self._find_col(["is_correct", "correct", "accepted", "label"])

        lexical_scores: list[float] = []
        rows: list[tuple[int, pd.Series]] = []
        for idx, row in self.df.iterrows():
            past_query = self._clean(row.get(q_col))
            if not past_query:
                continue
            lexical_scores.append(fuzz.token_set_ratio(query, past_query) / 100.0)
            rows.append((idx, row))

        if not rows:
            return []

        combined = np.asarray(lexical_scores, dtype=float)
        method = "lexical"

        embedding_scores = self._embedding_scores(query, [self._clean(r.get(q_col)) for _, r in rows])
        if embedding_scores is not None and len(embedding_scores) == len(combined):
            combined = 0.75 * embedding_scores + 0.25 * combined
            method = "hybrid_embedding+lexical"

        ranked: list[FeedbackExample] = []
        for score, (_, row) in zip(combined.tolist(), rows):
            if score < 0.30:
                continue
            ranked.append(
                FeedbackExample(
                    query=self._clean(row.get(q_col)),
                    corrected_logic=self._clean(row.get(logic_col)) if logic_col else "",
                    feedback=self._clean(row.get(feedback_col)) if feedback_col else "",
                    score=float(score),
                    is_positive=self._parse_bool(row.get(correct_col)) if correct_col else None,
                    retrieval_method=method,
                )
            )

        ranked.sort(key=lambda x: x.score, reverse=True)
        return ranked[:limit]

    def confidence_signal(self, query: str) -> tuple[float, float]:
        examples = self.relevant_examples(query, limit=1)
        if not examples:
            return 0.0, 0.0
        ex = examples[0]
        if ex.is_positive is True:
            return 1.0, ex.score
        if ex.is_positive is False:
            return -1.0, ex.score
        return 0.0, ex.score

    def _embedding_scores(self, query: str, row_queries: list[str]) -> np.ndarray | None:
        if not self.enable_embeddings or not os.getenv("OPENAI_API_KEY") or not row_queries:
            return None
        try:
            from openai import OpenAI

            if self._embedding_client is None:
                self._embedding_client = OpenAI()

            if self._row_embeddings is None or self._row_texts != row_queries:
                response = self._embedding_client.embeddings.create(
                    model=self.embedding_model,
                    input=row_queries,
                )
                self._row_embeddings = np.asarray(
                    [item.embedding for item in response.data], dtype=float
                )
                self._row_embeddings = self._normalize(self._row_embeddings)
                self._row_texts = list(row_queries)

            response = self._embedding_client.embeddings.create(
                model=self.embedding_model,
                input=[query],
            )
            q = np.asarray(response.data[0].embedding, dtype=float)[None, :]
            q = self._normalize(q)
            similarities = (self._row_embeddings @ q.T).reshape(-1)
            return np.clip((similarities + 1.0) / 2.0, 0.0, 1.0)
        except Exception:
            return None

    @staticmethod
    def _normalize(matrix: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return matrix / norms

    def _find_col(self, candidates: list[str]) -> str | None:
        mapping = {str(c).strip().lower(): str(c) for c in self.df.columns}
        for c in candidates:
            if c in mapping:
                return mapping[c]
        return None

    @staticmethod
    def _clean(value: Any) -> str:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return ""
        text = str(value).strip()
        return "" if text.lower() == "nan" else text

    @staticmethod
    def _parse_bool(value: Any) -> bool | None:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        v = str(value).strip().lower()
        if v in {"1", "true", "yes", "y", "correct", "accepted", "positive"}:
            return True
        if v in {"0", "false", "no", "n", "incorrect", "rejected", "negative"}:
            return False
        return None
