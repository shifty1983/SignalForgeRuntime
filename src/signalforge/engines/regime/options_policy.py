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

EVENT_RISK_REVIEW_STRATEGIES = {
    "put_credit_spread",
    "call_credit_spread",
    "iron_condor",
    "iron_butterfly",
    "covered_call",
}

HIGH_VOL_REVIEW_STRATEGIES = {
    "bull_call_debit_spread",
    "bear_put_debit_spread",
    "calendar_spread",
    "diagonal_spread",
}

LOW_VOL_REVIEW_STRATEGIES = {
    "put_credit_spread",
    "call_credit_spread",
    "iron_condor",
    "iron_butterfly",
    "covered_call",
}


@dataclass(frozen=True)
class RegimeOptionsPolicyInput:
    """
    Options-aware regime context for weekly planning and maintenance.

    This module translates macro/regime labels into defined-risk option strategy
    policy. It does not generate contracts, choose strikes/expirations, model
    fills, route orders, or create automatic maintenance/defense trades.
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


def build_regime_options_policy(
    regime_input: RegimeOptionsPolicyInput | Mapping[str, Any],
) -> dict[str, Any]:
    """
    Convert regime context into a defined-risk options strategy policy.

    Output strategy buckets:
    - preferred: regime-aligned defined-risk strategies
    - allowed: usable, but not the first expression of the regime
    - needs_review: usable only with asset/option/portfolio confirmation
    - blocked: hard-blocked undefined-risk strategies plus invalid conditions
    """

    parsed_input = _parse_regime_input(regime_input)
    errors = _validate_input(parsed_input)
    if errors:
        return _blocked_policy(parsed_input, errors)

    normalized_regime = _normalized_regime(parsed_input)
    template = _policy_template(normalized_regime)

    strategy_details = _build_strategy_details(
        template=template,
        regime_input=parsed_input,
    )

    strategy_policy = _bucket_strategy_details(strategy_details)
    warnings = _policy_warnings(
        regime_input=parsed_input,
        normalized_regime=normalized_regime,
        strategy_details=strategy_details,
    )

    status = "needs_review" if warnings else "ready"

    return {
        "artifact_type": "regime_options_policy",
        "status": status,
        "is_ready": status == "ready",
        "regime_label": parsed_input.regime_label,
        "normalized_regime": normalized_regime,
        "risk_environment": parsed_input.risk_environment,
        "volatility_regime": parsed_input.volatility_regime,
        "liquidity_regime": parsed_input.liquidity_regime,
        "event_risk": parsed_input.event_risk,
        "directional_bias": template["directional_bias"],
        "premium_preference": _premium_preference(parsed_input, template),
        "risk_posture": _risk_posture(parsed_input, template),
        "maintenance_posture": _maintenance_posture(parsed_input, template),
        "max_new_trade_bias": template["max_new_trade_bias"],
        "strategy_policy": strategy_policy,
        "strategy_policy_details": strategy_details,
        "warnings": warnings,
        "blocked_reasons": [],
        "excluded": EXCLUDED_ACTIONS,
        "metadata": dict(parsed_input.metadata),
    }


def build_regime_options_policy_from_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """
    Convenience wrapper for callers that already have row-shaped regime output.
    """

    return build_regime_options_policy(row)


def _parse_regime_input(
    regime_input: RegimeOptionsPolicyInput | Mapping[str, Any],
) -> RegimeOptionsPolicyInput:
    if isinstance(regime_input, RegimeOptionsPolicyInput):
        return regime_input

    if not isinstance(regime_input, Mapping):
        return RegimeOptionsPolicyInput(regime_label="")

    metadata = regime_input.get("metadata")
    if not isinstance(metadata, Mapping):
        metadata = {}

    return RegimeOptionsPolicyInput(
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


def _validate_input(regime_input: RegimeOptionsPolicyInput) -> list[str]:
    errors: list[str] = []

    if not regime_input.regime_label.strip():
        errors.append("regime_label is required")

    return errors


def _normalized_regime(regime_input: RegimeOptionsPolicyInput) -> str:
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


def _policy_template(normalized_regime: str) -> dict[str, Any]:
    templates: dict[str, dict[str, Any]] = {
        "goldilocks": {
            "directional_bias": "bullish",
            "premium_preference": "debit_or_selective_credit",
            "risk_posture": "normal",
            "maintenance_posture": "standard_review",
            "max_new_trade_bias": "bullish_or_neutral",
            "preferred": [
                "bull_call_debit_spread",
                "put_credit_spread",
                "diagonal_spread",
            ],
            "allowed": [
                "calendar_spread",
                "covered_call",
                "collar",
            ],
            "needs_review": [
                "iron_condor",
                "iron_butterfly",
                "bear_put_debit_spread",
                "call_credit_spread",
                "protective_put",
            ],
        },
        "risk_on": {
            "directional_bias": "bullish",
            "premium_preference": "debit_or_selective_credit",
            "risk_posture": "normal",
            "maintenance_posture": "standard_review",
            "max_new_trade_bias": "bullish",
            "preferred": [
                "bull_call_debit_spread",
                "put_credit_spread",
            ],
            "allowed": [
                "diagonal_spread",
                "calendar_spread",
                "covered_call",
                "collar",
            ],
            "needs_review": [
                "iron_condor",
                "iron_butterfly",
                "bear_put_debit_spread",
                "call_credit_spread",
                "protective_put",
            ],
        },
        "overheating": {
            "directional_bias": "bullish_with_volatility_risk",
            "premium_preference": "selective_defined_credit_or_tight_debit",
            "risk_posture": "reduced",
            "maintenance_posture": "faster_review_on_volatility_expansion",
            "max_new_trade_bias": "bullish_or_income_with_review",
            "preferred": [
                "put_credit_spread",
                "covered_call",
                "collar",
            ],
            "allowed": [
                "bull_call_debit_spread",
                "calendar_spread",
                "diagonal_spread",
                "iron_condor",
            ],
            "needs_review": [
                "iron_butterfly",
                "bear_put_debit_spread",
                "call_credit_spread",
                "protective_put",
            ],
        },
        "stagflation": {
            "directional_bias": "bearish_or_defensive",
            "premium_preference": "defensive_or_selective_defined_credit",
            "risk_posture": "defensive",
            "maintenance_posture": "tighten_risk_and_defense_review",
            "max_new_trade_bias": "bearish_or_defensive",
            "preferred": [
                "bear_put_debit_spread",
                "call_credit_spread",
                "protective_put",
                "collar",
            ],
            "allowed": [
                "calendar_spread",
                "covered_call",
            ],
            "needs_review": [
                "bull_call_debit_spread",
                "put_credit_spread",
                "iron_condor",
                "iron_butterfly",
                "diagonal_spread",
            ],
        },
        "risk_off": {
            "directional_bias": "bearish_or_defensive",
            "premium_preference": "defensive_debit_or_defined_credit",
            "risk_posture": "defensive",
            "maintenance_posture": "tighten_risk_and_defense_review",
            "max_new_trade_bias": "bearish_or_defensive",
            "preferred": [
                "bear_put_debit_spread",
                "call_credit_spread",
                "protective_put",
                "collar",
            ],
            "allowed": [
                "calendar_spread",
                "covered_call",
            ],
            "needs_review": [
                "bull_call_debit_spread",
                "put_credit_spread",
                "iron_condor",
                "iron_butterfly",
                "diagonal_spread",
            ],
        },
        "deflationary_slowdown": {
            "directional_bias": "bearish_or_defensive",
            "premium_preference": "defensive_debit_first",
            "risk_posture": "defensive",
            "maintenance_posture": "tighten_risk_and_defense_review",
            "max_new_trade_bias": "defensive_first",
            "preferred": [
                "bear_put_debit_spread",
                "protective_put",
                "collar",
            ],
            "allowed": [
                "call_credit_spread",
                "calendar_spread",
            ],
            "needs_review": [
                "bull_call_debit_spread",
                "put_credit_spread",
                "iron_condor",
                "iron_butterfly",
                "diagonal_spread",
                "covered_call",
            ],
        },
        "neutral": {
            "directional_bias": "neutral",
            "premium_preference": "balanced_debit_or_credit",
            "risk_posture": "normal",
            "maintenance_posture": "standard_review",
            "max_new_trade_bias": "balanced",
            "preferred": [
                "iron_condor",
                "calendar_spread",
                "covered_call",
            ],
            "allowed": [
                "bull_call_debit_spread",
                "bear_put_debit_spread",
                "put_credit_spread",
                "call_credit_spread",
                "collar",
            ],
            "needs_review": [
                "iron_butterfly",
                "diagonal_spread",
                "protective_put",
            ],
        },
        "range_bound": {
            "directional_bias": "neutral_range",
            "premium_preference": "defined_credit_or_time_spread",
            "risk_posture": "normal",
            "maintenance_posture": "watch_tested_short_strikes",
            "max_new_trade_bias": "neutral",
            "preferred": [
                "iron_condor",
                "calendar_spread",
                "iron_butterfly",
            ],
            "allowed": [
                "put_credit_spread",
                "call_credit_spread",
                "covered_call",
                "collar",
            ],
            "needs_review": [
                "bull_call_debit_spread",
                "bear_put_debit_spread",
                "diagonal_spread",
                "protective_put",
            ],
        },
        "mixed": {
            "directional_bias": "mixed",
            "premium_preference": "balanced_defined_risk_only",
            "risk_posture": "reduced",
            "maintenance_posture": "review_before_adding_risk",
            "max_new_trade_bias": "selective",
            "preferred": [
                "calendar_spread",
                "collar",
            ],
            "allowed": [
                "bull_call_debit_spread",
                "bear_put_debit_spread",
                "put_credit_spread",
                "call_credit_spread",
                "iron_condor",
                "covered_call",
            ],
            "needs_review": [
                "iron_butterfly",
                "diagonal_spread",
                "protective_put",
            ],
        },
        "event_risk": {
            "directional_bias": "event_risk",
            "premium_preference": "manual_review_required",
            "risk_posture": "defensive",
            "maintenance_posture": "event_risk_review_required",
            "max_new_trade_bias": "avoid_new_risk_without_review",
            "preferred": [
                "protective_put",
                "collar",
            ],
            "allowed": [
                "bear_put_debit_spread",
                "calendar_spread",
            ],
            "needs_review": [
                "bull_call_debit_spread",
                "put_credit_spread",
                "call_credit_spread",
                "iron_condor",
                "iron_butterfly",
                "diagonal_spread",
                "covered_call",
            ],
        },
    }

    # Composite macro taxonomy aliases. Keep the explicit composite labels
    # as normalized_regime values while reusing the closest existing policy
    # templates until each composite state has a fully bespoke policy.
    templates["reflation"] = templates["overheating"]
    templates["late_cycle_overheating"] = templates["overheating"]
    templates["disinflationary_slowdown"] = templates["deflationary_slowdown"]
    templates["deflationary_shock"] = templates["risk_off"]
    templates["credit_stress"] = templates["risk_off"]
    templates["liquidity_stress"] = templates["risk_off"]
    templates["risk_off_transition"] = templates["risk_off"]
    templates["neutral_mixed"] = templates["mixed"]

    return templates.get(normalized_regime, templates["mixed"])


def _build_strategy_details(
    *,
    template: Mapping[str, Any],
    regime_input: RegimeOptionsPolicyInput,
) -> list[dict[str, Any]]:
    catalog = build_option_strategy_catalog()
    base_status_by_strategy = _base_status_by_strategy(template)
    details: list[dict[str, Any]] = []

    for definition in catalog:
        base_status = base_status_by_strategy.get(definition.strategy, "needs_review")
        status, reasons = _adjusted_strategy_status(
            strategy=definition.strategy,
            base_status=base_status,
            regime_input=regime_input,
        )

        details.append(
            {
                "strategy": definition.strategy,
                "display_name": definition.display_name,
                "direction": definition.direction,
                "risk_profile": definition.risk_profile,
                "status": status,
                "reasons": reasons,
                "best_setups": list(definition.best_setups),
            }
        )

    for strategy in sorted(UNDEFINED_RISK_STRATEGIES):
        details.append(
            {
                "strategy": strategy,
                "display_name": strategy.replace("_", " ").title(),
                "direction": "undefined",
                "risk_profile": "undefined_risk",
                "status": "blocked",
                "reasons": ["undefined risk strategies are hard-blocked"],
                "best_setups": [],
            }
        )

    return sorted(details, key=lambda item: (item["status"], item["strategy"]))


def _base_status_by_strategy(template: Mapping[str, Any]) -> dict[str, str]:
    status_by_strategy: dict[str, str] = {}

    for status in ("preferred", "allowed", "needs_review"):
        for strategy in _string_list(template.get(status)):
            status_by_strategy[strategy] = status

    for strategy in UNDEFINED_RISK_STRATEGIES:
        status_by_strategy[strategy] = "blocked"

    return status_by_strategy


def _adjusted_strategy_status(
    *,
    strategy: str,
    base_status: str,
    regime_input: RegimeOptionsPolicyInput,
) -> tuple[str, list[str]]:
    reasons = [f"base regime policy: {base_status}"]
    status = base_status if base_status in VALID_POLICY_STATUSES else "needs_review"

    if regime_input.event_risk and strategy in EVENT_RISK_REVIEW_STRATEGIES:
        if status in {"preferred", "allowed"}:
            status = "needs_review"
        reasons.append("event risk requires manual review before adding or holding premium risk")

    volatility_regime = _clean(regime_input.volatility_regime)
    if volatility_regime in {"high_volatility", "volatility_expansion", "high_iv"}:
        if strategy in HIGH_VOL_REVIEW_STRATEGIES and status == "preferred":
            status = "allowed"
        reasons.append("high volatility favors tighter risk and closer review")

    if volatility_regime in {"low_volatility", "volatility_compression", "low_iv"}:
        if strategy in LOW_VOL_REVIEW_STRATEGIES and status == "preferred":
            status = "allowed"
        reasons.append("low volatility reduces premium-selling attractiveness")

    liquidity_regime = _clean(regime_input.liquidity_regime)
    if liquidity_regime in {"liquidity_contracting", "illiquid", "poor_liquidity"}:
        if status == "preferred":
            status = "allowed"
        elif status == "allowed":
            status = "needs_review"
        reasons.append("contracting liquidity requires reduced risk posture")

    return status, reasons


def _bucket_strategy_details(
    strategy_details: Sequence[Mapping[str, Any]],
) -> dict[str, list[str]]:
    buckets = {
        "preferred": [],
        "allowed": [],
        "needs_review": [],
        "blocked": [],
    }

    for detail in strategy_details:
        status = str(detail.get("status", "needs_review"))
        strategy = str(detail.get("strategy", ""))
        if status not in buckets or not strategy:
            buckets["needs_review"].append(strategy)
            continue

        buckets[status].append(strategy)

    return {key: sorted(values) for key, values in buckets.items()}


def _policy_warnings(
    *,
    regime_input: RegimeOptionsPolicyInput,
    normalized_regime: str,
    strategy_details: Sequence[Mapping[str, Any]],
) -> list[str]:
    warnings: list[str] = []

    if normalized_regime == "mixed":
        warnings.append("mixed or unknown regime requires selective defined-risk review")

    if regime_input.event_risk:
        warnings.append("event risk requires manual review before adding premium risk")

    volatility_regime = _clean(regime_input.volatility_regime)
    if volatility_regime in {"high_volatility", "volatility_expansion", "high_iv"}:
        warnings.append("high volatility requires tighter sizing and maintenance review")

    if volatility_regime in {"low_volatility", "volatility_compression", "low_iv"}:
        warnings.append("low volatility can reduce defined-credit attractiveness")

    liquidity_regime = _clean(regime_input.liquidity_regime)
    if liquidity_regime in {"liquidity_contracting", "illiquid", "poor_liquidity"}:
        warnings.append("contracting liquidity requires reduced risk posture")

    if not any(detail.get("status") == "preferred" for detail in strategy_details):
        warnings.append("no preferred defined-risk option strategies after adjustments")

    return _dedupe_strings(warnings)


def _premium_preference(
    regime_input: RegimeOptionsPolicyInput,
    template: Mapping[str, Any],
) -> str:
    volatility_regime = _clean(regime_input.volatility_regime)

    if regime_input.event_risk:
        return "manual_review_required"

    if volatility_regime in {"high_volatility", "volatility_expansion", "high_iv"}:
        return "defined_credit_or_defensive_with_tighter_review"

    if volatility_regime in {"low_volatility", "volatility_compression", "low_iv"}:
        return "defined_debit_or_time_spread_preferred"

    return str(template["premium_preference"])


def _risk_posture(
    regime_input: RegimeOptionsPolicyInput,
    template: Mapping[str, Any],
) -> str:
    liquidity_regime = _clean(regime_input.liquidity_regime)

    if regime_input.event_risk:
        return "defensive"

    if liquidity_regime in {"liquidity_contracting", "illiquid", "poor_liquidity"}:
        return "reduced"

    return str(template["risk_posture"])


def _maintenance_posture(
    regime_input: RegimeOptionsPolicyInput,
    template: Mapping[str, Any],
) -> str:
    if regime_input.event_risk:
        return "event_risk_review_required"

    if _risk_posture(regime_input, template) == "defensive":
        return "tighten_risk_and_defense_review"

    return str(template["maintenance_posture"])


def _blocked_policy(
    regime_input: RegimeOptionsPolicyInput,
    blocked_reasons: Sequence[str],
) -> dict[str, Any]:
    return {
        "artifact_type": "regime_options_policy",
        "status": "blocked",
        "is_ready": False,
        "regime_label": regime_input.regime_label,
        "normalized_regime": None,
        "risk_environment": regime_input.risk_environment,
        "volatility_regime": regime_input.volatility_regime,
        "liquidity_regime": regime_input.liquidity_regime,
        "event_risk": regime_input.event_risk,
        "directional_bias": None,
        "premium_preference": None,
        "risk_posture": None,
        "maintenance_posture": None,
        "max_new_trade_bias": None,
        "strategy_policy": {
            "preferred": [],
            "allowed": [],
            "needs_review": [],
            "blocked": sorted(UNDEFINED_RISK_STRATEGIES),
        },
        "strategy_policy_details": [],
        "warnings": [],
        "blocked_reasons": list(blocked_reasons),
        "excluded": EXCLUDED_ACTIONS,
        "metadata": dict(regime_input.metadata),
    }


def _string(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()


def _optional_string(value: Any) -> str | None:
    text = _string(value)
    return text or None


def _clean(value: Any) -> str:
    return _string(value).lower()


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []

    return [_clean(item) for item in value if _clean(item)]


def _dedupe_strings(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []

    for value in values:
        if value not in seen:
            seen.add(value)
            output.append(value)

    return output




