from __future__ import annotations

from .feedback import FeedbackExample
from .models import ConfidenceResult, ExecutionResult, QueryPlan, VerificationResult


def _clip(x: float) -> float:
    return max(0.0, min(1.0, x))


def _feedback_score(examples: list[FeedbackExample]) -> float:
    if not examples:
        return 0.5
    ex = examples[0]
    if ex.is_positive is True:
        return _clip(0.5 + 0.5 * ex.score)
    if ex.is_positive is False:
        return _clip(0.5 - 0.5 * ex.score)
    return 0.5


def calculate_confidence(
    plan: QueryPlan,
    result: ExecutionResult,
    valid_columns: set[str],
    feedback_examples: list[FeedbackExample],
    repaired: bool,
    metadata_warnings: list[str],
    verification: VerificationResult,
) -> ConfidenceResult:
    semantic = _clip(plan.semantic_confidence)

    refs = [c.split(".")[-1].strip('"`[]').lower() for c in plan.referenced_columns]
    valid = {c.lower() for c in valid_columns}
    schema_grounding = 1.0 if not refs else sum(c in valid for c in refs) / len(refs)
    if metadata_warnings:
        schema_grounding = max(0.0, schema_grounding - 0.08 * len(metadata_warnings))

    assumption_score = max(0.45, 1.0 - 0.12 * len(plan.assumptions))
    execution_score = 0.88 if result.row_count == 0 else 1.0

    breakdown = {
        "semantic_interpretation": semantic,
        "schema_grounding": _clip(schema_grounding),
        "assumption_clarity": _clip(assumption_score),
        "execution": execution_score,
        "result_verification": verification.score,
        "feedback_evidence": _feedback_score(feedback_examples),
    }

    score = (
        0.34 * breakdown["semantic_interpretation"]
        + 0.22 * breakdown["schema_grounding"]
        + 0.10 * breakdown["assumption_clarity"]
        + 0.14 * breakdown["execution"]
        + 0.12 * breakdown["result_verification"]
        + 0.08 * breakdown["feedback_evidence"]
    )

    reasons: list[str] = []
    if plan.assumptions:
        reasons.append(f"{len(plan.assumptions)} explicit assumption(s) reduced confidence.")
    if repaired:
        score -= 0.06
        reasons.append("Initial SQL required an automatic repair.")
    if result.row_count == 0:
        reasons.append("Execution returned zero rows.")
    reasons.extend(metadata_warnings)
    reasons.extend(verification.warnings)

    return ConfidenceResult(score=_clip(score), breakdown=breakdown, reasons=reasons)
