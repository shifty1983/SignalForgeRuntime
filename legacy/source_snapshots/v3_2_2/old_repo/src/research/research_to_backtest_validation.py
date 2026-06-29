from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date, datetime
from math import isfinite
from typing import Any, Iterable, Mapping


PASSING_HEALTH_STATUSES = {
    "pass",
    "passed",
    "healthy",
    "accepted",
    "ok",
    "success",
    "succeeded",
}

FAILING_HEALTH_STATUSES = {
    "fail",
    "failed",
    "unhealthy",
    "rejected",
    "error",
    "blocked",
}


@dataclass(frozen=True)
class ResearchToBacktestValidationResult:
    passed: bool
    status: str
    backtest_input_rows: list[dict[str, Any]] = field(default_factory=list)
    backtest_input_symbols: list[str] = field(default_factory=list)
    backtest_input_dates: list[str] = field(default_factory=list)
    target_weight_summary: dict[str, Any] = field(default_factory=dict)
    performance_summary_status: str | None = None
    failure_reasons: list[str] = field(default_factory=list)
    warning_reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


def validate_research_to_backtest_handoff(
    logged_operation_result: Any,
    price_rows: Iterable[Any],
    *,
    performance_summary: Mapping[str, Any] | None = None,
    max_abs_target_weight: float = 1.0,
    max_gross_target_weight: float = 1.0,
) -> ResearchToBacktestValidationResult:
    """
    Validate that an accepted logged research operation can become deterministic
    backtesting input without mutating the original research output.

    This function intentionally sits between Research Evaluation Operation and
    Backtesting. It does not run strategy logic, change signals, rewrite factor
    values, or fabricate backtest success.
    """
    failure_reasons: list[str] = []
    warning_reasons: list[str] = []

    health_status = _extract_health_status(logged_operation_result)
    if health_status not in PASSING_HEALTH_STATUSES:
        failure_reasons.append(
            f"logged operation is not accepted for backtesting: {health_status}"
        )

    raw_payload = _extract_research_payload(logged_operation_result)
    if not raw_payload:
        failure_reasons.append("missing downstream-ready research payload")
        return _failed_result(failure_reasons, warning_reasons, health_status)

    research_rows = _normalize_research_rows(raw_payload, failure_reasons)
    price_lookup = _build_price_lookup(price_rows, failure_reasons)

    if failure_reasons:
        return _failed_result(failure_reasons, warning_reasons, health_status)

    target_weight_summary = _validate_target_weights(
        research_rows=research_rows,
        max_abs_target_weight=max_abs_target_weight,
        max_gross_target_weight=max_gross_target_weight,
        failure_reasons=failure_reasons,
    )

    backtest_input_rows = _build_backtest_input_rows(
        research_rows=research_rows,
        price_lookup=price_lookup,
        failure_reasons=failure_reasons,
    )

    performance_summary_status = None
    if performance_summary is not None:
        performance_summary_status = _validate_performance_summary(
            performance_summary,
            failure_reasons,
        )

    if failure_reasons:
        return ResearchToBacktestValidationResult(
            passed=False,
            status="failed",
            backtest_input_rows=[],
            backtest_input_symbols=[],
            backtest_input_dates=[],
            target_weight_summary=target_weight_summary,
            performance_summary_status=performance_summary_status,
            failure_reasons=failure_reasons,
            warning_reasons=warning_reasons,
            metadata={"operation_health_status": health_status},
        )

    symbols = sorted({row["symbol"] for row in backtest_input_rows})
    dates = sorted({row["rebalance_date"] for row in backtest_input_rows})

    return ResearchToBacktestValidationResult(
        passed=True,
        status="passed",
        backtest_input_rows=backtest_input_rows,
        backtest_input_symbols=symbols,
        backtest_input_dates=dates,
        target_weight_summary=target_weight_summary,
        performance_summary_status=performance_summary_status,
        failure_reasons=[],
        warning_reasons=warning_reasons,
        metadata={"operation_health_status": health_status},
    )


def _failed_result(
    failure_reasons: list[str],
    warning_reasons: list[str],
    health_status: str,
) -> ResearchToBacktestValidationResult:
    return ResearchToBacktestValidationResult(
        passed=False,
        status="failed",
        failure_reasons=failure_reasons,
        warning_reasons=warning_reasons,
        metadata={"operation_health_status": health_status},
    )


