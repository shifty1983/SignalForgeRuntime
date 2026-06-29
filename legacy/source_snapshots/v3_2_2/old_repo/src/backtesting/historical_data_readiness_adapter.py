# src/backtesting/historical_data_readiness_adapter.py

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Iterable, Mapping, Sequence


ADAPTER_TYPE = "historical_data_readiness_adapter"

EXPLICIT_EXCLUSIONS = [
    "broker_api_calls",
    "order_routing",
    "order_submission",
    "fills",
    "live_execution",
    "slippage_modeling",
]

FORBIDDEN_BROKER_LIVE_FIELDS = {
    "broker",
    "broker_api",
    "broker_api_call",
    "broker_api_calls",
    "broker_order_id",
    "broker_route",
    "broker_routing",
    "routing_destination",
    "route_id",
    "order_route",
    "order_routing",
    "order_submission",
    "order_submission_status",
    "submitted_order_id",
    "fill",
    "fills",
    "fill_id",
    "fill_price",
    "fill_qty",
    "filled_quantity",
    "live",
    "live_execution",
    "live_order",
    "live_trade",
    "slippage",
    "slippage_bps",
    "slippage_model",
    "slippage_modeling",
}

CANDIDATE_FIELD_ALIASES = {
    "candidate_id": ("candidate_id", "id", "decision_id", "signal_id", "row_id"),
    "symbol": ("symbol", "ticker", "asset", "asset_symbol"),
    "as_of_date": (
        "as_of_date",
        "date",
        "decision_date",
        "signal_date",
        "timestamp",
        "asofdate",
    ),
    "direction": ("direction", "side", "signal", "trade_direction"),
    "candidate_status": (
        "candidate_status",
        "status",
        "decision_status",
        "selection_status",
        "review_status",
    ),
    "regime": ("regime", "market_regime", "macro_regime"),
    "asset_behavior": ("asset_behavior", "behavior", "asset_state", "market_behavior"),
}

PRICE_FIELD_ALIASES = {
    "symbol": ("symbol", "ticker", "asset", "asset_symbol"),
    "date": ("date", "as_of_date", "timestamp", "price_date"),
    "close": (
        "close",
        "adj_close",
        "adjusted_close",
        "settle",
        "settlement",
        "price",
        "last",
    ),
}

DIRECTION_ALIASES = {
    "long": "long",
    "buy": "long",
    "bullish": "long",
    "1": "long",
    "short": "short",
    "sell": "short",
    "bearish": "short",
    "-1": "short",
    "neutral": "neutral",
    "flat": "neutral",
    "hold": "neutral",
    "0": "neutral",
}

STATUS_ALIASES = {
    "accepted": "accepted",
    "accept": "accepted",
    "approved": "accepted",
    "selected": "accepted",
    "promoted": "accepted",
    "ready": "accepted",
    "rejected": "rejected",
    "reject": "rejected",
    "declined": "rejected",
    "failed": "rejected",
}

OPTION_BEHAVIOR_CONTEXT_FIELDS = (
    "option_behavior_status",
    "option_behavior_state",
    "option_behavior_score",
    "option_strategy_generation_mode",
    "option_strategy_generation_constraints",
    "option_behavior_warnings",
    "option_behavior_blocked_reasons",
    "option_iv_behavior",
    "option_vol_premium_behavior",
    "option_liquidity_behavior",
    "option_skew_behavior",
    "option_term_structure_behavior",
    "option_greek_behavior",
    "option_behavior_blocked",
    "option_behavior_needs_review",
)

OPTION_BEHAVIOR_LIST_FIELDS = {
    "option_strategy_generation_constraints",
    "option_behavior_warnings",
    "option_behavior_blocked_reasons",
}

OPTION_BEHAVIOR_BOOL_FIELDS = {
    "option_behavior_blocked",
    "option_behavior_needs_review",
}

OPTION_BEHAVIOR_NUMERIC_FIELDS = {
    "option_behavior_score",
}

OPTION_BEHAVIOR_CONTEXT_CONTAINERS = (
    "diagnostics",
    "metadata",
    "option_behavior_context",
    "option_behavior",
)


