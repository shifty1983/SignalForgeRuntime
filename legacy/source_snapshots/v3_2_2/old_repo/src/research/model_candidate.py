from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ModelCandidate:
    """A named research model candidate that can be evaluated for promotion."""

    model_id: str
    model_name: str
    factor_names: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.model_id:
            raise ValueError("model_id is required")

        if not self.model_name:
            raise ValueError("model_name is required")

        if not self.factor_names:
            raise ValueError("factor_names must contain at least one factor")

        normalized_factors = tuple(self.factor_names)
        object.__setattr__(self, "factor_names", normalized_factors)


@dataclass(frozen=True)
class ModelCandidateEvaluation:
    """Evaluation result for one promotion candidate."""

    candidate: ModelCandidate
    quality_report: Any
    promoted: bool
    failure_reasons: tuple[str, ...] = ()
    quality_score: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "failure_reasons", tuple(self.failure_reasons))

        if self.promoted and self.failure_reasons:
            raise ValueError("promoted evaluations cannot have failure_reasons")
