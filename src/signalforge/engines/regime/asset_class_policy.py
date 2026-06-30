from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from src.signalforge.engines.options_strategy.catalog import (
    UNDEFINED_RISK_STRATEGIES,
    build_option_strategy_catalog,
)


EXCLUDED_ACTIONS = [
    "broker_api_calls",
    "order_routing",
    "order_submission",
    "fills",
    "live_execution",
    "slippage_modeling",
    "automatic_maintenance_actions",
    "automatic_defense_actions",
]

VALID_POLICY_STATUSES = {
    "preferred",
    "allowed",
    "needs_review",
    "blocked",
}

ASSET_CLASSES = {
    "equities",
    "bonds",
    "credit",
    "commodities",
    "currencies",
    "volatility",
}

ASSET_CLASS_ALIASES = {
    "equity": "equities",
    "stock": "equities",
    "stocks": "equities",
    "index": "equities",
    "indices": "equities",
    "bond": "bonds",
    "treasury": "bonds",
    "treasuries": "bonds",
    "duration": "bonds",
    "corp_credit": "credit",
    "corporate_credit": "credit",
    "high_yield": "credit",
    "commodity": "commodities",
    "metals": "commodities",
    "energy": "commodities",
    "currency": "currencies",
    "fx": "currencies",
    "dollar": "currencies",
    "vol": "volatility",
    "vix": "volatility",
}

PREMIUM_SELLING_STRATEGIES = {
    "put_credit_spread",
    "call_credit_spread",
    "iron_condor",
    "iron_butterfly",
    "covered_call",
}

DIRECTIONAL_DEBIT_STRATEGIES = {
    "bull_call_debit_spread",
    "bear_put_debit_spread",
    "diagonal_spread",
}

DEFENSIVE_STRATEGIES = {
    "protective_put",
    "collar",
    "bear_put_debit_spread",
    "call_credit_spread",
}


@dataclass(frozen=True)
class RegimeAssetClassPolicyInput:
    """
    Macro-regime context used to set asset-class permissions and strategy-family
    buckets.

    This is a policy layer only. It does not classify individual symbols, select
    contracts, choose strikes/expirations, route orders, model fills, or create
    automatic maintenance/defense trades.
    """

    regime_label: str
    risk_environment: str | None = None
    volatility_regime: str | None = None
    liquidity_regime: str | None = None
    growth_regime: str | None = None
    inflation_regime: str | None = None
    rates_regime: str | None = None
    event_risk: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)


def build_regime_asset_class_policy(
    regime_input: RegimeAssetClassPolicyInput | Mapping[str, Any],
) -> dict[str, Any]:
    """
    Convert a macro/regime row into asset-class strategy permissions.

    Output asset-class buckets:
    - preferred: asset class and strategy family are aligned with the regime
    - allowed: usable, but asset behavior and option behavior must confirm
    - needs_review: possible, but requires explicit review/confirmation
    - blocked: hard-blocked undefined-risk strategies or invalid conditions
    """

    parsed_input = _parse_regime_input(regime_input)
    errors = _validate_input(parsed_input)
    if errors:
        return _blocked_policy(parsed_input, errors)

    normalized_regime = _normalized_regime(parsed_input)
    template = _asset_class_template(normalized_regime)
    asset_details = _build_asset_class_details(
        template=template,
        regime_input=parsed_input,
    )
    asset_policy = {
        detail["asset_class"]: _asset_class_policy_summary(detail)
        for detail in asset_details
    }
    warnings = _policy_warnings(
        regime_input=parsed_input,
        normalized_regime=normalized_regime,
        asset_details=asset_details,
    )
    status = "needs_review" if warnings else "ready"

    return {
        "artifact_type": "regime_asset_class_policy",
        "status": status,
        "is_ready": status == "ready",
        "regime_label": parsed_input.regime_label,
        "normalized_regime": normalized_regime,
        "risk_environment": parsed_input.risk_environment,
        "volatility_regime": parsed_input.volatility_regime,
        "liquidity_regime": parsed_input.liquidity_regime,
        "growth_regime": parsed_input.growth_regime,
        "inflation_regime": parsed_input.inflation_regime,
        "rates_regime": parsed_input.rates_regime,
        "event_risk": parsed_input.event_risk,
        "asset_class_policy": asset_policy,
        "asset_class_policy_details": asset_details,
        "warnings": warnings,
        "blocked_reasons": [],
        "excluded": EXCLUDED_ACTIONS,
        "metadata": dict(parsed_input.metadata),
    }


def build_regime_asset_class_policy_from_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """Convenience wrapper for row-shaped regime output."""

    return build_regime_asset_class_policy(row)


