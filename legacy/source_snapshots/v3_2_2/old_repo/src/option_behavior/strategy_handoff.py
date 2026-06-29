from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.option_behavior.diagnostics import diagnose_option_behavior_output


EXCLUDED_ACTIONS = [
    "broker_api_calls",
    "order_routing",
    "order_submission",
    "fills",
    "live_execution",
    "slippage_modeling",
]


VALID_HANDOFF_STATUSES = {
    "ready",
    "needs_review",
    "blocked",
}


def build_option_behavior_strategy_handoff(
    asset_behavior_result: Mapping[str, Any] | None,
    option_behavior_result: Mapping[str, Any] | None,
    options_analytics_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build the pure integration handoff from asset behavior + option behavior
    into strategy candidate generation.

    This does not generate strategies, score expected value, select trades,
    create operation records, write logs, audit results, route orders,
    submit orders, simulate fills, model slippage, or perform live execution.
    """

    warnings: list[str] = []
    blocked_reasons: list[str] = []

    if not isinstance(asset_behavior_result, Mapping):
        return _blocked_handoff(
            blocked_reasons=["invalid asset_behavior_result shape"],
        )

    if not isinstance(option_behavior_result, Mapping):
        return _blocked_handoff(
            blocked_reasons=["invalid option_behavior_result shape"],
        )

    if options_analytics_context is not None and not isinstance(
        options_analytics_context,
        Mapping,
    ):
        return _blocked_handoff(
            blocked_reasons=["invalid options_analytics_context shape"],
        )

    symbol = _extract_symbol(
        asset_behavior_result=asset_behavior_result,
        options_analytics_context=options_analytics_context,
    )

    if symbol is None:
        blocked_reasons.append("missing symbol for option behavior strategy handoff")

    asset_context = _build_asset_behavior_context(asset_behavior_result)

    option_diagnostics = diagnose_option_behavior_output(
        dict(option_behavior_result)
    )

    if not option_diagnostics["passed"]:
        blocked_reasons.extend(
            [
                f"invalid option behavior output: {error}"
                for error in option_diagnostics["errors"]
            ]
        )

    warnings.extend(option_diagnostics["warnings"])

    asset_status = _string_or_none(asset_behavior_result.get("status"))

    if asset_status == "blocked":
        blocked_reasons.append("asset behavior result is blocked")
    elif asset_status == "needs_review":
        warnings.append("asset behavior result needs review")

    option_behavior_state = _string_or_none(
        option_behavior_result.get("option_behavior_state")
    )

    if option_behavior_state == "constrained":
        warnings.append("option behavior state is constrained")

    options_context = _build_options_analytics_context(
        options_analytics_context=options_analytics_context,
    )

    option_context = _build_option_behavior_context(option_behavior_result)

    constraints = _build_strategy_generation_constraints(
        option_behavior_result=option_behavior_result,
        option_behavior_state=option_behavior_state,
    )

    strategy_generation_mode = _strategy_generation_mode(
        blocked_reasons=blocked_reasons,
        option_behavior_state=option_behavior_state,
        constraints=constraints,
    )

    handoff_status = _handoff_status(
        blocked_reasons=blocked_reasons,
        warnings=warnings,
    )

    return {
        "artifact_type": "option_behavior_strategy_handoff",
        "status": handoff_status,
        "handoff_status": handoff_status,
        "is_ready": handoff_status == "ready",
        "symbol": symbol,
        "strategy_generation_mode": strategy_generation_mode,
        "asset_behavior_context": asset_context,
        "options_analytics_context": options_context,
        "option_behavior_context": option_context,
        "strategy_generation_constraints": constraints,
        "warnings": _dedupe_strings(warnings),
        "blocked_reasons": _dedupe_strings(blocked_reasons),
        "source_layers": [
            "asset_behavior",
            "options",
            "option_behavior",
        ],
        "excluded": EXCLUDED_ACTIONS,
    }


def _blocked_handoff(
    blocked_reasons: list[str],
) -> dict[str, Any]:
    return {
        "artifact_type": "option_behavior_strategy_handoff",
        "status": "blocked",
        "handoff_status": "blocked",
        "is_ready": False,
        "symbol": None,
        "strategy_generation_mode": "blocked",
        "asset_behavior_context": {},
        "options_analytics_context": {},
        "option_behavior_context": {},
        "strategy_generation_constraints": [],
        "warnings": [],
        "blocked_reasons": blocked_reasons,
        "source_layers": [
            "asset_behavior",
            "options",
            "option_behavior",
        ],
        "excluded": EXCLUDED_ACTIONS,
    }


def _build_asset_behavior_context(
    asset_behavior_result: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "symbol": _string_or_none(asset_behavior_result.get("symbol")),
        "status": _string_or_none(asset_behavior_result.get("status")),
        "asset_behavior": _first_present_string(
            asset_behavior_result,
            [
                "asset_behavior",
                "behavior",
                "behavior_classification",
                "classification",
                "asset_behavior_state",
            ],
        ),
        "asset_behavior_score": asset_behavior_result.get("asset_behavior_score"),
        "trend_behavior": _string_or_none(asset_behavior_result.get("trend_behavior")),
        "volatility_behavior": _string_or_none(
            asset_behavior_result.get("volatility_behavior")
        ),
        "return_behavior": _string_or_none(asset_behavior_result.get("return_behavior")),
        "drawdown_behavior": _string_or_none(
            asset_behavior_result.get("drawdown_behavior")
        ),
        "correlation_behavior": _string_or_none(
            asset_behavior_result.get("correlation_behavior")
        ),
    }


def _build_options_analytics_context(
    options_analytics_context: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(options_analytics_context, Mapping):
        return {}

    return {
        "symbol": _string_or_none(options_analytics_context.get("symbol")),
        "analytics_status": _string_or_none(options_analytics_context.get("status")),
        "contract_count": options_analytics_context.get("contract_count"),
        "liquidity_regime": _string_or_none(
            options_analytics_context.get("liquidity_regime")
        ),
        "vol_premium_regime": _string_or_none(
            options_analytics_context.get("vol_premium_regime")
        ),
        "skew_regime": _string_or_none(options_analytics_context.get("skew_regime")),
        "term_structure_regime": _string_or_none(
            options_analytics_context.get("term_structure_regime")
        ),
        "source": _string_or_none(options_analytics_context.get("source")),
    }


def _build_option_behavior_context(
    option_behavior_result: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "iv_behavior": _string_or_none(option_behavior_result.get("iv_behavior")),
        "vol_premium_behavior": _string_or_none(
            option_behavior_result.get("vol_premium_behavior")
        ),
        "liquidity_behavior": _string_or_none(
            option_behavior_result.get("liquidity_behavior")
        ),
        "skew_behavior": _string_or_none(option_behavior_result.get("skew_behavior")),
        "term_structure_behavior": _string_or_none(
            option_behavior_result.get("term_structure_behavior")
        ),
        "greek_behavior": _string_or_none(
            option_behavior_result.get("greek_behavior")
        ),
        "option_behavior_score": option_behavior_result.get("option_behavior_score"),
        "option_behavior_state": _string_or_none(
            option_behavior_result.get("option_behavior_state")
        ),
    }


def _build_strategy_generation_constraints(
    option_behavior_result: Mapping[str, Any],
    option_behavior_state: str | None,
) -> list[str]:
    constraints: list[str] = []

    iv_behavior = _string_or_none(option_behavior_result.get("iv_behavior"))
    vol_premium_behavior = _string_or_none(
        option_behavior_result.get("vol_premium_behavior")
    )
    liquidity_behavior = _string_or_none(
        option_behavior_result.get("liquidity_behavior")
    )
    skew_behavior = _string_or_none(option_behavior_result.get("skew_behavior"))
    greek_behavior = _string_or_none(option_behavior_result.get("greek_behavior"))

    if option_behavior_state == "constrained":
        constraints.append("option_behavior_constrained")

    if iv_behavior in {"high_iv", "extreme_iv"}:
        constraints.append("avoid_unfiltered_long_volatility_candidates")

    if vol_premium_behavior == "rich_vol":
        constraints.append("require_vol_premium_awareness")

    if liquidity_behavior == "low_liquidity":
        constraints.append("require_liquidity_review")

    if liquidity_behavior == "untradable_liquidity":
        constraints.append("block_options_candidate_generation")

    if skew_behavior in {"downside_rich_skew", "upside_rich_skew", "distorted_skew"}:
        constraints.append("require_skew_aware_candidate_filtering")

    if greek_behavior in {"elevated_greek_risk", "high_greek_risk"}:
        constraints.append("require_greek_risk_review")

    return _dedupe_strings(constraints)


def _strategy_generation_mode(
    blocked_reasons: list[str],
    option_behavior_state: str | None,
    constraints: list[str],
) -> str:
    if blocked_reasons:
        return "blocked"

    if "block_options_candidate_generation" in constraints:
        return "underlying_only_or_manual_review"

    if option_behavior_state == "constrained":
        return "options_constrained"

    if option_behavior_state == "supportive":
        return "options_supported"

    return "options_neutral"


def _handoff_status(
    blocked_reasons: list[str],
    warnings: list[str],
) -> str:
    if blocked_reasons:
        return "blocked"

    if warnings:
        return "needs_review"

    return "ready"


def _extract_symbol(
    asset_behavior_result: Mapping[str, Any],
    options_analytics_context: Mapping[str, Any] | None,
) -> str | None:
    asset_symbol = _string_or_none(asset_behavior_result.get("symbol"))

    if asset_symbol is not None:
        return asset_symbol

    if isinstance(options_analytics_context, Mapping):
        return _string_or_none(options_analytics_context.get("symbol"))

    return None


def _first_present_string(
    source: Mapping[str, Any],
    keys: list[str],
) -> str | None:
    for key in keys:
        value = _string_or_none(source.get(key))

        if value is not None:
            return value

    return None


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None

    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None

    return None


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []

    for value in values:
        if value not in seen:
            deduped.append(value)
            seen.add(value)

    return deduped
