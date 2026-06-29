from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OpportunityMetrics:
    expected_return: float
    probability_of_profit: float
    reward_risk: float
    implied_volatility: float
    liquidity_score: float
    annualized_return: float | None = None
    risk_score: float | None = None
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    name: str | None = None


@dataclass(frozen=True)
class ScoringWeights:
    expected_return_weight: float = 0.30
    probability_weight: float = 0.20
    reward_risk_weight: float = 0.15
    liquidity_weight: float = 0.10
    iv_weight: float = 0.10
    annualized_return_weight: float = 0.00
    risk_score_weight: float = 0.00
    delta_weight: float = 0.05
    gamma_weight: float = 0.03
    theta_weight: float = 0.04
    vega_weight: float = 0.03


@dataclass(frozen=True)
class ComponentScores:
    expected_return_score: float
    probability_score: float
    reward_risk_score: float
    liquidity_score: float
    implied_volatility_score: float
    annualized_return_score: float
    risk_score: float
    delta_score: float
    gamma_score: float
    theta_score: float
    vega_score: float


@dataclass(frozen=True)
class OpportunityScoreResult:
    score: float
    metrics: OpportunityMetrics
    components: ComponentScores
    weights: ScoringWeights


def normalize(
    value: float,
    min_value: float,
    max_value: float,
) -> float:
    """
    Normalize value to 0-1 range.
    """
    if max_value <= min_value:
        return 0.0

    return max(0.0, min(1.0, (value - min_value) / (max_value - min_value)))


def inverse_normalize(
    value: float,
    min_value: float,
    max_value: float,
) -> float:
    """
    Normalize value where lower is better.
    """
    return 1.0 - normalize(
        value=value,
        min_value=min_value,
        max_value=max_value,
    )


def validate_weights(weights: ScoringWeights) -> None:
    """
    Validate all weights are non-negative.
    """
    values = [
        weights.expected_return_weight,
        weights.probability_weight,
        weights.reward_risk_weight,
        weights.liquidity_weight,
        weights.iv_weight,
        weights.annualized_return_weight,
        weights.risk_score_weight,
        weights.delta_weight,
        weights.gamma_weight,
        weights.theta_weight,
        weights.vega_weight,
    ]

    if any(value < 0 for value in values):
        raise ValueError("Scoring weights cannot be negative.")


def total_weight(weights: ScoringWeights) -> float:
    """
    Sum active scoring weights.
    """
    validate_weights(weights)

    return (
        weights.expected_return_weight
        + weights.probability_weight
        + weights.reward_risk_weight
        + weights.liquidity_weight
        + weights.iv_weight
        + weights.annualized_return_weight
        + weights.risk_score_weight
        + weights.delta_weight
        + weights.gamma_weight
        + weights.theta_weight
        + weights.vega_weight
    )


def score_expected_return(
    expected_return: float,
    min_return: float = -0.50,
    max_return: float = 0.50,
) -> float:
    return normalize(
        value=expected_return,
        min_value=min_return,
        max_value=max_return,
    )


def score_probability_of_profit(
    probability_of_profit: float,
) -> float:
    return normalize(
        value=probability_of_profit,
        min_value=0.0,
        max_value=1.0,
    )


def score_reward_risk(
    reward_risk: float,
    max_reward_risk: float = 10.0,
) -> float:
    return normalize(
        value=reward_risk,
        min_value=0.0,
        max_value=max_reward_risk,
    )


def score_liquidity(
    liquidity_score: float,
) -> float:
    return normalize(
        value=liquidity_score,
        min_value=0.0,
        max_value=1.0,
    )


def score_implied_volatility(
    implied_volatility: float,
    min_iv: float = 0.0,
    max_iv: float = 1.0,
) -> float:
    """
    Lower implied volatility receives a higher score.
    """
    return inverse_normalize(
        value=implied_volatility,
        min_value=min_iv,
        max_value=max_iv,
    )