def _parse_regime_input(
    regime_input: RegimeAssetClassPolicyInput | Mapping[str, Any],
) -> RegimeAssetClassPolicyInput:
    if isinstance(regime_input, RegimeAssetClassPolicyInput):
        return regime_input

    if not isinstance(regime_input, Mapping):
        return RegimeAssetClassPolicyInput(regime_label="")

    metadata = regime_input.get("metadata")
    if not isinstance(metadata, Mapping):
        metadata = {}

    return RegimeAssetClassPolicyInput(
        regime_label=_string(regime_input.get("regime_label")),
        risk_environment=_optional_string(regime_input.get("risk_environment")),
        volatility_regime=_optional_string(
            regime_input.get("volatility_regime")
            or regime_input.get("volatility_state")
        ),
        liquidity_regime=_optional_string(regime_input.get("liquidity_regime")),
        growth_regime=_optional_string(regime_input.get("growth_regime")),
        inflation_regime=_optional_string(regime_input.get("inflation_regime")),
        rates_regime=_optional_string(regime_input.get("rates_regime")),
        event_risk=bool(regime_input.get("event_risk", False)),
        metadata=dict(metadata),
    )


def _validate_input(regime_input: RegimeAssetClassPolicyInput) -> list[str]:
    errors: list[str] = []

    if not regime_input.regime_label.strip():
        errors.append("regime_label is required")

    return errors


def _normalized_regime(regime_input: RegimeAssetClassPolicyInput) -> str:
    regime_label = _clean(regime_input.regime_label)
    risk_environment = _clean(regime_input.risk_environment)

    if regime_label in {
        "goldilocks",
        "reflation",
        "late_cycle_overheating",
        "overheating",
        "stagflation",
        "disinflationary_slowdown",
        "deflationary_slowdown",
        "deflationary_shock",
        "credit_stress",
        "liquidity_stress",
        "risk_off_transition",
        "neutral_mixed",
        "mixed",
        "risk_on",
        "risk_off",
        "neutral",
        "range_bound",
        "event_risk",
    }:
        return regime_label

    if risk_environment == "risk_on":
        return "risk_on"

    if risk_environment == "risk_off":
        return "risk_off"

    if risk_environment == "event_risk":
        return "event_risk"

    return "mixed"


