from __future__ import annotations

import time
from typing import Any

from .confidence import calculate_confidence
from .config import Settings
from .data_loader import DatasetLoader
from .executor import DuckDBExecutor
from .feedback import FeedbackStore
from .gemini_planner import GeminiPlanner
from .llm_planner import LLMPlanner
from .models import EngineOutput, ExecutionResult
from .validator import validate_plan_metadata, validate_sql
from .verifier import verify_result


class AnalyticsQueryEngine:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.bundle = DatasetLoader(settings.dataset_dir).load()
        self.feedback = FeedbackStore(
            self.bundle.feedback_path,
            enable_embeddings=settings.enable_feedback_embeddings,
            embedding_model=settings.embedding_model,
        )
        self.planner = (
            GeminiPlanner(settings.model)
            if settings.provider == "gemini"
            else LLMPlanner(settings.model)
        )
        self.executor = DuckDBExecutor(self.bundle.tables, max_rows=settings.max_result_rows)
        self.schema_context = {
            "tables": self.bundle.profiles,
            "relationship_hints": self.bundle.relationship_hints,
            "sql_dialect": "DuckDB",
        }
        self.allowed_tables = set(self.bundle.tables)
        self.table_columns = {
            name: {str(c) for c in df.columns} for name, df in self.bundle.tables.items()
        }
        self.valid_columns = {c for cols in self.table_columns.values() for c in cols}

    def answer(self, query: str) -> EngineOutput:
        started = time.perf_counter()
        feedback_examples = self.feedback.relevant_examples(query, limit=3)
        plan = self.planner.plan(
            query=query,
            schema_context=self.schema_context,
            data_dictionary=self.bundle.data_dictionary,
            feedback_examples=feedback_examples,
        )

        repaired = False
        errors: list[str] = []
        result: ExecutionResult | None = None
        attempts = 0

        for attempt in range(self.settings.max_repair_attempts + 1):
            attempts = attempt + 1
            try:
                validate_sql(plan.sql, self.allowed_tables)
                result = self.executor.execute(plan.sql)
                break
            except Exception as exc:
                errors.append(str(exc))
                if attempt >= self.settings.max_repair_attempts:
                    raise RuntimeError(
                        "Could not produce a valid executable query after repair attempts: "
                        + " | ".join(errors)
                    ) from exc
                repaired = True
                plan = self.planner.repair(
                    query=query,
                    previous=plan,
                    error=str(exc),
                    schema_context=self.schema_context,
                    data_dictionary=self.bundle.data_dictionary,
                    feedback_examples=feedback_examples,
                )

        assert result is not None
        metadata_warnings = validate_plan_metadata(
            plan, self.allowed_tables, self.table_columns
        )
        verification = verify_result(plan, result)
        confidence = calculate_confidence(
            plan=plan,
            result=result,
            valid_columns=self.valid_columns,
            feedback_examples=feedback_examples,
            repaired=repaired,
            metadata_warnings=metadata_warnings,
            verification=verification,
        )

        serialized_result = self._serialize_result(result)
        explanation = plan.explanation.strip()
        if repaired:
            explanation += " The initial SQL failed validation/execution and was repaired using the concrete error before the final run."
        if result.truncated:
            explanation += (
                f" Output is truncated to {self.settings.max_result_rows} displayed rows; "
                f"the SQL produced {result.row_count} rows."
            )

        latency_ms = round((time.perf_counter() - started) * 1000.0, 2)
        retrieval_methods = sorted({ex.retrieval_method for ex in feedback_examples})

        return EngineOutput(
            query=query,
            generated_logic=plan.sql,
            result=serialized_result,
            confidence_score=confidence.score,
            explanation=explanation,
            understood_as=plan.understanding,
            assumptions=plan.assumptions,
            metadata={
                "provider": self.settings.provider,
                "model": self.settings.model,
                "complexity": plan.complexity,
                "query_features": plan.query_features.to_dict(),
                "expected_output": plan.expected_output.to_dict(),
                "used_tables": plan.used_tables,
                "referenced_columns": plan.referenced_columns,
                "row_count": result.row_count,
                "repaired": repaired,
                "attempts": attempts,
                "latency_ms": latency_ms,
                "feedback_examples_used": len(feedback_examples),
                "feedback_retrieval": retrieval_methods,
                "confidence_breakdown": {
                    k: round(v, 3) for k, v in confidence.breakdown.items()
                },
                "confidence_reasons": confidence.reasons,
                "verification_warnings": verification.warnings,
            },
        )

    def answer_safe(self, query: str) -> EngineOutput:
        try:
            return self.answer(query)
        except Exception as exc:
            return EngineOutput(
                query=query,
                generated_logic="",
                result=None,
                confidence_score=0.0,
                explanation=f"The query could not be executed reliably: {exc}",
                understood_as="Unable to produce a validated executable interpretation.",
                assumptions=[],
                metadata={"provider": self.settings.provider, "model": self.settings.model, "error": str(exc)},
            )

    @staticmethod
    def _serialize_result(result: ExecutionResult) -> Any:
        if result.row_count == 1 and len(result.columns) == 1 and result.rows:
            return result.rows[0][result.columns[0]]
        return result.rows
