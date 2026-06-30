from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from src.signalforge.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS


ARTIFACT_TYPE = "signalforge_asset_behavior_selection_to_decision_inputs"
SCHEMA_VERSION = "signalforge_asset_behavior_selection_to_decision_inputs.v1"

DIRECTIONAL_STANCE_FILE = "signalforge_asset_directional_stance.json"
RELATIVE_RANK_FILE = "signalforge_asset_relative_rank.json"
TRADABILITY_GATE_FILE = "signalforge_asset_tradability_gate.json"
SUMMARY_FILE = "signalforge_asset_behavior_decision_inputs_summary.json"


def build_signalforge_asset_behavior_selection_to_decision_inputs(
    selection_source: Mapping[str, Any] | None,
    *,
    output_dir: str | Path,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    blocker_items: list[dict[str, Any]] = []
    warning_items: list[dict[str, Any]] = []
    skipped_items: list[dict[str, Any]] = []

    if not isinstance(selection_source, Mapping):
        selection_source = {}
        blocker_items.append({"reason": "selection source must be a mapping"})

    candidates = selection_source.get("candidates")
    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes, bytearray)):
        candidates = []
        blocker_items.append({"reason": "selection source must contain candidates list"})

    stance_items: list[dict[str, Any]] = []
    rank_items: list[dict[str, Any]] = []
    tradability_items: list[dict[str, Any]] = []

    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, Mapping):
            skipped_items.append(
                {"reason": "candidate must be a mapping", "candidate_index": index}
            )
            continue

        symbol = _clean_symbol(candidate.get("symbol"))
        if symbol is None:
            skipped_items.append(
                {"reason": "candidate missing symbol", "candidate_index": index}
            )
            continue

        asset_class = _clean_text(candidate.get("asset_class")) or "unknown"
        if asset_class == "unknown":
            warning_items.append(
                {
                    "reason": "candidate asset class is unknown",
                    "symbol": symbol,
                }
            )

        selection_bucket = _clean_text(candidate.get("selection_bucket")) or "needs_review"
        behavior_state = _clean_text(candidate.get("behavior_state")) or "neutral"
        trend_behavior = _clean_text(candidate.get("trend_behavior")) or "trend_unknown"
        behavior_score = _float_or_default(candidate.get("behavior_score"), 0.0)
        selection_rank = _int_or_none(candidate.get("selection_rank"))

        combined_gate = _gate_from_candidate(candidate)
        manual_review_required = combined_gate != "allowed"

        directional_stance = _directional_stance_from_candidate(candidate)
        direction_fit_score = _direction_fit_score(
            directional_stance=directional_stance,
            behavior_score=behavior_score,
        )

        stance_items.append(
            {
                "artifact_type": "signalforge_asset_directional_stance_item",
                "symbol": symbol,
                "asset_class": asset_class,
                "directional_stance": directional_stance,
                "combined_gate": combined_gate,
                "manual_review_required": manual_review_required,
                "behavior_state": behavior_state,
                "trend_behavior": trend_behavior,
                "behavior_score": behavior_score,
                "selection_bucket": selection_bucket,
                "selection_rank": selection_rank,
                "selection_reasons": _as_list(candidate.get("selection_reasons")),
                "asset_class_policy_bucket": _clean_text(
                    candidate.get("asset_class_policy_bucket")
                ),
                "asset_class_policy_reason": _clean_text(
                    candidate.get("asset_class_policy_reason")
                ),
                "warnings": _as_list(candidate.get("warnings")),
                "blocked_reasons": _as_list(candidate.get("blocked_reasons")),
            }
        )

        rank_items.append(
            {
                "artifact_type": "signalforge_asset_relative_rank_item",
                "symbol": symbol,
                "asset_class": asset_class,
                "selection_rank": selection_rank,
                "relative_strength_score": behavior_score,
                "relative_weakness_score": max(0.0, 100.0 - behavior_score),
                "direction_fit_score": direction_fit_score,
                "behavior_score": behavior_score,
                "behavior_state": behavior_state,
                "trend_behavior": trend_behavior,
                "selection_bucket": selection_bucket,
                "selection_reasons": _as_list(candidate.get("selection_reasons")),
            }
        )

        tradability_items.append(
            {
                "artifact_type": "signalforge_asset_tradability_gate_item",
                "symbol": symbol,
                "asset_class": asset_class,
                "tradability_gate": combined_gate,
                "tradability_state": _tradability_state(combined_gate),
                "tradability_score": _tradability_score(
                    gate=combined_gate,
                    behavior_score=behavior_score,
                ),
                "manual_review_required": manual_review_required,
                "selection_bucket": selection_bucket,
                "status": _clean_text(candidate.get("status")),
                "behavior_state": behavior_state,
                "trend_behavior": trend_behavior,
                "asset_class_policy_bucket": _clean_text(
                    candidate.get("asset_class_policy_bucket")
                ),
                "asset_class_policy_reason": _clean_text(
                    candidate.get("asset_class_policy_reason")
                ),
                "warnings": _as_list(candidate.get("warnings")),
                "blocked_reasons": _as_list(candidate.get("blocked_reasons")),
            }
        )

    if not stance_items:
        blocker_items.append({"reason": "no directional stance items produced"})

    if not rank_items:
        blocker_items.append({"reason": "no relative rank items produced"})

    if not tradability_items:
        blocker_items.append({"reason": "no tradability gate items produced"})

    if skipped_items:
        warning_items.append(
            {
                "reason": "some selection candidates were skipped",
                "skipped_count": len(skipped_items),
            }
        )

    source_status = _clean_text(selection_source.get("status"))
    if source_status not in {None, "ready"}:
        warning_items.append(
            {
                "reason": "selection source is not ready",
                "source_status": source_status,
            }
        )

    status = "blocked" if blocker_items else "needs_review" if warning_items else "ready"

    shared_metadata = _shared_metadata(selection_source, status=status)

    directional_stance = {
        **shared_metadata,
        "artifact_type": "signalforge_asset_directional_stance",
        "schema_version": "signalforge_asset_directional_stance.v1",
        "contract": "asset_directional_stance",
        "instrument_directional_stances": _sort_by_symbol(stance_items),
        "directional_stance_summary": {
            "item_count": len(stance_items),
            "directional_stance_counts": dict(
                Counter(item["directional_stance"] for item in stance_items)
            ),
            "gate_counts": dict(Counter(item["combined_gate"] for item in stance_items)),
        },
    }

    relative_rank = {
        **shared_metadata,
        "artifact_type": "signalforge_asset_relative_rank",
        "schema_version": "signalforge_asset_relative_rank.v1",
        "contract": "asset_relative_rank",
        "relative_rank_items": _sort_relative_rank_items(rank_items),
        "relative_rank_summary": {
            "item_count": len(rank_items),
            "asset_class_counts": dict(Counter(item["asset_class"] for item in rank_items)),
        },
    }

    tradability_gate = {
        **shared_metadata,
        "artifact_type": "signalforge_asset_tradability_gate",
        "schema_version": "signalforge_asset_tradability_gate.v1",
        "contract": "asset_tradability_gate",
        "tradability_gate_items": _sort_by_symbol(tradability_items),
        "tradability_gate_summary": {
            "item_count": len(tradability_items),
            "tradability_gate_counts": dict(
                Counter(item["tradability_gate"] for item in tradability_items)
            ),
            "tradability_state_counts": dict(
                Counter(item["tradability_state"] for item in tradability_items)
            ),
        },
    }

    directional_path = output_path / DIRECTIONAL_STANCE_FILE
    relative_path = output_path / RELATIVE_RANK_FILE
    tradability_path = output_path / TRADABILITY_GATE_FILE
    summary_path = output_path / SUMMARY_FILE

    directional_path.write_text(
        json.dumps(directional_stance, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    relative_path.write_text(
        json.dumps(relative_rank, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    tradability_path.write_text(
        json.dumps(tradability_gate, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    summary = {
        "artifact_type": ARTIFACT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "source_artifact_type": selection_source.get("artifact_type"),
        "source_status": selection_source.get("status"),
        "macro_regime_label": selection_source.get("macro_regime_label"),
        "policy_regime_label": selection_source.get("policy_regime_label"),
        "weekly_planning_label": selection_source.get("weekly_planning_label"),
        "market_confirmation": selection_source.get("market_confirmation"),
        "candidate_count": len(candidates),
        "directional_stance_item_count": len(stance_items),
        "relative_rank_item_count": len(rank_items),
        "tradability_gate_item_count": len(tradability_items),
        "asset_class_counts": dict(Counter(item["asset_class"] for item in stance_items)),
        "directional_stance_counts": dict(
            Counter(item["directional_stance"] for item in stance_items)
        ),
        "gate_counts": dict(Counter(item["combined_gate"] for item in stance_items)),
        "blocker_items": blocker_items,
        "warning_items": warning_items,
        "skipped_items": skipped_items,
        "files": {
            "asset_directional_stance": str(directional_path),
            "relative_rank": str(relative_path),
            "tradability_gate": str(tradability_path),
            "summary": str(summary_path),
        },
        "next_step": "run_asset_behavior_decision_export_cli",
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }

    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    return summary


def _shared_metadata(selection_source: Mapping[str, Any], *, status: str) -> dict[str, Any]:
    return {
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "source_artifact_type": selection_source.get("artifact_type"),
        "source_status": selection_source.get("status"),
        "macro_regime_label": selection_source.get("macro_regime_label"),
        "policy_regime_label": selection_source.get("policy_regime_label"),
        "weekly_planning_label": selection_source.get("weekly_planning_label"),
        "market_confirmation": selection_source.get("market_confirmation"),
        "aggregate_market_bias": selection_source.get("aggregate_market_bias"),
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _gate_from_candidate(candidate: Mapping[str, Any]) -> str:
    status = _clean_text(candidate.get("status"))
    selection_bucket = _clean_text(candidate.get("selection_bucket"))
    blocked_reasons = _as_list(candidate.get("blocked_reasons"))

    if status == "blocked" or selection_bucket == "blocked" or blocked_reasons:
        return "blocked"

    if selection_bucket == "allowed":
        return "allowed"

    return "needs_review"


def _directional_stance_from_candidate(candidate: Mapping[str, Any]) -> str:
    behavior_state = _clean_text(candidate.get("behavior_state"))
    trend_behavior = _clean_text(candidate.get("trend_behavior"))
    period_return = _float_or_default(candidate.get("period_return"), 0.0)

    if behavior_state == "constructive":
        return "long_bias"

    if behavior_state == "defensive":
        return "short_bias"

    if trend_behavior == "downtrend" and period_return < 0:
        return "short_bias"

    return "neutral_bias"


def _direction_fit_score(*, directional_stance: str, behavior_score: float) -> float:
    if directional_stance == "bullish_bias":
        return behavior_score

    if directional_stance == "bearish_bias":
        return max(0.0, 100.0 - behavior_score)

    return max(0.0, 100.0 - abs(behavior_score - 50.0))


def _tradability_state(gate: str) -> str:
    if gate == "allowed":
        return "tradable"

    if gate == "blocked":
        return "blocked"

    return "manual_review"


def _tradability_score(*, gate: str, behavior_score: float) -> float:
    if gate == "allowed":
        return behavior_score

    if gate == "needs_review":
        return max(0.0, behavior_score - 25.0)

    return 0.0


def _sort_by_symbol(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(items, key=lambda item: str(item.get("symbol") or ""))


def _sort_relative_rank_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: (
            item.get("selection_rank") is None,
            item.get("selection_rank") if item.get("selection_rank") is not None else 999999,
            str(item.get("symbol") or ""),
        ),
    )


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []

    if isinstance(value, list):
        return value

    if isinstance(value, tuple):
        return list(value)

    if isinstance(value, dict):
        return [value]

    return [value]


def _clean_symbol(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    return text or None


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    return text or None


def _float_or_default(value: Any, default: float) -> float:
    try:
        if value is None:
            return default

        return float(value)
    except (TypeError, ValueError):
        return default


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None:
            return None

        return int(value)
    except (TypeError, ValueError):
        return None