def _extract_health_status(value: Any) -> str:
    if _get_any(value, ["accepted", "is_accepted"]) is False:
        return "rejected"

    if _get_any(value, ["success", "succeeded"]) is False:
        return "failed"

    raw_status = _get_any(
        value,
        [
            "operation_health_status",
            "health_status",
            "health_gate_status",
            "status",
            "operation_status",
        ],
    )

    if raw_status is None:
        if _get_any(value, ["accepted", "is_accepted"]) is True:
            return "accepted"
        if _get_any(value, ["success", "succeeded"]) is True:
            return "success"
        return "missing"

    if not isinstance(raw_status, str):
        nested_status = _get_any(raw_status, ["status", "health_status"])
        if nested_status is not None:
            raw_status = nested_status

    return str(raw_status).strip().lower()


def _extract_research_payload(value: Any) -> list[dict[str, Any]]:
    payload = _get_any(
        value,
        [
            "downstream_ready_payload",
            "downstream_payload",
            "accepted_research_payload",
            "research_payload",
            "backtest_payload",
            "evaluated_output",
            "evaluation_output",
            "output",
            "rows",
        ],
    )

    if payload is None:
        return []

    if isinstance(payload, Mapping):
        for key in (
            "rows",
            "records",
            "payload",
            "research_rows",
            "signals",
            "outputs",
        ):
            if key in payload:
                payload = payload[key]
                break

    return _to_records(payload)


