from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


DEFINED_RISK_STRATEGIES = {
    "long_call",
    "long_put",
    "bull_call_debit_spread",
    "bear_put_debit_spread",
    "put_credit_spread",
    "call_credit_spread",
    "iron_condor",
    "iron_butterfly",
    "calendar_spread",
    "diagonal_spread",
    "protective_put",
    "collar",
    "covered_call",
}

UNDEFINED_RISK_STRATEGIES = {
    "naked_short_call",
    "naked_short_put",
    "short_straddle",
    "short_strangle",
    "uncovered_ratio_spread",
    "uncovered_call",
    "undefined_risk_call_spread",
    "undefined_risk_put_spread",
}

DIRECTIONAL_BULLISH = "bullish"
DIRECTIONAL_BEARISH = "bearish"
DIRECTIONAL_NEUTRAL = "neutral"
DIRECTIONAL_DEFENSIVE = "defensive"

SETUP_MOMENTUM = "momentum"
SETUP_TREND = "trend_following"
SETUP_MEAN_REVERSION = "mean_reversion"
SETUP_PORTFOLIO_DEFENSE = "portfolio_defense"
SETUP_INCOME = "income"


@dataclass(frozen=True)
class OptionStrategyDefinition:
    """
    Static metadata for an approved option strategy family.

    This is a catalog record only. It does not build contracts, calculate
    expected value, optimize strikes/expirations, submit orders, model fills,
    or monitor live positions.
    """

    strategy: str
    display_name: str
    direction: str
    setup_families: tuple[str, ...]
    defined_risk: bool
    risk_profile: str
    best_setups: tuple[str, ...]
    preferred_regimes: tuple[str, ...] = field(default_factory=tuple)
    preferred_asset_behaviors: tuple[str, ...] = field(default_factory=tuple)
    preferred_option_behaviors: Mapping[str, tuple[str, ...]] = field(
        default_factory=dict
    )
    required_context: tuple[str, ...] = field(default_factory=tuple)
    blocked_when: tuple[str, ...] = field(default_factory=tuple)
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "display_name": self.display_name,
            "direction": self.direction,
            "setup_families": list(self.setup_families),
            "defined_risk": self.defined_risk,
            "risk_profile": self.risk_profile,
            "best_setups": list(self.best_setups),
            "preferred_regimes": list(self.preferred_regimes),
            "preferred_asset_behaviors": list(self.preferred_asset_behaviors),
            "preferred_option_behaviors": {
                key: list(values)
                for key, values in self.preferred_option_behaviors.items()
            },
            "required_context": list(self.required_context),
            "blocked_when": list(self.blocked_when),
            "notes": list(self.notes),
        }