def score_risk(
    risk_score: float | None,
) -> float:
    """
    Lower risk receives a higher score.

    Missing risk_score is treated neutrally.
    """
    if risk_score is None:
        return 0.50

    return inverse_normalize(
        value=risk_score,
        min_value=0.0,
        max_value=1.0,
    )


def score_delta(
    delta: float | None,
    target_abs_delta: float = 0.50,
    max_distance: float = 0.50,
) -> float:
    """
    Score delta exposure.

    Higher score means the absolute delta is closer to the target.
    Default target is 0.50, useful for balanced directional option exposure.
    """
    if delta is None:
        return 0.50

    distance = abs(abs(delta) - target_abs_delta)

    return inverse_normalize(
        value=distance,
        min_value=0.0,
        max_value=max_distance,
    )


def score_gamma(
    gamma: float | None,
    max_abs_gamma: float = 0.10,
) -> float:
    """
    Score gamma exposure.

    Lower absolute gamma receives a higher score because extreme gamma
    can create unstable PnL and sizing behavior.
    """
    if gamma is None:
        return 0.50

    return inverse_normalize(
        value=abs(gamma),
        min_value=0.0,
        max_value=max_abs_gamma,
    )


def score_theta(
    theta: float | None,
    min_theta: float = -1.0,
    max_theta: float = 1.0,
) -> float:
    """
    Score theta exposure.

    Higher theta is better. Positive theta strategies benefit from time decay.
    """
    if theta is None:
        return 0.50

    return normalize(
        value=theta,
        min_value=min_theta,
        max_value=max_theta,
    )


def score_vega(
    vega: float | None,
    max_abs_vega: float = 1.0,
) -> float:
    """
    Score vega exposure.

    Lower absolute vega receives a higher score by default because high
    volatility sensitivity can make EV less stable.
    """
    if vega is None:
        return 0.50

    return inverse_normalize(
        value=abs(vega),
        min_value=0.0,
        max_value=max_abs_vega,
    )


def component_scores(
    metrics: OpportunityMetrics,
) -> ComponentScores:
    """
    Calculate normalized component scores.
    """
    annualized_value = (
        metrics.annualized_return
        if metrics.annualized_return is not None
        else metrics.expected_return
    )

    return ComponentScores(
        expected_return_score=score_expected_return(metrics.expected_return),
        probability_score=score_probability_of_profit(metrics.probability_of_profit),
        reward_risk_score=score_reward_risk(metrics.reward_risk),
        liquidity_score=score_liquidity(metrics.liquidity_score),
        implied_volatility_score=score_implied_volatility(metrics.implied_volatility),
        annualized_return_score=score_expected_return(annualized_value),
        risk_score=score_risk(metrics.risk_score),
        delta_score=score_delta(metrics.delta),
        gamma_score=score_gamma(metrics.gamma),
        theta_score=score_theta(metrics.theta),
        vega_score=score_vega(metrics.vega),
    )


def weighted_score(
    components: ComponentScores,
    weights: ScoringWeights,
) -> float:
    """
    Combine component scores into one weighted score.
    """
    weight_sum = total_weight(weights)

    if weight_sum <= 0:
        return 0.0

    raw_score = (
        components.expected_return_score * weights.expected_return_weight
        + components.probability_score * weights.probability_weight
        + components.reward_risk_score * weights.reward_risk_weight
        + components.liquidity_score * weights.liquidity_weight
        + components.implied_volatility_score * weights.iv_weight
        + components.annualized_return_score * weights.annualized_return_weight
        + components.risk_score * weights.risk_score_weight
        + components.delta_score * weights.delta_weight
        + components.gamma_score * weights.gamma_weight
        + components.theta_score * weights.theta_weight
        + components.vega_score * weights.vega_weight
    )

    return raw_score / weight_sum


def score_opportunity(
    metrics: OpportunityMetrics,
    weights: ScoringWeights | None = None,
) -> OpportunityScoreResult:
    """
    Full opportunity score result with component breakdown.
    """
    active_weights = weights or ScoringWeights()
    components = component_scores(metrics)

    score = weighted_score(
        components=components,
        weights=active_weights,
    )

    return OpportunityScoreResult(
        score=round(score, 4),
        metrics=metrics,
        components=components,
        weights=active_weights,
    )


