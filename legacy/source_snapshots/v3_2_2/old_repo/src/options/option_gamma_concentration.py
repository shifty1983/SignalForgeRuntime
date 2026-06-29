from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from src.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS


OPTION_GAMMA_CONCENTRATION_SCHEMA_VERSION = "signalforge_option_gamma_concentration.v1"

DEFAULT_STRIKE_CLUSTER_SHARE_THRESHOLD = 0.40
DEFAULT_EXPIRATION_CLUSTER_SHARE_THRESHOLD = 0.50
DEFAULT_LOW_TOTAL_GAMMA_THRESHOLD = 0.01


class _MissingType:
    pass


_MISSING = _MissingType()


def build_signalforge_option_gamma_concentration(
    option_source: Mapping[str, Any] | Sequence[Any] | None,
    *,
    strike_cluster_share_threshold: float = DEFAULT_STRIKE_CLUSTER_SHARE_THRESHOLD,
    expiration_cluster_share_threshold: float = DEFAULT_EXPIRATION_CLUSTER_SHARE_THRESHOLD,
    low_total_gamma_threshold: float = DEFAULT_LOW_TOTAL_GAMMA_THRESHOLD,
) -> dict[str, Any]:
    """Classify option gamma concentration by underlying symbol.

    This is a feature/decision layer. It consumes option-chain-like rows and
    produces compact gamma concentration labels for strategy selection and risk
    filtering. It intentionally does not attempt to retain or export raw option
    chains.
    """

    threshold_error = _threshold_error(
        strike_cluster_share_threshold=strike_cluster_share_threshold,
        expiration_cluster_share_threshold=expiration_cluster_share_threshold,
        low_total_gamma_threshold=low_total_gamma_threshold,
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
        _build_gamma_item(
            symbol=symbol,
            rows=rows,
            strike_cluster_share_threshold=strike_cluster_share_threshold,
            expiration_cluster_share_threshold=expiration_cluster_share_threshold,
            low_total_gamma_threshold=low_total_gamma_threshold,
        )
        for symbol, rows in sorted(grouped_rows.items())
    ]

    ready_count = sum(1 for item in items if item["coverage_status"] == "ready")
    needs_review_count = len(items) - ready_count
    status = "ready" if needs_review_count == 0 and not malformed_rows else "needs_review"

    summary = _summary(items, malformed_rows)

    return {
        "artifact_type": "signalforge_option_gamma_concentration",
        "schema_version": OPTION_GAMMA_CONCENTRATION_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "contract": "option_gamma_concentration",
        "adapter_type": "option_gamma_concentration_builder",
        "review_scope": "gamma_concentration_behavior_not_raw_option_chain_export",
        "source_artifact": _source_artifact_type(option_source),
        "thresholds": {
            "strike_cluster_share_threshold": strike_cluster_share_threshold,
            "expiration_cluster_share_threshold": expiration_cluster_share_threshold,
            "low_total_gamma_threshold": low_total_gamma_threshold,
        },
        "covered_capabilities": ["gamma_concentration"],
        "next_build_recommendations": [
            {
                "capability": "theta_sensitivity",
                "priority": "medium",
                "recommendation": "Promote theta from source-readiness coverage into an explicit theta behavior classifier output.",
            }
        ],
        "option_gamma_concentration_items": items,
        "option_gamma_concentration_summary": summary,
        "malformed_option_rows": malformed_rows[:100],
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _build_gamma_item(
    *,
    symbol: str,
    rows: Sequence[Mapping[str, Any]],
    strike_cluster_share_threshold: float,
    expiration_cluster_share_threshold: float,
    low_total_gamma_threshold: float,
) -> dict[str, Any]:
    strike_weights: dict[str, float] = defaultdict(float)
    expiration_weights: dict[str, float] = defaultdict(float)
    usable_rows = 0
    missing_gamma_rows = 0
    missing_strike_rows = 0
    missing_expiration_rows = 0
    gamma_weight_source_counts: Counter[str] = Counter()

    for row in rows:
        gamma = _clean_float(_first_present(row, ("gamma", "Gamma")))
        if gamma is None:
            missing_gamma_rows += 1
            continue

        strike = _clean_float(_first_present(row, ("strike", "strike_price", "Strike")))
        expiration = _clean_text(
            _first_present(row, ("expiration", "expiry", "expiration_date", "Expiration"))
        )

        if strike is None:
            missing_strike_rows += 1
            continue
        if expiration is None:
            missing_expiration_rows += 1
            continue

        weight, weight_source = _gamma_weight(row, gamma)
        if weight <= 0:
            continue

        usable_rows += 1
        gamma_weight_source_counts[weight_source] += 1
        strike_key = _strike_key(strike)
        expiration_key = _date_key(expiration)
        strike_weights[strike_key] += weight
        expiration_weights[expiration_key] += weight

    total_weight = sum(strike_weights.values())
    dominant_strike, dominant_strike_weight = _top_weight(strike_weights)
    dominant_expiration, dominant_expiration_weight = _top_weight(expiration_weights)

    strike_share = (dominant_strike_weight / total_weight) if total_weight > 0 else 0.0
    expiration_share = (dominant_expiration_weight / total_weight) if total_weight > 0 else 0.0

    state, reasons = _gamma_concentration_state(
        usable_rows=usable_rows,
        total_gamma_weight=total_weight,
        top_strike_gamma_share=strike_share,
        top_expiration_gamma_share=expiration_share,
        strike_cluster_share_threshold=strike_cluster_share_threshold,
        expiration_cluster_share_threshold=expiration_cluster_share_threshold,
        low_total_gamma_threshold=low_total_gamma_threshold,
    )
    coverage_status = "ready" if state != "needs_review" else "needs_review"

    return {
        "artifact_type": "option_gamma_concentration_item",
        "symbol": symbol,
        "coverage_status": coverage_status,
        "gamma_concentration_state": state,
        "gamma_concentration_reasons": reasons,
        "row_count": len(rows),
        "usable_gamma_row_count": usable_rows,
        "missing_gamma_row_count": missing_gamma_rows,
        "missing_strike_row_count": missing_strike_rows,
        "missing_expiration_row_count": missing_expiration_rows,
        "total_gamma_weight": _round(total_weight),
        "dominant_strike": dominant_strike,
        "dominant_strike_gamma_weight": _round(dominant_strike_weight),
        "dominant_strike_gamma_share": _round(strike_share),
        "dominant_expiration": dominant_expiration,
        "dominant_expiration_gamma_weight": _round(dominant_expiration_weight),
        "dominant_expiration_gamma_share": _round(expiration_share),
        "strike_bucket_count": len(strike_weights),
        "expiration_bucket_count": len(expiration_weights),
        "gamma_weight_source_counts": dict(sorted(gamma_weight_source_counts.items())),
        "manual_review_required": coverage_status != "ready",
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _gamma_weight(row: Mapping[str, Any], gamma: float) -> tuple[float, str]:
    open_interest = _clean_float(
        _first_present(row, ("open_interest", "openinterest", "OpenInterest"))
    )
    volume = _clean_float(_first_present(row, ("volume", "Volume")))

    base = abs(gamma)
    if open_interest is not None and open_interest > 0:
        return base * open_interest, "abs_gamma_x_open_interest"
    if volume is not None and volume > 0:
        return base * volume, "abs_gamma_x_volume"
    return base, "abs_gamma"


def _gamma_concentration_state(
    *,
    usable_rows: int,
    total_gamma_weight: float,
    top_strike_gamma_share: float,
    top_expiration_gamma_share: float,
    strike_cluster_share_threshold: float,
    expiration_cluster_share_threshold: float,
    low_total_gamma_threshold: float,
) -> tuple[str, list[str]]:
    if usable_rows == 0:
        return "needs_review", ["no_usable_gamma_rows"]

    if total_gamma_weight <= low_total_gamma_threshold:
        return "low_gamma", ["total_gamma_weight_below_low_threshold"]

    strike_clustered = top_strike_gamma_share >= strike_cluster_share_threshold
    expiration_clustered = top_expiration_gamma_share >= expiration_cluster_share_threshold

    if strike_clustered and expiration_clustered:
        return "gamma_clustered", [
            "dominant_strike_exceeds_cluster_threshold",
            "dominant_expiration_exceeds_cluster_threshold",
        ]
    if strike_clustered:
        return "strike_gamma_clustered", ["dominant_strike_exceeds_cluster_threshold"]
    if expiration_clustered:
        return "expiration_gamma_clustered", [
            "dominant_expiration_exceeds_cluster_threshold"
        ]

    return "gamma_distributed", ["gamma_weight_distributed_across_strikes_and_expirations"]


def _summary(
    items: Sequence[Mapping[str, Any]],
    malformed_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    coverage_counts = Counter(_clean_text(item.get("coverage_status")) for item in items)
    state_counts = Counter(_clean_text(item.get("gamma_concentration_state")) for item in items)

    return {
        "symbol_count": len(items),
        "ready_symbol_count": coverage_counts.get("ready", 0),
        "needs_review_symbol_count": coverage_counts.get("needs_review", 0),
        "malformed_row_count": len(malformed_rows),
        "coverage_status_counts": dict(sorted(coverage_counts.items())),
        "gamma_concentration_state_counts": dict(sorted(state_counts.items())),
        "covered_capabilities": ["gamma_concentration"],
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
    strike_cluster_share_threshold: float,
    expiration_cluster_share_threshold: float,
    low_total_gamma_threshold: float,
) -> str | None:
    share_values = {
        "strike_cluster_share_threshold": strike_cluster_share_threshold,
        "expiration_cluster_share_threshold": expiration_cluster_share_threshold,
    }
    for name, value in share_values.items():
        if value <= 0 or value > 1:
            return f"{name} must be greater than 0 and less than or equal to 1"
    if low_total_gamma_threshold < 0:
        return "low_total_gamma_threshold must be greater than or equal to 0"
    return None


def _blocked_result(reason: str) -> dict[str, Any]:
    return {
        "artifact_type": "signalforge_option_gamma_concentration",
        "schema_version": OPTION_GAMMA_CONCENTRATION_SCHEMA_VERSION,
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "contract": "option_gamma_concentration",
        "adapter_type": "option_gamma_concentration_builder",
        "review_scope": "gamma_concentration_behavior_not_raw_option_chain_export",
        "blocker_items": [{"reason": reason}],
        "covered_capabilities": ["gamma_concentration"],
        "option_gamma_concentration_items": [],
        "option_gamma_concentration_summary": {
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


def _top_weight(weights: Mapping[str, float]) -> tuple[str | None, float]:
    if not weights:
        return None, 0.0
    key, value = max(weights.items(), key=lambda item: (item[1], item[0]))
    return key, value


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


def _strike_key(strike: float) -> str:
    return f"{strike:.4f}".rstrip("0").rstrip(".")


def _date_key(text: str) -> str:
    return text.split(" ")[0]


def _round(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 6)
