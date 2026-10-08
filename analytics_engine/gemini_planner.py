from __future__ import annotations

import json
import os
from typing import Any

from google import genai
from google.genai import types

from .feedback import FeedbackExample
from .llm_planner import QUERY_PLAN_SCHEMA, SYSTEM_INSTRUCTIONS
from .models import QueryPlan


class GeminiPlanner:
    """Gemini-backed semantic planner using the same strict query-plan contract."""

    def __init__(self, model: str, client: genai.Client | None = None):
        self.model = model
        self.client = client

    def plan(
        self,
        query: str,
        schema_context: dict[str, Any],
        data_dictionary: Any,
        feedback_examples: list[FeedbackExample],
    ) -> QueryPlan:
        return self._call(
            self._build_payload(query, schema_context, data_dictionary, feedback_examples)
        )

    def repair(
        self,
        query: str,
        previous: QueryPlan,
        error: str,
        schema_context: dict[str, Any],
        data_dictionary: Any,
        feedback_examples: list[FeedbackExample],
    ) -> QueryPlan:
        payload = self._build_payload(
            query, schema_context, data_dictionary, feedback_examples
        )
        payload["repair_context"] = {
            "previous_sql": previous.sql,
            "previous_understanding": previous.understanding,
            "validator_or_execution_error": error,
            "instruction": (
                "Repair the SQL while preserving business intent. Change the interpretation "
                "only if the previous interpretation is unsupported by the supplied schema."
            ),
        }
        return self._call(payload)

    def _call(self, payload: dict[str, Any]) -> QueryPlan:
        if self.client is None:
            api_key = os.getenv("GEMINI_API_KEY", "").strip()
            if not api_key:
                raise RuntimeError(
                    "GEMINI_API_KEY is not configured. Add it to the local .env file."
                )
            self.client = genai.Client(api_key=api_key)

        response = self.client.models.generate_content(
            model=self.model,
            contents=json.dumps(payload, ensure_ascii=False, default=str),
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTIONS,
                temperature=0.1,
                response_mime_type="application/json",
                response_json_schema=QUERY_PLAN_SCHEMA,
            ),
        )

        text = (response.text or "").strip()
        if not text:
            raise RuntimeError("Gemini returned an empty structured response.")
        return QueryPlan.from_dict(json.loads(text))

    @staticmethod
    def _build_payload(
        query: str,
        schema_context: dict[str, Any],
        data_dictionary: Any,
        feedback_examples: list[FeedbackExample],
    ) -> dict[str, Any]:
        feedback = [
            {
                "past_query": ex.query,
                "corrected_logic": ex.corrected_logic,
                "feedback": ex.feedback,
                "is_positive": ex.is_positive,
                "similarity": round(ex.score, 3),
                "retrieval_method": ex.retrieval_method,
            }
            for ex in feedback_examples
        ]
        return {
            "task": "Translate the business question into grounded DuckDB SQL.",
            "business_question": query,
            "schema_context": schema_context,
            "data_dictionary": data_dictionary,
            "relevant_feedback_examples": feedback,
        }
