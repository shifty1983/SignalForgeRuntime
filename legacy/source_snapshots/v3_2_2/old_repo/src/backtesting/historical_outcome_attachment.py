# src/backtesting/historical_outcome_attachment.py

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Mapping


REQUIRED_CANDIDATE_FIELDS = {
    "candidate_id",
    "symbol",
    "as_of_date",
    "direction",
    "candidate_status",
    "regime",
    "asset_behavior",
}

REQUIRED_PRICE_FIELDS = {
    "symbol",
    "date",
    "close",
}

BLOCKED_LIVE_OR_BROKER_FIELDS = {
    "broker",
    "broker_id",
    "broker_account",
    "broker_order_id",
    "order_id",
    "order_submission",
    "order_submitted",
    "order_status",
    "fill",
    "fill_price",
    "filled_quantity",
    "route",
    "routing",
    "live_execution",
    "live_order",
    "slippage",
    "slippage_model",
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


def attach_historical_forward_returns(
    candidate_rows: Iterable[Mapping[str, Any]],
    price_rows: Iterable[Mapping[str, Any]],
    *,
    forward_window: int = 1,
) -> dict[str, Any]:
    candidates = [dict(row) for row in candidate_rows]
    prices = [dict(row) for row in price_rows]

    validation_errors = validate_historical_outcome_attachment_inputs(
        candidates,
        prices,
        forward_window=forward_window,
    )

    if validation_errors:
        return {
            "attachment_status": "blocked",
            "is_blocked": True,
            "validation_errors": validation_errors,
            "historical_candidate_rows": [],
            "summary": {
                "candidate_count": len(candidates),
                "price_row_count": len(prices),
                "attached_candidate_count": 0,
                "missing_outcome_count": 0,
                "forward_window": forward_window,
            },
        }

    price_index = _build_price_index(prices)

    historical_candidate_rows: list[dict[str, Any]] = []
    missing_outcome_errors: list[str] = []

    for index, candidate in enumerate(candidates):
        symbol = str(candidate["symbol"])
        as_of_date = str(candidate["as_of_date"])

        symbol_prices = price_index.get(symbol, [])

        as_of_position = _find_price_position(symbol_prices, as_of_date)

        if as_of_position is None:
            missing_outcome_errors.append(
                f"candidate_rows[{index}] missing as_of close for {symbol} on {as_of_date}"
            )
            continue

        forward_position = as_of_position + forward_window

        if forward_position >= len(symbol_prices):
            missing_outcome_errors.append(
                f"candidate_rows[{index}] missing forward close for {symbol} "
                f"from {as_of_date} with forward_window={forward_window}"
            )
            continue

        as_of_close = float(symbol_prices[as_of_position]["close"])
        forward_close = float(symbol_prices[forward_position]["close"])
        forward_date = str(symbol_prices[forward_position]["date"])

        forward_return = (forward_close / as_of_close) - 1.0

        historical_candidate_row = {
            "candidate_id": candidate["candidate_id"],
            "symbol": symbol,
            "as_of_date": as_of_date,
            "direction": candidate["direction"],
            "candidate_status": candidate["candidate_status"],
            "regime": candidate["regime"],
            "asset_behavior": candidate["asset_behavior"],
            "forward_return": _round(forward_return),
            "outcome_start_close": _round(as_of_close),
            "outcome_end_close": _round(forward_close),
            "outcome_end_date": forward_date,
            "forward_window": forward_window,
        }

        historical_candidate_row.update(
            _option_behavior_context_from_candidate(candidate)
        )

        historical_candidate_rows.append(historical_candidate_row)

    if missing_outcome_errors:
        return {
            "attachment_status": "blocked",
            "is_blocked": True,
            "validation_errors": missing_outcome_errors,
            "historical_candidate_rows": [],
            "summary": {
                "candidate_count": len(candidates),
                "price_row_count": len(prices),
                "attached_candidate_count": 0,
                "missing_outcome_count": len(missing_outcome_errors),
                "forward_window": forward_window,
            },
        }

    historical_candidate_rows = sorted(
        historical_candidate_rows,
        key=lambda row: (
            str(row["as_of_date"]),
            str(row["symbol"]),
            str(row["candidate_id"]),
        ),
    )

    return {
        "attachment_status": "completed",
        "is_blocked": False,
        "validation_errors": [],
        "historical_candidate_rows": historical_candidate_rows,
        "summary": {
            "candidate_count": len(candidates),
            "price_row_count": len(prices),
            "attached_candidate_count": len(historical_candidate_rows),
            "missing_outcome_count": 0,
            "forward_window": forward_window,
        },
    }


def validate_historical_outcome_attachment_inputs(
    candidate_rows: Iterable[Mapping[str, Any]],
    price_rows: Iterable[Mapping[str, Any]],
    *,
    forward_window: int = 1,
) -> list[str]:
    candidates = list(candidate_rows)
    prices = list(price_rows)

    validation_errors: list[str] = []

    if forward_window <= 0:
        validation_errors.append("forward_window must be greater than 0")

    if not candidates:
        validation_errors.append("candidate_rows must not be empty")

    if not prices:
        validation_errors.append("price_rows must not be empty")

    seen_candidate_ids: set[str] = set()

    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, Mapping):
            validation_errors.append(f"candidate_rows[{index}] must be a mapping")
            continue

        missing_fields = sorted(REQUIRED_CANDIDATE_FIELDS - set(candidate.keys()))
        if missing_fields:
            validation_errors.append(
                f"candidate_rows[{index}] missing required fields: {missing_fields}"
            )

        blocked_fields = sorted(BLOCKED_LIVE_OR_BROKER_FIELDS & set(candidate.keys()))
        if blocked_fields:
            validation_errors.append(
                f"candidate_rows[{index}] contains blocked broker/live fields: {blocked_fields}"
            )

        candidate_id = candidate.get("candidate_id")
        if candidate_id in seen_candidate_ids:
            validation_errors.append(
                f"candidate_rows[{index}] duplicate candidate_id: {candidate_id}"
            )
        elif candidate_id is not None:
            seen_candidate_ids.add(str(candidate_id))

    for index, price in enumerate(prices):
        if not isinstance(price, Mapping):
            validation_errors.append(f"price_rows[{index}] must be a mapping")
            continue

        missing_fields = sorted(REQUIRED_PRICE_FIELDS - set(price.keys()))
        if missing_fields:
            validation_errors.append(
                f"price_rows[{index}] missing required fields: {missing_fields}"
            )

        blocked_fields = sorted(BLOCKED_LIVE_OR_BROKER_FIELDS & set(price.keys()))
        if blocked_fields:
            validation_errors.append(
                f"price_rows[{index}] contains blocked broker/live fields: {blocked_fields}"
            )

        close = price.get("close")
        if close is not None:
            try:
                numeric_close = float(close)
            except (TypeError, ValueError):
                validation_errors.append(f"price_rows[{index}] close must be numeric")
                continue

            if numeric_close <= 0:
                validation_errors.append(
                    f"price_rows[{index}] close must be greater than 0"
                )

            if numeric_close != numeric_close:
                validation_errors.append(f"price_rows[{index}] close must not be NaN")

    return validation_errors

def _option_behavior_context_from_candidate(
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        field_name: candidate[field_name]
        for field_name in OPTION_BEHAVIOR_CONTEXT_FIELDS
        if field_name in candidate
    }

def _build_price_index(
    price_rows: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in price_rows:
        grouped[str(row["symbol"])].append(
            {
                "symbol": str(row["symbol"]),
                "date": str(row["date"]),
                "close": float(row["close"]),
            }
        )

    return {
        symbol: sorted(rows, key=lambda row: str(row["date"]))
        for symbol, rows in sorted(grouped.items(), key=lambda item: item[0])
    }


def _find_price_position(
    symbol_prices: list[dict[str, Any]],
    as_of_date: str,
) -> int | None:
    for index, row in enumerate(symbol_prices):
        if str(row["date"]) == str(as_of_date):
            return index

    return None


def _round(value: float) -> float:
    return round(float(value), 10)
