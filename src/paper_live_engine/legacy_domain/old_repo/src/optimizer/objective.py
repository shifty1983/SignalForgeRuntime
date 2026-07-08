"""
Optimizer objective scoring.

This module converts Strategy Selection / Expected Value outputs into a
single optimizer-ready objective score.

The solver will later use this score to choose and weight candidates.
Hard portfolio constraints belong in constraints.py. This module only
handles preference scoring and soft penalties.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


Number = int | float


@dataclass(frozen=True)
class ObjectiveWeights:
    """
    Weights used to create the optimizer objective score.

    All positive weights reward desirable candidate traits.
    Penalties are handled separately through ObjectiveConfig.
    """

    expected_return: float = 0.30
    probability: float = 0.20
    risk_reward: float = 0.15
    confidence: float = 0.10
    liquidity: float = 0.10
    capital_efficiency: float = 0.10
    opportunity_score: float = 0.05

    def total_positive_weight(self) -> float:
        return sum(
            value
            for value in (
                self.expected_return,
                self.probability,
                self.risk_reward,
                self.confidence,
                self.liquidity,
                self.capital_efficiency,
                self.opportunity_score,
            )
            if value > 0
        )


@dataclass(frozen=True)
class GreekPenaltyConfig:
    """
    Soft Greek penalties.

    These do not replace hard Greek constraints. They simply make the
    objective prefer cleaner trades when two candidates are otherwise similar.
    """

    enabled: bool = True

    delta_penalty: float = 0.05
    gamma_penalty: float = 0.03
    theta_penalty: float = 0.02
    vega_penalty: float = 0.03

    delta_soft_cap: float = 1.00
    gamma_soft_cap: float = 0.20
    theta_soft_cap: float = 1.00
    vega_soft_cap: float = 1.00


@dataclass(frozen=True)
class ObjectiveConfig:
    """
    Full objective scoring configuration.
    """

    weights: ObjectiveWeights = field(default_factory=ObjectiveWeights)
    greek_penalties: GreekPenaltyConfig = field(default_factory=GreekPenaltyConfig)

    transaction_cost_penalty: float = 0.05
    max_expected_return_for_scaling: float = 0.25
    max_risk_reward_for_scaling: float = 5.0
    max_cost_for_scaling: float = 0.05


@dataclass(frozen=True)
class ObjectiveBreakdown:
    """
    Transparent scoring output for a single candidate.
    """

    objective_score: float
    expected_return_score: float
    probability_score: float
    risk_reward_score: float
    confidence_score: float
    liquidity_score: float
    capital_efficiency_score: float
    opportunity_score: float
    greek_penalty: float
    transaction_cost_penalty: float


class OptimizationObjective:
    """
    Scores candidates for portfolio optimization.

    Expected input is a mapping-like candidate produced by the Strategy
    Selection layer. The scorer is intentionally tolerant of multiple column
    names so upstream modules can evolve without breaking the optimizer.
    """

    def __init__(self, config: ObjectiveConfig | None = None) -> None:
        self.config = config or ObjectiveConfig()

    def score_candidate(self, candidate: Mapping[str, Any]) -> ObjectiveBreakdown:
        expected_return_score = self._expected_return_score(candidate)
        probability_score = self._probability_score(candidate)
        risk_reward_score = self._risk_reward_score(candidate)
        confidence_score = self._confidence_score(candidate)
        liquidity_score = self._liquidity_score(candidate)
        capital_efficiency_score = self._capital_efficiency_score(candidate)
        opportunity_score = self._opportunity_score(candidate)

        greek_penalty = self._greek_penalty(candidate)
        transaction_cost_penalty = self._transaction_cost_penalty(candidate)

        weights = self.config.weights
        total_weight = weights.total_positive_weight()

        if total_weight <= 0:
            raise ValueError("At least one positive objective weight is required.")

        weighted_score = (
            expected_return_score * weights.expected_return
            + probability_score * weights.probability
            + risk_reward_score * weights.risk_reward
            + confidence_score * weights.confidence
            + liquidity_score * weights.liquidity
            + capital_efficiency_score * weights.capital_efficiency
            + opportunity_score * weights.opportunity_score
        ) / total_weight

        objective_score = 100.0 * (
            weighted_score
            - greek_penalty
            - transaction_cost_penalty
        )

        return ObjectiveBreakdown(
            objective_score=round(objective_score, 6),
            expected_return_score=round(expected_return_score, 6),
            probability_score=round(probability_score, 6),
            risk_reward_score=round(risk_reward_score, 6),
            confidence_score=round(confidence_score, 6),
            liquidity_score=round(liquidity_score, 6),
            capital_efficiency_score=round(capital_efficiency_score, 6),
            opportunity_score=round(opportunity_score, 6),
            greek_penalty=round(greek_penalty, 6),
            transaction_cost_penalty=round(transaction_cost_penalty, 6),
        )

    def score_candidates(
        self,
        candidates: Iterable[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        scored: list[dict[str, Any]] = []

        for candidate in candidates:
            breakdown = self.score_candidate(candidate)
            row = dict(candidate)
            row["objective_score"] = breakdown.objective_score
            row["objective_breakdown"] = breakdown
            scored.append(row)

        return scored

    def rank_candidates(
        self,
        candidates: Iterable[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        scored = self.score_candidates(candidates)
        return sorted(scored, key=lambda row: row["objective_score"], reverse=True)

    def _expected_return_score(self, candidate: Mapping[str, Any]) -> float:
        value = _first_number(
            candidate,
            (
                "expected_return",
                "expected_return_pct",
                "ev_return",
                "ev_return_pct",
                "return_on_risk",
            ),
            default=0.0,
        )

        value = _percentage_to_decimal_if_needed(value)
        max_value = self.config.max_expected_return_for_scaling

        if max_value <= 0:
            raise ValueError("max_expected_return_for_scaling must be positive.")

        return _clamp(value / max_value, -1.0, 1.0)

    def _probability_score(self, candidate: Mapping[str, Any]) -> float:
        value = _first_number(
            candidate,
            (
                "probability",
                "probability_of_profit",
                "pop",
                "win_probability",
                "success_probability",
            ),
            default=0.0,
        )
        return _clamp_probability(value)

    def _risk_reward_score(self, candidate: Mapping[str, Any]) -> float:
        value = _first_number(
            candidate,
            (
                "risk_reward",
                "risk_reward_ratio",
                "reward_to_risk",
                "max_reward_to_max_loss",
            ),
            default=0.0,
        )

        max_value = self.config.max_risk_reward_for_scaling

        if max_value <= 0:
            raise ValueError("max_risk_reward_for_scaling must be positive.")

        return _clamp(value / max_value, 0.0, 1.0)

    def _confidence_score(self, candidate: Mapping[str, Any]) -> float:
        value = _first_number(
            candidate,
            (
                "confidence",
                "model_confidence",
                "signal_confidence",
                "selection_confidence",
            ),
            default=0.0,
        )
        return _clamp_probability(value)

    def _liquidity_score(self, candidate: Mapping[str, Any]) -> float:
        explicit_score = _first_number(
            candidate,
            (
                "liquidity_score",
                "option_liquidity_score",
                "market_liquidity_score",
            ),
            default=None,
        )

        if explicit_score is not None:
            return _clamp_probability(explicit_score)

        bid_ask_spread = _first_number(
            candidate,
            (
                "bid_ask_spread_pct",
                "spread_pct",
                "relative_spread",
            ),
            default=None,
        )

        if bid_ask_spread is not None:
            bid_ask_spread = _percentage_to_decimal_if_needed(bid_ask_spread)
            return _clamp(1.0 - bid_ask_spread / 0.10, 0.0, 1.0)

        volume = _first_number(candidate, ("volume", "option_volume"), default=0.0)
        open_interest = _first_number(candidate, ("open_interest", "oi"), default=0.0)

        volume_score = _clamp(volume / 1_000.0, 0.0, 1.0)
        oi_score = _clamp(open_interest / 5_000.0, 0.0, 1.0)

        return (volume_score + oi_score) / 2.0

    def _capital_efficiency_score(self, candidate: Mapping[str, Any]) -> float:
        value = _first_number(
            candidate,
            (
                "capital_efficiency",
                "return_on_capital",
                "return_on_margin",
                "return_on_risk",
            ),
            default=None,
        )

        if value is not None:
            value = _percentage_to_decimal_if_needed(value)
            return _clamp(value / self.config.max_expected_return_for_scaling, -1.0, 1.0)

        max_profit = _first_number(candidate, ("max_profit", "max_reward"), default=None)
        max_loss = _first_number(candidate, ("max_loss", "max_risk"), default=None)

        if max_profit is not None and max_loss not in (None, 0):
            return _clamp(abs(max_profit) / abs(max_loss) / self.config.max_risk_reward_for_scaling, 0.0, 1.0)

        return 0.0

    def _opportunity_score(self, candidate: Mapping[str, Any]) -> float:
        value = _first_number(
            candidate,
            (
                "opportunity_score",
                "selection_score",
                "strategy_score",
                "candidate_score",
            ),
            default=0.0,
        )
        return _clamp_probability(value)

    def _greek_penalty(self, candidate: Mapping[str, Any]) -> float:
        penalties = self.config.greek_penalties

        if not penalties.enabled:
            return 0.0

        delta = abs(_first_number(candidate, ("delta", "net_delta"), default=0.0))
        gamma = abs(_first_number(candidate, ("gamma", "net_gamma"), default=0.0))
        theta = abs(_first_number(candidate, ("theta", "net_theta"), default=0.0))
        vega = abs(_first_number(candidate, ("vega", "net_vega"), default=0.0))

        return (
            _safe_scaled(delta, penalties.delta_soft_cap) * penalties.delta_penalty
            + _safe_scaled(gamma, penalties.gamma_soft_cap) * penalties.gamma_penalty
            + _safe_scaled(theta, penalties.theta_soft_cap) * penalties.theta_penalty
            + _safe_scaled(vega, penalties.vega_soft_cap) * penalties.vega_penalty
        )

    def _transaction_cost_penalty(self, candidate: Mapping[str, Any]) -> float:
        cost = _first_number(
            candidate,
            (
                "transaction_cost",
                "estimated_cost",
                "cost_pct",
                "slippage_pct",
            ),
            default=0.0,
        )

        cost = _percentage_to_decimal_if_needed(cost)
        max_cost = self.config.max_cost_for_scaling

        if max_cost <= 0:
            raise ValueError("max_cost_for_scaling must be positive.")

        return _clamp(cost / max_cost, 0.0, 1.0) * self.config.transaction_cost_penalty


def calculate_objective_score(
    candidate: Mapping[str, Any],
    config: ObjectiveConfig | None = None,
) -> float:
    """
    Convenience function for scoring a single candidate.
    """

    return OptimizationObjective(config=config).score_candidate(candidate).objective_score


def rank_by_objective(
    candidates: Iterable[Mapping[str, Any]],
    config: ObjectiveConfig | None = None,
) -> list[dict[str, Any]]:
    """
    Convenience function for scoring and ranking candidates.
    """

    return OptimizationObjective(config=config).rank_candidates(candidates)


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


def _percentage_to_decimal_if_needed(value: float) -> float:
    if abs(value) > 1.0:
        return value / 100.0

    return value


def _clamp_probability(value: float) -> float:
    value = _percentage_to_decimal_if_needed(value)
    return _clamp(value, 0.0, 1.0)


def _safe_scaled(value: float, soft_cap: float) -> float:
    if soft_cap <= 0:
        return 0.0

    return _clamp(value / soft_cap, 0.0, 1.0)


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))
