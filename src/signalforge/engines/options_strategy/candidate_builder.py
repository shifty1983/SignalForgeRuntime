from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from src.signalforge.engines.options_strategy.setup_matcher import (
    OptionStrategySetupInput,
    match_defined_risk_option_strategies,
)


EXCLUDED_ACTIONS = [
    "broker_api_calls",
    "order_routing",
    "order_submission",
    "fills",
    "live_execution",
    "slippage_modeling",
    "maintenance_actions",
    "defense_actions",
]


VALID_GENERATION_STATUSES = {
    "ready",
    "needs_review",
    "blocked",
}


def build_option_strategy_candidates_from_handoff(
    option_behavior_strategy_handoff: Mapping[str, Any] | None,
    *,
    market_regime: str,
    setup_family: str | None = None,
    has_underlying_position: bool = False,
    max_candidates: int | None = None,
    minimum_score: float = 2.0,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build defined-risk option strategy family candidates from the existing
    option-behavior strategy handoff.

    This is the first concrete strategy-generation layer after regime,
    asset behavior, and option behavior. It only recommends defined-risk
    strategy families. It does not choose contracts, strikes, expirations,
    position size, expected value, orders, fills, maintenance actions,
    defense actions, or live execution.
    """

    if not isinstance(option_behavior_strategy_handoff, Mapping):
        return _blocked_generation(
            symbol=None,
            market_regime=market_regime,
            setup_family=setup_family,
            blocked_reasons=["invalid option_behavior_strategy_handoff shape"],
            metadata=metadata,
        )

    handoff_status = _string_or_none(option_behavior_strategy_handoff.get("status"))
    if handoff_status not in VALID_GENERATION_STATUSES:
        return _blocked_generation(
            symbol=_string_or_none(option_behavior_strategy_handoff.get("symbol")),
            market_regime=market_regime,
            setup_family=setup_family,
            blocked_reasons=["invalid option behavior strategy handoff status"],
            metadata=metadata,
        )

    symbol = _string_or_none(option_behavior_strategy_handoff.get("symbol"))
    warnings = list(_strings(option_behavior_strategy_handoff.get("warnings")))
    blocked_reasons = list(
        _strings(option_behavior_strategy_handoff.get("blocked_reasons"))
    )

    constraints = list(
        _strings(option_behavior_strategy_handoff.get("strategy_generation_constraints"))
    )

    if handoff_status == "blocked":
        if not blocked_reasons:
            blocked_reasons.append("option behavior strategy handoff is blocked")
        return _blocked_generation(
            symbol=symbol,
            market_regime=market_regime,
            setup_family=setup_family,
            blocked_reasons=blocked_reasons,
            warnings=warnings,
            metadata=metadata,
            source_handoff=option_behavior_strategy_handoff,
        )

    if "block_options_candidate_generation" in constraints:
        blocked_reasons.append("option behavior handoff blocks options candidate generation")
        return _blocked_generation(
            symbol=symbol,
            market_regime=market_regime,
            setup_family=setup_family,
            blocked_reasons=_dedupe_strings(blocked_reasons),
            warnings=warnings,
            metadata=metadata,
            source_handoff=option_behavior_strategy_handoff,
        )

    asset_behavior_context = option_behavior_strategy_handoff.get(
        "asset_behavior_context"
    )
    option_behavior_context = option_behavior_strategy_handoff.get(
        "option_behavior_context"
    )

    if not isinstance(asset_behavior_context, Mapping):
        blocked_reasons.append("missing asset behavior context")

    if not isinstance(option_behavior_context, Mapping):
        blocked_reasons.append("missing option behavior context")

    if blocked_reasons:
        return _blocked_generation(
            symbol=symbol,
            market_regime=market_regime,
            setup_family=setup_family,
            blocked_reasons=_dedupe_strings(blocked_reasons),
            warnings=warnings,
            metadata=metadata,
            source_handoff=option_behavior_strategy_handoff,
        )

    asset_behavior = _best_asset_behavior(asset_behavior_context)
    if asset_behavior is None:
        return _blocked_generation(
            symbol=symbol,
            market_regime=market_regime,
            setup_family=setup_family,
            blocked_reasons=["missing asset behavior for options strategy generation"],
            warnings=warnings,
            metadata=metadata,
            source_handoff=option_behavior_strategy_handoff,
        )

    matcher_result = match_defined_risk_option_strategies(
        OptionStrategySetupInput(
            symbol=symbol or "",
            market_regime=market_regime,
            asset_behavior=asset_behavior,
            setup_family=setup_family,
            option_behavior=dict(option_behavior_context),
            has_underlying_position=has_underlying_position,
            max_candidates=max_candidates,
            metadata={
                "source_artifact_type": option_behavior_strategy_handoff.get(
                    "artifact_type"
                ),
                "source_handoff_status": handoff_status,
                **dict(metadata or {}),
            },
        ),
        minimum_score=minimum_score,
    )

    combined_warnings = _dedupe_strings(
        [
            *warnings,
            *list(_strings(matcher_result.get("warnings"))),
        ]
    )

    matcher_status = _string_or_none(matcher_result.get("status")) or "blocked"
    generation_status = _generation_status(
        handoff_status=handoff_status,
        matcher_status=matcher_status,
        warnings=combined_warnings,
    )

    return {
        "artifact_type": "defined_risk_option_strategy_candidates",
        "status": generation_status,
        "is_ready": generation_status == "ready",
        "symbol": symbol,
        "market_regime": market_regime,
        "asset_behavior": asset_behavior,
        "setup_family": setup_family,
        "candidate_count": int(matcher_result.get("candidate_count", 0)),
        "rejected_count": int(matcher_result.get("rejected_count", 0)),
        "candidates": list(matcher_result.get("candidates", [])),
        "rejected_strategies": list(matcher_result.get("rejected_strategies", [])),
        "warnings": combined_warnings,
        "blocked_reasons": list(_strings(matcher_result.get("blocking_reasons"))),
        "strategy_generation_constraints": constraints,
        "source_handoff_summary": _source_handoff_summary(
            option_behavior_strategy_handoff
        ),
        "excluded": EXCLUDED_ACTIONS,
        "metadata": dict(metadata or {}),
    }


def _blocked_generation(
    *,
    symbol: str | None,
    market_regime: str,
    setup_family: str | None,
    blocked_reasons: Sequence[str],
    warnings: Sequence[str] | None = None,
    metadata: Mapping[str, Any] | None = None,
    source_handoff: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "artifact_type": "defined_risk_option_strategy_candidates",
        "status": "blocked",
        "is_ready": False,
        "symbol": symbol,
        "market_regime": market_regime,
        "asset_behavior": None,
        "setup_family": setup_family,
        "candidate_count": 0,
        "rejected_count": 0,
        "candidates": [],
        "rejected_strategies": [],
        "warnings": _dedupe_strings(list(warnings or [])),
        "blocked_reasons": _dedupe_strings(list(blocked_reasons)),
        "strategy_generation_constraints": list(
            _strings(
                source_handoff.get("strategy_generation_constraints")
                if isinstance(source_handoff, Mapping)
                else None
            )
        ),
        "source_handoff_summary": _source_handoff_summary(source_handoff),
        "excluded": EXCLUDED_ACTIONS,
        "metadata": dict(metadata or {}),
    }


def _generation_status(
    *,
    handoff_status: str,
    matcher_status: str,
    warnings: Sequence[str],
) -> str:
    if matcher_status == "blocked":
        return "blocked"

    if matcher_status == "needs_review":
        return "needs_review"

    if handoff_status == "needs_review" or warnings:
        return "needs_review"

    return "ready"


def _best_asset_behavior(asset_behavior_context: Mapping[str, Any]) -> str | None:
    for key in (
        "asset_behavior",
        "trend_behavior",
        "return_behavior",
        "volatility_behavior",
        "drawdown_behavior",
    ):
        value = _string_or_none(asset_behavior_context.get(key))
        if value is not None:
            return value

    return None


def _source_handoff_summary(
    source_handoff: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(source_handoff, Mapping):
        return {}

    return {
        "artifact_type": _string_or_none(source_handoff.get("artifact_type")),
        "status": _string_or_none(source_handoff.get("status")),
        "handoff_status": _string_or_none(source_handoff.get("handoff_status")),
        "strategy_generation_mode": _string_or_none(
            source_handoff.get("strategy_generation_mode")
        ),
        "source_layers": list(_strings(source_handoff.get("source_layers"))),
    }


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None

    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None

    return None


def _strings(value: Any) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()

    return tuple(item for item in value if isinstance(item, str) and item.strip())


def _dedupe_strings(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []

    for value in values:
        if value not in seen:
            seen.add(value)
            output.append(value)

    return output



