from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class QueryFeatures:
    aggregation: bool = False
    grouping: bool = False
    filtering: bool = False
    ranking: bool = False
    contribution: bool = False
    comparison: bool = False
    target_comparison: bool = False
    time_based: bool = False
    nested_logic: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "QueryFeatures":
        data = data or {}
        return cls(**{name: bool(data.get(name, False)) for name in cls.__dataclass_fields__})

    def to_dict(self) -> dict[str, bool]:
        return {name: bool(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass
class ExpectedOutput:
    grain: str = ""
    columns: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ExpectedOutput":
        data = data or {}
        return cls(
            grain=str(data.get("grain", "")).strip(),
            columns=[str(x) for x in data.get("columns", [])],
        )

    def to_dict(self) -> dict[str, Any]:
        return {"grain": self.grain, "columns": self.columns}


@dataclass
class QueryPlan:
    understanding: str
    sql: str
    used_tables: list[str] = field(default_factory=list)
    referenced_columns: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    explanation: str = ""
    semantic_confidence: float = 0.5
    complexity: str = "moderate"
    query_features: QueryFeatures = field(default_factory=QueryFeatures)
    expected_output: ExpectedOutput = field(default_factory=ExpectedOutput)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QueryPlan":
        return cls(
            understanding=str(data.get("understanding", "")).strip(),
            sql=str(data.get("sql", "")).strip(),
            used_tables=[str(x) for x in data.get("used_tables", [])],
            referenced_columns=[str(x) for x in data.get("referenced_columns", [])],
            assumptions=[str(x) for x in data.get("assumptions", [])],
            explanation=str(data.get("explanation", "")).strip(),
            semantic_confidence=float(data.get("semantic_confidence", 0.5)),
            complexity=str(data.get("complexity", "moderate")).strip().lower(),
            query_features=QueryFeatures.from_dict(data.get("query_features")),
            expected_output=ExpectedOutput.from_dict(data.get("expected_output")),
        )


@dataclass
class ExecutionResult:
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    truncated: bool = False


@dataclass
class VerificationResult:
    score: float
    warnings: list[str] = field(default_factory=list)


@dataclass
class ConfidenceResult:
    score: float
    breakdown: dict[str, float]
    reasons: list[str] = field(default_factory=list)


@dataclass
class EngineOutput:
    query: str
    generated_logic: str
    result: Any
    confidence_score: float
    explanation: str
    understood_as: str
    assumptions: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "generated_logic": self.generated_logic,
            "result": self.result,
            "confidence_score": round(float(self.confidence_score), 3),
            "explanation": self.explanation,
            "understood_as": self.understood_as,
            "assumptions": self.assumptions,
            "metadata": self.metadata,
        }
