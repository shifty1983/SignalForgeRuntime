from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import polars as pl

from src.signalforge.engines.strategy_selection.candidates import REQUIRED_CANDIDATE_COLUMNS


@dataclass(frozen=True)
class CandidateFilterConfig:
    min_score: float | None = None
    max_score: float | None = None
    min_probability: float | None = None
    max_probability: float | None = None
    max_loss: float | None = None
    min_expected_return: float | None = None
    min_expected_value: float | None = None
    min_confidence: float | None = None
    min_risk_reward: float | None = None
    min_liquidity_score: float | None = None
    max_bid_ask_spread_pct: float | None = None
    min_volume: float | None = None
    min_open_interest: float | None = None
    min_days_to_expiration: int | None = None
    max_days_to_expiration: int | None = None
    allowed_strategies: Sequence[str] | None = None
    allowed_regimes: Sequence[str] | None = None
    allowed_asset_classes: Sequence[str] | None = None
    allowed_directions: Sequence[str] | None = None
    require_selection_eligible: bool = False
    
    min_delta: float | None = None
    max_delta: float | None = None
    min_gamma: float | None = None
    max_gamma: float | None = None
    min_theta: float | None = None
    max_theta: float | None = None
    min_vega: float | None = None
    max_vega: float | None = None
    min_rho: float | None = None
    max_rho: float | None = None

    min_net_delta: float | None = None
    max_net_delta: float | None = None
    min_net_gamma: float | None = None
    max_net_gamma: float | None = None
    min_net_theta: float | None = None
    max_net_theta: float | None = None
    min_net_vega: float | None = None
    max_net_vega: float | None = None
    min_net_rho: float | None = None
    max_net_rho: float | None = None

    max_abs_delta: float | None = None
    max_abs_gamma: float | None = None
    max_abs_theta: float | None = None
    max_abs_vega: float | None = None
    max_abs_rho: float | None = None

    max_abs_net_delta: float | None = None
    max_abs_net_gamma: float | None = None
    max_abs_net_theta: float | None = None
    max_abs_net_vega: float | None = None
    max_abs_net_rho: float | None = None


def _validate_candidate_frame(df: pl.DataFrame) -> None:
    if not isinstance(df, pl.DataFrame):
        raise TypeError("Candidate data must be a Polars DataFrame.")

    missing = REQUIRED_CANDIDATE_COLUMNS - set(df.columns)

    if missing:
        raise ValueError(f"Missing required candidate columns: {sorted(missing)}")


def _require_column(
    df: pl.DataFrame,
    column: str,
    label: str,
) -> None:
    if column not in df.columns:
        raise ValueError(f"Missing {label} column: {column}")


def _validate_probability_threshold(value: float, name: str) -> None:
    if value < 0.0 or value > 1.0:
        raise ValueError(f"{name} must be between 0 and 1.")


def _normalize_label(value: str) -> str:
    return value.strip().replace("-", "_").replace(" ", "_").lower()