def _asset_class_template(normalized_regime: str) -> dict[str, Any]:
    templates: dict[str, dict[str, Any]] = {
        "goldilocks": {
            "equities": _asset(
                status="preferred",
                directional_bias="bullish",
                thesis="growth expansion with falling inflation favors risk assets",
                preferred=("bull_call_debit_spread", "put_credit_spread", "diagonal_spread"),
                allowed=("covered_call", "calendar_spread", "collar"),
                needs_review=("iron_condor", "iron_butterfly", "bear_put_debit_spread", "call_credit_spread", "protective_put"),
            ),
            "credit": _asset(
                status="preferred",
                directional_bias="bullish_or_income",
                thesis="risk-on backdrop supports credit exposure with defined risk",
                preferred=("put_credit_spread", "bull_call_debit_spread"),
                allowed=("covered_call", "diagonal_spread", "calendar_spread", "collar"),
                needs_review=("iron_condor", "bear_put_debit_spread", "call_credit_spread", "protective_put", "iron_butterfly"),
            ),
            "bonds": _asset(
                status="allowed",
                directional_bias="neutral_to_bullish",
                thesis="falling inflation can support duration, but growth expansion limits urgency",
                preferred=("calendar_spread", "diagonal_spread"),
                allowed=("bull_call_debit_spread", "put_credit_spread", "collar"),
                needs_review=("bear_put_debit_spread", "call_credit_spread", "iron_condor", "iron_butterfly", "protective_put", "covered_call"),
            ),
            "commodities": _asset(
                status="allowed",
                directional_bias="selective",
                thesis="falling inflation makes commodity exposure selective rather than primary",
                preferred=("calendar_spread", "diagonal_spread"),
                allowed=("bull_call_debit_spread", "put_credit_spread", "collar"),
                needs_review=("bear_put_debit_spread", "call_credit_spread", "iron_condor", "iron_butterfly", "protective_put", "covered_call"),
            ),
            "currencies": _asset(
                status="allowed",
                directional_bias="selective",
                thesis="currency setups require asset behavior confirmation",
                preferred=("calendar_spread",),
                allowed=("bull_call_debit_spread", "bear_put_debit_spread", "diagonal_spread", "collar"),
                needs_review=("put_credit_spread", "call_credit_spread", "iron_condor", "iron_butterfly", "protective_put", "covered_call"),
            ),
            "volatility": _asset(
                status="needs_review",
                directional_bias="avoid_new_long_vol_without_confirmation",
                thesis="benign regime usually disfavors standalone long-vol exposure",
                preferred=(),
                allowed=("calendar_spread", "diagonal_spread"),
                needs_review=("bull_call_debit_spread", "bear_put_debit_spread", "put_credit_spread", "call_credit_spread", "iron_condor", "iron_butterfly", "protective_put", "collar", "covered_call"),
            ),
        },
        "risk_on": {},
        "overheating": {
            "equities": _asset(
                status="allowed",
                directional_bias="bullish_with_volatility_risk",
                thesis="growth supports equities but rising inflation/rates require tighter review",
                preferred=("put_credit_spread", "covered_call", "collar"),
                allowed=("bull_call_debit_spread", "diagonal_spread", "calendar_spread", "iron_condor"),
                needs_review=("bear_put_debit_spread", "call_credit_spread", "iron_butterfly", "protective_put"),
            ),
            "bonds": _asset(
                status="needs_review",
                directional_bias="bearish_duration",
                thesis="rising inflation/rates can pressure duration-sensitive assets",
                preferred=("bear_put_debit_spread", "call_credit_spread"),
                allowed=("calendar_spread", "collar"),
                needs_review=("bull_call_debit_spread", "put_credit_spread", "diagonal_spread", "iron_condor", "iron_butterfly", "protective_put", "covered_call"),
            ),
            "credit": _asset(
                status="allowed",
                directional_bias="income_with_review",
                thesis="growth helps credit but tighter financial conditions require review",
                preferred=("put_credit_spread", "covered_call"),
                allowed=("bull_call_debit_spread", "calendar_spread", "collar"),
                needs_review=("bear_put_debit_spread", "call_credit_spread", "iron_condor", "iron_butterfly", "diagonal_spread", "protective_put"),
            ),
            "commodities": _asset(
                status="preferred",
                directional_bias="bullish_inflation_sensitive",
                thesis="rising inflation can support commodity-linked assets",
                preferred=("bull_call_debit_spread", "put_credit_spread", "diagonal_spread"),
                allowed=("calendar_spread", "collar"),
                needs_review=("bear_put_debit_spread", "call_credit_spread", "iron_condor", "iron_butterfly", "protective_put", "covered_call"),
            ),
            "currencies": _asset(
                status="allowed",
                directional_bias="rates_sensitive",
                thesis="currency setups depend on rate differentials and trend behavior",
                preferred=("calendar_spread", "diagonal_spread"),
                allowed=("bull_call_debit_spread", "bear_put_debit_spread", "collar"),
                needs_review=("put_credit_spread", "call_credit_spread", "iron_condor", "iron_butterfly", "protective_put", "covered_call"),
            ),
            "volatility": _asset(
                status="needs_review",
                directional_bias="volatility_expansion_risk",
                thesis="overheating can create volatility expansion risk",
                preferred=("calendar_spread",),
                allowed=("bull_call_debit_spread", "diagonal_spread", "collar"),
                needs_review=("bear_put_debit_spread", "put_credit_spread", "call_credit_spread", "iron_condor", "iron_butterfly", "protective_put", "covered_call"),
            ),
        },
        "stagflation": {
            "equities": _asset(
                status="needs_review",
                directional_bias="bearish_or_defensive",
                thesis="weak growth and rising inflation create poor equity risk/reward",
                preferred=("bear_put_debit_spread", "call_credit_spread", "protective_put", "collar"),
                allowed=("calendar_spread", "covered_call"),
                needs_review=("bull_call_debit_spread", "put_credit_spread", "iron_condor", "iron_butterfly", "diagonal_spread"),
            ),
            "bonds": _asset(
                status="needs_review",
                directional_bias="bearish_duration_or_selective",
                thesis="inflation and rate pressure can hurt duration even as growth slows",
                preferred=("bear_put_debit_spread", "call_credit_spread"),
                allowed=("calendar_spread", "collar"),
                needs_review=("bull_call_debit_spread", "put_credit_spread", "diagonal_spread", "iron_condor", "iron_butterfly", "protective_put", "covered_call"),
            ),
            "credit": _asset(
                status="needs_review",
                directional_bias="defensive",
                thesis="slowing growth can widen spreads and pressure credit",
                preferred=("bear_put_debit_spread", "call_credit_spread", "protective_put", "collar"),
                allowed=("calendar_spread",),
                needs_review=("bull_call_debit_spread", "put_credit_spread", "iron_condor", "iron_butterfly", "diagonal_spread", "covered_call"),
            ),
            "commodities": _asset(
                status="allowed",
                directional_bias="selective_bullish",
                thesis="inflation may support commodities, but growth contraction requires confirmation",
                preferred=("bull_call_debit_spread", "diagonal_spread", "collar"),
                allowed=("put_credit_spread", "calendar_spread"),
                needs_review=("bear_put_debit_spread", "call_credit_spread", "iron_condor", "iron_butterfly", "protective_put", "covered_call"),
            ),
            "currencies": _asset(
                status="allowed",
                directional_bias="safe_haven_or_rates_sensitive",
                thesis="currency behavior depends on relative rates and safe-haven demand",
                preferred=("calendar_spread", "diagonal_spread"),
                allowed=("bull_call_debit_spread", "bear_put_debit_spread", "collar"),
                needs_review=("put_credit_spread", "call_credit_spread", "iron_condor", "iron_butterfly", "protective_put", "covered_call"),
            ),
            "volatility": _asset(
                status="needs_review",
                directional_bias="volatility_upside_risk",
                thesis="stagflation can raise volatility and event-risk sensitivity",
                preferred=("calendar_spread", "collar"),
                allowed=("bull_call_debit_spread", "diagonal_spread", "protective_put"),
                needs_review=("bear_put_debit_spread", "put_credit_spread", "call_credit_spread", "iron_condor", "iron_butterfly", "covered_call"),
            ),
        },
        "risk_off": {},
        "deflationary_slowdown": {
            "equities": _asset(
                status="needs_review",
                directional_bias="bearish_or_defensive",
                thesis="growth contraction and falling inflation favor defensive equity posture",
                preferred=("bear_put_debit_spread", "call_credit_spread", "protective_put", "collar"),
                allowed=("calendar_spread",),
                needs_review=("bull_call_debit_spread", "put_credit_spread", "iron_condor", "iron_butterfly", "diagonal_spread", "covered_call"),
            ),
            "bonds": _asset(
                status="preferred",
                directional_bias="bullish_duration",
                thesis="falling inflation and slowing growth can support duration exposure",
                preferred=("bull_call_debit_spread", "put_credit_spread", "diagonal_spread"),
                allowed=("calendar_spread", "collar"),
                needs_review=("bear_put_debit_spread", "call_credit_spread", "iron_condor", "iron_butterfly", "protective_put", "covered_call"),
            ),
            "credit": _asset(
                status="needs_review",
                directional_bias="defensive",
                thesis="slowdown can pressure credit spreads despite lower rates",
                preferred=("bear_put_debit_spread", "call_credit_spread", "protective_put", "collar"),
                allowed=("calendar_spread",),
                needs_review=("bull_call_debit_spread", "put_credit_spread", "iron_condor", "iron_butterfly", "diagonal_spread", "covered_call"),
            ),
            "commodities": _asset(
                status="needs_review",
                directional_bias="bearish_or_selective",
                thesis="falling inflation and weak growth can pressure cyclical commodities",
                preferred=("bear_put_debit_spread", "call_credit_spread"),
                allowed=("calendar_spread", "collar"),
                needs_review=("bull_call_debit_spread", "put_credit_spread", "iron_condor", "iron_butterfly", "diagonal_spread", "protective_put", "covered_call"),
            ),
            "currencies": _asset(
                status="allowed",
                directional_bias="safe_haven_or_rates_sensitive",
                thesis="currency setups depend on relative central-bank and safe-haven behavior",
                preferred=("calendar_spread",),
                allowed=("bull_call_debit_spread", "bear_put_debit_spread", "diagonal_spread", "collar"),
                needs_review=("put_credit_spread", "call_credit_spread", "iron_condor", "iron_butterfly", "protective_put", "covered_call"),
            ),
            "volatility": _asset(
                status="needs_review",
                directional_bias="volatility_upside_risk",
                thesis="slowdown can raise volatility and hedging demand",
                preferred=("calendar_spread", "collar", "protective_put"),
                allowed=("bull_call_debit_spread", "diagonal_spread"),
                needs_review=("bear_put_debit_spread", "put_credit_spread", "call_credit_spread", "iron_condor", "iron_butterfly", "covered_call"),
            ),
        },
        "neutral": {
            "equities": _asset(
                status="allowed",
                directional_bias="neutral_to_selective",
                thesis="neutral regime requires asset behavior confirmation",
                preferred=("iron_condor", "calendar_spread", "covered_call"),
                allowed=("bull_call_debit_spread", "bear_put_debit_spread", "put_credit_spread", "call_credit_spread", "collar"),
                needs_review=("iron_butterfly", "diagonal_spread", "protective_put"),
            ),
            "bonds": _asset(
                status="allowed",
                directional_bias="neutral",
                thesis="neutral regime favors range or confirmation-based duration setups",
                preferred=("calendar_spread", "iron_condor"),
                allowed=("bull_call_debit_spread", "bear_put_debit_spread", "put_credit_spread", "call_credit_spread", "collar"),
                needs_review=("iron_butterfly", "diagonal_spread", "protective_put", "covered_call"),
            ),
            "credit": _asset(
                status="allowed",
                directional_bias="income_with_confirmation",
                thesis="neutral backdrop can support credit income if spreads and liquidity confirm",
                preferred=("put_credit_spread", "iron_condor", "calendar_spread"),
                allowed=("bull_call_debit_spread", "call_credit_spread", "covered_call", "collar"),
                needs_review=("bear_put_debit_spread", "iron_butterfly", "diagonal_spread", "protective_put"),
            ),
            "commodities": _asset(
                status="allowed",
                directional_bias="selective",
                thesis="commodity exposure needs trend or range confirmation",
                preferred=("calendar_spread", "iron_condor"),
                allowed=("bull_call_debit_spread", "bear_put_debit_spread", "put_credit_spread", "call_credit_spread", "collar"),
                needs_review=("iron_butterfly", "diagonal_spread", "protective_put", "covered_call"),
            ),
            "currencies": _asset(
                status="allowed",
                directional_bias="selective",
                thesis="currency setups require trend/range confirmation",
                preferred=("calendar_spread",),
                allowed=("bull_call_debit_spread", "bear_put_debit_spread", "diagonal_spread", "collar"),
                needs_review=("put_credit_spread", "call_credit_spread", "iron_condor", "iron_butterfly", "protective_put", "covered_call"),
            ),
            "volatility": _asset(
                status="needs_review",
                directional_bias="review_only",
                thesis="standalone volatility exposure remains review-only",
                preferred=(),
                allowed=("calendar_spread",),
                needs_review=("bull_call_debit_spread", "bear_put_debit_spread", "put_credit_spread", "call_credit_spread", "iron_condor", "iron_butterfly", "diagonal_spread", "protective_put", "collar", "covered_call"),
            ),
        },
        "range_bound": {},
        "mixed": {
            "equities": _asset(
                status="needs_review",
                directional_bias="mixed",
                thesis="mixed regime requires asset-level confirmation before adding risk",
                preferred=("calendar_spread", "collar"),
                allowed=("bull_call_debit_spread", "bear_put_debit_spread", "put_credit_spread", "call_credit_spread", "iron_condor", "covered_call"),
                needs_review=("iron_butterfly", "diagonal_spread", "protective_put"),
            ),
            "bonds": _asset(
                status="needs_review",
                directional_bias="mixed",
                thesis="duration exposure requires rates and trend confirmation",
                preferred=("calendar_spread", "collar"),
                allowed=("bull_call_debit_spread", "bear_put_debit_spread", "put_credit_spread", "call_credit_spread", "iron_condor"),
                needs_review=("iron_butterfly", "diagonal_spread", "protective_put", "covered_call"),
            ),
            "credit": _asset(
                status="needs_review",
                directional_bias="mixed",
                thesis="credit exposure requires spread and liquidity confirmation",
                preferred=("calendar_spread", "collar"),
                allowed=("bull_call_debit_spread", "bear_put_debit_spread", "put_credit_spread", "call_credit_spread", "iron_condor", "covered_call"),
                needs_review=("iron_butterfly", "diagonal_spread", "protective_put"),
            ),
            "commodities": _asset(
                status="needs_review",
                directional_bias="mixed",
                thesis="commodity exposure requires inflation and trend confirmation",
                preferred=("calendar_spread", "collar"),
                allowed=("bull_call_debit_spread", "bear_put_debit_spread", "put_credit_spread", "call_credit_spread", "iron_condor"),
                needs_review=("iron_butterfly", "diagonal_spread", "protective_put", "covered_call"),
            ),
            "currencies": _asset(
                status="needs_review",
                directional_bias="mixed",
                thesis="currency exposure requires trend and relative-rate confirmation",
                preferred=("calendar_spread",),
                allowed=("bull_call_debit_spread", "bear_put_debit_spread", "diagonal_spread", "collar"),
                needs_review=("put_credit_spread", "call_credit_spread", "iron_condor", "iron_butterfly", "protective_put", "covered_call"),
            ),
            "volatility": _asset(
                status="needs_review",
                directional_bias="review_only",
                thesis="mixed regime keeps volatility exposure review-only",
                preferred=(),
                allowed=("calendar_spread", "collar"),
                needs_review=("bull_call_debit_spread", "bear_put_debit_spread", "put_credit_spread", "call_credit_spread", "iron_condor", "iron_butterfly", "diagonal_spread", "protective_put", "covered_call"),
            ),
        },
        "event_risk": {
            "equities": _asset(
                status="needs_review",
                directional_bias="defensive_event_risk",
                thesis="event risk requires review before adding new equity risk",
                preferred=("protective_put", "collar"),
                allowed=("bear_put_debit_spread", "calendar_spread"),
                needs_review=("bull_call_debit_spread", "put_credit_spread", "call_credit_spread", "iron_condor", "iron_butterfly", "diagonal_spread", "covered_call"),
            ),
            "bonds": _asset(
                status="needs_review",
                directional_bias="event_sensitive",
                thesis="event risk can create rate and duration gaps",
                preferred=("calendar_spread", "collar"),
                allowed=("bull_call_debit_spread", "bear_put_debit_spread", "diagonal_spread"),
                needs_review=("put_credit_spread", "call_credit_spread", "iron_condor", "iron_butterfly", "protective_put", "covered_call"),
            ),
            "credit": _asset(
                status="needs_review",
                directional_bias="defensive_event_risk",
                thesis="event risk can gap credit spreads",
                preferred=("protective_put", "collar", "bear_put_debit_spread"),
                allowed=("calendar_spread", "call_credit_spread"),
                needs_review=("bull_call_debit_spread", "put_credit_spread", "iron_condor", "iron_butterfly", "diagonal_spread", "covered_call"),
            ),
            "commodities": _asset(
                status="needs_review",
                directional_bias="event_sensitive",
                thesis="event risk can create commodity gaps and volatility shocks",
                preferred=("collar", "calendar_spread"),
                allowed=("bull_call_debit_spread", "bear_put_debit_spread", "diagonal_spread"),
                needs_review=("put_credit_spread", "call_credit_spread", "iron_condor", "iron_butterfly", "protective_put", "covered_call"),
            ),
            "currencies": _asset(
                status="needs_review",
                directional_bias="event_sensitive",
                thesis="currency event risk requires manual review",
                preferred=("calendar_spread", "collar"),
                allowed=("bull_call_debit_spread", "bear_put_debit_spread", "diagonal_spread"),
                needs_review=("put_credit_spread", "call_credit_spread", "iron_condor", "iron_butterfly", "protective_put", "covered_call"),
            ),
            "volatility": _asset(
                status="needs_review",
                directional_bias="event_risk_review_only",
                thesis="volatility exposure around events requires manual review",
                preferred=("calendar_spread", "collar"),
                allowed=("bull_call_debit_spread", "diagonal_spread", "protective_put"),
                needs_review=("bear_put_debit_spread", "put_credit_spread", "call_credit_spread", "iron_condor", "iron_butterfly", "covered_call"),
            ),
        },
    }

    templates["risk_on"] = templates["goldilocks"]
    templates["risk_off"] = templates["deflationary_slowdown"]
    templates["range_bound"] = templates["neutral"]

    # Composite macro taxonomy aliases. Keep the explicit composite labels
    # as normalized_regime values while routing them to the closest existing
    # asset-class policy template.
    templates["reflation"] = templates["overheating"]
    templates["late_cycle_overheating"] = templates["overheating"]
    templates["disinflationary_slowdown"] = templates["deflationary_slowdown"]
    templates["deflationary_shock"] = templates["deflationary_slowdown"]
    templates["credit_stress"] = templates["risk_off"]
    templates["liquidity_stress"] = templates["risk_off"]
    templates["risk_off_transition"] = templates["risk_off"]
    templates["neutral_mixed"] = templates["mixed"]

    return templates.get(normalized_regime, templates["mixed"])


