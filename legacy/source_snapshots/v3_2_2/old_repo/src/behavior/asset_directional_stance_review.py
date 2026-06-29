from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from src.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS


ASSET_DIRECTIONAL_STANCE_REVIEW_SCHEMA_VERSION = (
    "signalforge_asset_directional_stance_review.v1"
)


def build_signalforge_asset_directional_stance_review(
    source: Mapping[str, Any] | None,
    *,
    top_n: int = 25,
) -> dict[str, Any]:
    """
    Build a compact review/export artifact from instrument directional stance.

    This layer does not create new direction logic. It organizes the current
    long / short / neutral stance output into reviewable candidate sets.

    It performs no broker API calls, order routing, order submission, fills,
    live execution, slippage modeling, or automatic strategy/parameter/pause
    changes.
    """

    if not isinstance(source, Mapping):
        return _blocked_result("asset directional stance source must be a mapping")

    stances = source.get("instrument_directional_stances")
    if not isinstance(stances, Sequence) or isinstance(stances, (str, bytes, bytearray)):
        return _blocked_result(
            "asset directional stance source must contain instrument_directional_stances list"
        )

    if not stances:
        return _blocked_result("instrument_directional_stances list is empty")

    review_items: list[dict[str, Any]] = []
    skipped_items: list[dict[str, Any]] = []
    warning_items: list[dict[str, Any]] = []

    for index, item in enumerate(stances):
        if not isinstance(item, Mapping):
            skipped_items.append(
                {
                    "reason": "instrument stance item must be a mapping",
                    "item_index": index,
                }
            )
            continue

        symbol = _clean_symbol(item.get("symbol"))
        if symbol is None:
            skipped_items.append(
                {
                    "reason": "instrument stance item missing symbol",
                    "item_index": index,
                }
            )
            continue

        review_items.append(_review_item(item, symbol=symbol))

    if not review_items:
        return _blocked_result("no reviewable instrument stance items were produced")

    source_status = _clean_text(source.get("status"))
    if source_status not in {None, "ready"}:
        warning_items.append(
            {
                "reason": "asset directional stance source is not ready",
                "source_status": source_status,
            }
        )

    if skipped_items:
        warning_items.append(
            {
                "reason": "some instrument stance items were skipped",
                "skipped_count": len(skipped_items),
            }
        )

    status = "needs_review" if warning_items else "ready"

    long_candidates = _top_items(
        review_items,
        direction="long_bias",
        gate=None,
        manual_review_required=None,
        top_n=top_n,
    )
    short_candidates = _top_items(
        review_items,
        direction="short_bias",
        gate=None,
        manual_review_required=None,
        top_n=top_n,
    )
    neutral_candidates = _top_items(
        review_items,
        direction="neutral_bias",
        gate=None,
        manual_review_required=None,
        top_n=top_n,
    )

    clean_long_candidates = _top_items(
        review_items,
        direction="long_bias",
        gate="allowed",
        manual_review_required=False,
        top_n=top_n,
    )
    clean_short_candidates = _top_items(
        review_items,
        direction="short_bias",
        gate="allowed",
        manual_review_required=False,
        top_n=top_n,
    )

    review_required_items = _top_items(
        review_items,
        direction=None,
        gate="review_required",
        manual_review_required=None,
        top_n=top_n,
    )
    blocked_items = _top_items(
        review_items,
        direction=None,
        gate="blocked",
        manual_review_required=None,
        top_n=top_n,
    )

    conflict_items = _top_alignment_items(
        review_items,
        alignment="regime_behavior_conflict",
        top_n=top_n,
    )
    regime_unconfirmed_items = _top_alignment_items(
        review_items,
        alignment="regime_unconfirmed_by_behavior",
        top_n=top_n,
    )
    behavior_led_items = _top_alignment_items(
        review_items,
        alignment="behavior_led",
        top_n=top_n,
    )

    return {
        "artifact_type": "signalforge_asset_directional_stance_review",
        "schema_version": ASSET_DIRECTIONAL_STANCE_REVIEW_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "contract": "asset_directional_stance_review",
        "adapter_type": "asset_directional_stance_review_builder",
        "source_artifact_type": source.get("artifact_type"),
        "source_status": source.get("status"),
        "macro_regime_label": source.get("macro_regime_label"),
        "policy_regime_label": source.get("policy_regime_label"),
        "weekly_planning_label": source.get("weekly_planning_label"),
        "market_confirmation": source.get("market_confirmation"),
        "aggregate_market_bias": source.get("aggregate_market_bias"),
        "top_n": top_n,
        "top_long_candidates": long_candidates,
        "top_short_candidates": short_candidates,
        "top_neutral_candidates": neutral_candidates,
        "clean_long_candidates": clean_long_candidates,
        "clean_short_candidates": clean_short_candidates,
        "review_required_items": review_required_items,
        "blocked_items": blocked_items,
        "regime_behavior_conflict_items": conflict_items,
        "regime_unconfirmed_by_behavior_items": regime_unconfirmed_items,
        "behavior_led_items": behavior_led_items,
        "review_summary": _review_summary(review_items),
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


def _review_item(item: Mapping[str, Any], *, symbol: str) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "asset_class": _clean_text(item.get("asset_class")) or "unknown",
        "directional_stance": _clean_text(item.get("directional_stance")) or "neutral_bias",
        "combined_gate": _clean_text(item.get("combined_gate")) or "allowed",
        "manual_review_required": bool(item.get("manual_review_required")),
        "stance_score": _float_or_default(item.get("stance_score"), 0.0),
        "long_score": _float_or_default(item.get("long_score"), 0.0),
        "short_score": _float_or_default(item.get("short_score"), 0.0),
        "neutral_score": _float_or_default(item.get("neutral_score"), 0.0),
        "behavior_directional_stance": _clean_text(
            item.get("behavior_directional_stance")
        ),
        "regime_directional_stance": _clean_text(
            item.get("regime_directional_stance")
        ),
        "stance_alignment": _clean_text(item.get("stance_alignment")) or "unknown",
        "behavior_state": _clean_text(item.get("behavior_state")),
        "trend_behavior": _clean_text(item.get("trend_behavior")),
        "return_behavior": _clean_text(item.get("return_behavior")),
        "selection_bucket": _clean_text(item.get("selection_bucket")),
        "regime_policy_bucket": _clean_text(item.get("regime_policy_bucket")),
        "stance_reasons": list(item.get("stance_reasons") or []),
        "conflict_reasons": list(item.get("conflict_reasons") or []),
        "source_selection_reasons": list(item.get("source_selection_reasons") or []),
        "source_regime_reasons": list(item.get("source_regime_reasons") or []),
    }