def _normalize_research_rows(
    raw_rows: Iterable[Any],
    failure_reasons: list[str],
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []

    for index, raw_row in enumerate(_to_records(raw_rows)):
        row = _as_dict(raw_row)

        symbol = row.get("symbol")
        as_of_date = row.get("as_of_date", row.get("date"))
        signal = row.get("signal")
        direction = row.get("direction")
        target_weight = row.get("target_weight")

        missing_fields = [
            field_name
            for field_name, value in {
                "symbol": symbol,
                "as_of_date": as_of_date,
                "signal": signal,
                "direction": direction,
                "target_weight": target_weight,
            }.items()
            if value is None
        ]

        if missing_fields:
            failure_reasons.append(
                f"research payload row {index} missing fields: {missing_fields}"
            )
            continue

        try:
            normalized_weight = float(target_weight)
        except (TypeError, ValueError):
            failure_reasons.append(
                f"research payload row {index} has non-numeric target_weight"
            )
            continue

        normalized.append(
            {
                "symbol": str(symbol),
                "as_of_date": _normalize_date(as_of_date),
                "signal": signal,
                "direction": str(direction),
                "target_weight": normalized_weight,
                "diagnostics": row.get("diagnostics", {}),
                "metadata": row.get("metadata", {}),
            }
        )

    return sorted(normalized, key=lambda row: (row["as_of_date"], row["symbol"]))


def _build_price_lookup(
    price_rows: Iterable[Any],
    failure_reasons: list[str],
) -> dict[tuple[str, str], dict[str, Any]]:
    lookup: dict[tuple[str, str], dict[str, Any]] = {}

    for index, raw_row in enumerate(_to_records(price_rows)):
        row = _as_dict(raw_row)

        symbol = row.get("symbol")
        raw_date = row.get("as_of_date", row.get("date", row.get("rebalance_date")))
        raw_price = row.get("close", row.get("price"))

        missing_fields = [
            field_name
            for field_name, value in {
                "symbol": symbol,
                "date": raw_date,
                "close": raw_price,
            }.items()
            if value is None
        ]

        if missing_fields:
            failure_reasons.append(
                f"price row {index} missing fields: {missing_fields}"
            )
            continue

        try:
            close = float(raw_price)
        except (TypeError, ValueError):
            failure_reasons.append(f"price row {index} has non-numeric close")
            continue

        if not isfinite(close) or close <= 0:
            failure_reasons.append(f"price row {index} has invalid close: {close}")
            continue

        normalized_date = _normalize_date(raw_date)
        lookup[(str(symbol), normalized_date)] = {
            "symbol": str(symbol),
            "date": normalized_date,
            "close": close,
        }

    return lookup


def _validate_target_weights(
    research_rows: list[dict[str, Any]],
    max_abs_target_weight: float,
    max_gross_target_weight: float,
    failure_reasons: list[str],
) -> dict[str, Any]:
    gross_by_date: dict[str, float] = {}
    net_by_date: dict[str, float] = {}
    seen_keys: set[tuple[str, str]] = set()

    for row in research_rows:
        key = (row["symbol"], row["as_of_date"])
        if key in seen_keys:
            failure_reasons.append(
                f"duplicate research target for symbol/date: {key}"
            )
        seen_keys.add(key)

        weight = row["target_weight"]

        if not isfinite(weight):
            failure_reasons.append(
                f"target weight is not finite for {row['symbol']} {row['as_of_date']}"
            )
            continue

        if abs(weight) > max_abs_target_weight:
            failure_reasons.append(
                "target weight exceeds max absolute limit for "
                f"{row['symbol']} {row['as_of_date']}: {weight}"
            )

        gross_by_date[row["as_of_date"]] = (
            gross_by_date.get(row["as_of_date"], 0.0) + abs(weight)
        )
        net_by_date[row["as_of_date"]] = (
            net_by_date.get(row["as_of_date"], 0.0) + weight
        )

    for as_of_date, gross_weight in gross_by_date.items():
        if gross_weight > max_gross_target_weight + 1e-12:
            failure_reasons.append(
                f"gross target weight exceeds limit for {as_of_date}: "
                f"{gross_weight}"
            )

    return {
        "row_count": len(research_rows),
        "gross_by_date": {
            as_of_date: round(value, 10)
            for as_of_date, value in sorted(gross_by_date.items())
        },
        "net_by_date": {
            as_of_date: round(value, 10)
            for as_of_date, value in sorted(net_by_date.items())
        },
        "max_abs_target_weight": max_abs_target_weight,
        "max_gross_target_weight": max_gross_target_weight,
    }


def _build_backtest_input_rows(
    research_rows: list[dict[str, Any]],
    price_lookup: dict[tuple[str, str], dict[str, Any]],
    failure_reasons: list[str],
) -> list[dict[str, Any]]:
    backtest_rows: list[dict[str, Any]] = []

    for row in research_rows:
        key = (row["symbol"], row["as_of_date"])
        price_row = price_lookup.get(key)

        if price_row is None:
            failure_reasons.append(
                f"missing price row for {row['symbol']} {row['as_of_date']}"
            )
            continue

        backtest_rows.append(
            {
                "symbol": row["symbol"],
                "rebalance_date": row["as_of_date"],
                "signal": row["signal"],
                "direction": row["direction"],
                "target_weight": row["target_weight"],
                "close": price_row["close"],
                "diagnostics": row["diagnostics"],
                "metadata": row["metadata"],
            }
        )

    return sorted(backtest_rows, key=lambda row: (row["rebalance_date"], row["symbol"]))


def _validate_performance_summary(
    performance_summary: Mapping[str, Any],
    failure_reasons: list[str],
) -> str:
    starting_failure_count = len(failure_reasons)

    required_fields = {
        "total_return",
        "equity_curve",
        "rebalance_count",
        "turnover",
        "diagnostics",
    }

    missing_fields = sorted(required_fields - set(performance_summary.keys()))
    if missing_fields:
        failure_reasons.append(
            f"performance summary missing fields: {missing_fields}"
        )

    for numeric_field in ("total_return", "rebalance_count", "turnover"):
        if numeric_field not in performance_summary:
            continue

        value = performance_summary[numeric_field]
        if not isinstance(value, (int, float)) or not isfinite(float(value)):
            failure_reasons.append(
                f"performance summary field is not finite: {numeric_field}"
            )

    equity_curve = performance_summary.get("equity_curve")
    if not isinstance(equity_curve, list) or not equity_curve:
        failure_reasons.append(
            "performance summary equity_curve is empty or invalid"
        )

    return "failed" if len(failure_reasons) > starting_failure_count else "passed"


def _get_any(value: Any, names: list[str]) -> Any:
    for name in names:
        if isinstance(value, Mapping) and name in value:
            return value[name]

        if hasattr(value, name):
            return getattr(value, name)

    return None


def _to_records(value: Any) -> list[Any]:
    if value is None:
        return []

    if hasattr(value, "to_dict"):
        try:
            records = value.to_dict(orient="records")
            if isinstance(records, list):
                return records
        except TypeError:
            pass

    if isinstance(value, Mapping):
        return [value]

    if isinstance(value, list):
        return value

    if isinstance(value, tuple):
        return list(value)

    return list(value)


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)

    if is_dataclass(value):
        return asdict(value)

    if hasattr(value, "__dict__"):
        return dict(value.__dict__)

    raise TypeError(f"cannot convert value to dict: {type(value)!r}")


def _normalize_date(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()

    if isinstance(value, date):
        return value.isoformat()

    return str(value)