def _asset(
    *,
    status: str,
    directional_bias: str,
    thesis: str,
    preferred: Sequence[str],
    allowed: Sequence[str],
    needs_review: Sequence[str],
) -> dict[str, Any]:
    return {
        "asset_class_status": status,
        "directional_bias": directional_bias,
        "thesis": thesis,
        "preferred": list(preferred),
        "allowed": list(allowed),
        "needs_review": list(needs_review),
    }


def _build_asset_class_details(
    *,
    template: Mapping[str, Any],
    regime_input: RegimeAssetClassPolicyInput,
) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []

    for asset_class in sorted(ASSET_CLASSES):
        raw_asset_policy = template.get(asset_class)
        if not isinstance(raw_asset_policy, Mapping):
            raw_asset_policy = _fallback_asset_policy()

        adjusted = _adjusted_asset_policy(
            asset_class=asset_class,
            asset_policy=raw_asset_policy,
            regime_input=regime_input,
        )
        strategy_policy = _complete_strategy_policy(
            preferred=adjusted["preferred"],
            allowed=adjusted["allowed"],
            needs_review=adjusted["needs_review"],
        )

        details.append(
            {
                "asset_class": asset_class,
                "asset_class_status": adjusted["asset_class_status"],
                "directional_bias": adjusted["directional_bias"],
                "thesis": adjusted["thesis"],
                "strategy_policy": strategy_policy,
                "warnings": _dedupe_strings(adjusted["warnings"]),
                "reasons": _dedupe_strings(adjusted["reasons"]),
            }
        )

    return details


