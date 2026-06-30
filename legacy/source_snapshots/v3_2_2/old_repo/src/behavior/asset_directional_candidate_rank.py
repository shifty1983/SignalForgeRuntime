from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from src.signalforge.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS


ASSET_DIRECTIONAL_CANDIDATE_RANK_SCHEMA_VERSION = (
    "signalforge_asset_directional_candidate_rank.v1"
)

DIRECTIONAL_STANCES = {"long_bias", "short_bias", "neutral_bias"}
GATES = {"allowed", "review_required", "blocked"}


def build_signalforge_asset_directional_candidate_rank(
    source: Mapping[str, Any] | None,
    *,
    top_n: int = 50,
) -> dict[str, Any]:
    """
    Rank instrument directional stances into strategy-selection-ready lists.

    This does not create a new directional signal. It ranks existing
    long / short / neutral stance output by stance score, alignment, gate,
    manual review status, and conflict status.

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

    ranked_items: list[dict[str, Any]] = []
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

        ranked_items.append(_rank_item(item, symbol=symbol))

    if not ranked_items:
        return _blocked_result("no rankable instrument stance items were produced")

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

    ranked_long_candidates = _ranked_direction(ranked_items, "long_bias", top_n)
    ranked_short_candidates = _ranked_direction(ranked_items, "short_bias", top_n)
    ranked_neutral_candidates = _ranked_direction(ranked_items, "neutral_bias", top_n)
    ranked_neutral_position_candidates = _ranked_neutral_positions(
        ranked_items,
        top_n,
    )
    ranked_review_candidates = _ranked_review_items(ranked_items, top_n)
    ranked_conflict_candidates = _ranked_alignment(
        ranked_items,
        "regime_behavior_conflict",
        top_n,
    )
    ranked_regime_unconfirmed_candidates = _ranked_alignment(
        ranked_items,
        "regime_unconfirmed_by_behavior",
        top_n,
    )
    ranked_behavior_led_candidates = _ranked_alignment(
        ranked_items,
        "behavior_led",
        top_n,
    )

    return {
        "artifact_type": "signalforge_asset_directional_candidate_rank",
        "schema_version": ASSET_DIRECTIONAL_CANDIDATE_RANK_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "contract": "asset_directional_candidate_rank",
        "adapter_type": "asset_directional_candidate_rank_builder",
        "source_artifact_type": source.get("artifact_type"),
        "source_status": source.get("status"),
        "macro_regime_label": source.get("macro_regime_label"),
        "policy_regime_label": source.get("policy_regime_label"),
        "weekly_planning_label": source.get("weekly_planning_label"),
        "market_confirmation": source.get("market_confirmation"),
        "aggregate_market_bias": source.get("aggregate_market_bias"),
        "top_n": top_n,
        "ranked_long_candidates": ranked_long_candidates,
        "ranked_short_candidates": ranked_short_candidates,
        "ranked_neutral_candidates": ranked_neutral_candidates,
        "ranked_neutral_position_candidates": ranked_neutral_position_candidates,
        "ranked_review_candidates": ranked_review_candidates,
        "ranked_conflict_candidates": ranked_conflict_candidates,
        "ranked_regime_unconfirmed_candidates": ranked_regime_unconfirmed_candidates,
        "ranked_behavior_led_candidates": ranked_behavior_led_candidates,
        "candidate_rank_summary": _rank_summary(ranked_items),
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


def _rank_item(item: Mapping[str, Any], *, symbol: str) -> dict[str, Any]:
    directional_stance = _clean_stance(item.get("directional_stance"))
    combined_gate = _clean_gate(item.get("combined_gate"))
    alignment = _clean_text(item.get("stance_alignment")) or "unknown"
    manual_review_required = bool(item.get("manual_review_required"))

    stance_score = _float_or_default(item.get("stance_score"), 0.0)
    long_score = _float_or_default(item.get("long_score"), 0.0)
    short_score = _float_or_default(item.get("short_score"), 0.0)
    neutral_score = _float_or_default(item.get("neutral_score"), 0.0)

    directional_score = _directional_score(
        stance=directional_stance,
        long_score=long_score,
        short_score=short_score,
        neutral_score=neutral_score,
    )

    rank_score, rank_reasons, rank_penalties = _rank_score(
        directional_score=directional_score,
        stance_score=stance_score,
        alignment=alignment,
        combined_gate=combined_gate,
        manual_review_required=manual_review_required,
        conflict_reasons=list(item.get("conflict_reasons") or []),
    )

    clean_candidate = (
        combined_gate == "allowed"
        and not manual_review_required
        and alignment not in {
            "regime_behavior_conflict",
            "regime_unconfirmed_by_behavior",
        }
        and not item.get("conflict_reasons")
    )

    return {
        "artifact_type": "asset_directional_candidate_rank_item",
        "symbol": symbol,
        "asset_class": _clean_text(item.get("asset_class")) or "unknown",
        "directional_stance": directional_stance,
        "combined_gate": combined_gate,
        "manual_review_required": manual_review_required,
        "clean_candidate": clean_candidate,
        "rank_score": rank_score,
        "directional_score": round(directional_score, 4),
        "stance_score": round(stance_score, 4),
        "long_score": round(long_score, 4),
        "short_score": round(short_score, 4),
        "neutral_score": round(neutral_score, 4),
        "stance_alignment": alignment,
        "behavior_directional_stance": _clean_text(
            item.get("behavior_directional_stance")
        ),
        "regime_directional_stance": _clean_text(
            item.get("regime_directional_stance")
        ),
        "behavior_state": _clean_text(item.get("behavior_state")),
        "trend_behavior": _clean_text(item.get("trend_behavior")),
        "return_behavior": _clean_text(item.get("return_behavior")),
        "selection_bucket": _clean_text(item.get("selection_bucket")),
        "regime_policy_bucket": _clean_text(item.get("regime_policy_bucket")),
        "regime_policy_reason": item.get("regime_policy_reason"),
        "rank_reasons": rank_reasons,
        "rank_penalties": rank_penalties,
        "stance_reasons": list(item.get("stance_reasons") or []),
        "conflict_reasons": list(item.get("conflict_reasons") or []),
        "source_selection_reasons": list(item.get("source_selection_reasons") or []),
        "source_regime_reasons": list(item.get("source_regime_reasons") or []),
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _rank_score(
    *,
    directional_score: float,
    stance_score: float,
    alignment: str,
    combined_gate: str,
    manual_review_required: bool,
    conflict_reasons: Sequence[str],
) -> tuple[float, list[str], list[str]]:
    raw_score = (directional_score * 0.65) + (stance_score * 0.35)
    reasons = ["directional_score_weighted", "stance_score_weighted"]
    penalties: list[str] = []

    if alignment == "aligned":
        raw_score += 0.08
        reasons.append("behavior_regime_aligned_bonus")
    elif alignment == "behavior_led":
        raw_score += 0.03
        reasons.append("behavior_led_minor_bonus")
    elif alignment == "regime_unconfirmed_by_behavior":
        raw_score -= 0.08
        penalties.append("regime_unconfirmed_by_behavior_penalty")
    elif alignment == "regime_behavior_conflict":
        raw_score -= 0.18
        penalties.append("regime_behavior_conflict_penalty")

    if combined_gate == "review_required":
        raw_score -= 0.12
        penalties.append("review_required_gate_penalty")
    elif combined_gate == "blocked":
        raw_score -= 0.50
        penalties.append("blocked_gate_penalty")

    if manual_review_required:
        raw_score -= 0.05
        penalties.append("manual_review_required_penalty")

    if conflict_reasons:
        raw_score -= 0.05
        penalties.append("conflict_reason_penalty")

    return round(_clamp(raw_score, 0.0, 1.0), 4), reasons, penalties


def _ranked_direction(
    items: Sequence[Mapping[str, Any]],
    direction: str,
    top_n: int,
) -> list[dict[str, Any]]:
    return _sort_ranked_items(
        item for item in items if item.get("directional_stance") == direction
    )[:top_n]


def _ranked_neutral_positions(
    items: Sequence[Mapping[str, Any]],
    top_n: int,
) -> list[dict[str, Any]]:
    return _sort_ranked_items(
        item
        for item in items
        if item.get("directional_stance") == "neutral_bias"
        and item.get("combined_gate") != "blocked"
    )[:top_n]


def _ranked_review_items(
    items: Sequence[Mapping[str, Any]],
    top_n: int,
) -> list[dict[str, Any]]:
    return _sort_ranked_items(
        item
        for item in items
        if item.get("combined_gate") == "review_required"
        or item.get("manual_review_required")
    )[:top_n]


def _ranked_alignment(
    items: Sequence[Mapping[str, Any]],
    alignment: str,
    top_n: int,
) -> list[dict[str, Any]]:
    return _sort_ranked_items(
        item for item in items if item.get("stance_alignment") == alignment
    )[:top_n]


def _sort_ranked_items(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [dict(item) for item in items],
        key=lambda item: (
            -_float_or_default(item.get("rank_score"), 0.0),
            str(item.get("asset_class")),
            str(item.get("symbol")),
        ),
    )


def _rank_summary(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    stance_counts = _count_by(items, "directional_stance")
    gate_counts = _count_by(items, "combined_gate")
    asset_class_counts = _count_by(items, "asset_class")
    alignment_counts = _count_by(items, "stance_alignment")

    long_items = [
        item for item in items if item.get("directional_stance") == "long_bias"
    ]
    short_items = [
        item for item in items if item.get("directional_stance") == "short_bias"
    ]
    neutral_items = [
        item for item in items if item.get("directional_stance") == "neutral_bias"
    ]
    clean_long_items = [
        item
        for item in long_items
        if item.get("clean_candidate")
    ]
    clean_short_items = [
        item
        for item in short_items
        if item.get("clean_candidate")
    ]
    clean_neutral_items = [
        item
        for item in neutral_items
        if item.get("clean_candidate")
    ]
    neutral_position_items = [
        item
        for item in neutral_items
        if item.get("combined_gate") != "blocked"
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
        "clean_long_candidate_count": len(clean_long_items),
        "clean_short_candidate_count": len(clean_short_items),
        "clean_neutral_candidate_count": len(clean_neutral_items),
        "neutral_position_candidate_count": len(neutral_position_items),
        "review_required_count": gate_counts.get("review_required", 0),
        "blocked_count": gate_counts.get("blocked", 0),
        "conflict_count": alignment_counts.get("regime_behavior_conflict", 0),
        "regime_unconfirmed_count": alignment_counts.get(
            "regime_unconfirmed_by_behavior",
            0,
        ),
        "behavior_led_count": alignment_counts.get("behavior_led", 0),
        "top_clean_long_symbols": [
            item["symbol"] for item in _sort_ranked_items(clean_long_items)[:25]
        ],
        "top_clean_short_symbols": [
            item["symbol"] for item in _sort_ranked_items(clean_short_items)[:25]
        ],
        "top_clean_neutral_symbols": [
            item["symbol"] for item in _sort_ranked_items(clean_neutral_items)[:25]
        ],
        "top_neutral_position_symbols": [
            item["symbol"] for item in _sort_ranked_items(neutral_position_items)[:25]
        ],
    }


def _count_by(items: Sequence[Mapping[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}

    for item in items:
        value = str(item.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1

    return dict(sorted(counts.items()))


def _directional_score(
    *,
    stance: str,
    long_score: float,
    short_score: float,
    neutral_score: float,
) -> float:
    if stance == "long_bias":
        return long_score

    if stance == "short_bias":
        return short_score

    return neutral_score


def _clean_symbol(value: Any) -> str | None:
    text = _clean_text(value)
    return text.upper() if text else None


def _clean_stance(value: Any) -> str:
    text = _clean_text(value)
    if text in DIRECTIONAL_STANCES:
        return text
    return "neutral_bias"


def _clean_gate(value: Any) -> str:
    text = _clean_text(value)
    if text in GATES:
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
        "artifact_type": "signalforge_asset_directional_candidate_rank",
        "schema_version": ASSET_DIRECTIONAL_CANDIDATE_RANK_SCHEMA_VERSION,
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "contract": "asset_directional_candidate_rank",
        "adapter_type": "asset_directional_candidate_rank_builder",
        "top_n": None,
        "ranked_long_candidates": [],
        "ranked_short_candidates": [],
        "ranked_neutral_candidates": [],
        "ranked_neutral_position_candidates": [],
        "ranked_review_candidates": [],
        "ranked_conflict_candidates": [],
        "ranked_regime_unconfirmed_candidates": [],
        "ranked_behavior_led_candidates": [],
        "candidate_rank_summary": {
            "instrument_count": 0,
            "stance_counts": {},
            "gate_counts": {},
            "asset_class_counts": {},
            "alignment_counts": {},
            "long_bias_count": 0,
            "short_bias_count": 0,
            "neutral_bias_count": 0,
            "clean_long_candidate_count": 0,
            "clean_short_candidate_count": 0,
            "clean_neutral_candidate_count": 0,
            "neutral_position_candidate_count": 0,
            "review_required_count": 0,
            "blocked_count": 0,
            "conflict_count": 0,
            "regime_unconfirmed_count": 0,
            "behavior_led_count": 0,
            "top_clean_long_symbols": [],
            "top_clean_short_symbols": [],
            "top_clean_neutral_symbols": [],
            "top_neutral_position_symbols": [],
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