def _top_items(
    items: Sequence[Mapping[str, Any]],
    *,
    direction: str | None,
    gate: str | None,
    manual_review_required: bool | None,
    top_n: int,
) -> list[dict[str, Any]]:
    filtered = []

    for item in items:
        if direction is not None and item.get("directional_stance") != direction:
            continue

        if gate is not None and item.get("combined_gate") != gate:
            continue

        if (
            manual_review_required is not None
            and item.get("manual_review_required") is not manual_review_required
        ):
            continue

        filtered.append(dict(item))

    return _sorted_review_items(filtered)[:top_n]


def _top_alignment_items(
    items: Sequence[Mapping[str, Any]],
    *,
    alignment: str,
    top_n: int,
) -> list[dict[str, Any]]:
    filtered = [
        dict(item)
        for item in items
        if item.get("stance_alignment") == alignment
    ]

    return _sorted_review_items(filtered)[:top_n]


def _sorted_review_items(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [dict(item) for item in items],
        key=lambda item: (
            -_float_or_default(item.get("stance_score"), 0.0),
            str(item.get("asset_class")),
            str(item.get("symbol")),
        ),
    )


def _review_summary(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    stance_counts = _count_by(items, "directional_stance")
    gate_counts = _count_by(items, "combined_gate")
    asset_class_counts = _count_by(items, "asset_class")
    alignment_counts = _count_by(items, "stance_alignment")

    long_items = [
        item for item in items
        if item.get("directional_stance") == "long_bias"
    ]
    short_items = [
        item for item in items
        if item.get("directional_stance") == "short_bias"
    ]
    neutral_items = [
        item for item in items
        if item.get("directional_stance") == "neutral_bias"
    ]
    review_items = [
        item for item in items
        if item.get("combined_gate") == "review_required"
    ]
    blocked_items = [
        item for item in items
        if item.get("combined_gate") == "blocked"
    ]

    return {
        "instrument_count": len(items),
        "stance_counts": stance_counts,
        "gate_counts": gate_counts,
        "asset_class_counts": asset_class_counts,
        "alignment_counts": alignment_counts,
        "long_bias_count": len(long_items),
        "short_bias_count": len(short_items),
        "neutral_bias_count": len(neutral_items),
        "review_required_count": len(review_items),
        "blocked_count": len(blocked_items),
        "clean_long_candidate_count": len(
            [
                item for item in long_items
                if item.get("combined_gate") == "allowed"
                and not item.get("manual_review_required")
            ]
        ),
        "clean_short_candidate_count": len(
            [
                item for item in short_items
                if item.get("combined_gate") == "allowed"
                and not item.get("manual_review_required")
            ]
        ),
        "conflict_count": alignment_counts.get("regime_behavior_conflict", 0),
        "regime_unconfirmed_count": alignment_counts.get(
            "regime_unconfirmed_by_behavior",
            0,
        ),
        "behavior_led_count": alignment_counts.get("behavior_led", 0),
    }


def _count_by(items: Sequence[Mapping[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}

    for item in items:
        value = str(item.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1

    return dict(sorted(counts.items()))


def _clean_symbol(value: Any) -> str | None:
    text = _clean_text(value)
    return text.upper() if text else None


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


def _blocked_result(reason: str) -> dict[str, Any]:
    return {
        "artifact_type": "signalforge_asset_directional_stance_review",
        "schema_version": ASSET_DIRECTIONAL_STANCE_REVIEW_SCHEMA_VERSION,
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "contract": "asset_directional_stance_review",
        "adapter_type": "asset_directional_stance_review_builder",
        "top_n": None,
        "top_long_candidates": [],
        "top_short_candidates": [],
        "top_neutral_candidates": [],
        "review_required_items": [],
        "blocked_items": [],
        "regime_behavior_conflict_items": [],
        "regime_unconfirmed_by_behavior_items": [],
        "behavior_led_items": [],
        "review_summary": {
            "instrument_count": 0,
            "stance_counts": {},
            "gate_counts": {},
            "asset_class_counts": {},
            "alignment_counts": {},
            "long_bias_count": 0,
            "short_bias_count": 0,
            "neutral_bias_count": 0,
            "review_required_count": 0,
            "blocked_count": 0,
            "clean_long_candidate_count": 0,
            "clean_short_candidate_count": 0,
            "conflict_count": 0,
            "regime_unconfirmed_count": 0,
            "behavior_led_count": 0,
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