def _fallback_asset_policy() -> dict[str, Any]:
    return _asset(
        status="needs_review",
        directional_bias="unknown",
        thesis="asset-class policy not defined for this regime",
        preferred=(),
        allowed=("calendar_spread", "collar"),
        needs_review=(
            "bull_call_debit_spread",
            "bear_put_debit_spread",
            "put_credit_spread",
            "call_credit_spread",
            "iron_condor",
            "iron_butterfly",
            "diagonal_spread",
            "protective_put",
            "covered_call",
        ),
    )


def _adjusted_asset_policy(
    *,
    asset_class: str,
    asset_policy: Mapping[str, Any],
    regime_input: RegimeAssetClassPolicyInput,
) -> dict[str, Any]:
    status = _clean(asset_policy.get("asset_class_status")) or "needs_review"
    if status not in VALID_POLICY_STATUSES:
        status = "needs_review"

    preferred = set(_strings(asset_policy.get("preferred")))
    allowed = set(_strings(asset_policy.get("allowed")))
    needs_review = set(_strings(asset_policy.get("needs_review")))
    warnings: list[str] = []
    reasons: list[str] = [f"base asset-class policy: {status}"]

    if regime_input.event_risk:
        preferred, allowed, needs_review = _move_to_review(
            preferred=preferred,
            allowed=allowed,
            needs_review=needs_review,
            strategies=PREMIUM_SELLING_STRATEGIES,
        )
        if status == "preferred":
            status = "allowed"
        if asset_class in {"equities", "credit", "volatility"}:
            status = "needs_review"
        warnings.append("event risk requires manual review before adding asset-class risk")
        reasons.append("event risk downgraded premium and gap-sensitive exposure")

    liquidity_regime = _clean(regime_input.liquidity_regime)
    if liquidity_regime in {"liquidity_contracting", "illiquid", "poor_liquidity"}:
        if status == "preferred":
            status = "allowed"
        elif status == "allowed":
            status = "needs_review"
        preferred, allowed, needs_review = _downgrade_strategy_set(
            preferred=preferred,
            allowed=allowed,
            needs_review=needs_review,
            strategies=PREMIUM_SELLING_STRATEGIES,
        )
        warnings.append("contracting liquidity requires reduced asset-class risk posture")
        reasons.append("liquidity contraction downgraded premium and risk-sensitive exposure")

    volatility_regime = _clean(regime_input.volatility_regime)
    if volatility_regime in {"high_volatility", "volatility_expansion", "high_iv"}:
        preferred, allowed, needs_review = _downgrade_strategy_set(
            preferred=preferred,
            allowed=allowed,
            needs_review=needs_review,
            strategies=DIRECTIONAL_DEBIT_STRATEGIES,
        )
        warnings.append("high volatility requires tighter asset-class confirmation")
        reasons.append("high volatility downgraded directional debit exposure")

    if volatility_regime in {"low_volatility", "volatility_compression", "low_iv"}:
        preferred, allowed, needs_review = _downgrade_strategy_set(
            preferred=preferred,
            allowed=allowed,
            needs_review=needs_review,
            strategies=PREMIUM_SELLING_STRATEGIES,
        )
        warnings.append("low volatility reduces premium-selling attractiveness")
        reasons.append("low volatility downgraded defined-credit exposure")

    if _clean(regime_input.risk_environment) == "risk_off" and asset_class in {"equities", "credit"}:
        if status == "preferred":
            status = "allowed"
        preferred.update(DEFENSIVE_STRATEGIES & needs_review)
        needs_review.difference_update(DEFENSIVE_STRATEGIES)
        warnings.append("risk-off environment favors defensive confirmation")
        reasons.append("risk-off overlay promoted defensive strategies")

    return {
        "asset_class_status": status,
        "directional_bias": _string(asset_policy.get("directional_bias")),
        "thesis": _string(asset_policy.get("thesis")),
        "preferred": sorted(preferred),
        "allowed": sorted(allowed),
        "needs_review": sorted(needs_review),
        "warnings": warnings,
        "reasons": reasons,
    }


