from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from src.signalforge.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS


ASSET_DIRECTIONAL_STANCE_SCHEMA_VERSION = "signalforge_asset_directional_stance.v1"

DIRECTIONAL_STANCES = {"long_bias", "short_bias", "neutral_bias"}
GATES = {"allowed", "review_required", "blocked"}


def build_signalforge_asset_directional_stance(
    asset_behavior_selection: Mapping[str, Any] | None,
    regime_directional_policy: Mapping[str, Any] | None,
    *,
    symbols: Sequence[str] | None = None,
) -> dict[str, Any]:
    """
    Combine instrument behavior with regime directional policy.

    This layer answers long / short / neutral for each instrument.
    It does not route orders, submit orders, model fills, perform live
    execution, model slippage, or make automatic strategy/parameter/pause
    changes.
    """

    if not isinstance(asset_behavior_selection, Mapping):
        return _blocked_result("asset behavior selection must be a mapping")

    if not isinstance(regime_directional_policy, Mapping):
        return _blocked_result("regime directional policy must be a mapping")

    candidates = asset_behavior_selection.get("candidates")
    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes, bytearray)):
        return _blocked_result("asset behavior selection must contain candidates list")

    regime_policy_by_class = _extract_regime_policy_by_asset_class(regime_directional_policy)
    if not regime_policy_by_class:
        return _blocked_result("regime directional policy must contain asset class directional policies")

    requested_symbols = _normalize_symbols(symbols)

    stances: list[dict[str, Any]] = []
    skipped_items: list[dict[str, Any]] = []
    warning_items: list[dict[str, Any]] = []

    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, Mapping):
            skipped_items.append(
                {
                    "reason": "candidate must be a mapping",
                    "item_index": index,
                }
            )
            continue

        symbol = _clean_symbol(candidate.get("symbol"))
        if symbol is None:
            skipped_items.append(
                {
                    "reason": "candidate missing symbol",
                    "item_index": index,
                }
            )
            continue

        if requested_symbols is not None and symbol not in requested_symbols:
            continue

        asset_class = _clean_text(candidate.get("asset_class")) or "unknown"
        regime_policy = regime_policy_by_class.get(asset_class)

        if regime_policy is None:
            warning_items.append(
                {
                    "reason": "missing regime directional policy for asset class",
                    "symbol": symbol,
                    "asset_class": asset_class,
                }
            )
            regime_policy = _neutral_regime_policy(asset_class)

        stances.append(
            _build_instrument_stance(
                candidate=candidate,
                regime_policy=regime_policy,
            )
        )

    if requested_symbols is not None:
        observed = {item["symbol"] for item in stances}
        for missing_symbol in sorted(requested_symbols - observed):
            warning_items.append(
                {
                    "reason": "requested symbol did not produce directional stance",
                    "symbol": missing_symbol,
                }
            )

    if not stances:
        return _blocked_result("no instrument directional stances were produced")

    source_status = _clean_text(asset_behavior_selection.get("status"))
    regime_status = _clean_text(regime_directional_policy.get("status"))

    if source_status not in {None, "ready"}:
        warning_items.append(
            {
                "reason": "asset behavior selection source is not ready",
                "source_status": source_status,
            }
        )

    if regime_status not in {None, "ready"}:
        warning_items.append(
            {
                "reason": "regime directional policy source is not ready",
                "regime_status": regime_status,
            }
        )

    status = "needs_review" if warning_items else "ready"

    stances = sorted(stances, key=lambda item: (item["directional_rank"], item["symbol"]))

    return {
        "artifact_type": "signalforge_asset_directional_stance",
        "schema_version": ASSET_DIRECTIONAL_STANCE_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "contract": "asset_directional_stance",
        "adapter_type": "asset_directional_stance_builder",
        "asset_behavior_selection_artifact_type": asset_behavior_selection.get("artifact_type"),
        "asset_behavior_selection_status": asset_behavior_selection.get("status"),
        "regime_directional_policy_artifact_type": regime_directional_policy.get("artifact_type"),
        "regime_directional_policy_status": regime_directional_policy.get("status"),
        "macro_regime_label": regime_directional_policy.get("macro_regime_label"),
        "policy_regime_label": regime_directional_policy.get("policy_regime_label"),
        "weekly_planning_label": regime_directional_policy.get("weekly_planning_label"),
        "market_confirmation": regime_directional_policy.get("market_confirmation"),
        "aggregate_market_bias": regime_directional_policy.get("aggregate_market_bias"),
        "instrument_directional_stances": stances,
        "directional_stance_summary": _directional_stance_summary(stances),
        "skipped_items": skipped_items,
        "blocker_items": [],
        "warning_items": _dedupe_items(warning_items),
        "requested_symbols": sorted(requested_symbols) if requested_symbols is not None else None,
        "observed_symbol_count": len(stances),
        "observed_symbols": sorted(item["symbol"] for item in stances),
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _build_instrument_stance(
    *,
    candidate: Mapping[str, Any],
    regime_policy: Mapping[str, Any],
) -> dict[str, Any]:
    symbol = _clean_symbol(candidate.get("symbol")) or "UNKNOWN"
    asset_class = _clean_text(candidate.get("asset_class")) or "unknown"

    behavior_stance, behavior_reasons = _behavior_directional_stance(candidate)
    regime_stance = _clean_stance(regime_policy.get("regime_directional_stance"))

    behavior_gate = _behavior_gate(candidate)
    regime_gate = _clean_gate(regime_policy.get("policy_gate"))

    final_stance, alignment, stance_reasons, conflict_reasons = _combine_stances(
        behavior_stance=behavior_stance,
        regime_stance=regime_stance,
        behavior_reasons=behavior_reasons,
    )

    combined_gate = _combined_gate(
        behavior_gate=behavior_gate,
        regime_gate=regime_gate,
        conflict_reasons=conflict_reasons,
    )

    scores = _combined_scores(
        final_stance=final_stance,
        behavior_stance=behavior_stance,
        regime_stance=regime_stance,
        regime_policy=regime_policy,
        combined_gate=combined_gate,
    )

    manual_review_required = (
        combined_gate in {"review_required", "blocked"}
        or bool(conflict_reasons)
        or alignment in {"regime_behavior_conflict", "regime_unconfirmed_by_behavior"}
    )

    return {
        "artifact_type": "asset_directional_stance_item",
        "symbol": symbol,
        "asset_class": asset_class,
        "directional_stance": final_stance,
        "directional_rank": _directional_rank(final_stance),
        "stance_score": scores["stance_score"],
        "long_score": scores["long_score"],
        "short_score": scores["short_score"],
        "neutral_score": scores["neutral_score"],
        "behavior_directional_stance": behavior_stance,
        "regime_directional_stance": regime_stance,
        "stance_alignment": alignment,
        "combined_gate": combined_gate,
        "behavior_gate": behavior_gate,
        "regime_policy_gate": regime_gate,
        "manual_review_required": manual_review_required,
        "as_of_date": candidate.get("as_of_date"),
        "behavior_state": candidate.get("behavior_state"),
        "trend_behavior": candidate.get("trend_behavior"),
        "return_behavior": candidate.get("return_behavior"),
        "volatility_behavior": candidate.get("volatility_behavior"),
        "drawdown_behavior": candidate.get("drawdown_behavior"),
        "behavior_score": candidate.get("behavior_score"),
        "selection_bucket": candidate.get("selection_bucket"),
        "asset_class_policy_bucket": candidate.get("asset_class_policy_bucket"),
        "regime_policy_bucket": regime_policy.get("policy_bucket"),
        "regime_policy_reason": regime_policy.get("policy_reason"),
        "stance_reasons": stance_reasons,
        "conflict_reasons": conflict_reasons,
        "source_selection_reasons": list(candidate.get("selection_reasons") or []),
        "source_regime_reasons": list(regime_policy.get("stance_reasons") or []),
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _behavior_directional_stance(candidate: Mapping[str, Any]) -> tuple[str, list[str]]:
    behavior_state = _clean_text(candidate.get("behavior_state"))
    trend_behavior = _clean_text(candidate.get("trend_behavior"))
    return_behavior = _clean_text(candidate.get("return_behavior"))

    reasons: list[str] = []

    short_reasons = []
    long_reasons = []

    if behavior_state == "defensive":
        short_reasons.append("defensive_behavior_state")
    elif behavior_state == "constructive":
        long_reasons.append("constructive_behavior_state")

    if trend_behavior == "downtrend":
        short_reasons.append("downtrend_behavior")
    elif trend_behavior == "uptrend":
        long_reasons.append("uptrend_behavior")

    if return_behavior == "negative":
        short_reasons.append("negative_return_behavior")
    elif return_behavior == "positive":
        long_reasons.append("positive_return_behavior")

    if len(short_reasons) > len(long_reasons):
        reasons.extend(short_reasons)
        return "short_bias", reasons

    if len(long_reasons) > len(short_reasons):
        reasons.extend(long_reasons)
        return "long_bias", reasons

    reasons.append("mixed_or_neutral_asset_behavior")
    return "neutral_bias", reasons


def _combine_stances(
    *,
    behavior_stance: str,
    regime_stance: str,
    behavior_reasons: Sequence[str],
) -> tuple[str, str, list[str], list[str]]:
    reasons = list(behavior_reasons)
    conflicts: list[str] = []

    if behavior_stance == regime_stance:
        reasons.append("behavior_aligned_with_regime")
        return behavior_stance, "aligned", reasons, conflicts

    if regime_stance == "neutral_bias" and behavior_stance in {"long_bias", "short_bias"}:
        reasons.append("behavior_leads_neutral_regime")
        return behavior_stance, "behavior_led", reasons, conflicts

    if behavior_stance == "neutral_bias" and regime_stance in {"long_bias", "short_bias"}:
        reasons.append("regime_bias_not_confirmed_by_asset_behavior")
        return "neutral_bias", "regime_unconfirmed_by_behavior", reasons, conflicts

    if behavior_stance in {"long_bias", "short_bias"} and regime_stance in {"long_bias", "short_bias"}:
        conflicts.append("behavior_direction_conflicts_with_regime_direction")
        reasons.append("regime_behavior_directional_conflict")
        return "neutral_bias", "regime_behavior_conflict", reasons, conflicts

    reasons.append("neutral_combination")
    return "neutral_bias", "neutral", reasons, conflicts


def _combined_scores(
    *,
    final_stance: str,
    behavior_stance: str,
    regime_stance: str,
    regime_policy: Mapping[str, Any],
    combined_gate: str,
) -> dict[str, float]:
    regime_long = _float_or_default(regime_policy.get("long_score"), 0.33)
    regime_short = _float_or_default(regime_policy.get("short_score"), 0.33)
    regime_neutral = _float_or_default(regime_policy.get("neutral_score"), 0.34)

    behavior_scores = _behavior_scores(behavior_stance)

    long_score = (behavior_scores["long_score"] + regime_long) / 2
    short_score = (behavior_scores["short_score"] + regime_short) / 2
    neutral_score = (behavior_scores["neutral_score"] + regime_neutral) / 2

    if final_stance == "neutral_bias":
        neutral_score = max(neutral_score, 0.65)

    if behavior_stance == regime_stance and final_stance in {"long_bias", "short_bias"}:
        if final_stance == "long_bias":
            long_score = min(long_score + 0.12, 0.95)
        else:
            short_score = min(short_score + 0.12, 0.95)

    if combined_gate == "review_required":
        neutral_score = min(neutral_score + 0.08, 0.95)

    if combined_gate == "blocked":
        long_score = min(long_score, 0.20)
        short_score = min(short_score, 0.20)
        neutral_score = max(neutral_score, 0.80)

    return {
        "stance_score": round(max(long_score, short_score, neutral_score), 4),
        "long_score": round(long_score, 4),
        "short_score": round(short_score, 4),
        "neutral_score": round(neutral_score, 4),
    }


def _behavior_scores(behavior_stance: str) -> dict[str, float]:
    if behavior_stance == "long_bias":
        return {"long_score": 0.70, "short_score": 0.10, "neutral_score": 0.20}

    if behavior_stance == "short_bias":
        return {"long_score": 0.10, "short_score": 0.70, "neutral_score": 0.20}

    return {"long_score": 0.20, "short_score": 0.20, "neutral_score": 0.60}


def _behavior_gate(candidate: Mapping[str, Any]) -> str:
    selection_bucket = _clean_text(candidate.get("selection_bucket"))
    status = _clean_text(candidate.get("status"))

    if selection_bucket == "blocked" or status == "blocked":
        return "blocked"

    if selection_bucket == "needs_review" or status == "needs_review":
        return "review_required"

    return "allowed"


def _combined_gate(
    *,
    behavior_gate: str,
    regime_gate: str,
    conflict_reasons: Sequence[str],
) -> str:
    if behavior_gate == "blocked" or regime_gate == "blocked":
        return "blocked"

    if behavior_gate == "review_required" or regime_gate == "review_required" or conflict_reasons:
        return "review_required"

    return "allowed"


def _extract_regime_policy_by_asset_class(
    regime_directional_policy: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    policies = regime_directional_policy.get("asset_class_directional_policies")
    if not isinstance(policies, Sequence) or isinstance(policies, (str, bytes, bytearray)):
        return {}

    result: dict[str, dict[str, Any]] = {}

    for item in policies:
        if not isinstance(item, Mapping):
            continue

        asset_class = _clean_text(item.get("asset_class"))
        if asset_class:
            result[asset_class] = dict(item)

    return result


def _neutral_regime_policy(asset_class: str) -> dict[str, Any]:
    return {
        "asset_class": asset_class,
        "policy_bucket": "allowed",
        "policy_gate": "allowed",
        "regime_directional_stance": "neutral_bias",
        "long_score": 0.20,
        "short_score": 0.20,
        "neutral_score": 0.60,
        "policy_reason": "missing regime directional policy defaulted to neutral",
        "stance_reasons": ["missing_regime_policy_default_neutral"],
    }


def _directional_stance_summary(stances: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    stance_counts = Counter(str(item.get("directional_stance")) for item in stances)
    gate_counts = Counter(str(item.get("combined_gate")) for item in stances)
    asset_class_counts = Counter(str(item.get("asset_class")) for item in stances)
    alignment_counts = Counter(str(item.get("stance_alignment")) for item in stances)

    return {
        "instrument_count": len(stances),
        "stance_counts": dict(sorted(stance_counts.items())),
        "gate_counts": dict(sorted(gate_counts.items())),
        "asset_class_counts": dict(sorted(asset_class_counts.items())),
        "alignment_counts": dict(sorted(alignment_counts.items())),
        "long_bias_symbols": sorted(
            str(item.get("symbol"))
            for item in stances
            if item.get("directional_stance") == "long_bias"
        ),
        "short_bias_symbols": sorted(
            str(item.get("symbol"))
            for item in stances
            if item.get("directional_stance") == "short_bias"
        ),
        "neutral_bias_symbols": sorted(
            str(item.get("symbol"))
            for item in stances
            if item.get("directional_stance") == "neutral_bias"
        ),
        "review_required_symbols": sorted(
            str(item.get("symbol"))
            for item in stances
            if item.get("combined_gate") == "review_required"
        ),
        "blocked_symbols": sorted(
            str(item.get("symbol"))
            for item in stances
            if item.get("combined_gate") == "blocked"
        ),
        "manual_review_symbols": sorted(
            str(item.get("symbol"))
            for item in stances
            if item.get("manual_review_required")
        ),
    }


def _normalize_symbols(symbols: Sequence[str] | None) -> set[str] | None:
    if symbols is None:
        return None

    cleaned = {_clean_symbol(symbol) for symbol in symbols}
    return {symbol for symbol in cleaned if symbol}


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


def _directional_rank(stance: str) -> int:
    return {
        "long_bias": 0,
        "short_bias": 1,
        "neutral_bias": 2,
    }.get(stance, 9)


def _dedupe_items(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[tuple[str, str], ...]] = set()
    deduped: list[dict[str, Any]] = []

    for item in items:
        normalized = {str(key): str(value) for key, value in item.items()}
        key = tuple(sorted(normalized.items()))
        if key in seen:
            continue

        seen.add(key)
        deduped.append(dict(item))

    return deduped


def _blocked_result(reason: str) -> dict[str, Any]:
    return {
        "artifact_type": "signalforge_asset_directional_stance",
        "schema_version": ASSET_DIRECTIONAL_STANCE_SCHEMA_VERSION,
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "contract": "asset_directional_stance",
        "adapter_type": "asset_directional_stance_builder",
        "instrument_directional_stances": [],
        "directional_stance_summary": {
            "instrument_count": 0,
            "stance_counts": {},
            "gate_counts": {},
            "asset_class_counts": {},
            "alignment_counts": {},
            "long_bias_symbols": [],
            "short_bias_symbols": [],
            "neutral_bias_symbols": [],
            "review_required_symbols": [],
            "blocked_symbols": [],
            "manual_review_symbols": [],
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