def opportunity_score(
    metrics: OpportunityMetrics,
    expected_return_weight: float = 0.30,
    probability_weight: float = 0.20,
    reward_risk_weight: float = 0.15,
    liquidity_weight: float = 0.10,
    iv_weight: float = 0.10,
    delta_weight: float = 0.05,
    gamma_weight: float = 0.03,
    theta_weight: float = 0.04,
    vega_weight: float = 0.03,
) -> float:
    """
    Composite opportunity ranking score.

    Higher score = more attractive opportunity.
    """
    weights = ScoringWeights(
        expected_return_weight=expected_return_weight,
        probability_weight=probability_weight,
        reward_risk_weight=reward_risk_weight,
        liquidity_weight=liquidity_weight,
        iv_weight=iv_weight,
        delta_weight=delta_weight,
        gamma_weight=gamma_weight,
        theta_weight=theta_weight,
        vega_weight=vega_weight,
    )

    return score_opportunity(
        metrics=metrics,
        weights=weights,
    ).score


def rank_opportunities(
    opportunities: list[OpportunityMetrics],
    weights: ScoringWeights | None = None,
    descending: bool = True,
) -> list[OpportunityScoreResult]:
    """
    Rank opportunities by composite opportunity score.
    """
    results = [
        score_opportunity(
            metrics=metrics,
            weights=weights,
        )
        for metrics in opportunities
    ]

    return sorted(
        results,
        key=lambda result: result.score,
        reverse=descending,
    )


def passes_minimum_thresholds(
    metrics: OpportunityMetrics,
    min_expected_return: float = 0.0,
    min_probability_of_profit: float = 0.50,
    min_reward_risk: float = 1.0,
    min_liquidity_score: float = 0.50,
    max_implied_volatility: float = 1.0,
    max_abs_delta: float | None = None,
    max_abs_gamma: float | None = None,
    min_theta: float | None = None,
    max_abs_vega: float | None = None,
) -> bool:
    """
    Basic gate before ranking an opportunity.

    Greek thresholds are optional. They are only applied when provided.
    """
    if metrics.expected_return < min_expected_return:
        return False

    if metrics.probability_of_profit < min_probability_of_profit:
        return False

    if metrics.reward_risk < min_reward_risk:
        return False

    if metrics.liquidity_score < min_liquidity_score:
        return False

    if metrics.implied_volatility > max_implied_volatility:
        return False

    if max_abs_delta is not None and metrics.delta is not None:
        if abs(metrics.delta) > max_abs_delta:
            return False

    if max_abs_gamma is not None and metrics.gamma is not None:
        if abs(metrics.gamma) > max_abs_gamma:
            return False

    if min_theta is not None and metrics.theta is not None:
        if metrics.theta < min_theta:
            return False

    if max_abs_vega is not None and metrics.vega is not None:
        if abs(metrics.vega) > max_abs_vega:
            return False

    return True


def filter_opportunities(
    opportunities: list[OpportunityMetrics],
    min_expected_return: float = 0.0,
    min_probability_of_profit: float = 0.50,
    min_reward_risk: float = 1.0,
    min_liquidity_score: float = 0.50,
    max_implied_volatility: float = 1.0,
    max_abs_delta: float | None = None,
    max_abs_gamma: float | None = None,
    min_theta: float | None = None,
    max_abs_vega: float | None = None,
) -> list[OpportunityMetrics]:
    """
    Filter opportunities using minimum quality thresholds.
    """
    return [
        metrics
        for metrics in opportunities
        if passes_minimum_thresholds(
            metrics=metrics,
            min_expected_return=min_expected_return,
            min_probability_of_profit=min_probability_of_profit,
            min_reward_risk=min_reward_risk,
            min_liquidity_score=min_liquidity_score,
            max_implied_volatility=max_implied_volatility,
            max_abs_delta=max_abs_delta,
            max_abs_gamma=max_abs_gamma,
            min_theta=min_theta,
            max_abs_vega=max_abs_vega,
        )
    ]