def _complete_strategy_policy(
    *,
    preferred: Sequence[str],
    allowed: Sequence[str],
    needs_review: Sequence[str],
) -> dict[str, list[str]]:
    catalog_strategies = {definition.strategy for definition in build_option_strategy_catalog()}

    preferred_set = {strategy for strategy in _strings(preferred) if strategy in catalog_strategies}
    allowed_set = {
        strategy
        for strategy in _strings(allowed)
        if strategy in catalog_strategies and strategy not in preferred_set
    }
    review_set = {
        strategy
        for strategy in _strings(needs_review)
        if strategy in catalog_strategies
        and strategy not in preferred_set
        and strategy not in allowed_set
    }
    review_set.update(catalog_strategies - preferred_set - allowed_set - review_set)

    return {
        "preferred": sorted(preferred_set),
        "allowed": sorted(allowed_set),
        "needs_review": sorted(review_set),
        "blocked": sorted(UNDEFINED_RISK_STRATEGIES),
    }


def _asset_class_policy_summary(detail: Mapping[str, Any]) -> dict[str, Any]:
    strategy_policy = detail.get("strategy_policy")
    if not isinstance(strategy_policy, Mapping):
        strategy_policy = {}

    return {
        "asset_class_status": detail.get("asset_class_status"),
        "directional_bias": detail.get("directional_bias"),
        "thesis": detail.get("thesis"),
        "preferred_count": len(_strings(strategy_policy.get("preferred"))),
        "allowed_count": len(_strings(strategy_policy.get("allowed"))),
        "needs_review_count": len(_strings(strategy_policy.get("needs_review"))),
        "blocked_count": len(_strings(strategy_policy.get("blocked"))),
    }


