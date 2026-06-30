from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from src.signalforge.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS


OPTION_THETA_SENSITIVITY_SCHEMA_VERSION = "signalforge_option_theta_sensitivity.v1"

DEFAULT_LOW_AVG_ABS_THETA_THRESHOLD = 0.01
DEFAULT_ELEVATED_AVG_ABS_THETA_THRESHOLD = 0.03
DEFAULT_HIGH_AVG_ABS_THETA_THRESHOLD = 0.07
DEFAULT_HIGH_MAX_ABS_THETA_THRESHOLD = 0.12


class _MissingType:
    pass


_MISSING = _MissingType()


def build_signalforge_option_theta_sensitivity(
    option_source: Mapping[str, Any] | Sequence[Any] | None,
    *,
    low_avg_abs_theta_threshold: float = DEFAULT_LOW_AVG_ABS_THETA_THRESHOLD,
    elevated_avg_abs_theta_threshold: float = DEFAULT_ELEVATED_AVG_ABS_THETA_THRESHOLD,
    high_avg_abs_theta_threshold: float = DEFAULT_HIGH_AVG_ABS_THETA_THRESHOLD,
    high_max_abs_theta_threshold: float = DEFAULT_HIGH_MAX_ABS_THETA_THRESHOLD,
) -> dict[str, Any]:
    """Classify option theta sensitivity by underlying symbol.

    This is a compact Options Behavior feature artifact. It consumes
    option-chain-like rows and emits per-symbol theta decay sensitivity labels
    for strategy selection. It does not retain or export raw option chains.
    """

    threshold_error = _threshold_error(
        low_avg_abs_theta_threshold=low_avg_abs_theta_threshold,
        elevated_avg_abs_theta_threshold=elevated_avg_abs_theta_threshold,
        high_avg_abs_theta_threshold=high_avg_abs_theta_threshold,
        high_max_abs_theta_threshold=high_max_abs_theta_threshold,
    )
    if threshold_error:
        return _blocked_result(threshold_error)

    option_rows = _extract_option_rows(option_source)
    if not option_rows:
        return _blocked_result("option source contains no option_rows")

    malformed_rows: list[dict[str, Any]] = []
    grouped_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for index, row in enumerate(option_rows):
        if not isinstance(row, Mapping):
            malformed_rows.append({"row_index": index, "reason": "option row must be a mapping"})
            continue

        symbol = _clean_symbol(
            _first_present(row, ("underlying_symbol", "symbol", "ticker", "underlying"))
        )
        if symbol is None:
            malformed_rows.append({"row_index": index, "reason": "missing underlying symbol"})
            continue

        grouped_rows[symbol].append(dict(row))

    if not grouped_rows:
        return _blocked_result("no option rows with valid symbols were found")

    items = [
        _build_theta_item(
            symbol=symbol,
            rows=rows,
            low_avg_abs_theta_threshold=low_avg_abs_theta_threshold,
            elevated_avg_abs_theta_threshold=elevated_avg_abs_theta_threshold,
            high_avg_abs_theta_threshold=high_avg_abs_theta_threshold,
            high_max_abs_theta_threshold=high_max_abs_theta_threshold,
        )
        for symbol, rows in sorted(grouped_rows.items())
    ]

    ready_count = sum(1 for item in items if item["coverage_status"] == "ready")
    needs_review_count = len(items) - ready_count
    status = "ready" if needs_review_count == 0 and not malformed_rows else "needs_review"
    summary = _summary(items, malformed_rows)

    return {
        "artifact_type": "signalforge_option_theta_sensitivity",
        "schema_version": OPTION_THETA_SENSITIVITY_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "contract": "option_theta_sensitivity",
        "adapter_type": "option_theta_sensitivity_builder",
        "review_scope": "theta_sensitivity_behavior_not_raw_option_chain_export",
        "source_artifact": _source_artifact_type(option_source),
        "thresholds": {
            "low_avg_abs_theta_threshold": low_avg_abs_theta_threshold,
            "elevated_avg_abs_theta_threshold": elevated_avg_abs_theta_threshold,
            "high_avg_abs_theta_threshold": high_avg_abs_theta_threshold,
            "high_max_abs_theta_threshold": high_max_abs_theta_threshold,
        },
        "covered_capabilities": ["theta_sensitivity"],
        "next_build_recommendations": [
            {
                "capability": "options_behavior_integration",
                "priority": "medium",
                "recommendation": "Merge IV, gamma, theta, skew, term structure, and liquidity behavior into a unified Options Behavior decision artifact.",
            }
        ],
        "option_theta_sensitivity_items": items,
        "option_theta_sensitivity_summary": summary,
        "malformed_option_rows": malformed_rows[:100],
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _build_theta_item(
    *,
    symbol: str,
    rows: Sequence[Mapping[str, Any]],
    low_avg_abs_theta_threshold: float,
    elevated_avg_abs_theta_threshold: float,
    high_avg_abs_theta_threshold: float,
    high_max_abs_theta_threshold: float,
) -> dict[str, Any]:
    usable_rows = 0
    missing_theta_rows = 0
    positive_theta_rows = 0
    negative_theta_rows = 0
    zero_theta_rows = 0
    abs_theta_values: list[float] = []
    weighted_abs_theta_sum = 0.0
    theta_weight_total = 0.0
    signed_theta_weight_sum = 0.0
    theta_weight_source_counts: Counter[str] = Counter()

    for row in rows:
        theta = _clean_float(_first_present(row, ("theta", "Theta")))
        if theta is None:
            missing_theta_rows += 1
            continue

        usable_rows += 1
        abs_theta = abs(theta)
        abs_theta_values.append(abs_theta)

        if theta < 0:
            negative_theta_rows += 1
        elif theta > 0:
            positive_theta_rows += 1
        else:
            zero_theta_rows += 1

        weight, weight_source = _theta_weight(row)
        theta_weight_source_counts[weight_source] += 1
        weighted_abs_theta_sum += abs_theta * weight
        signed_theta_weight_sum += theta * weight
        theta_weight_total += weight

    avg_abs_theta = (sum(abs_theta_values) / len(abs_theta_values)) if abs_theta_values else 0.0
    max_abs_theta = max(abs_theta_values) if abs_theta_values else 0.0
    weighted_avg_abs_theta = (
        weighted_abs_theta_sum / theta_weight_total if theta_weight_total > 0 else avg_abs_theta
    )
    weighted_net_theta = (
        signed_theta_weight_sum / theta_weight_total if theta_weight_total > 0 else 0.0
    )

    state, reasons = _theta_sensitivity_state(
        usable_rows=usable_rows,
        avg_abs_theta=avg_abs_theta,
        max_abs_theta=max_abs_theta,
        low_avg_abs_theta_threshold=low_avg_abs_theta_threshold,
        elevated_avg_abs_theta_threshold=elevated_avg_abs_theta_threshold,
        high_avg_abs_theta_threshold=high_avg_abs_theta_threshold,
        high_max_abs_theta_threshold=high_max_abs_theta_threshold,
    )
    coverage_status = "ready" if state != "needs_review" else "needs_review"

    return {
        "artifact_type": "option_theta_sensitivity_item",
        "symbol": symbol,
        "coverage_status": coverage_status,
        "theta_sensitivity_state": state,
        "theta_sensitivity_reasons": reasons,
        "row_count": len(rows),
        "usable_theta_row_count": usable_rows,
        "missing_theta_row_count": missing_theta_rows,
        "negative_theta_row_count": negative_theta_rows,
        "positive_theta_row_count": positive_theta_rows,
        "zero_theta_row_count": zero_theta_rows,
        "avg_abs_theta": _round(avg_abs_theta),
        "max_abs_theta": _round(max_abs_theta),
        "weighted_avg_abs_theta": _round(weighted_avg_abs_theta),
        "weighted_net_theta": _round(weighted_net_theta),
        "theta_direction_bias": _theta_direction_bias(
            negative_theta_rows=negative_theta_rows,
            positive_theta_rows=positive_theta_rows,
            zero_theta_rows=zero_theta_rows,
        ),
        "theta_weight_total": _round(theta_weight_total),
        "theta_weight_source_counts": dict(sorted(theta_weight_source_counts.items())),
        "manual_review_required": coverage_status != "ready",
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _theta_sensitivity_state(
    *,
    usable_rows: int,
    avg_abs_theta: float,
    max_abs_theta: float,
    low_avg_abs_theta_threshold: float,
    elevated_avg_abs_theta_threshold: float,
    high_avg_abs_theta_threshold: float,
    high_max_abs_theta_threshold: float,
) -> tuple[str, list[str]]:
    if usable_rows == 0:
        return "needs_review", ["no_usable_theta_rows"]

    if avg_abs_theta >= high_avg_abs_theta_threshold or max_abs_theta >= high_max_abs_theta_threshold:
        return "high_theta_sensitivity", ["theta_exceeds_high_threshold"]

    if avg_abs_theta >= elevated_avg_abs_theta_threshold:
        return "elevated_theta_sensitivity", ["theta_exceeds_elevated_threshold"]

    if avg_abs_theta <= low_avg_abs_theta_threshold:
        return "low_theta_sensitivity", ["theta_below_low_threshold"]

    return "normal_theta_sensitivity", ["theta_within_normal_range"]


def _theta_direction_bias(
    *,
    negative_theta_rows: int,
    positive_theta_rows: int,
    zero_theta_rows: int,
) -> str:
    if negative_theta_rows > positive_theta_rows and negative_theta_rows > zero_theta_rows:
        return "negative_theta_dominant"
    if positive_theta_rows > negative_theta_rows and positive_theta_rows > zero_theta_rows:
        return "positive_theta_dominant"
    if zero_theta_rows > negative_theta_rows and zero_theta_rows > positive_theta_rows:
        return "zero_theta_dominant"
    return "mixed_theta"


def _theta_weight(row: Mapping[str, Any]) -> tuple[float, str]:
    open_interest = _clean_float(
        _first_present(row, ("open_interest", "openinterest", "OpenInterest"))
    )
    volume = _clean_float(_first_present(row, ("volume", "Volume")))

    if open_interest is not None and open_interest > 0:
        return open_interest, "open_interest"
    if volume is not None and volume > 0:
        return volume, "volume"
    return 1.0, "equal_weight"


def _summary(
    items: Sequence[Mapping[str, Any]],
    malformed_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    coverage_counts = Counter(_clean_text(item.get("coverage_status")) for item in items)
    state_counts = Counter(_clean_text(item.get("theta_sensitivity_state")) for item in items)

    return {
        "symbol_count": len(items),
        "ready_symbol_count": coverage_counts.get("ready", 0),
        "needs_review_symbol_count": coverage_counts.get("needs_review", 0),
        "malformed_row_count": len(malformed_rows),
        "coverage_status_counts": dict(sorted(coverage_counts.items())),
        "theta_sensitivity_state_counts": dict(sorted(state_counts.items())),
        "covered_capabilities": ["theta_sensitivity"],
    }


def _extract_option_rows(source: Mapping[str, Any] | Sequence[Any] | None) -> list[Any]:
    if source is None:
        return []

    if isinstance(source, Mapping):
        for key in (
            "option_rows",
            "rows",
            "quantconnect_option_rows",
            "data",
            "items",
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
    low_avg_abs_theta_threshold: float,
    elevated_avg_abs_theta_threshold: float,
    high_avg_abs_theta_threshold: float,
    high_max_abs_theta_threshold: float,
) -> str | None:
    values = {
        "low_avg_abs_theta_threshold": low_avg_abs_theta_threshold,
        "elevated_avg_abs_theta_threshold": elevated_avg_abs_theta_threshold,
        "high_avg_abs_theta_threshold": high_avg_abs_theta_threshold,
        "high_max_abs_theta_threshold": high_max_abs_theta_threshold,
    }
    for name, value in values.items():
        if value < 0:
            return f"{name} must be greater than or equal to 0"

    if not low_avg_abs_theta_threshold < elevated_avg_abs_theta_threshold < high_avg_abs_theta_threshold:
        return "theta average thresholds must increase from low to elevated to high"

    return None


def _blocked_result(reason: str) -> dict[str, Any]:
    return {
        "artifact_type": "signalforge_option_theta_sensitivity",
        "schema_version": OPTION_THETA_SENSITIVITY_SCHEMA_VERSION,
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "contract": "option_theta_sensitivity",
        "adapter_type": "option_theta_sensitivity_builder",
        "review_scope": "theta_sensitivity_behavior_not_raw_option_chain_export",
        "blocker_items": [{"reason": reason}],
        "covered_capabilities": ["theta_sensitivity"],
        "option_theta_sensitivity_items": [],
        "option_theta_sensitivity_summary": {
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