def adapt_historical_data_for_validation(
    candidate_records: Iterable[Mapping[str, Any]],
    price_records: Iterable[Mapping[str, Any]],
    *,
    forward_windows: Sequence[int] = (1,),
    candidate_field_map: Mapping[str, str] | None = None,
    price_field_map: Mapping[str, str] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    metadata_dict = dict(metadata or {})
    candidate_field_map_dict = dict(candidate_field_map or {})
    price_field_map_dict = dict(price_field_map or {})

    validation_errors: list[str] = []
    warnings: list[str] = []

    normalized_candidates = _normalize_candidate_records(
        candidate_records,
        candidate_field_map=candidate_field_map_dict,
        validation_errors=validation_errors,
        warnings=warnings,
    )

    normalized_prices = _normalize_price_records(
        price_records,
        price_field_map=price_field_map_dict,
        validation_errors=validation_errors,
    )

    _validate_forward_windows(forward_windows, validation_errors)

    if not normalized_candidates:
        validation_errors.append("candidate_records produced no valid candidate rows")

    if not normalized_prices:
        validation_errors.append("price_records produced no valid price rows")

    _validate_candidate_uniqueness(normalized_candidates, validation_errors)
    _validate_price_uniqueness(normalized_prices, validation_errors)
    _validate_candidate_price_alignment(
        normalized_candidates,
        normalized_prices,
        forward_windows=forward_windows,
        validation_errors=validation_errors,
    )
    _add_candidate_mix_warnings(normalized_candidates, warnings)

    candidate_rows = sorted(
        normalized_candidates,
        key=lambda row: (
            row["as_of_date"],
            row["symbol"],
            row["candidate_id"],
        ),
    )
    price_rows = sorted(
        normalized_prices,
        key=lambda row: (
            row["symbol"],
            row["date"],
        ),
    )

    blocked_reasons = list(validation_errors)

    if validation_errors:
        adapter_status = "blocked"
    elif warnings:
        adapter_status = "needs_review"
    else:
        adapter_status = "ready"

    return {
        "adapter_type": ADAPTER_TYPE,
        "adapter_status": adapter_status,
        "is_ready": adapter_status == "ready",
        "is_blocked": adapter_status == "blocked",
        "validation_errors": validation_errors,
        "warnings": warnings,
        "blocked_reasons": blocked_reasons,
        "candidate_rows": candidate_rows,
        "price_rows": price_rows,
        "readiness_summary": {
            "candidate_count": len(candidate_rows),
            "price_row_count": len(price_rows),
            "accepted_candidate_count": sum(
                1 for row in candidate_rows if row["candidate_status"] == "accepted"
            ),
            "rejected_candidate_count": sum(
                1 for row in candidate_rows if row["candidate_status"] == "rejected"
            ),
            "symbol_count": len({row["symbol"] for row in price_rows}),
            "candidate_symbol_count": len({row["symbol"] for row in candidate_rows}),
            "max_forward_window": max(forward_windows) if forward_windows else None,
            "validation_error_count": len(validation_errors),
            "warning_count": len(warnings),
            "blocked_reason_count": len(blocked_reasons),
        },
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
        "metadata": metadata_dict,
    }


def _normalize_candidate_records(
    candidate_records: Iterable[Mapping[str, Any]],
    *,
    candidate_field_map: Mapping[str, str],
    validation_errors: list[str],
    warnings: list[str],
) -> list[dict[str, Any]]:
    normalized_rows: list[dict[str, Any]] = []

    for index, record in enumerate(candidate_records):
        if not isinstance(record, Mapping):
            validation_errors.append(f"candidate_records[{index}] must be a mapping")
            continue

        forbidden_fields = _find_forbidden_fields(record)
        if forbidden_fields:
            validation_errors.append(
                f"candidate_records[{index}] contains broker/live/slippage fields: "
                f"{forbidden_fields}"
            )
            continue

        symbol = _normalize_symbol(
            _extract_field(
                record,
                "symbol",
                candidate_field_map,
                CANDIDATE_FIELD_ALIASES,
            )
        )
        as_of_date = _normalize_date(
            _extract_field(
                record,
                "as_of_date",
                candidate_field_map,
                CANDIDATE_FIELD_ALIASES,
            )
        )
        direction = _normalize_direction(
            _extract_field(
                record,
                "direction",
                candidate_field_map,
                CANDIDATE_FIELD_ALIASES,
            )
        )
        candidate_status = _normalize_candidate_status(
            _extract_field(
                record,
                "candidate_status",
                candidate_field_map,
                CANDIDATE_FIELD_ALIASES,
            )
        )
        regime = _normalize_label(
            _extract_field(
                record,
                "regime",
                candidate_field_map,
                CANDIDATE_FIELD_ALIASES,
            )
        )
        asset_behavior = _normalize_label(
            _extract_field(
                record,
                "asset_behavior",
                candidate_field_map,
                CANDIDATE_FIELD_ALIASES,
            )
        )
        candidate_id_value = _extract_field(
            record,
            "candidate_id",
            candidate_field_map,
            CANDIDATE_FIELD_ALIASES,
        )

        row_errors: list[str] = []

        if not symbol:
            row_errors.append("missing symbol")

        if not as_of_date:
            row_errors.append("missing or invalid as_of_date")

        if not direction:
            row_errors.append("missing or invalid direction")

        if not candidate_status:
            row_errors.append("missing or invalid candidate_status")

        if not regime:
            row_errors.append("missing regime")

        if not asset_behavior:
            row_errors.append("missing asset_behavior")

        if row_errors:
            validation_errors.append(
                f"candidate_records[{index}] invalid candidate row: {row_errors}"
            )
            continue

        generated_candidate_id = False
        if candidate_id_value is None or str(candidate_id_value).strip() == "":
            candidate_id = _build_candidate_id(
                symbol=symbol,
                as_of_date=as_of_date,
                direction=direction,
                candidate_status=candidate_status,
                index=index,
            )
            generated_candidate_id = True
            warnings.append(
                f"candidate_records[{index}] missing candidate_id; generated deterministic id"
            )
        else:
            candidate_id = str(candidate_id_value).strip()

        normalized_row = {
            "candidate_id": candidate_id,
            "symbol": symbol,
            "as_of_date": as_of_date,
            "direction": direction,
            "candidate_status": candidate_status,
            "regime": regime,
            "asset_behavior": asset_behavior,
            "metadata": {
                "source_index": index,
                "generated_candidate_id": generated_candidate_id,
            },
        }

        normalized_row.update(_extract_option_behavior_context(record))

        normalized_rows.append(normalized_row)

    return normalized_rows

def _extract_option_behavior_context(
    record: Mapping[str, Any],
) -> dict[str, Any]:
    context: dict[str, Any] = {}

    _merge_option_behavior_fields(context, record)

    for container_name in OPTION_BEHAVIOR_CONTEXT_CONTAINERS:
        container = record.get(container_name)

        if isinstance(container, Mapping):
            _merge_option_behavior_fields(context, container)

            nested_context = container.get("option_behavior_context")
            if isinstance(nested_context, Mapping):
                _merge_option_behavior_fields(context, nested_context)

    return context


def _merge_option_behavior_fields(
    target: dict[str, Any],
    source: Mapping[str, Any],
) -> None:
    for field_name in OPTION_BEHAVIOR_CONTEXT_FIELDS:
        if field_name not in source:
            continue

        normalized_value = _normalize_option_behavior_value(
            field_name,
            source[field_name],
        )

        if normalized_value is not None:
            target[field_name] = normalized_value


def _normalize_option_behavior_value(
    field_name: str,
    value: Any,
) -> Any:
    if value is None:
        return None

    if field_name in OPTION_BEHAVIOR_LIST_FIELDS:
        return _normalize_string_list(value)

    if field_name in OPTION_BEHAVIOR_BOOL_FIELDS:
        if isinstance(value, bool):
            return value

        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes"}:
                return True
            if normalized in {"false", "0", "no"}:
                return False

        return None

    if field_name in OPTION_BEHAVIOR_NUMERIC_FIELDS:
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            return None

        if numeric_value != numeric_value:
            return None

        return round(numeric_value, 10)

    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None

    return str(value)


def _normalize_string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []

    if not isinstance(value, Sequence):
        return []

    strings: list[str] = []

    for item in value:
        if isinstance(item, str) and item.strip():
            strings.append(item.strip())

    return strings

def _normalize_price_records(
    price_records: Iterable[Mapping[str, Any]],
    *,
    price_field_map: Mapping[str, str],
    validation_errors: list[str],
) -> list[dict[str, Any]]:
    normalized_rows: list[dict[str, Any]] = []

    for index, record in enumerate(price_records):
        if not isinstance(record, Mapping):
            validation_errors.append(f"price_records[{index}] must be a mapping")
            continue

        forbidden_fields = _find_forbidden_fields(record)
        if forbidden_fields:
            validation_errors.append(
                f"price_records[{index}] contains broker/live/slippage fields: "
                f"{forbidden_fields}"
            )
            continue

        symbol = _normalize_symbol(
            _extract_field(record, "symbol", price_field_map, PRICE_FIELD_ALIASES)
        )
        price_date = _normalize_date(
            _extract_field(record, "date", price_field_map, PRICE_FIELD_ALIASES)
        )
        close = _normalize_close(
            _extract_field(record, "close", price_field_map, PRICE_FIELD_ALIASES)
        )

        row_errors: list[str] = []

        if not symbol:
            row_errors.append("missing symbol")

        if not price_date:
            row_errors.append("missing or invalid date")

        if close is None:
            row_errors.append("missing or invalid close")

        if row_errors:
            validation_errors.append(
                f"price_records[{index}] invalid price row: {row_errors}"
            )
            continue

        normalized_rows.append(
            {
                "symbol": symbol,
                "date": price_date,
                "close": close,
                "metadata": {
                    "source_index": index,
                },
            }
        )

    return normalized_rows


def _extract_field(
    record: Mapping[str, Any],
    canonical_field: str,
    field_map: Mapping[str, str],
    alias_map: Mapping[str, Sequence[str]],
) -> Any:
    if canonical_field in field_map:
        return _lookup_case_insensitive(record, field_map[canonical_field])

    for alias in alias_map[canonical_field]:
        value = _lookup_case_insensitive(record, alias)
        if value is not None:
            return value

    return None


def _lookup_case_insensitive(record: Mapping[str, Any], field_name: str) -> Any:
    if field_name in record:
        return record[field_name]

    lookup = {str(key).lower(): key for key in record.keys()}
    matched_key = lookup.get(str(field_name).lower())

    if matched_key is None:
        return None

    return record[matched_key]


def _normalize_symbol(value: Any) -> str | None:
    if value is None:
        return None

    normalized = str(value).strip().upper()

    return normalized or None


def _normalize_date(value: Any) -> str | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.date().isoformat()

    if isinstance(value, date):
        return value.isoformat()

    text = str(value).strip()
    if not text:
        return None

    text = text.replace("Z", "")
    text = text.split("T")[0].split(" ")[0]

    for date_format in ("%Y-%m-%d", "%m/%d/%Y", "%Y%m%d"):
        try:
            return datetime.strptime(text, date_format).date().isoformat()
        except ValueError:
            continue

    return None


def _normalize_direction(value: Any) -> str | None:
    if value is None:
        return None

    normalized = str(value).strip().lower()

    return DIRECTION_ALIASES.get(normalized)


def _normalize_candidate_status(value: Any) -> str | None:
    if value is None:
        return None

    normalized = str(value).strip().lower()

    return STATUS_ALIASES.get(normalized)


def _normalize_label(value: Any) -> str | None:
    if value is None:
        return None

    normalized = str(value).strip().lower().replace(" ", "_").replace("-", "_")

    return normalized or None


def _normalize_close(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None

    try:
        close = float(value)
    except (TypeError, ValueError):
        return None

    if close != close:
        return None

    if close in {float("inf"), float("-inf")}:
        return None

    return close


def _find_forbidden_fields(record: Mapping[str, Any]) -> list[str]:
    forbidden_fields: list[str] = []

    for key in record.keys():
        normalized_key = str(key).strip().lower()
        if normalized_key in FORBIDDEN_BROKER_LIVE_FIELDS:
            forbidden_fields.append(str(key))

    return sorted(forbidden_fields)


def _validate_forward_windows(
    forward_windows: Sequence[int],
    validation_errors: list[str],
) -> None:
    if not forward_windows:
        validation_errors.append("forward_windows must contain at least one window")
        return

    for window in forward_windows:
        if not isinstance(window, int) or isinstance(window, bool) or window <= 0:
            validation_errors.append(
                f"forward_windows contains invalid window: {window}"
            )


def _validate_candidate_uniqueness(
    candidate_rows: list[dict[str, Any]],
    validation_errors: list[str],
) -> None:
    seen_candidate_ids: set[str] = set()

    for row in candidate_rows:
        candidate_id = row["candidate_id"]
        if candidate_id in seen_candidate_ids:
            validation_errors.append(f"duplicate candidate_id detected: {candidate_id}")
        seen_candidate_ids.add(candidate_id)


def _validate_price_uniqueness(
    price_rows: list[dict[str, Any]],
    validation_errors: list[str],
) -> None:
    seen_price_keys: set[tuple[str, str]] = set()

    for row in price_rows:
        price_key = (row["symbol"], row["date"])
        if price_key in seen_price_keys:
            validation_errors.append(
                f"duplicate price row detected for symbol/date: {price_key}"
            )
        seen_price_keys.add(price_key)


def _validate_candidate_price_alignment(
    candidate_rows: list[dict[str, Any]],
    price_rows: list[dict[str, Any]],
    *,
    forward_windows: Sequence[int],
    validation_errors: list[str],
) -> None:
    if not candidate_rows or not price_rows or not forward_windows:
        return

    if any(not isinstance(window, int) or window <= 0 for window in forward_windows):
        return

    max_forward_window = max(forward_windows)

    dates_by_symbol: dict[str, list[str]] = {}
    for price_row in price_rows:
        dates_by_symbol.setdefault(price_row["symbol"], []).append(price_row["date"])

    for symbol in dates_by_symbol:
        dates_by_symbol[symbol] = sorted(set(dates_by_symbol[symbol]))

    for candidate_row in candidate_rows:
        symbol = candidate_row["symbol"]
        as_of_date = candidate_row["as_of_date"]
        candidate_id = candidate_row["candidate_id"]

        if symbol not in dates_by_symbol:
            validation_errors.append(
                f"candidate {candidate_id} symbol {symbol} has no price rows"
            )
            continue

        symbol_dates = dates_by_symbol[symbol]

        if as_of_date not in symbol_dates:
            validation_errors.append(
                f"candidate {candidate_id} as_of_date {as_of_date} "
                f"does not exist in price rows for {symbol}"
            )
            continue

        date_index = symbol_dates.index(as_of_date)
        available_forward_rows = len(symbol_dates) - date_index - 1

        if available_forward_rows < max_forward_window:
            validation_errors.append(
                f"candidate {candidate_id} has insufficient forward price rows "
                f"for max_forward_window={max_forward_window}; "
                f"available_forward_rows={available_forward_rows}"
            )


def _add_candidate_mix_warnings(
    candidate_rows: list[dict[str, Any]],
    warnings: list[str],
) -> None:
    if not candidate_rows:
        return

    accepted_count = sum(
        1 for row in candidate_rows if row["candidate_status"] == "accepted"
    )
    rejected_count = sum(
        1 for row in candidate_rows if row["candidate_status"] == "rejected"
    )

    if accepted_count == 0:
        warnings.append("candidate_rows contain no accepted candidates")

    if rejected_count == 0:
        warnings.append("candidate_rows contain no rejected candidates")


def _build_candidate_id(
    *,
    symbol: str,
    as_of_date: str,
    direction: str,
    candidate_status: str,
    index: int,
) -> str:
    return (
        f"candidate:{symbol}:{as_of_date}:"
        f"{direction}:{candidate_status}:{index}"
    )
