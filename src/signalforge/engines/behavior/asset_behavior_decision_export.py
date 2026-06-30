from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from signalforge.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS


ASSET_BEHAVIOR_DECISION_EXPORT_SCHEMA_VERSION = (
    "signalforge_asset_behavior_decision_export.v1"
)


def build_signalforge_asset_behavior_decision_export(
    asset_directional_stance: Mapping[str, Any] | None,
    relative_rank: Mapping[str, Any] | None,
    tradability_gate: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """
    Build final asset-behavior handoff decisions for option behavior.

    This layer merges directional stance, relative rank, and underlying
    tradability into one strategy-selection / option-behavior handoff artifact.

    It does not choose option strategies, create orders, route orders, submit
    orders, model fills, or perform broker/execution activity.
    """

    if not isinstance(asset_directional_stance, Mapping):
        return _blocked_result("asset directional stance source must be a mapping")

    if not isinstance(relative_rank, Mapping):
        return _blocked_result("relative rank source must be a mapping")

    if not isinstance(tradability_gate, Mapping):
        return _blocked_result("tradability gate source must be a mapping")

    stance_items = asset_directional_stance.get("instrument_directional_stances")
    if not isinstance(stance_items, Sequence) or isinstance(
        stance_items,
        (str, bytes, bytearray),
    ):
        return _blocked_result(
            "asset directional stance source must contain instrument_directional_stances list"
        )

    relative_items = relative_rank.get("relative_rank_items")
    if not isinstance(relative_items, Sequence) or isinstance(
        relative_items,
        (str, bytes, bytearray),
    ):
        return _blocked_result(
            "relative rank source must contain relative_rank_items list"
        )

    tradability_items = tradability_gate.get("tradability_gate_items")
    if not isinstance(tradability_items, Sequence) or isinstance(
        tradability_items,
        (str, bytes, bytearray),
    ):
        return _blocked_result(
            "tradability gate source must contain tradability_gate_items list"
        )

    if not stance_items:
        return _blocked_result("instrument_directional_stances list is empty")

    if not relative_items:
        return _blocked_result("relative_rank_items list is empty")

    if not tradability_items:
        return _blocked_result("tradability_gate_items list is empty")

    stance_by_symbol = _items_by_symbol(stance_items)
    tradability_by_symbol = _items_by_symbol(tradability_items)

    decision_items: list[dict[str, Any]] = []
    skipped_items: list[dict[str, Any]] = []
    warning_items: list[dict[str, Any]] = []

    for index, relative in enumerate(relative_items):
        if not isinstance(relative, Mapping):
            skipped_items.append(
                {
                    "reason": "relative rank item must be a mapping",
                    "item_index": index,
                }
            )
            continue

        symbol = _clean_symbol(relative.get("symbol"))
        if symbol is None:
            skipped_items.append(
                {
                    "reason": "relative rank item missing symbol",
                    "item_index": index,
                }
            )
            continue

        stance = stance_by_symbol.get(symbol)
        if stance is None:
            skipped_items.append(
                {
                    "symbol": symbol,
                    "reason": "missing directional stance for symbol",
                    "item_index": index,
                }
            )
            continue

        tradability = tradability_by_symbol.get(symbol)
        if tradability is None:
            skipped_items.append(
                {
                    "symbol": symbol,
                    "reason": "missing tradability gate for symbol",
                    "item_index": index,
                }
            )
            continue

        decision_items.append(
            _decision_item(
                symbol=symbol,
                stance=stance,
                relative=relative,
                tradability=tradability,
            )
        )

    if not decision_items:
        return _blocked_result("no asset behavior decision items were produced")

    if skipped_items:
        warning_items.append(
            {
                "reason": "some symbols were skipped during decision export build",
                "skipped_count": len(skipped_items),
            }
        )

    _append_source_status_warning(
        warning_items,
        source_name="asset directional stance",
        source=asset_directional_stance,
    )
    _append_source_status_warning(
        warning_items,
        source_name="relative rank",
        source=relative_rank,
    )
    _append_source_status_warning(
        warning_items,
        source_name="tradability gate",
        source=tradability_gate,
    )

    status = "needs_review" if warning_items else "ready"

    return {
        "artifact_type": "signalforge_asset_behavior_decision_export",
        "schema_version": ASSET_BEHAVIOR_DECISION_EXPORT_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "contract": "asset_behavior_decision_export",
        "adapter_type": "asset_behavior_decision_export_builder",
        "source_artifacts": {
            "asset_directional_stance": asset_directional_stance.get("artifact_type"),
            "relative_rank": relative_rank.get("artifact_type"),
            "tradability_gate": tradability_gate.get("artifact_type"),
        },
        "source_statuses": {
            "asset_directional_stance": asset_directional_stance.get("status"),
            "relative_rank": relative_rank.get("status"),
            "tradability_gate": tradability_gate.get("status"),
        },
        "macro_regime_label": asset_directional_stance.get("macro_regime_label")
        or relative_rank.get("macro_regime_label")
        or tradability_gate.get("macro_regime_label"),
        "policy_regime_label": asset_directional_stance.get("policy_regime_label")
        or relative_rank.get("policy_regime_label")
        or tradability_gate.get("policy_regime_label"),
        "weekly_planning_label": asset_directional_stance.get("weekly_planning_label")
        or relative_rank.get("weekly_planning_label")
        or tradability_gate.get("weekly_planning_label"),
        "market_confirmation": asset_directional_stance.get("market_confirmation")
        or relative_rank.get("market_confirmation")
        or tradability_gate.get("market_confirmation"),
        "aggregate_market_bias": asset_directional_stance.get("aggregate_market_bias")
        or relative_rank.get("aggregate_market_bias")
        or tradability_gate.get("aggregate_market_bias"),
        "asset_behavior_decision_items": _sort_decision_items(decision_items),
        "asset_behavior_decision_summary": _summary(decision_items),
        "skipped_items": skipped_items,
        "blocker_items": [],
        "warning_items": warning_items,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _decision_item(
    *,
    symbol: str,
    stance: Mapping[str, Any],
    relative: Mapping[str, Any],
    tradability: Mapping[str, Any],
) -> dict[str, Any]:
    directional_stance = _clean_text(stance.get("directional_stance")) or "neutral_bias"
    stance_gate = _clean_gate(stance.get("combined_gate"))
    tradability_gate = _clean_gate(tradability.get("tradability_gate"))

    final_gate = _final_gate(
        stance_gate=stance_gate,
        tradability_gate=tradability_gate,
        manual_review_required=bool(stance.get("manual_review_required"))
        or bool(tradability.get("manual_review_required")),
    )

    final_decision = _final_decision(
        directional_stance=directional_stance,
        final_gate=final_gate,
    )

    option_behavior_handoff = _option_behavior_handoff(final_gate)

    final_decision_score = _final_decision_score(
        directional_stance=directional_stance,
        final_gate=final_gate,
        relative=relative,
        tradability=tradability,
    )

    decision_reasons = _decision_reasons(
        directional_stance=directional_stance,
        stance_gate=stance_gate,
        tradability_gate=tradability_gate,
        final_gate=final_gate,
        final_decision=final_decision,
    )

    return {
        "artifact_type": "asset_behavior_decision_item",
        "symbol": symbol,
        "asset_class": _clean_text(stance.get("asset_class"))
        or _clean_text(relative.get("asset_class"))
        or _clean_text(tradability.get("asset_class"))
        or "unknown",
        "directional_stance": directional_stance,
        "final_decision": final_decision,
        "final_gate": final_gate,
        "option_behavior_handoff": option_behavior_handoff,
        "final_decision_score": final_decision_score,
        "stance_gate": stance_gate,
        "tradability_gate": tradability_gate,
        "tradability_state": _clean_text(tradability.get("tradability_state")),
        "tradability_score": _float_or_default(
            tradability.get("tradability_score"),
            0.0,
        ),
        "relative_strength_score": _float_or_default(
            relative.get("relative_strength_score"),
            0.0,
        ),
        "relative_weakness_score": _float_or_default(
            relative.get("relative_weakness_score"),
            0.0,
        ),
        "direction_fit_score": _float_or_default(
            relative.get("direction_fit_score"),
            0.0,
        ),
        "universe_strength_rank": relative.get("universe_strength_rank"),
        "universe_weakness_rank": relative.get("universe_weakness_rank"),
        "asset_class_strength_rank": relative.get("asset_class_strength_rank"),
        "asset_class_weakness_rank": relative.get("asset_class_weakness_rank"),
        "directional_fit_rank": relative.get("directional_fit_rank"),
        "multi_horizon_confirmation": _clean_text(
            relative.get("multi_horizon_confirmation")
        ),
        "trend_consistency": _clean_text(relative.get("trend_consistency")),
        "stance_alignment": _clean_text(stance.get("stance_alignment")),
        "behavior_directional_stance": _clean_text(
            stance.get("behavior_directional_stance")
        ),
        "regime_directional_stance": _clean_text(
            stance.get("regime_directional_stance")
        ),
        "manual_review_required": final_gate != "allowed",
        "decision_reasons": decision_reasons,
        "stance_reasons": list(stance.get("stance_reasons") or []),
        "conflict_reasons": list(stance.get("conflict_reasons") or []),
        "tradability_reasons": list(tradability.get("tradability_reasons") or []),
        "tradability_review_reasons": list(tradability.get("review_reasons") or []),
        "tradability_blocked_reasons": list(tradability.get("blocked_reasons") or []),
        "relative_rank_reasons": list(relative.get("relative_rank_reasons") or []),
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _final_gate(
    *,
    stance_gate: str,
    tradability_gate: str,
    manual_review_required: bool,
) -> str:
    if stance_gate == "blocked" or tradability_gate == "blocked":
        return "blocked"

    if (
        stance_gate == "review_required"
        or tradability_gate == "review_required"
        or manual_review_required
    ):
        return "review_required"

    return "allowed"


def _final_decision(
    *,
    directional_stance: str,
    final_gate: str,
) -> str:
    if final_gate == "blocked":
        return "blocked"

    if directional_stance == "long_bias":
        return "eligible_long"

    if directional_stance == "short_bias":
        return "eligible_short"

    return "neutral_position"


def _option_behavior_handoff(final_gate: str) -> str:
    if final_gate == "blocked":
        return "blocked"

    if final_gate == "review_required":
        return "review_required"

    return "ready"


def _final_decision_score(
    *,
    directional_stance: str,
    final_gate: str,
    relative: Mapping[str, Any],
    tradability: Mapping[str, Any],
) -> float:
    if directional_stance == "long_bias":
        directional_score = _float_or_default(relative.get("relative_strength_score"), 0.0)
    elif directional_stance == "short_bias":
        directional_score = _float_or_default(relative.get("relative_weakness_score"), 0.0)
    else:
        directional_score = _float_or_default(relative.get("direction_fit_score"), 0.0)

    tradability_score = _float_or_default(tradability.get("tradability_score"), 0.0)
    direction_fit_score = _float_or_default(relative.get("direction_fit_score"), 0.0)

    gate_adjustment = {
        "allowed": 0.0,
        "review_required": -0.15,
        "blocked": -0.50,
    }.get(final_gate, -0.15)

    score = (
        (directional_score * 0.45)
        + (direction_fit_score * 0.25)
        + (tradability_score * 0.30)
        + gate_adjustment
    )

    return round(_clamp(score, 0.0, 1.0), 6)


def _decision_reasons(
    *,
    directional_stance: str,
    stance_gate: str,
    tradability_gate: str,
    final_gate: str,
    final_decision: str,
) -> list[str]:
    return [
        f"directional_stance:{directional_stance}",
        f"stance_gate:{stance_gate}",
        f"tradability_gate:{tradability_gate}",
        f"final_gate:{final_gate}",
        f"final_decision:{final_decision}",
    ]


def _summary(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    final_decision_counts = Counter(
        str(item.get("final_decision") or "unknown") for item in items
    )
    final_gate_counts = Counter(
        str(item.get("final_gate") or "unknown") for item in items
    )
    directional_stance_counts = Counter(
        str(item.get("directional_stance") or "unknown") for item in items
    )
    asset_class_counts = Counter(
        str(item.get("asset_class") or "unknown") for item in items
    )
    option_handoff_counts = Counter(
        str(item.get("option_behavior_handoff") or "unknown") for item in items
    )

    sorted_items = _sort_decision_items(items)

    eligible_long = [
        item for item in sorted_items if item.get("final_decision") == "eligible_long"
    ]
    eligible_short = [
        item for item in sorted_items if item.get("final_decision") == "eligible_short"
    ]
    neutral_position = [
        item for item in sorted_items if item.get("final_decision") == "neutral_position"
    ]
    review_required = [
        item for item in sorted_items if item.get("final_gate") == "review_required"
    ]
    blocked = [
        item for item in sorted_items if item.get("final_decision") == "blocked"
    ]
    option_ready = [
        item for item in sorted_items if item.get("option_behavior_handoff") == "ready"
    ]

    return {
        "instrument_count": len(items),
        "final_decision_counts": dict(sorted(final_decision_counts.items())),
        "final_gate_counts": dict(sorted(final_gate_counts.items())),
        "directional_stance_counts": dict(sorted(directional_stance_counts.items())),
        "asset_class_counts": dict(sorted(asset_class_counts.items())),
        "option_behavior_handoff_counts": dict(sorted(option_handoff_counts.items())),
        "eligible_long_count": len(eligible_long),
        "eligible_short_count": len(eligible_short),
        "neutral_position_count": len(neutral_position),
        "review_required_count": len(review_required),
        "blocked_count": len(blocked),
        "option_behavior_ready_count": len(option_ready),
        "top_eligible_long_symbols": [
            item["symbol"] for item in eligible_long[:25]
        ],
        "top_eligible_short_symbols": [
            item["symbol"] for item in eligible_short[:25]
        ],
        "top_neutral_position_symbols": [
            item["symbol"] for item in neutral_position[:25]
        ],
        "review_required_symbols": [
            item["symbol"] for item in review_required[:25]
        ],
        "blocked_symbols": [
            item["symbol"] for item in blocked[:25]
        ],
        "option_behavior_ready_symbols": [
            item["symbol"] for item in option_ready[:25]
        ],
    }


def _sort_decision_items(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [dict(item) for item in items],
        key=lambda item: (
            -_float_or_default(item.get("final_decision_score"), 0.0),
            str(item.get("asset_class")),
            str(item.get("symbol")),
        ),
    )


def _items_by_symbol(items: Sequence[Any]) -> dict[str, Mapping[str, Any]]:
    output: dict[str, Mapping[str, Any]] = {}

    for item in items:
        if not isinstance(item, Mapping):
            continue

        symbol = _clean_symbol(item.get("symbol"))
        if symbol:
            output[symbol] = item

    return output


def _append_source_status_warning(
    warning_items: list[dict[str, Any]],
    *,
    source_name: str,
    source: Mapping[str, Any],
) -> None:
    source_status = _clean_text(source.get("status"))

    if source_status not in {None, "ready"}:
        warning_items.append(
            {
                "reason": f"{source_name} source is not ready",
                "source_status": source_status,
            }
        )


def _clean_symbol(value: Any) -> str | None:
    text = _clean_text(value)
    return text.upper() if text else None


def _clean_gate(value: Any) -> str:
    text = _clean_text(value)

    if text in {"allowed", "review_required", "blocked"}:
        return text

    return "allowed"


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip().lower()
    return text or None


def _float_or_default(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, floor: float, ceiling: float) -> float:
    return max(floor, min(ceiling, value))


def _blocked_result(reason: str) -> dict[str, Any]:
    return {
        "artifact_type": "signalforge_asset_behavior_decision_export",
        "schema_version": ASSET_BEHAVIOR_DECISION_EXPORT_SCHEMA_VERSION,
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "contract": "asset_behavior_decision_export",
        "adapter_type": "asset_behavior_decision_export_builder",
        "source_artifacts": {},
        "source_statuses": {},
        "asset_behavior_decision_items": [],
        "asset_behavior_decision_summary": {
            "instrument_count": 0,
            "final_decision_counts": {},
            "final_gate_counts": {},
            "directional_stance_counts": {},
            "asset_class_counts": {},
            "option_behavior_handoff_counts": {},
            "eligible_long_count": 0,
            "eligible_short_count": 0,
            "neutral_position_count": 0,
            "review_required_count": 0,
            "blocked_count": 0,
            "option_behavior_ready_count": 0,
            "top_eligible_long_symbols": [],
            "top_eligible_short_symbols": [],
            "top_neutral_position_symbols": [],
            "review_required_symbols": [],
            "blocked_symbols": [],
            "option_behavior_ready_symbols": [],
        },
        "skipped_items": [],
        "blocker_items": [{"reason": reason}],
        "warning_items": [],
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }




