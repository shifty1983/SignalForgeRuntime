from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from src.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS


OPTION_IV_EXPANSION_CONTRACTION_SCHEMA_VERSION = (
    "signalforge_option_iv_expansion_contraction.v1"
)

DEFAULT_EXPANSION_ABS_THRESHOLD = 0.02
DEFAULT_EXPANSION_PCT_THRESHOLD = 0.10
DEFAULT_SPIKE_ABS_THRESHOLD = 0.08
DEFAULT_SPIKE_PCT_THRESHOLD = 0.30


class _MissingType:
    pass


_MISSING = _MissingType()


def build_signalforge_option_iv_expansion_contraction(
    iv_history_source: Mapping[str, Any] | Sequence[Any] | None,
    *,
    expansion_abs_threshold: float = DEFAULT_EXPANSION_ABS_THRESHOLD,
    expansion_pct_threshold: float = DEFAULT_EXPANSION_PCT_THRESHOLD,
    spike_abs_threshold: float = DEFAULT_SPIKE_ABS_THRESHOLD,
    spike_pct_threshold: float = DEFAULT_SPIKE_PCT_THRESHOLD,
) -> dict[str, Any]:
    """Classify IV expansion, contraction, stability, spike, or crush by symbol.

    This artifact consumes the SignalForge IV history snapshot output. It is a
    feature/decision layer and intentionally does not store contract-level option
    rows or raw option-chain data.
    """

    threshold_error = _threshold_error(
        expansion_abs_threshold=expansion_abs_threshold,
        expansion_pct_threshold=expansion_pct_threshold,
        spike_abs_threshold=spike_abs_threshold,
        spike_pct_threshold=spike_pct_threshold,
    )
    if threshold_error:
        return _blocked_result(threshold_error)

    source_items = _extract_iv_history_items(iv_history_source)
    if not source_items:
        return _blocked_result("IV history source contains no option_iv_history_items")

    items: list[dict[str, Any]] = []
    malformed_items: list[dict[str, Any]] = []

    for index, item in enumerate(source_items):
        if not isinstance(item, Mapping):
            malformed_items.append(
                {"item_index": index, "reason": "IV history item must be a mapping"}
            )
            continue

        expanded_item = _build_expansion_item(
            item,
            expansion_abs_threshold=expansion_abs_threshold,
            expansion_pct_threshold=expansion_pct_threshold,
            spike_abs_threshold=spike_abs_threshold,
            spike_pct_threshold=spike_pct_threshold,
        )
        if expanded_item is None:
            malformed_items.append(
                {"item_index": index, "reason": "missing symbol on IV history item"}
            )
            continue
        items.append(expanded_item)

    if not items:
        return _blocked_result("no IV expansion/contraction items were produced")

    ready_count = sum(1 for item in items if item["coverage_status"] == "ready")
    needs_review_count = len(items) - ready_count
    status = "ready" if needs_review_count == 0 and not malformed_items else "needs_review"

    summary = _summary(items, malformed_items)

    return {
        "artifact_type": "signalforge_option_iv_expansion_contraction",
        "schema_version": OPTION_IV_EXPANSION_CONTRACTION_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "contract": "option_iv_expansion_contraction",
        "adapter_type": "option_iv_expansion_contraction_builder",
        "review_scope": "iv_expansion_contraction_behavior_not_raw_option_chain_export",
        "source_artifact": _source_artifact_type(iv_history_source),
        "thresholds": {
            "expansion_abs_threshold": expansion_abs_threshold,
            "expansion_pct_threshold": expansion_pct_threshold,
            "spike_abs_threshold": spike_abs_threshold,
            "spike_pct_threshold": spike_pct_threshold,
        },
        "covered_capabilities": ["iv_expansion_contraction"],
        "next_build_recommendations": [
            {
                "capability": "gamma_concentration",
                "priority": "medium",
                "recommendation": "Aggregate gamma by strike and expiration to classify clustered gamma risk.",
            },
            {
                "capability": "theta_sensitivity",
                "priority": "medium",
                "recommendation": "Promote theta from source-readiness coverage into an explicit theta behavior classifier output.",
            },
        ],
        "option_iv_expansion_items": items,
        "option_iv_expansion_summary": summary,
        "malformed_iv_history_items": malformed_items[:100],
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _build_expansion_item(
    item: Mapping[str, Any],
    *,
    expansion_abs_threshold: float,
    expansion_pct_threshold: float,
    spike_abs_threshold: float,
    spike_pct_threshold: float,
) -> dict[str, Any] | None:
    symbol = _clean_symbol(_first_present(item, ("symbol", "underlying_symbol", "ticker")))
    if symbol is None:
        return None

    current_iv = _clean_float(
        _first_present(item, ("current_implied_volatility", "current_iv", "implied_volatility"))
    )
    prior_iv = _clean_float(_first_present(item, ("prior_implied_volatility", "prior_iv")))
    iv_change = _clean_float(item.get("iv_change"))
    iv_change_pct = _clean_float(item.get("iv_change_pct"))

    if iv_change is None and current_iv is not None and prior_iv is not None:
        iv_change = current_iv - prior_iv

    if iv_change_pct is None and iv_change is not None and prior_iv is not None and prior_iv > 0:
        iv_change_pct = iv_change / prior_iv

    source_state = _clean_text(item.get("iv_history_state"))
    state, reasons = _expansion_state(
        source_state=source_state,
        current_iv=current_iv,
        prior_iv=prior_iv,
        iv_change=iv_change,
        iv_change_pct=iv_change_pct,
        expansion_abs_threshold=expansion_abs_threshold,
        expansion_pct_threshold=expansion_pct_threshold,
        spike_abs_threshold=spike_abs_threshold,
        spike_pct_threshold=spike_pct_threshold,
    )

    coverage_status = "ready" if state not in {"needs_review", "unclassified"} else "needs_review"

    return {
        "artifact_type": "option_iv_expansion_item",
        "symbol": symbol,
        "coverage_status": coverage_status,
        "iv_expansion_state": state,
        "iv_expansion_reasons": reasons,
        "current_quote_date": item.get("current_quote_date"),
        "prior_quote_date": item.get("prior_quote_date"),
        "current_implied_volatility": _round(current_iv),
        "prior_implied_volatility": _round(prior_iv),
        "iv_change": _round(iv_change),
        "iv_change_pct": _round(iv_change_pct),
        "iv_rank": item.get("iv_rank"),
        "iv_percentile": item.get("iv_percentile"),
        "iv_rank_state": item.get("iv_rank_state"),
        "iv_percentile_state": item.get("iv_percentile_state"),
        "source_iv_history_state": source_state,
        "source_history_reasons": item.get("history_reasons") or [],
        "manual_review_required": coverage_status != "ready",
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _expansion_state(
    *,
    source_state: str | None,
    current_iv: float | None,
    prior_iv: float | None,
    iv_change: float | None,
    iv_change_pct: float | None,
    expansion_abs_threshold: float,
    expansion_pct_threshold: float,
    spike_abs_threshold: float,
    spike_pct_threshold: float,
) -> tuple[str, list[str]]:
    reasons: list[str] = []

    if source_state and source_state != "ready":
        reasons.append("source_iv_history_not_ready")
    if current_iv is None or current_iv <= 0:
        reasons.append("missing_current_iv")
    if prior_iv is None or prior_iv <= 0:
        reasons.append("missing_prior_iv")
    if iv_change is None:
        reasons.append("missing_iv_change")

    if reasons:
        return "needs_review", reasons

    assert iv_change is not None

    pct = iv_change_pct if iv_change_pct is not None else 0.0

    if iv_change >= spike_abs_threshold or pct >= spike_pct_threshold:
        return "iv_spike", ["iv_change_exceeds_spike_threshold"]

    if iv_change <= -spike_abs_threshold or pct <= -spike_pct_threshold:
        return "iv_crush", ["iv_change_exceeds_crush_threshold"]

    if iv_change >= expansion_abs_threshold or pct >= expansion_pct_threshold:
        return "iv_expanding", ["iv_change_exceeds_expansion_threshold"]

    if iv_change <= -expansion_abs_threshold or pct <= -expansion_pct_threshold:
        return "iv_contracting", ["iv_change_exceeds_contraction_threshold"]

    return "iv_stable", ["iv_change_within_stable_threshold"]


def _summary(
    items: Sequence[Mapping[str, Any]],
    malformed_items: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    expansion_counts = Counter(_clean_text(item.get("iv_expansion_state")) for item in items)
    coverage_counts = Counter(_clean_text(item.get("coverage_status")) for item in items)

    return {
        "symbol_count": len(items),
        "ready_symbol_count": coverage_counts.get("ready", 0),
        "needs_review_symbol_count": coverage_counts.get("needs_review", 0),
        "malformed_item_count": len(malformed_items),
        "coverage_status_counts": dict(sorted(coverage_counts.items())),
        "iv_expansion_state_counts": dict(sorted(expansion_counts.items())),
        "covered_capabilities": ["iv_expansion_contraction"],
    }


def _extract_iv_history_items(source: Mapping[str, Any] | Sequence[Any] | None) -> list[Any]:
    if source is None:
        return []

    if isinstance(source, Mapping):
        for key in (
            "option_iv_history_items",
            "iv_history_items",
            "items",
            "data",
        ):
            value = source.get(key)
            if isinstance(value, Sequence) and not isinstance(
                value,
                (str, bytes, bytearray),
            ):
                return list(value)
        return []

    if isinstance(source, Sequence) and not isinstance(source, (str, bytes, bytearray)):
        return list(source)

    return []


def _source_artifact_type(source: Mapping[str, Any] | Sequence[Any] | None) -> str | None:
    if isinstance(source, Mapping):
        artifact_type = _clean_text(source.get("artifact_type"))
        return artifact_type or "mapping"
    if isinstance(source, Sequence) and not isinstance(source, (str, bytes, bytearray)):
        return "sequence"
    return None


def _threshold_error(
    *,
    expansion_abs_threshold: float,
    expansion_pct_threshold: float,
    spike_abs_threshold: float,
    spike_pct_threshold: float,
) -> str | None:
    values = {
        "expansion_abs_threshold": expansion_abs_threshold,
        "expansion_pct_threshold": expansion_pct_threshold,
        "spike_abs_threshold": spike_abs_threshold,
        "spike_pct_threshold": spike_pct_threshold,
    }
    for name, value in values.items():
        if value <= 0:
            return f"{name} must be greater than 0"

    if spike_abs_threshold < expansion_abs_threshold:
        return "spike_abs_threshold must be greater than or equal to expansion_abs_threshold"
    if spike_pct_threshold < expansion_pct_threshold:
        return "spike_pct_threshold must be greater than or equal to expansion_pct_threshold"

    return None


def _blocked_result(reason: str) -> dict[str, Any]:
    return {
        "artifact_type": "signalforge_option_iv_expansion_contraction",
        "schema_version": OPTION_IV_EXPANSION_CONTRACTION_SCHEMA_VERSION,
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "contract": "option_iv_expansion_contraction",
        "adapter_type": "option_iv_expansion_contraction_builder",
        "review_scope": "iv_expansion_contraction_behavior_not_raw_option_chain_export",
        "blocker_items": [{"reason": reason}],
        "covered_capabilities": ["iv_expansion_contraction"],
        "option_iv_expansion_items": [],
        "option_iv_expansion_summary": {
            "symbol_count": 0,
            "ready_symbol_count": 0,
            "needs_review_symbol_count": 0,
            "malformed_item_count": 0,
        },
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _first_present(row: Mapping[str, Any], names: Sequence[str]) -> Any:
    for name in names:
        value = row.get(name, _MISSING)
        if value is not _MISSING and value is not None:
            return value
    return None


def _clean_symbol(value: Any) -> str | None:
    text = _clean_text(value)
    if text is None:
        return None
    return text.split(" ")[0].upper()


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clean_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _round(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 6)
