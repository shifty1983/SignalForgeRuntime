from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from src.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS


OPTION_IV_HISTORY_SNAPSHOT_SCHEMA_VERSION = (
    "signalforge_option_iv_history_snapshot.v1"
)

DEFAULT_MIN_HISTORY_POINTS = 3


class _MissingType:
    pass


_MISSING = _MissingType()


def build_signalforge_option_iv_history_snapshot(
    option_source: Mapping[str, Any] | Sequence[Any] | None,
    *,
    min_history_points: int = DEFAULT_MIN_HISTORY_POINTS,
) -> dict[str, Any]:
    """Build per-symbol IV history state for IV rank/percentile classification.

    This artifact is intentionally feature-level. It summarizes historical IV
    observations by underlying symbol and quote date. It does not export or store
    contract-level option chains.
    """

    if min_history_points < 1:
        return _blocked_result("min_history_points must be at least 1")

    option_rows = _extract_option_rows(option_source)
    if not option_rows:
        return _blocked_result("option source contains no option rows")

    observations_by_symbol_date, malformed_rows = _group_iv_observations(option_rows)
    if not observations_by_symbol_date:
        return _blocked_result("option source contains no usable IV observations")

    symbol_items = _build_symbol_items(
        observations_by_symbol_date,
        min_history_points=min_history_points,
    )

    if not symbol_items:
        return _blocked_result("no IV history items were produced")

    ready_count = sum(1 for item in symbol_items if item["iv_history_state"] == "ready")
    needs_review_count = len(symbol_items) - ready_count
    status = "ready" if needs_review_count == 0 and not malformed_rows else "needs_review"

    summary = _summary(symbol_items, malformed_rows)

    return {
        "artifact_type": "signalforge_option_iv_history_snapshot",
        "schema_version": OPTION_IV_HISTORY_SNAPSHOT_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "contract": "option_iv_history_snapshot",
        "adapter_type": "option_iv_history_snapshot_builder",
        "review_scope": "iv_rank_percentile_foundation_not_raw_option_chain_export",
        "source_artifact": _option_source_artifact_type(option_source),
        "min_history_points": min_history_points,
        "covered_capabilities": ["iv_rank_percentile"],
        "partial_capabilities": ["iv_expansion_contraction"],
        "next_build_recommendations": [
            {
                "capability": "iv_expansion_contraction",
                "priority": "high",
                "recommendation": "Use current/prior IV observations from this snapshot to classify IV expansion, contraction, or stable IV.",
            }
        ],
        "option_iv_history_items": symbol_items,
        "option_iv_history_summary": summary,
        "malformed_option_rows": malformed_rows[:100],
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _build_symbol_items(
    observations_by_symbol_date: Mapping[tuple[str, str], Sequence[float]],
    *,
    min_history_points: int,
) -> list[dict[str, Any]]:
    dated_iv_by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for (symbol, quote_date), values in observations_by_symbol_date.items():
        clean_values = [_clean_float(value) for value in values]
        clean_values = [value for value in clean_values if value is not None and value > 0]
        if not clean_values:
            continue

        avg_iv = sum(clean_values) / len(clean_values)
        dated_iv_by_symbol[symbol].append(
            {
                "quote_date": quote_date,
                "avg_implied_volatility": avg_iv,
                "contract_count": len(clean_values),
                "min_contract_iv": min(clean_values),
                "max_contract_iv": max(clean_values),
            }
        )

    items: list[dict[str, Any]] = []
    for symbol in sorted(dated_iv_by_symbol):
        history = sorted(dated_iv_by_symbol[symbol], key=lambda row: row["quote_date"])
        if not history:
            continue
        items.append(_symbol_item(symbol, history, min_history_points=min_history_points))

    return items


def _symbol_item(
    symbol: str,
    history: Sequence[Mapping[str, Any]],
    *,
    min_history_points: int,
) -> dict[str, Any]:
    current = history[-1]
    prior = history[-2] if len(history) >= 2 else None
    values = [_clean_float(item.get("avg_implied_volatility")) for item in history]
    values = [value for value in values if value is not None and value > 0]

    current_iv = _clean_float(current.get("avg_implied_volatility"))
    prior_iv = _clean_float(prior.get("avg_implied_volatility")) if prior else None
    min_iv = min(values) if values else None
    max_iv = max(values) if values else None

    state, reasons = _history_state(
        history_count=len(values),
        min_history_points=min_history_points,
        min_iv=min_iv,
        max_iv=max_iv,
    )

    iv_rank = None
    iv_percentile = None
    iv_rank_state = "unclassified"
    iv_percentile_state = "unclassified"

    if state == "ready" and current_iv is not None and min_iv is not None and max_iv is not None:
        iv_rank = ((current_iv - min_iv) / (max_iv - min_iv)) * 100.0
        iv_percentile = (sum(1 for value in values if value <= current_iv) / len(values)) * 100.0
        iv_rank_state = _rank_state(iv_rank)
        iv_percentile_state = _percentile_state(iv_percentile)

    iv_change = None
    iv_change_pct = None
    if current_iv is not None and prior_iv is not None:
        iv_change = current_iv - prior_iv
        if prior_iv > 0:
            iv_change_pct = iv_change / prior_iv

    return {
        "artifact_type": "option_iv_history_item",
        "symbol": symbol,
        "iv_history_state": state,
        "coverage_status": "ready" if state == "ready" else "needs_review",
        "history_reasons": reasons,
        "history_count": len(values),
        "min_history_points": min_history_points,
        "current_quote_date": current.get("quote_date"),
        "prior_quote_date": prior.get("quote_date") if prior else None,
        "current_implied_volatility": _round(current_iv),
        "prior_implied_volatility": _round(prior_iv),
        "iv_change": _round(iv_change),
        "iv_change_pct": _round(iv_change_pct),
        "min_implied_volatility": _round(min_iv),
        "max_implied_volatility": _round(max_iv),
        "iv_rank": _round(iv_rank),
        "iv_percentile": _round(iv_percentile),
        "iv_rank_state": iv_rank_state,
        "iv_percentile_state": iv_percentile_state,
        "latest_contract_count": current.get("contract_count"),
        "history": [dict(item) for item in history],
        "manual_review_required": state != "ready",
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _history_state(
    *,
    history_count: int,
    min_history_points: int,
    min_iv: float | None,
    max_iv: float | None,
) -> tuple[str, list[str]]:
    reasons: list[str] = []

    if history_count < min_history_points:
        reasons.append("insufficient_iv_history")

    if min_iv is None or max_iv is None:
        reasons.append("missing_iv_values")
    elif math.isclose(min_iv, max_iv, rel_tol=0.0, abs_tol=1e-12):
        reasons.append("flat_iv_history")

    if reasons:
        return "needs_review", reasons

    return "ready", ["iv_history_ready"]


def _rank_state(value: float | None) -> str:
    if value is None:
        return "unclassified"
    if value >= 70.0:
        return "high_iv_rank"
    if value <= 30.0:
        return "low_iv_rank"
    return "normal_iv_rank"


def _percentile_state(value: float | None) -> str:
    if value is None:
        return "unclassified"
    if value >= 70.0:
        return "high_iv_percentile"
    if value <= 30.0:
        return "low_iv_percentile"
    return "normal_iv_percentile"


def _summary(
    items: Sequence[Mapping[str, Any]],
    malformed_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    state_counts = Counter(_clean_text(item.get("iv_history_state")) for item in items)
    rank_counts = Counter(_clean_text(item.get("iv_rank_state")) for item in items)
    percentile_counts = Counter(_clean_text(item.get("iv_percentile_state")) for item in items)

    return {
        "symbol_count": len(items),
        "ready_symbol_count": state_counts.get("ready", 0),
        "needs_review_symbol_count": state_counts.get("needs_review", 0),
        "malformed_row_count": len(malformed_rows),
        "iv_history_state_counts": dict(sorted(state_counts.items())),
        "iv_rank_state_counts": dict(sorted(rank_counts.items())),
        "iv_percentile_state_counts": dict(sorted(percentile_counts.items())),
        "covered_capabilities": ["iv_rank_percentile"],
        "partial_capabilities": ["iv_expansion_contraction"],
    }


def _group_iv_observations(
    option_rows: Sequence[Any],
) -> tuple[dict[tuple[str, str], list[float]], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    malformed: list[dict[str, Any]] = []

    for index, row in enumerate(option_rows):
        if not isinstance(row, Mapping):
            malformed.append({"row_index": index, "reason": "option row must be a mapping"})
            continue

        symbol = _clean_symbol(_first_present(row, ("underlying_symbol", "symbol", "ticker")))
        quote_date = _clean_text(_first_present(row, ("quote_date", "date", "timestamp")))
        iv = _clean_float(
            _first_present(row, ("implied_volatility", "avg_implied_volatility", "iv"))
        )

        if symbol is None:
            malformed.append({"row_index": index, "reason": "missing symbol"})
            continue
        if quote_date is None:
            malformed.append({"row_index": index, "reason": "missing quote_date"})
            continue
        if iv is None or iv <= 0:
            malformed.append({"row_index": index, "symbol": symbol, "reason": "missing or invalid implied_volatility"})
            continue

        grouped[(symbol, quote_date[:10])].append(iv)

    return dict(grouped), malformed


def _extract_option_rows(source: Mapping[str, Any] | Sequence[Any] | None) -> list[Any]:
    if source is None:
        return []

    if isinstance(source, Mapping):
        for key in (
            "option_rows",
            "options",
            "quantconnect_option_rows",
            "rows",
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


def _option_source_artifact_type(source: Mapping[str, Any] | Sequence[Any] | None) -> str | None:
    if isinstance(source, Mapping):
        artifact_type = _clean_text(source.get("artifact_type"))
        return artifact_type or "mapping"
    if isinstance(source, Sequence) and not isinstance(source, (str, bytes, bytearray)):
        return "sequence"
    return None


def _blocked_result(reason: str) -> dict[str, Any]:
    return {
        "artifact_type": "signalforge_option_iv_history_snapshot",
        "schema_version": OPTION_IV_HISTORY_SNAPSHOT_SCHEMA_VERSION,
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "contract": "option_iv_history_snapshot",
        "adapter_type": "option_iv_history_snapshot_builder",
        "review_scope": "iv_rank_percentile_foundation_not_raw_option_chain_export",
        "blocker_items": [{"reason": reason}],
        "option_iv_history_items": [],
        "option_iv_history_summary": {
            "symbol_count": 0,
            "ready_symbol_count": 0,
            "needs_review_symbol_count": 0,
            "malformed_row_count": 0,
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
