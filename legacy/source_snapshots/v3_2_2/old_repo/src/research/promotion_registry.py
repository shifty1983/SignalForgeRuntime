from __future__ import annotations

from dataclasses import dataclass, field

from src.research.model_candidate import ModelCandidate


@dataclass
class PromotionCandidateRegistry:
    """Registry for model promotion candidates."""

    candidates: dict[str, ModelCandidate] = field(default_factory=dict)

    def register(self, candidate: ModelCandidate) -> None:
        if candidate.model_id in self.candidates:
            raise ValueError(f"Duplicate model candidate id: {candidate.model_id}")

        self.candidates[candidate.model_id] = candidate

    def get(self, model_id: str) -> ModelCandidate:
        try:
            return self.candidates[model_id]
        except KeyError as exc:
            raise KeyError(f"Unknown model candidate id: {model_id}") from exc

    def list_candidates(self) -> tuple[ModelCandidate, ...]:
        return tuple(self.candidates.values())

    def candidate_ids(self) -> tuple[str, ...]:
        return tuple(self.candidates.keys())

    def clear(self) -> None:
        self.candidates.clear()