def _filter_numeric_bounds(
    df: pl.DataFrame,
    column: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> pl.DataFrame:
    _validate_candidate_frame(df)

    if minimum is None and maximum is None:
        return df

    _require_column(df, column, "numeric filter")

    value_expr = pl.col(column).cast(pl.Float64, strict=False)
    condition = value_expr.is_not_null()

    if minimum is not None:
        condition = condition & (value_expr >= minimum)

    if maximum is not None:
        condition = condition & (value_expr <= maximum)

    return df.filter(condition)


def filter_by_min_score(
    df: pl.DataFrame,
    min_score: float,
    score_column: str = "opportunity_score",
) -> pl.DataFrame:
    """
    Keep candidates with opportunity_score greater than or equal to min_score.
    """
    _validate_candidate_frame(df)
    _require_column(df, score_column, "score")

    return _filter_numeric_bounds(
        df,
        score_column,
        minimum=min_score,
    )


def filter_by_score_range(
    df: pl.DataFrame,
    min_score: float | None = None,
    max_score: float | None = None,
    score_column: str = "opportunity_score",
) -> pl.DataFrame:
    """
    Keep candidates within a score range.
    """
    _validate_candidate_frame(df)
    _require_column(df, score_column, "score")

    return _filter_numeric_bounds(
        df,
        score_column,
        minimum=min_score,
        maximum=max_score,
    )


def filter_by_min_probability(
    df: pl.DataFrame,
    min_probability: float,
    probability_column: str = "probability_of_profit",
) -> pl.DataFrame:
    """
    Keep candidates with probability_of_profit greater than or equal to min_probability.
    """
    _validate_probability_threshold(min_probability, "min_probability")
    _validate_candidate_frame(df)
    _require_column(df, probability_column, "probability")

    return _filter_numeric_bounds(
        df,
        probability_column,
        minimum=min_probability,
    )


def filter_by_probability_range(
    df: pl.DataFrame,
    min_probability: float | None = None,
    max_probability: float | None = None,
    probability_column: str = "probability_of_profit",
) -> pl.DataFrame:
    """
    Keep candidates within a probability range.
    """
    if min_probability is not None:
        _validate_probability_threshold(min_probability, "min_probability")

    if max_probability is not None:
        _validate_probability_threshold(max_probability, "max_probability")

    if (
        min_probability is not None
        and max_probability is not None
        and min_probability > max_probability
    ):
        raise ValueError("min_probability cannot be greater than max_probability.")

    _validate_candidate_frame(df)
    _require_column(df, probability_column, "probability")

    return _filter_numeric_bounds(
        df,
        probability_column,
        minimum=min_probability,
        maximum=max_probability,
    )


def filter_by_max_loss(
    df: pl.DataFrame,
    max_loss: float,
    loss_column: str = "max_loss",
) -> pl.DataFrame:
    """
    Keep candidates where max_loss is less than or equal to the allowed max_loss.
    """
    if max_loss < 0:
        raise ValueError("max_loss must be greater than or equal to 0.")

    _validate_candidate_frame(df)
    _require_column(df, loss_column, "loss")

    return _filter_numeric_bounds(
        df,
        loss_column,
        maximum=max_loss,
    )


def filter_by_min_expected_return(
    df: pl.DataFrame,
    min_expected_return: float,
    expected_return_column: str = "expected_return",
) -> pl.DataFrame:
    """
    Keep candidates with expected_return greater than or equal to the threshold.
    """
    return _filter_numeric_bounds(
        df,
        expected_return_column,
        minimum=min_expected_return,
    )


def filter_by_min_expected_value(
    df: pl.DataFrame,
    min_expected_value: float,
    expected_value_column: str = "expected_value",
) -> pl.DataFrame:
    """
    Keep candidates with expected_value greater than or equal to the threshold.
    """
    return _filter_numeric_bounds(
        df,
        expected_value_column,
        minimum=min_expected_value,
    )


def filter_by_min_confidence(
    df: pl.DataFrame,
    min_confidence: float,
    confidence_column: str = "confidence",
) -> pl.DataFrame:
    """
    Keep candidates with confidence greater than or equal to min_confidence.
    """
    _validate_probability_threshold(min_confidence, "min_confidence")

    return _filter_numeric_bounds(
        df,
        confidence_column,
        minimum=min_confidence,
    )


def filter_by_min_risk_reward(
    df: pl.DataFrame,
    min_risk_reward: float,
    risk_reward_column: str = "risk_reward",
) -> pl.DataFrame:
    """
    Keep candidates with risk_reward greater than or equal to the threshold.
    """
    return _filter_numeric_bounds(
        df,
        risk_reward_column,
        minimum=min_risk_reward,
    )


def filter_by_min_liquidity_score(
    df: pl.DataFrame,
    min_liquidity_score: float,
    liquidity_score_column: str = "liquidity_score",
) -> pl.DataFrame:
    """
    Keep candidates with liquidity_score greater than or equal to the threshold.
    """
    _validate_probability_threshold(min_liquidity_score, "min_liquidity_score")

    return _filter_numeric_bounds(
        df,
        liquidity_score_column,
        minimum=min_liquidity_score,
    )


def filter_by_max_bid_ask_spread(
    df: pl.DataFrame,
    max_bid_ask_spread_pct: float,
    spread_column: str = "bid_ask_spread_pct",
) -> pl.DataFrame:
    """
    Keep candidates with bid/ask spread less than or equal to the threshold.
    """
    if max_bid_ask_spread_pct < 0:
        raise ValueError("max_bid_ask_spread_pct must be greater than or equal to 0.")

    return _filter_numeric_bounds(
        df,
        spread_column,
        maximum=max_bid_ask_spread_pct,
    )


def filter_by_min_volume(
    df: pl.DataFrame,
    min_volume: float,
    volume_column: str = "volume",
) -> pl.DataFrame:
    """
    Keep candidates with volume greater than or equal to the threshold.
    """
    return _filter_numeric_bounds(
        df,
        volume_column,
        minimum=min_volume,
    )


def filter_by_min_open_interest(
    df: pl.DataFrame,
    min_open_interest: float,
    open_interest_column: str = "open_interest",
) -> pl.DataFrame:
    """
    Keep candidates with open_interest greater than or equal to the threshold.
    """
    return _filter_numeric_bounds(
        df,
        open_interest_column,
        minimum=min_open_interest,
    )


def filter_by_days_to_expiration_range(
    df: pl.DataFrame,
    min_days_to_expiration: int | None = None,
    max_days_to_expiration: int | None = None,
    dte_column: str = "days_to_expiration",
) -> pl.DataFrame:
    """
    Keep option candidates within a days-to-expiration range.
    """
    if min_days_to_expiration is not None and min_days_to_expiration < 0:
        raise ValueError("min_days_to_expiration must be greater than or equal to 0.")

    if max_days_to_expiration is not None and max_days_to_expiration < 0:
        raise ValueError("max_days_to_expiration must be greater than or equal to 0.")

    if (
        min_days_to_expiration is not None
        and max_days_to_expiration is not None
        and min_days_to_expiration > max_days_to_expiration
    ):
        raise ValueError(
            "min_days_to_expiration cannot be greater than max_days_to_expiration."
        )

    return _filter_numeric_bounds(
        df,
        dte_column,
        minimum=min_days_to_expiration,
        maximum=max_days_to_expiration,
    )

def filter_by_greek_range(
    df: pl.DataFrame,
    greek_column: str,
    minimum: float | None = None,
    maximum: float | None = None,
) -> pl.DataFrame:
    """
    Keep candidates where a Greek exposure falls within a numeric range.
    """
    return _filter_numeric_bounds(
        df,
        greek_column,
        minimum=minimum,
        maximum=maximum,
    )


def filter_by_abs_greek_limit(
    df: pl.DataFrame,
    greek_column: str,
    max_abs_value: float,
) -> pl.DataFrame:
    """
    Keep candidates where absolute Greek exposure is less than or equal to a limit.
    """
    _validate_candidate_frame(df)
    _require_column(df, greek_column, "Greek")

    if max_abs_value < 0:
        raise ValueError("max_abs_value must be greater than or equal to 0.")

    value_expr = pl.col(greek_column).cast(pl.Float64, strict=False)

    return df.filter(
        value_expr.is_not_null() & (value_expr.abs() <= max_abs_value)
    )


def filter_by_delta_range(
    df: pl.DataFrame,
    min_delta: float | None = None,
    max_delta: float | None = None,
    delta_column: str = "delta",
) -> pl.DataFrame:
    return filter_by_greek_range(
        df,
        greek_column=delta_column,
        minimum=min_delta,
        maximum=max_delta,
    )


def filter_by_gamma_range(
    df: pl.DataFrame,
    min_gamma: float | None = None,
    max_gamma: float | None = None,
    gamma_column: str = "gamma",
) -> pl.DataFrame:
    return filter_by_greek_range(
        df,
        greek_column=gamma_column,
        minimum=min_gamma,
        maximum=max_gamma,
    )


def filter_by_theta_range(
    df: pl.DataFrame,
    min_theta: float | None = None,
    max_theta: float | None = None,
    theta_column: str = "theta",
) -> pl.DataFrame:
    return filter_by_greek_range(
        df,
        greek_column=theta_column,
        minimum=min_theta,
        maximum=max_theta,
    )


def filter_by_vega_range(
    df: pl.DataFrame,
    min_vega: float | None = None,
    max_vega: float | None = None,
    vega_column: str = "vega",
) -> pl.DataFrame:
    return filter_by_greek_range(
        df,
        greek_column=vega_column,
        minimum=min_vega,
        maximum=max_vega,
    )


def filter_by_rho_range(
    df: pl.DataFrame,
    min_rho: float | None = None,
    max_rho: float | None = None,
    rho_column: str = "rho",
) -> pl.DataFrame:
    return filter_by_greek_range(
        df,
        greek_column=rho_column,
        minimum=min_rho,
        maximum=max_rho,
    )

def filter_by_allowed_strategies(
    df: pl.DataFrame,
    allowed_strategies: Sequence[str],
    strategy_column: str = "strategy",
) -> pl.DataFrame:
    """
    Keep only candidates whose strategy is in the allowed strategy list.
    """
    _validate_candidate_frame(df)
    _require_column(df, strategy_column, "strategy")

    normalized_allowed = [_normalize_label(strategy) for strategy in allowed_strategies]

    return df.filter(
        pl.col(strategy_column)
        .cast(pl.Utf8)
        .str.strip_chars()
        .str.replace_all(r"[\s\-]+", "_")
        .str.to_lowercase()
        .is_in(normalized_allowed)
    )


def filter_by_allowed_regimes(
    df: pl.DataFrame,
    allowed_regimes: Sequence[str],
    regime_column: str = "regime",
) -> pl.DataFrame:
    """
    Keep only candidates whose regime is in the allowed regime list.
    """
    _validate_candidate_frame(df)
    _require_column(df, regime_column, "regime")

    normalized_allowed = [_normalize_label(regime) for regime in allowed_regimes]

    return df.filter(
        pl.col(regime_column)
        .cast(pl.Utf8)
        .str.strip_chars()
        .str.replace_all(r"[\s\-]+", "_")
        .str.to_lowercase()
        .is_in(normalized_allowed)
    )


def filter_by_allowed_asset_classes(
    df: pl.DataFrame,
    allowed_asset_classes: Sequence[str],
    asset_class_column: str = "asset_class",
) -> pl.DataFrame:
    """
    Keep only candidates whose asset class is allowed.
    """
    _validate_candidate_frame(df)
    _require_column(df, asset_class_column, "asset_class")

    normalized_allowed = [
        _normalize_label(asset_class) for asset_class in allowed_asset_classes
    ]

    return df.filter(
        pl.col(asset_class_column)
        .cast(pl.Utf8)
        .str.strip_chars()
        .str.replace_all(r"[\s\-]+", "_")
        .str.to_lowercase()
        .is_in(normalized_allowed)
    )


def filter_by_allowed_directions(
    df: pl.DataFrame,
    allowed_directions: Sequence[str],
    direction_column: str = "direction",
) -> pl.DataFrame:
    """
    Keep only candidates whose directional exposure is allowed.
    """
    _validate_candidate_frame(df)
    _require_column(df, direction_column, "direction")

    normalized_allowed = [_normalize_label(direction) for direction in allowed_directions]

    return df.filter(
        pl.col(direction_column)
        .cast(pl.Utf8)
        .str.strip_chars()
        .str.replace_all(r"[\s\-]+", "_")
        .str.to_lowercase()
        .is_in(normalized_allowed)
    )


def filter_by_selection_eligible(
    df: pl.DataFrame,
    require_eligible: bool = True,
    eligibility_column: str = "selection_eligible",
) -> pl.DataFrame:
    """
    Keep only rows marked as selection_eligible when requested.
    """
    _validate_candidate_frame(df)

    if not require_eligible:
        return df

    _require_column(df, eligibility_column, "selection eligibility")

    return df.filter(
        pl.col(eligibility_column).cast(pl.Boolean, strict=False)
    )


def apply_candidate_filters(
    df: pl.DataFrame,
    min_score: float | None = None,
    min_probability: float | None = None,
    max_loss: float | None = None,
    allowed_strategies: Sequence[str] | None = None,
    allowed_regimes: Sequence[str] | None = None,
    *,
    config: CandidateFilterConfig | None = None,
    max_score: float | None = None,
    max_probability: float | None = None,
    min_expected_return: float | None = None,
    min_expected_value: float | None = None,
    min_confidence: float | None = None,
    min_risk_reward: float | None = None,
    min_liquidity_score: float | None = None,
    max_bid_ask_spread_pct: float | None = None,
    min_volume: float | None = None,
    min_open_interest: float | None = None,
    min_days_to_expiration: int | None = None,
    max_days_to_expiration: int | None = None,
    allowed_asset_classes: Sequence[str] | None = None,
    allowed_directions: Sequence[str] | None = None,
    require_selection_eligible: bool | None = None,
    min_delta: float | None = None,
    max_delta: float | None = None,
    min_gamma: float | None = None,
    max_gamma: float | None = None,
    min_theta: float | None = None,
    max_theta: float | None = None,
    min_vega: float | None = None,
    max_vega: float | None = None,
    min_rho: float | None = None,
    max_rho: float | None = None,
    min_net_delta: float | None = None,
    max_net_delta: float | None = None,
    min_net_gamma: float | None = None,
    max_net_gamma: float | None = None,
    min_net_theta: float | None = None,
    max_net_theta: float | None = None,
    min_net_vega: float | None = None,
    max_net_vega: float | None = None,
    min_net_rho: float | None = None,
    max_net_rho: float | None = None,
    max_abs_delta: float | None = None,
    max_abs_gamma: float | None = None,
    max_abs_theta: float | None = None,
    max_abs_vega: float | None = None,
    max_abs_rho: float | None = None,
    max_abs_net_delta: float | None = None,
    max_abs_net_gamma: float | None = None,
    max_abs_net_theta: float | None = None,
    max_abs_net_vega: float | None = None,
    max_abs_net_rho: float | None = None,
) -> pl.DataFrame:
    """
    Apply the full candidate filtering pipeline.

    Supports:
    - score filters
    - probability filters
    - risk filters
    - expected value filters
    - confidence filters
    - liquidity filters
    - option DTE filters
    - strategy/regime/asset/direction filters
    - selection eligibility flags
    """
    _validate_candidate_frame(df)

    cfg = config or CandidateFilterConfig()

    min_score = cfg.min_score if min_score is None else min_score
    max_score = cfg.max_score if max_score is None else max_score
    min_probability = (
        cfg.min_probability if min_probability is None else min_probability
    )
    max_probability = (
        cfg.max_probability if max_probability is None else max_probability
    )
    max_loss = cfg.max_loss if max_loss is None else max_loss
    min_expected_return = (
        cfg.min_expected_return
        if min_expected_return is None
        else min_expected_return
    )
    min_expected_value = (
        cfg.min_expected_value if min_expected_value is None else min_expected_value
    )
    min_confidence = (
        cfg.min_confidence if min_confidence is None else min_confidence
    )
    min_risk_reward = (
        cfg.min_risk_reward if min_risk_reward is None else min_risk_reward
    )
    min_liquidity_score = (
        cfg.min_liquidity_score
        if min_liquidity_score is None
        else min_liquidity_score
    )
    max_bid_ask_spread_pct = (
        cfg.max_bid_ask_spread_pct
        if max_bid_ask_spread_pct is None
        else max_bid_ask_spread_pct
    )
    min_volume = cfg.min_volume if min_volume is None else min_volume
    min_open_interest = (
        cfg.min_open_interest if min_open_interest is None else min_open_interest
    )
    min_days_to_expiration = (
        cfg.min_days_to_expiration
        if min_days_to_expiration is None
        else min_days_to_expiration
    )
    max_days_to_expiration = (
        cfg.max_days_to_expiration
        if max_days_to_expiration is None
        else max_days_to_expiration
    )
    allowed_strategies = (
        cfg.allowed_strategies
        if allowed_strategies is None
        else allowed_strategies
    )
    allowed_regimes = (
        cfg.allowed_regimes if allowed_regimes is None else allowed_regimes
    )
    allowed_asset_classes = (
        cfg.allowed_asset_classes
        if allowed_asset_classes is None
        else allowed_asset_classes
    )
    allowed_directions = (
        cfg.allowed_directions
        if allowed_directions is None
        else allowed_directions
    )
    require_selection_eligible = (
        cfg.require_selection_eligible
        if require_selection_eligible is None
        else require_selection_eligible
    )
    min_delta = cfg.min_delta if min_delta is None else min_delta
    max_delta = cfg.max_delta if max_delta is None else max_delta
    min_gamma = cfg.min_gamma if min_gamma is None else min_gamma
    max_gamma = cfg.max_gamma if max_gamma is None else max_gamma
    min_theta = cfg.min_theta if min_theta is None else min_theta
    max_theta = cfg.max_theta if max_theta is None else max_theta
    min_vega = cfg.min_vega if min_vega is None else min_vega
    max_vega = cfg.max_vega if max_vega is None else max_vega
    min_rho = cfg.min_rho if min_rho is None else min_rho
    max_rho = cfg.max_rho if max_rho is None else max_rho

    min_net_delta = cfg.min_net_delta if min_net_delta is None else min_net_delta
    max_net_delta = cfg.max_net_delta if max_net_delta is None else max_net_delta
    min_net_gamma = cfg.min_net_gamma if min_net_gamma is None else min_net_gamma
    max_net_gamma = cfg.max_net_gamma if max_net_gamma is None else max_net_gamma
    min_net_theta = cfg.min_net_theta if min_net_theta is None else min_net_theta
    max_net_theta = cfg.max_net_theta if max_net_theta is None else max_net_theta
    min_net_vega = cfg.min_net_vega if min_net_vega is None else min_net_vega
    max_net_vega = cfg.max_net_vega if max_net_vega is None else max_net_vega
    min_net_rho = cfg.min_net_rho if min_net_rho is None else min_net_rho
    max_net_rho = cfg.max_net_rho if max_net_rho is None else max_net_rho

    max_abs_delta = cfg.max_abs_delta if max_abs_delta is None else max_abs_delta
    max_abs_gamma = cfg.max_abs_gamma if max_abs_gamma is None else max_abs_gamma
    max_abs_theta = cfg.max_abs_theta if max_abs_theta is None else max_abs_theta
    max_abs_vega = cfg.max_abs_vega if max_abs_vega is None else max_abs_vega
    max_abs_rho = cfg.max_abs_rho if max_abs_rho is None else max_abs_rho

    max_abs_net_delta = (
        cfg.max_abs_net_delta if max_abs_net_delta is None else max_abs_net_delta
    )
    max_abs_net_gamma = (
        cfg.max_abs_net_gamma if max_abs_net_gamma is None else max_abs_net_gamma
    )
    max_abs_net_theta = (
        cfg.max_abs_net_theta if max_abs_net_theta is None else max_abs_net_theta
    )
    max_abs_net_vega = (
        cfg.max_abs_net_vega if max_abs_net_vega is None else max_abs_net_vega
    )
    max_abs_net_rho = (
        cfg.max_abs_net_rho if max_abs_net_rho is None else max_abs_net_rho
    )

    result = df

    if min_score is not None or max_score is not None:
        result = filter_by_score_range(
            result,
            min_score=min_score,
            max_score=max_score,
        )

    if min_probability is not None or max_probability is not None:
        result = filter_by_probability_range(
            result,
            min_probability=min_probability,
            max_probability=max_probability,
        )

    if max_loss is not None:
        result = filter_by_max_loss(result, max_loss=max_loss)

    if min_expected_return is not None:
        result = filter_by_min_expected_return(
            result,
            min_expected_return=min_expected_return,
        )

    if min_expected_value is not None:
        result = filter_by_min_expected_value(
            result,
            min_expected_value=min_expected_value,
        )

    if min_confidence is not None:
        result = filter_by_min_confidence(
            result,
            min_confidence=min_confidence,
        )

    if min_risk_reward is not None:
        result = filter_by_min_risk_reward(
            result,
            min_risk_reward=min_risk_reward,
        )

    if min_liquidity_score is not None:
        result = filter_by_min_liquidity_score(
            result,
            min_liquidity_score=min_liquidity_score,
        )

    if max_bid_ask_spread_pct is not None:
        result = filter_by_max_bid_ask_spread(
            result,
            max_bid_ask_spread_pct=max_bid_ask_spread_pct,
        )

    if min_volume is not None:
        result = filter_by_min_volume(
            result,
            min_volume=min_volume,
        )

    if min_open_interest is not None:
        result = filter_by_min_open_interest(
            result,
            min_open_interest=min_open_interest,
        )

    if min_days_to_expiration is not None or max_days_to_expiration is not None:
        result = filter_by_days_to_expiration_range(
            result,
            min_days_to_expiration=min_days_to_expiration,
            max_days_to_expiration=max_days_to_expiration,
        )

    if allowed_strategies is not None:
        result = filter_by_allowed_strategies(
            result,
            allowed_strategies=allowed_strategies,
        )

    if allowed_regimes is not None:
        result = filter_by_allowed_regimes(
            result,
            allowed_regimes=allowed_regimes,
        )

    if allowed_asset_classes is not None:
        result = filter_by_allowed_asset_classes(
            result,
            allowed_asset_classes=allowed_asset_classes,
        )

    if allowed_directions is not None:
        result = filter_by_allowed_directions(
            result,
            allowed_directions=allowed_directions,
        )

    if require_selection_eligible:
        result = filter_by_selection_eligible(result)
        
    greek_ranges = {
        "delta": (min_delta, max_delta),
        "gamma": (min_gamma, max_gamma),
        "theta": (min_theta, max_theta),
        "vega": (min_vega, max_vega),
        "rho": (min_rho, max_rho),
        "net_delta": (min_net_delta, max_net_delta),
        "net_gamma": (min_net_gamma, max_net_gamma),
        "net_theta": (min_net_theta, max_net_theta),
        "net_vega": (min_net_vega, max_net_vega),
        "net_rho": (min_net_rho, max_net_rho),
    }

    for greek_column, (minimum, maximum) in greek_ranges.items():
        if minimum is not None or maximum is not None:
            result = filter_by_greek_range(
                result,
                greek_column=greek_column,
                minimum=minimum,
                maximum=maximum,
            )

    abs_greek_limits = {
        "delta": max_abs_delta,
        "gamma": max_abs_gamma,
        "theta": max_abs_theta,
        "vega": max_abs_vega,
        "rho": max_abs_rho,
        "net_delta": max_abs_net_delta,
        "net_gamma": max_abs_net_gamma,
        "net_theta": max_abs_net_theta,
        "net_vega": max_abs_net_vega,
        "net_rho": max_abs_net_rho,
    }

    for greek_column, max_abs_value in abs_greek_limits.items():
        if max_abs_value is not None:
            result = filter_by_abs_greek_limit(
                result,
                greek_column=greek_column,
                max_abs_value=max_abs_value,
            )

    return result
