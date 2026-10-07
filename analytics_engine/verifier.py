from __future__ import annotations

from .models import ExecutionResult, QueryPlan, VerificationResult


def verify_result(plan: QueryPlan, result: ExecutionResult) -> VerificationResult:
    warnings: list[str] = []
    score = 1.0

    actual = {c.lower() for c in result.columns}
    expected = {c.lower() for c in plan.expected_output.columns if c.strip()}
    missing = expected - actual
    if missing:
        score -= min(0.25, 0.05 * len(missing))
        warnings.append("Expected output alias(es) not present: " + ", ".join(sorted(missing)))

    if result.row_count == 0:
        score -= 0.12
        warnings.append("Query executed successfully but returned zero rows.")

    features = plan.query_features
    if features.target_comparison and len({t.lower() for t in plan.used_tables}) < 2:
        score -= 0.20
        warnings.append("Target comparison was requested but planner metadata uses fewer than two tables.")

    if features.contribution:
        pct_cols = [
            c for c in result.columns
            if any(token in c.lower() for token in ("pct", "percent", "percentage", "share", "contribution"))
        ]
        if not pct_cols:
            score -= 0.10
            warnings.append("Contribution query has no clearly named percentage/share output column.")

    if features.ranking:
        rankish = any(
            any(token in c.lower() for token in ("rank", "row_number", "position"))
            for c in result.columns
        )
        if not rankish:
            score -= 0.03

    return VerificationResult(score=max(0.0, min(1.0, score)), warnings=warnings)