def _policy_warnings(
    *,
    regime_input: RegimeAssetClassPolicyInput,
    normalized_regime: str,
    asset_details: Sequence[Mapping[str, Any]],
) -> list[str]:
    warnings: list[str] = []

    if normalized_regime == "mixed":
        warnings.append("mixed or unknown regime requires asset-class confirmation")

    if regime_input.event_risk:
        warnings.append("event risk requires manual review before adding asset-class risk")

    if _clean(regime_input.liquidity_regime) in {
        "liquidity_contracting",
        "illiquid",
        "poor_liquidity",
    }:
        warnings.append("contracting liquidity requires reduced asset-class risk posture")

    if _clean(regime_input.volatility_regime) in {
        "high_volatility",
        "volatility_expansion",
        "high_iv",
    }:
        warnings.append("high volatility requires tighter asset-class confirmation")

    if not any(detail.get("asset_class_status") == "preferred" for detail in asset_details):
        warnings.append("no preferred asset classes after regime policy adjustments")

    for detail in asset_details:
        warnings.extend(_strings(detail.get("warnings")))

    return _dedupe_strings(warnings)


def _blocked_policy(
    regime_input: RegimeAssetClassPolicyInput,
    blocked_reasons: Sequence[str],
) -> dict[str, Any]:
    return {
        "artifact_type": "regime_asset_class_policy",
        "status": "blocked",
        "is_ready": False,
        "regime_label": regime_input.regime_label,
        "normalized_regime": None,
        "risk_environment": regime_input.risk_environment,
        "volatility_regime": regime_input.volatility_regime,
        "liquidity_regime": regime_input.liquidity_regime,
        "growth_regime": regime_input.growth_regime,
        "inflation_regime": regime_input.inflation_regime,
        "rates_regime": regime_input.rates_regime,
        "event_risk": regime_input.event_risk,
        "asset_class_policy": {},
        "asset_class_policy_details": [],
        "warnings": [],
        "blocked_reasons": list(blocked_reasons),
        "excluded": EXCLUDED_ACTIONS,
        "metadata": dict(regime_input.metadata),
    }


