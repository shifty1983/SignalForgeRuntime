from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from src.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS


OPTION_BEHAVIOR_SOURCE_READINESS_SCHEMA_VERSION = (
    "signalforge_option_behavior_source_readiness.v1"
)


def build_signalforge_option_behavior_source_readiness(
    asset_behavior_decision_export: Mapping[str, Any] | None,
    option_source: Mapping[str, Any] | Sequence[Any] | None,
) -> dict[str, Any]:
    if not isinstance(asset_behavior_decision_export, Mapping):
        return _blocked_result("asset behavior decision export source must be a mapping")

    decision_items = asset_behavior_decision_export.get("asset_behavior_decision_items")
    if not isinstance(decision_items, Sequence) or isinstance(
        decision_items, (str, bytes, bytearray)
    ):
        return _blocked_result(
            "asset behavior decision export must contain asset_behavior_decision_items list"
        )

    if not decision_items:
        return _blocked_result("asset_behavior_decision_items list is empty")

    option_rows = _extract_option_rows(option_source)
    if not option_rows:
        return _blocked_result("option source contains no option rows")

    rows_by_symbol, malformed_rows = _group_option_rows(option_rows)

    readiness_items: list[dict[str, Any]] = []
    skipped_items: list[dict[str, Any]] = []
    warning_items: list[dict[str, Any]] = []

    for index, item in enumerate(decision_items):
        if not isinstance(item, Mapping):
            skipped_items.append(
                {
                    "reason": "asset behavior decision item must be a mapping",
                    "item_index": index,
                }
            )
            continue

        symbol = _clean_symbol(item.get("symbol"))
        if symbol is None:
            skipped_items.append(
                {
                    "reason": "asset behavior decision item missing symbol",
                    "item_index": index,
                }
            )
            continue

        readiness_items.append(
            _readiness_item(
                asset_decision=item,
                symbol=symbol,
                option_rows=rows_by_symbol.get(symbol, []),
            )
        )

    if not readiness_items:
        return _blocked_result("no option behavior source readiness items were produced")

    if skipped_items:
        warning_items.append(
            {
                "reason": "some asset behavior decision items were skipped",
                "skipped_count": len(skipped_items),
            }
        )

    if malformed_rows:
        warning_items.append(
            {
                "reason": "some option rows were malformed and ignored",
                "malformed_row_count": len(malformed_rows),
            }
        )

    source_status = _clean_text(asset_behavior_decision_export.get("status"))
    if source_status not in {None, "ready"}:
        warning_items.append(
            {
                "reason": "asset behavior decision export source is not ready",
                "source_status": source_status,
            }
        )

    status = "needs_review" if warning_items else "ready"

    return {
        "artifact_type": "signalforge_option_behavior_source_readiness",
        "schema_version": OPTION_BEHAVIOR_SOURCE_READINESS_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "contract": "option_behavior_source_readiness",
        "adapter_type": "option_behavior_source_readiness_builder",
        "source_artifacts": {
            "asset_behavior_decision_export": asset_behavior_decision_export.get(
                "artifact_type"
            ),
            "option_source": _option_source_artifact_type(option_source),
        },
        "source_statuses": {
            "asset_behavior_decision_export": asset_behavior_decision_export.get(
                "status"
            ),
            "option_source": _option_source_status(option_source),
        },
        "macro_regime_label": asset_behavior_decision_export.get("macro_regime_label"),
        "policy_regime_label": asset_behavior_decision_export.get("policy_regime_label"),
        "weekly_planning_label": asset_behavior_decision_export.get(
            "weekly_planning_label"
        ),
        "market_confirmation": asset_behavior_decision_export.get("market_confirmation"),
        "aggregate_market_bias": asset_behavior_decision_export.get(
            "aggregate_market_bias"
        ),
        "option_behavior_source_readiness_items": _sort_readiness_items(
            readiness_items
        ),
        "option_behavior_source_readiness_summary": _summary(readiness_items),
        "malformed_option_rows": malformed_rows[:100],
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


def _readiness_item(
    *,
    asset_decision: Mapping[str, Any],
    symbol: str,
    option_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    final_decision = _clean_text(asset_decision.get("final_decision")) or "unknown"
    final_gate = _clean_text(asset_decision.get("final_gate")) or "review_required"
    option_behavior_handoff = (
        _clean_text(asset_decision.get("option_behavior_handoff")) or "review_required"
    )

    usable_rows = [_normalize_option_row(row) for row in option_rows]
    usable_rows = [row for row in usable_rows if row is not None]

    coverage = _coverage_summary(usable_rows)

    readiness_gate, readiness_state, reasons = _source_readiness_gate(
        final_gate=final_gate,
        option_behavior_handoff=option_behavior_handoff,
        usable_row_count=len(usable_rows),
        coverage=coverage,
    )
    quote_gate, quote_state, quote_reasons = _execution_quote_gate(coverage)

    return {
        "artifact_type": "option_behavior_source_readiness_item",
        "symbol": symbol,
        "asset_class": _clean_text(asset_decision.get("asset_class")) or "unknown",
        "directional_stance": _clean_text(asset_decision.get("directional_stance"))
        or "neutral_bias",
        "asset_final_decision": final_decision,
        "asset_final_gate": final_gate,
        "asset_option_behavior_handoff": option_behavior_handoff,
        "option_source_gate": readiness_gate,
        "option_source_state": readiness_state,
        "option_row_count": len(usable_rows),
        "expiration_count": coverage["expiration_count"],
        "strike_count": coverage["strike_count"],
        "call_count": coverage["call_count"],
        "put_count": coverage["put_count"],
        "has_bid_ask": coverage["has_bid_ask"],
        "has_implied_volatility": coverage["has_implied_volatility"],
        "has_delta": coverage["has_delta"],
        "has_gamma": coverage["has_gamma"],
        "has_theta": coverage["has_theta"],
        "has_vega": coverage["has_vega"],
        "earliest_expiration": coverage["earliest_expiration"],
        "latest_expiration": coverage["latest_expiration"],
        "source_readiness_reasons": reasons,
        "execution_quote_gate": quote_gate,
        "execution_quote_state": quote_state,
        "execution_quote_reasons": quote_reasons,
        "manual_review_required": readiness_gate != "ready" or quote_gate != "ready",
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _execution_quote_gate(
    coverage: Mapping[str, Any],
) -> tuple[str, str, list[str]]:
    if coverage["has_bid_ask"]:
        return ("ready", "execution_quotes_ready", ["bid_ask_available"])

    return (
        "review_required",
        "missing_bid_ask",
        ["missing_bid_ask"],
    )


def _source_readiness_gate(
    *,
    final_gate: str,
    option_behavior_handoff: str,
    usable_row_count: int,
    coverage: Mapping[str, Any],
) -> tuple[str, str, list[str]]:
    reasons: list[str] = []

    if final_gate == "blocked" or option_behavior_handoff == "blocked":
        return (
            "blocked",
            "asset_behavior_blocked",
            ["asset_behavior_handoff_blocked"],
        )

    if usable_row_count <= 0:
        return (
            "blocked",
            "missing_option_rows",
            ["no_option_rows_for_symbol"],
        )

    if coverage["expiration_count"] <= 0:
        return (
            "blocked",
            "missing_expiration_coverage",
            ["no_valid_expirations"],
        )

    if coverage["strike_count"] <= 0:
        return (
            "blocked",
            "missing_strike_coverage",
            ["no_valid_strikes"],
        )

    if coverage["call_count"] <= 0 or coverage["put_count"] <= 0:
        reasons.append("missing_call_or_put_side")

    if not coverage["has_implied_volatility"]:
        reasons.append("missing_implied_volatility")

    if option_behavior_handoff == "review_required" or final_gate == "review_required":
        reasons.append("asset_behavior_requires_review")

    if reasons:
        return ("review_required", "option_source_needs_review", reasons)

    return (
        "ready",
        "option_source_ready",
        ["option_source_has_required_shape"],
    )


def _extract_option_rows(option_source: Mapping[str, Any] | Sequence[Any] | None) -> list[Any]:
    if option_source is None:
        return []

    if isinstance(option_source, Sequence) and not isinstance(
        option_source, (str, bytes, bytearray)
    ):
        return list(option_source)

    if not isinstance(option_source, Mapping):
        return []

    direct_keys = (
        "option_rows",
        "options",
        "option_chain",
        "option_chains",
        "contracts",
        "rows",
        "data",
    )

    for key in direct_keys:
        value = option_source.get(key)
        if _looks_like_option_rows(value):
            return list(value)

    nested_paths = (
        ("import_result", "option_rows"),
        ("import_result", "options"),
        ("import_result", "option_chain"),
        ("import_result", "option_chains"),
        ("import_result", "contracts"),
        ("result", "option_rows"),
        ("result", "options"),
        ("payload", "option_rows"),
        ("payload", "options"),
        ("data", "option_rows"),
        ("data", "options"),
    )

    for path in nested_paths:
        value = _get_nested(option_source, path)
        if _looks_like_option_rows(value):
            return list(value)

    recursive_match = _find_option_rows_recursively(option_source)
    return recursive_match or []


def _group_option_rows(
    option_rows: Sequence[Any],
) -> tuple[dict[str, list[Mapping[str, Any]]], list[dict[str, Any]]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    malformed: list[dict[str, Any]] = []

    for index, row in enumerate(option_rows):
        normalized = _normalize_option_row(row)
        if normalized is None:
            malformed.append(
                {
                    "item_index": index,
                    "reason": "option row missing required symbol/expiration/strike/right fields",
                }
            )
            continue

        grouped[normalized["symbol"]].append(normalized)

    return dict(grouped), malformed


def _normalize_option_row(row: Any) -> dict[str, Any] | None:
    if not isinstance(row, Mapping):
        return None

    symbol = _clean_symbol(
        row.get("underlying_symbol")
        or row.get("underlying")
        or row.get("symbol")
        or row.get("ticker")
    )
    expiration = _clean_date_text(
        row.get("expiration")
        or row.get("expiry")
        or row.get("expiration_date")
        or row.get("expiry_date")
    )
    strike = _float_or_none(row.get("strike") or row.get("strike_price"))
    right = _normalize_right(
        row.get("right")
        or row.get("option_right")
        or row.get("type")
        or row.get("contract_type")
    )

    if symbol is None or expiration is None or strike is None or right is None:
        return None

    return {
        "symbol": symbol,
        "expiration": expiration,
        "strike": strike,
        "right": right,
        "bid": _float_or_none(row.get("bid")),
        "ask": _float_or_none(row.get("ask")),
        "implied_volatility": _float_or_none(
            row.get("implied_volatility")
            or row.get("iv")
            or row.get("implied_vol")
        ),
        "delta": _float_or_none(row.get("delta")),
        "gamma": _float_or_none(row.get("gamma")),
        "theta": _float_or_none(row.get("theta")),
        "vega": _float_or_none(row.get("vega")),
    }


def _coverage_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    expirations = sorted(
        {str(row["expiration"]) for row in rows if row.get("expiration") is not None}
    )
    strikes = sorted(
        {float(row["strike"]) for row in rows if row.get("strike") is not None}
    )

    return {
        "expiration_count": len(expirations),
        "strike_count": len(strikes),
        "call_count": sum(1 for row in rows if row.get("right") == "call"),
        "put_count": sum(1 for row in rows if row.get("right") == "put"),
        "has_bid_ask": any(
            row.get("bid") is not None and row.get("ask") is not None
            for row in rows
        ),
        "has_implied_volatility": any(
            row.get("implied_volatility") is not None for row in rows
        ),
        "has_delta": any(row.get("delta") is not None for row in rows),
        "has_gamma": any(row.get("gamma") is not None for row in rows),
        "has_theta": any(row.get("theta") is not None for row in rows),
        "has_vega": any(row.get("vega") is not None for row in rows),
        "earliest_expiration": expirations[0] if expirations else None,
        "latest_expiration": expirations[-1] if expirations else None,
    }


def _summary(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    gate_counts = Counter(str(item.get("option_source_gate") or "unknown") for item in items)
    state_counts = Counter(str(item.get("option_source_state") or "unknown") for item in items)
    execution_quote_gate_counts = Counter(
        str(item.get("execution_quote_gate") or "unknown") for item in items
    )
    decision_counts = Counter(str(item.get("asset_final_decision") or "unknown") for item in items)
    asset_class_counts = Counter(str(item.get("asset_class") or "unknown") for item in items)

    ready_items = [item for item in items if item.get("option_source_gate") == "ready"]
    review_items = [
        item for item in items if item.get("option_source_gate") == "review_required"
    ]
    blocked_items = [
        item for item in items if item.get("option_source_gate") == "blocked"
    ]

    sorted_items = _sort_readiness_items(items)

    return {
        "instrument_count": len(items),
        "option_source_gate_counts": dict(sorted(gate_counts.items())),
        "option_source_state_counts": dict(sorted(state_counts.items())),
        "execution_quote_gate_counts": dict(sorted(execution_quote_gate_counts.items())),
        "asset_final_decision_counts": dict(sorted(decision_counts.items())),
        "asset_class_counts": dict(sorted(asset_class_counts.items())),
        "ready_count": len(ready_items),
        "review_required_count": len(review_items),
        "blocked_count": len(blocked_items),
        "ready_symbols": [
            item["symbol"] for item in sorted_items if item.get("option_source_gate") == "ready"
        ][:25],
        "review_required_symbols": [
            item["symbol"]
            for item in sorted_items
            if item.get("option_source_gate") == "review_required"
        ][:25],
        "blocked_symbols": [
            item["symbol"]
            for item in sorted_items
            if item.get("option_source_gate") == "blocked"
        ][:25],
        "ready_long_symbols": [
            item["symbol"]
            for item in sorted_items
            if item.get("option_source_gate") == "ready"
            and item.get("asset_final_decision") == "eligible_long"
        ][:25],
        "ready_short_symbols": [
            item["symbol"]
            for item in sorted_items
            if item.get("option_source_gate") == "ready"
            and item.get("asset_final_decision") == "eligible_short"
        ][:25],
        "ready_neutral_symbols": [
            item["symbol"]
            for item in sorted_items
            if item.get("option_source_gate") == "ready"
            and item.get("asset_final_decision") == "neutral_position"
        ][:25],
    }


def _sort_readiness_items(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    gate_rank = {
        "ready": 0,
        "review_required": 1,
        "blocked": 2,
    }

    return sorted(
        [dict(item) for item in items],
        key=lambda item: (
            gate_rank.get(str(item.get("option_source_gate")), 9),
            str(item.get("asset_class")),
            str(item.get("symbol")),
        ),
    )


def _looks_like_option_rows(value: Any) -> bool:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return False

    sample = [item for item in list(value)[:10] if isinstance(item, Mapping)]
    if not sample:
        return False

    return any(_normalize_option_row(item) is not None for item in sample)


def _find_option_rows_recursively(value: Any) -> list[Any] | None:
    if _looks_like_option_rows(value):
        return list(value)

    if isinstance(value, Mapping):
        for child in value.values():
            found = _find_option_rows_recursively(child)
            if found:
                return found

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for child in value:
            found = _find_option_rows_recursively(child)
            if found:
                return found

    return None


def _get_nested(value: Any, path: Sequence[str]) -> Any:
    current = value

    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)

    return current


def _option_source_artifact_type(option_source: Any) -> Any:
    if isinstance(option_source, Mapping):
        return option_source.get("artifact_type")
    return None


def _option_source_status(option_source: Any) -> Any:
    if isinstance(option_source, Mapping):
        return option_source.get("status")
    return None


def _clean_symbol(value: Any) -> str | None:
    text = _clean_text(value)
    return text.upper() if text else None


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip().lower()
    return text or None


def _clean_date_text(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    return text or None


def _normalize_right(value: Any) -> str | None:
    text = _clean_text(value)

    if text in {"c", "call", "calls"}:
        return "call"

    if text in {"p", "put", "puts"}:
        return "put"

    return None


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _blocked_result(reason: str) -> dict[str, Any]:
    return {
        "artifact_type": "signalforge_option_behavior_source_readiness",
        "schema_version": OPTION_BEHAVIOR_SOURCE_READINESS_SCHEMA_VERSION,
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "contract": "option_behavior_source_readiness",
        "adapter_type": "option_behavior_source_readiness_builder",
        "source_artifacts": {},
        "source_statuses": {},
        "option_behavior_source_readiness_items": [],
        "option_behavior_source_readiness_summary": {
            "instrument_count": 0,
            "option_source_gate_counts": {},
            "option_source_state_counts": {},
            "asset_final_decision_counts": {},
            "asset_class_counts": {},
            "ready_count": 0,
            "review_required_count": 0,
            "blocked_count": 0,
            "ready_symbols": [],
            "review_required_symbols": [],
            "blocked_symbols": [],
            "ready_long_symbols": [],
            "ready_short_symbols": [],
            "ready_neutral_symbols": [],
        },
        "malformed_option_rows": [],
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