CATALOG: tuple[OptionStrategyDefinition, ...] = (
    OptionStrategyDefinition(
        strategy="bull_call_debit_spread",
        display_name="Bull Call Debit Spread",
        direction=DIRECTIONAL_BULLISH,
        setup_families=(SETUP_MOMENTUM, SETUP_TREND),
        defined_risk=True,
        risk_profile="defined_debit",
        best_setups=(
            "controlled bullish trend",
            "bullish breakout continuation",
            "moderate upside target with capped risk",
        ),
        preferred_regimes=("risk_on", "neutral", "bullish"),
        preferred_asset_behaviors=(
            "uptrend",
            "controlled_uptrend",
            "breakout_continuation",
            "bullish_momentum",
        ),
        preferred_option_behaviors={
            "iv_behavior": ("low_iv", "normal_iv"),
            "vol_premium_behavior": ("cheap_vol", "neutral_vol"),
            "liquidity_behavior": ("high_liquidity", "medium_liquidity"),
        },
        blocked_when=("untradable_liquidity", "extreme_iv"),
    ),
    OptionStrategyDefinition(
        strategy="put_credit_spread",
        display_name="Bull Put Credit Spread",
        direction=DIRECTIONAL_BULLISH,
        setup_families=(SETUP_MEAN_REVERSION, SETUP_TREND, SETUP_INCOME),
        defined_risk=True,
        risk_profile="defined_credit",
        best_setups=(
            "support holding after a pullback",
            "bullish to neutral outlook",
            "premium collection when downside support is clear",
        ),
        preferred_regimes=("risk_on", "neutral", "bullish"),
        preferred_asset_behaviors=(
            "support_holding",
            "bullish_mean_reversion",
            "controlled_uptrend",
            "range_support",
        ),
        preferred_option_behaviors={
            "iv_behavior": ("normal_iv", "high_iv"),
            "vol_premium_behavior": ("rich_vol", "neutral_vol"),
            "liquidity_behavior": ("high_liquidity", "medium_liquidity"),
            "skew_behavior": ("downside_rich_skew", "balanced_skew"),
        },
        blocked_when=("untradable_liquidity", "extreme_iv"),
    ),
    OptionStrategyDefinition(
        strategy="bear_put_debit_spread",
        display_name="Bear Put Debit Spread",
        direction=DIRECTIONAL_BEARISH,
        setup_families=(SETUP_MOMENTUM, SETUP_TREND),
        defined_risk=True,
        risk_profile="defined_debit",
        best_setups=(
            "controlled bearish trend",
            "breakdown continuation",
            "moderate downside target with capped risk",
        ),
        preferred_regimes=("risk_off", "neutral", "bearish"),
        preferred_asset_behaviors=(
            "downtrend",
            "controlled_downtrend",
            "breakdown_continuation",
            "bearish_momentum",
        ),
        preferred_option_behaviors={
            "iv_behavior": ("low_iv", "normal_iv"),
            "vol_premium_behavior": ("cheap_vol", "neutral_vol"),
            "liquidity_behavior": ("high_liquidity", "medium_liquidity"),
        },
        blocked_when=("untradable_liquidity", "extreme_iv"),
    ),
    OptionStrategyDefinition(
        strategy="call_credit_spread",
        display_name="Bear Call Credit Spread",
        direction=DIRECTIONAL_BEARISH,
        setup_families=(SETUP_MEAN_REVERSION, SETUP_TREND, SETUP_INCOME),
        defined_risk=True,
        risk_profile="defined_credit",
        best_setups=(
            "resistance holding after a rally",
            "bearish to neutral outlook",
            "premium collection when upside resistance is clear",
        ),
        preferred_regimes=("risk_off", "neutral", "bearish"),
        preferred_asset_behaviors=(
            "resistance_holding",
            "bearish_mean_reversion",
            "controlled_downtrend",
            "range_resistance",
        ),
        preferred_option_behaviors={
            "iv_behavior": ("normal_iv", "high_iv"),
            "vol_premium_behavior": ("rich_vol", "neutral_vol"),
            "liquidity_behavior": ("high_liquidity", "medium_liquidity"),
            "skew_behavior": ("upside_rich_skew", "balanced_skew"),
        },
        blocked_when=("untradable_liquidity", "extreme_iv"),
    ),
    OptionStrategyDefinition(
        strategy="iron_condor",
        display_name="Iron Condor",
        direction=DIRECTIONAL_NEUTRAL,
        setup_families=(SETUP_MEAN_REVERSION, SETUP_INCOME),
        defined_risk=True,
        risk_profile="defined_credit",
        best_setups=(
            "range-bound asset behavior",
            "low trend strength",
            "premium collection with defined risk on both sides",
        ),
        preferred_regimes=("neutral", "range_bound", "mixed"),
        preferred_asset_behaviors=(
            "range_bound",
            "low_trend_strength",
            "neutral_mean_reversion",
            "balanced_range",
        ),
        preferred_option_behaviors={
            "iv_behavior": ("normal_iv", "high_iv"),
            "vol_premium_behavior": ("rich_vol",),
            "liquidity_behavior": ("high_liquidity",),
            "skew_behavior": ("balanced_skew",),
        },
        blocked_when=("untradable_liquidity", "strong_trend", "extreme_iv"),
    ),
    OptionStrategyDefinition(
        strategy="iron_butterfly",
        display_name="Iron Butterfly",
        direction=DIRECTIONAL_NEUTRAL,
        setup_families=(SETUP_MEAN_REVERSION, SETUP_INCOME),
        defined_risk=True,
        risk_profile="defined_credit",
        best_setups=(
            "very tight expected range",
            "pin or compression setup",
            "high premium with clear review requirement",
        ),
        preferred_regimes=("neutral", "range_bound"),
        preferred_asset_behaviors=(
            "range_bound",
            "pin_risk",
            "volatility_compression",
        ),
        preferred_option_behaviors={
            "iv_behavior": ("high_iv",),
            "vol_premium_behavior": ("rich_vol",),
            "liquidity_behavior": ("high_liquidity",),
            "skew_behavior": ("balanced_skew",),
        },
        blocked_when=("untradable_liquidity", "strong_trend", "extreme_iv"),
        notes=("requires review because reward zone is narrow",),
    ),
    OptionStrategyDefinition(
        strategy="calendar_spread",
        display_name="Calendar Spread",
        direction=DIRECTIONAL_NEUTRAL,
        setup_families=(SETUP_MEAN_REVERSION,),
        defined_risk=True,
        risk_profile="defined_debit",
        best_setups=(
            "near-term range with time-spread advantage",
            "expected move contained in front expiration",
        ),
        preferred_regimes=("neutral", "range_bound", "mixed"),
        preferred_asset_behaviors=(
            "range_bound",
            "neutral_mean_reversion",
            "volatility_compression",
        ),
        preferred_option_behaviors={
            "iv_behavior": ("low_iv", "normal_iv"),
            "liquidity_behavior": ("high_liquidity", "medium_liquidity"),
            "term_structure_behavior": (
                "contango_term_structure",
                "flat_term_structure",
            ),
        },
        blocked_when=("untradable_liquidity", "extreme_iv"),
    ),
    OptionStrategyDefinition(
        strategy="diagonal_spread",
        display_name="Diagonal Spread",
        direction="directional",
        setup_families=(SETUP_TREND, SETUP_MOMENTUM),
        defined_risk=True,
        risk_profile="defined_debit",
        best_setups=(
            "directional setup with time-spread benefit",
            "trend continuation with controlled risk",
        ),
        preferred_regimes=("risk_on", "risk_off", "neutral"),
        preferred_asset_behaviors=(
            "controlled_uptrend",
            "controlled_downtrend",
            "breakout_continuation",
            "breakdown_continuation",
        ),
        preferred_option_behaviors={
            "iv_behavior": ("low_iv", "normal_iv"),
            "liquidity_behavior": ("high_liquidity", "medium_liquidity"),
            "term_structure_behavior": (
                "contango_term_structure",
                "flat_term_structure",
            ),
        },
        blocked_when=("untradable_liquidity", "extreme_iv"),
    ),
    OptionStrategyDefinition(
        strategy="protective_put",
        display_name="Protective Put",
        direction=DIRECTIONAL_DEFENSIVE,
        setup_families=(SETUP_PORTFOLIO_DEFENSE,),
        defined_risk=True,
        risk_profile="defensive_debit",
        best_setups=(
            "existing long position needs downside protection",
            "portfolio drawdown risk rising",
        ),
        preferred_regimes=("risk_off", "mixed", "event_risk"),
        preferred_asset_behaviors=(
            "existing_long_position",
            "downside_risk_rising",
            "event_risk",
        ),
        preferred_option_behaviors={
            "iv_behavior": ("low_iv", "normal_iv"),
            "liquidity_behavior": ("high_liquidity", "medium_liquidity"),
        },
        required_context=("has_underlying_position",),
        blocked_when=("untradable_liquidity", "extreme_iv"),
    ),
    OptionStrategyDefinition(
        strategy="collar",
        display_name="Collar",
        direction=DIRECTIONAL_DEFENSIVE,
        setup_families=(SETUP_PORTFOLIO_DEFENSE,),
        defined_risk=True,
        risk_profile="defensive_defined_range",
        best_setups=(
            "existing long position needs protection",
            "willing to cap upside to finance downside hedge",
        ),
        preferred_regimes=("risk_off", "mixed", "event_risk", "neutral"),
        preferred_asset_behaviors=(
            "existing_long_position",
            "downside_risk_rising",
            "range_bound",
        ),
        preferred_option_behaviors={
            "iv_behavior": ("normal_iv", "high_iv"),
            "liquidity_behavior": ("high_liquidity", "medium_liquidity"),
        },
        required_context=("has_underlying_position",),
        blocked_when=("untradable_liquidity",),
    ),
    OptionStrategyDefinition(
        strategy="covered_call",
        display_name="Covered Call",
        direction="neutral_to_bullish",
        setup_families=(SETUP_INCOME,),
        defined_risk=True,
        risk_profile="stock_covered_income",
        best_setups=(
            "existing long shares",
            "neutral to mildly bullish outlook",
            "upside cap acceptable",
        ),
        preferred_regimes=("neutral", "risk_on", "mixed"),
        preferred_asset_behaviors=(
            "existing_long_position",
            "range_bound",
            "controlled_uptrend",
        ),
        preferred_option_behaviors={
            "iv_behavior": ("normal_iv", "high_iv"),
            "vol_premium_behavior": ("rich_vol", "neutral_vol"),
            "liquidity_behavior": ("high_liquidity", "medium_liquidity"),
        },
        required_context=("has_underlying_position",),
        blocked_when=("untradable_liquidity",),
        notes=("covered by existing shares; do not use as uncovered short call",),
    ),
)