def _move_to_review(
    *,
    preferred: set[str],
    allowed: set[str],
    needs_review: set[str],
    strategies: set[str],
) -> tuple[set[str], set[str], set[str]]:
    affected = (preferred | allowed) & strategies
    preferred = preferred - affected
    allowed = allowed - affected
    needs_review = needs_review | affected
    return preferred, allowed, needs_review


def _downgrade_strategy_set(
    *,
    preferred: set[str],
    allowed: set[str],
    needs_review: set[str],
    strategies: set[str],
) -> tuple[set[str], set[str], set[str]]:
    preferred_affected = preferred & strategies
    allowed_affected = allowed & strategies
    preferred = preferred - preferred_affected
    allowed = (allowed - allowed_affected) | preferred_affected
    needs_review = needs_review | allowed_affected
    return preferred, allowed, needs_review


def normalize_asset_class(value: Any) -> str:
    cleaned = _clean(value)
    if cleaned in ASSET_CLASSES:
        return cleaned

    return ASSET_CLASS_ALIASES.get(cleaned, cleaned)


def _string(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()


def _optional_string(value: Any) -> str | None:
    text = _string(value)
    return text or None


def _clean(value: Any) -> str:
    return _string(value).lower()


def _strings(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []

    return [_clean(item) for item in value if _clean(item)]


def _dedupe_strings(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []

    for value in values:
        cleaned = _clean(value)
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            output.append(cleaned)

    return output


