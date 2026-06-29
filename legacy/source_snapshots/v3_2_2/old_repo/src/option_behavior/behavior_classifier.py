from __future__ import annotations

from collections import Counter
from numbers import Real
from typing import Any

import polars as pl

from src.option_behavior.behavior_score import build_option_behavior_score
from src.option_behavior.schema import validate_option_behavior_inputs


def classify_option_behavior(
    option_df: pl.DataFrame,
    score_weights: dict | None = None,
) -> dict:
    """
    Classify option behavior from existing options analytics output.

    This layer consumes columns produced by src/options, including optional:
    - liquidity_regime
    - vol_premium_regime
    - skew_regime
    - term_structure_regime
    - iv_rv_ratio
    - delta / gamma / vega

    It does not calculate IV surfaces, skew, term structure, liquidity metrics,
    Greeks, option opportunities, expected value, strategy selection, logging,
    operation records, audits, health reports, routing, fills, or live execution.
    """

    validate_option_behavior_inputs(option_df)

    summary = summarize_option_behavior_inputs(option_df)

    iv_behavior = classify_iv_behavior(
        avg_implied_volatility=summary["avg_implied_volatility"],
    )

    vol_premium_behavior = classify_vol_premium_behavior(option_df)

    liquidity_behavior = classify_liquidity_behavior(
        option_df=option_df,
        total_volume=summary["total_volume"],
        total_open_interest=summary["total_open_interest"],
        avg_spread_pct=summary["avg_spread_pct"],
    )

    skew_behavior = classify_skew_behavior(option_df)

    term_structure_behavior = classify_term_structure_behavior(option_df)

    greek_behavior = classify_greek_behavior(
        avg_abs_gamma=summary["avg_abs_gamma"],
        avg_abs_vega=summary["avg_abs_vega"],
    )

    base_behavior = {
        "iv_behavior": iv_behavior,
        "vol_premium_behavior": vol_premium_behavior,
        "liquidity_behavior": liquidity_behavior,
        "skew_behavior": skew_behavior,
        "term_structure_behavior": term_structure_behavior,
        "greek_behavior": greek_behavior,
        **summary,
    }

    score_result = build_option_behavior_score(
        behavior=base_behavior,
        weights=score_weights,
    )

    return {
        **base_behavior,
        **score_result,
    }


def summarize_option_behavior_inputs(
    option_df: pl.DataFrame,
) -> dict:
    validate_option_behavior_inputs(option_df)

    expressions = [
        pl.col("implied_volatility").mean().alias("avg_implied_volatility"),
        pl.col("spread_pct").mean().alias("avg_spread_pct"),
        pl.col("volume").sum().alias("total_volume"),
        pl.col("open_interest").sum().alias("total_open_interest"),
        pl.len().alias("contract_count"),
    ]

    for column in ["delta", "gamma", "vega"]:
        if column in option_df.columns:
            expressions.append(
                pl.col(column).abs().mean().alias(f"avg_abs_{column}")
            )
        else:
            expressions.append(
                pl.lit(None).alias(f"avg_abs_{column}")
            )

    summary = option_df.select(expressions).to_dicts()[0]

    return {
        key: _float_or_none(value)
        if key != "contract_count"
        else int(value)
        for key, value in summary.items()
    }


def classify_iv_behavior(
    avg_implied_volatility: float,
    low_threshold: float = 0.25,
    high_threshold: float = 0.60,
    extreme_threshold: float = 1.00,
) -> str:
    if avg_implied_volatility >= extreme_threshold:
        return "extreme_iv"

    if avg_implied_volatility >= high_threshold:
        return "high_iv"

    if avg_implied_volatility <= low_threshold:
        return "low_iv"

    return "normal_iv"


def classify_vol_premium_behavior(
    option_df: pl.DataFrame,
    rich_threshold: float = 1.25,
    cheap_threshold: float = 0.90,
) -> str:
    regime = _dominant_string(option_df, "vol_premium_regime")

    if regime == "rich":
        return "rich_vol"

    if regime == "cheap":
        return "cheap_vol"

    if regime == "neutral":
        return "neutral_vol"

    if "iv_rv_ratio" not in option_df.columns:
        return "unknown_vol_premium"

    avg_ratio = option_df.select(pl.col("iv_rv_ratio").mean()).item()

    if avg_ratio is None:
        return "unknown_vol_premium"

    if avg_ratio >= rich_threshold:
        return "rich_vol"

    if avg_ratio <= cheap_threshold:
        return "cheap_vol"

    return "neutral_vol"


def classify_liquidity_behavior(
    option_df: pl.DataFrame,
    total_volume: float,
    total_open_interest: float,
    avg_spread_pct: float,
    max_spread_pct: float = 0.25,
) -> str:
    if total_volume <= 0 and total_open_interest <= 0:
        return "untradable_liquidity"

    if avg_spread_pct > max_spread_pct:
        return "untradable_liquidity"

    regime = _dominant_string(option_df, "liquidity_regime")

    if regime == "high":
        return "high_liquidity"

    if regime == "medium":
        return "medium_liquidity"

    if regime == "low":
        return "low_liquidity"

    if total_volume < 100 or total_open_interest < 500:
        return "low_liquidity"

    if total_volume >= 5_000 and total_open_interest >= 20_000 and avg_spread_pct <= 0.08:
        return "high_liquidity"

    return "medium_liquidity"


def classify_skew_behavior(
    option_df: pl.DataFrame,
) -> str:
    regime = _dominant_string(option_df, "skew_regime")

    if regime == "balanced":
        return "balanced_skew"

    if regime == "downside_rich":
        return "downside_rich_skew"

    if regime == "upside_rich":
        return "upside_rich_skew"

    if regime is None:
        return "unknown_skew"

    return "distorted_skew"


def classify_term_structure_behavior(
    option_df: pl.DataFrame,
) -> str:
    regime = _dominant_string(option_df, "term_structure_regime")

    if regime == "flat":
        return "flat_term_structure"

    if regime == "contango":
        return "contango_term_structure"

    if regime == "backwardation":
        return "backwardated_term_structure"

    return "unknown_term_structure"


def classify_greek_behavior(
    avg_abs_gamma: float | None,
    avg_abs_vega: float | None,
    elevated_gamma_threshold: float = 0.05,
    high_gamma_threshold: float = 0.10,
    elevated_vega_threshold: float = 0.15,
    high_vega_threshold: float = 0.25,
) -> str:
    if avg_abs_gamma is None and avg_abs_vega is None:
        return "unknown_greek_risk"

    gamma = avg_abs_gamma or 0.0
    vega = avg_abs_vega or 0.0

    if gamma >= high_gamma_threshold or vega >= high_vega_threshold:
        return "high_greek_risk"

    if gamma >= elevated_gamma_threshold or vega >= elevated_vega_threshold:
        return "elevated_greek_risk"

    return "normal_greek_risk"


def _dominant_string(
    df: pl.DataFrame,
    column: str,
) -> str | None:
    if column not in df.columns:
        return None

    values = [
        str(value).strip().lower()
        for value in df.get_column(column).drop_nulls().to_list()
        if str(value).strip()
    ]

    if not values:
        return None

    return Counter(values).most_common(1)[0][0]


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None

    if isinstance(value, bool):
        return None

    if isinstance(value, Real):
        return float(value)

    return None