def build_option_strategy_catalog() -> tuple[OptionStrategyDefinition, ...]:
    return CATALOG


def catalog_as_dicts() -> list[dict[str, Any]]:
    return [definition.to_dict() for definition in build_option_strategy_catalog()]


def get_strategy_definition(strategy: str) -> OptionStrategyDefinition:
    normalized_strategy = strategy.strip().lower()
    for definition in CATALOG:
        if definition.strategy == normalized_strategy:
            return definition

    raise KeyError(f"Unknown option strategy: {strategy}")


def is_defined_risk_strategy(strategy: str) -> bool:
    normalized_strategy = strategy.strip().lower()

    if normalized_strategy in UNDEFINED_RISK_STRATEGIES:
        return False

    if normalized_strategy in DEFINED_RISK_STRATEGIES:
        return True

    try:
        return get_strategy_definition(normalized_strategy).defined_risk
    except KeyError:
        return False


def validate_defined_risk_catalog(
    catalog: tuple[OptionStrategyDefinition, ...] | None = None,
) -> None:
    active_catalog = catalog or CATALOG

    if not active_catalog:
        raise ValueError("Option strategy catalog is empty")

    seen: set[str] = set()

    for definition in active_catalog:
        if definition.strategy in seen:
            raise ValueError(f"Duplicate option strategy: {definition.strategy}")

        seen.add(definition.strategy)

        if definition.strategy in UNDEFINED_RISK_STRATEGIES:
            raise ValueError(
                f"Undefined-risk strategy cannot be catalog-approved: "
                f"{definition.strategy}"
            )

        if not definition.defined_risk:
            raise ValueError(
                f"Catalog strategy must be defined-risk: {definition.strategy}"
            )

        if not definition.best_setups:
            raise ValueError(
                f"Catalog strategy missing best setups: {definition.strategy}"
            )

        if not definition.setup_families:
            raise ValueError(
                f"Catalog strategy missing setup families: {definition.strategy}"
            )

