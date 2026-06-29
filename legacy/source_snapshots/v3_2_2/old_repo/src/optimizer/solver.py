"""
Optimizer solver.

This module connects:
- objective.py      -> scoring and ranking candidates
- constraints.py   -> hard portfolio guardrails
- portfolio.py     -> standardized optimized portfolio output

The solver uses a transparent greedy selection process:
1. score / rank candidates
2. assign candidate weights
3. reject candidates that fail hard constraints
4. add candidates while the full portfolio remains valid
5. return an OptimizedPortfolio plus rejection diagnostics
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Iterable, Mapping

from src.optimizer.constraints import (
    ConstraintCheckResult,
    PortfolioConstraintChecker,
    PortfolioConstraints,
)
from src.optimizer.objective import OptimizationObjective, ObjectiveConfig
from src.optimizer.portfolio import OptimizedPortfolio


@dataclass(frozen=True)
class SolverConfig:
    """
    Solver behavior configuration.
    """

    target_total_weight: float = 1.00
    default_position_weight: float | None = None

    weighting_method: str = "equal"
    use_existing_weights: bool = True

    rescore_candidates: bool = True
    min_objective_score: float | None = None

    max_selected_candidates: int | None = None
    portfolio_name: str = "optimized_portfolio"


@dataclass(frozen=True)
class RejectedCandidate:
    """
    Candidate rejected by the optimizer.
    """

    symbol: str | None
    reason: str
    objective_score: float | None = None
    violations: tuple[str, ...] = field(default_factory=tuple)
    candidate: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "reason": self.reason,
            "objective_score": self.objective_score,
            "violations": list(self.violations),
            "candidate": _json_safe_dict(self.candidate),
        }


@dataclass(frozen=True)
class OptimizationSolveResult:
    """
    Full solver result.
    """

    portfolio: OptimizedPortfolio
    scored_candidates: tuple[dict[str, Any], ...]
    selected_candidates: tuple[dict[str, Any], ...]
    rejected_candidates: tuple[RejectedCandidate, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def candidate_count(self) -> int:
        return len(self.scored_candidates)

    @property
    def selected_count(self) -> int:
        return len(self.selected_candidates)

    @property
    def rejected_count(self) -> int:
        return len(self.rejected_candidates)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_count": self.candidate_count,
            "selected_count": self.selected_count,
            "rejected_count": self.rejected_count,
            "portfolio": self.portfolio.to_dict(),
            "scored_candidates": [
                _json_safe_dict(candidate)
                for candidate in self.scored_candidates
            ],
            "selected_candidates": [
                _json_safe_dict(candidate)
                for candidate in self.selected_candidates
            ],
            "rejected_candidates": [
                rejected.to_dict()
                for rejected in self.rejected_candidates
            ],
            "metadata": dict(self.metadata),
        }


class OptimizerSolver:
    """
    Greedy optimizer solver.

    This is intentionally deterministic and explainable. It does not attempt
    quadratic optimization yet. That can be added later behind the same output
    contract once the full system is stable.
    """

    def __init__(
        self,
        objective: OptimizationObjective | None = None,
        constraints: PortfolioConstraints | None = None,
        config: SolverConfig | None = None,
    ) -> None:
        self.objective = objective or OptimizationObjective()
        self.constraint_checker = PortfolioConstraintChecker(constraints)
        self.constraints = self.constraint_checker.constraints
        self.config = config or SolverConfig()

        self._validate_config()

    def solve(
        self,
        candidates: Iterable[Mapping[str, Any]],
    ) -> OptimizationSolveResult:
        ranked_candidates = self._score_and_rank(candidates)

        selected: list[dict[str, Any]] = []
        rejected: list[RejectedCandidate] = []

        positive_score_total = sum(
            max(0.0, _first_number(candidate, ("objective_score",), default=0.0))
            for candidate in ranked_candidates
        )

        selection_limit = self._selection_limit(len(ranked_candidates))

        for candidate in ranked_candidates:
            if len(selected) >= selection_limit:
                break

            candidate_row = dict(candidate)
            objective_score = _first_number(
                candidate_row,
                ("objective_score",),
                default=0.0,
            )

            if (
                self.config.min_objective_score is not None
                and objective_score < self.config.min_objective_score
            ):
                rejected.append(
                    RejectedCandidate(
                        symbol=_first_string(candidate_row, ("symbol", "ticker", "underlying")),
                        reason="min_objective_score",
                        objective_score=objective_score,
                        candidate=_json_safe_dict(candidate_row),
                    )
                )
                continue

            candidate_row["weight"] = self._determine_weight(
                candidate=candidate_row,
                positive_score_total=positive_score_total,
                candidate_count=max(1, len(ranked_candidates)),
                selection_limit=selection_limit,
            )

            candidate_check = self.constraint_checker.check_candidate(candidate_row)

            if not candidate_check.passed:
                rejected.append(
                    self._rejection(
                        candidate=candidate_row,
                        reason="candidate_constraints",
                        check=candidate_check,
                    )
                )
                continue

            trial_positions = [*selected, candidate_row]
            portfolio_check = self.constraint_checker.check_portfolio(trial_positions)

            if not portfolio_check.passed:
                rejected.append(
                    self._rejection(
                        candidate=candidate_row,
                        reason="portfolio_constraints",
                        check=portfolio_check,
                    )
                )
                continue

            selected.append(_json_safe_dict(candidate_row))

        portfolio = OptimizedPortfolio.from_candidates(
            candidates=selected,
            name=self.config.portfolio_name,
            metadata={
                "solver": "greedy",
                "weighting_method": self.config.weighting_method,
                "target_total_weight": self.config.target_total_weight,
            },
        )

        return OptimizationSolveResult(
            portfolio=portfolio,
            scored_candidates=tuple(_json_safe_dict(candidate) for candidate in ranked_candidates),
            selected_candidates=tuple(selected),
            rejected_candidates=tuple(rejected),
            metadata={
                "solver": "greedy",
                "selection_limit": selection_limit,
                "rescore_candidates": self.config.rescore_candidates,
            },
        )

    def _score_and_rank(
        self,
        candidates: Iterable[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        rows = [dict(candidate) for candidate in candidates]

        if self.config.rescore_candidates:
            return self.objective.rank_candidates(rows)

        for row in rows:
            if "objective_score" not in row:
                row["objective_score"] = self.objective.score_candidate(row).objective_score

        return sorted(
            rows,
            key=lambda row: _first_number(row, ("objective_score",), default=0.0),
            reverse=True,
        )

    def _determine_weight(
        self,
        candidate: Mapping[str, Any],
        positive_score_total: float,
        candidate_count: int,
        selection_limit: int,
    ) -> float:
        existing_weight = _position_weight(candidate)

        if self.config.use_existing_weights and existing_weight is not None:
            return self._clamp_position_weight(existing_weight)

        method = self.config.weighting_method.lower().strip()

        if method == "provided":
            if existing_weight is not None:
                return self._clamp_position_weight(existing_weight)

            return self._clamp_position_weight(self._equal_weight(selection_limit))

        if method == "equal":
            return self._clamp_position_weight(self._equal_weight(selection_limit))

        if method == "objective":
            objective_score = max(
                0.0,
                _first_number(candidate, ("objective_score",), default=0.0),
            )

            if positive_score_total <= 0:
                return self._clamp_position_weight(self._equal_weight(selection_limit))

            weight = (
                objective_score
                / positive_score_total
                * self.config.target_total_weight
            )
            return self._clamp_position_weight(weight)

        raise ValueError(
            "weighting_method must be one of: 'equal', 'provided', or 'objective'."
        )

    def _equal_weight(self, selection_limit: int) -> float:
        if self.config.default_position_weight is not None:
            return self.config.default_position_weight

        if selection_limit <= 0:
            return 0.0

        return self.config.target_total_weight / selection_limit

    def _clamp_position_weight(self, weight: float) -> float:
        min_weight = self.constraints.min_position_weight
        max_weight = self.constraints.max_position_weight

        if (
            min_weight is not None
            and max_weight is not None
            and min_weight > max_weight
        ):
            raise ValueError("min_position_weight cannot exceed max_position_weight.")

        adjusted = weight

        if max_weight is not None:
            adjusted = min(adjusted, max_weight)

        if min_weight is not None:
            adjusted = max(adjusted, min_weight)

        return adjusted

    def _selection_limit(self, candidate_count: int) -> int:
        limits: list[int] = [candidate_count]

        if self.constraints.max_positions is not None:
            limits.append(self.constraints.max_positions)

        if self.config.max_selected_candidates is not None:
            limits.append(self.config.max_selected_candidates)

        return max(0, min(limits))

    def _rejection(
        self,
        candidate: Mapping[str, Any],
        reason: str,
        check: ConstraintCheckResult,
    ) -> RejectedCandidate:
        return RejectedCandidate(
            symbol=_first_string(candidate, ("symbol", "ticker", "underlying")),
            reason=reason,
            objective_score=_first_number(candidate, ("objective_score",), default=None),
            violations=tuple(check.messages()),
            candidate=_json_safe_dict(candidate),
        )

    def _validate_config(self) -> None:
        if self.config.target_total_weight < 0:
            raise ValueError("target_total_weight cannot be negative.")

        if (
            self.config.default_position_weight is not None
            and self.config.default_position_weight < 0
        ):
            raise ValueError("default_position_weight cannot be negative.")

        if (
            self.config.max_selected_candidates is not None
            and self.config.max_selected_candidates < 0
        ):
            raise ValueError("max_selected_candidates cannot be negative.")


def solve_optimized_portfolio(
    candidates: Iterable[Mapping[str, Any]],
    objective_config: ObjectiveConfig | None = None,
    constraints: PortfolioConstraints | None = None,
    solver_config: SolverConfig | None = None,
) -> OptimizationSolveResult:
    """
    Convenience function for solving an optimized portfolio.
    """

    objective = OptimizationObjective(config=objective_config)

    return OptimizerSolver(
        objective=objective,
        constraints=constraints,
        config=solver_config,
    ).solve(candidates)


def _position_weight(candidate: Mapping[str, Any]) -> float | None:
    value = _first_number(
        candidate,
        (
            "weight",
            "target_weight",
            "allocation",
            "allocation_pct",
            "position_weight",
        ),
        default=None,
    )

    if value is None:
        return None

    return _percentage_to_decimal_if_needed(value)


def _first_number(
    values: Mapping[str, Any],
    names: tuple[str, ...],
    default: float | None,
) -> float | None:
    for name in names:
        value = values.get(name)

        if value is None:
            continue

        if isinstance(value, bool):
            continue

        if isinstance(value, (int, float)):
            return float(value)

        try:
            return float(value)
        except (TypeError, ValueError):
            continue

    return default


def _first_string(
    values: Mapping[str, Any],
    names: tuple[str, ...],
) -> str | None:
    for name in names:
        value = values.get(name)

        if value is None:
            continue

        text = str(value).strip()

        if text:
            return text

    return None


def _percentage_to_decimal_if_needed(value: float) -> float:
    if abs(value) > 1.0:
        return value / 100.0

    return value


def _json_safe_dict(values: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: _json_safe_value(value)
        for key, value in values.items()
    }


def _json_safe_value(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)

    if isinstance(value, Mapping):
        return _json_safe_dict(value)

    if isinstance(value, tuple):
        return [_json_safe_value(item) for item in value]

    if isinstance(value, list):
        return [_json_safe_value(item) for item in value]

    return value
