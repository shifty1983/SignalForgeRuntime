from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DecisionReport:
    decision_id: str
    operation_type: str
    candidate_count: int
    selected_count: int
    selected_symbols: tuple[str, ...]
    selection_score: float
    ranking_available: bool
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "operation_type": self.operation_type,
            "candidate_count": self.candidate_count,
            "selected_count": self.selected_count,
            "selected_symbols": list(self.selected_symbols),
            "selection_score": self.selection_score,
            "ranking_available": self.ranking_available,
            "metadata": self.metadata,
        }


def build_decision_report(
    *,
    decision_id: str,
    ranked_candidates: list[dict[str, Any]],
    selected_candidates: list[dict[str, Any]],
    metadata: dict[str, Any] | None = None,
) -> DecisionReport:
    if not ranked_candidates:
        raise ValueError("ranked_candidates_required")

    if not selected_candidates:
        raise ValueError("selected_candidates_required")

    selected_symbols = tuple(
        str(candidate["symbol"]) for candidate in selected_candidates
    )

    scores = [
        float(candidate.get("selection_score", candidate.get("quality_score", 0.0)))
        for candidate in selected_candidates
    ]

    selection_score = round(sum(scores) / len(scores), 6)

    return DecisionReport(
        decision_id=decision_id,
        operation_type="decision_dry_run",
        candidate_count=len(ranked_candidates),
        selected_count=len(selected_candidates),
        selected_symbols=selected_symbols,
        selection_score=selection_score,
        ranking_available=True,
        metadata=metadata or {},
    )
