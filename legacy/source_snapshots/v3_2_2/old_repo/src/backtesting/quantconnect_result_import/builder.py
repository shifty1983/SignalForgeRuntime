from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Mapping


SCHEMA_VERSION = "quantconnect_result_import.v1"
SOURCE_PLATFORM = "quantconnect"
IMPORT_TYPE = "manual_backtest_result_import"

EXPLICIT_EXCLUSIONS = [
    "quantconnect_api_calls",
    "broker_api_calls",
    "order_routing",
    "order_submission",
    "live_execution",
    "local_fill_simulation",
    "local_slippage_modeling",
    "external_data_warehouse_access",
]

LOG_KEYS = ("logs", "log_lines", "backtest_logs", "algorithm_logs")
WARNING_KEYS = ("warnings", "warning_messages")
ERROR_KEYS = ("errors", "error_messages", "runtime_errors")
BLOCKED_REASON_KEYS = ("blocked_reasons", "blocked_reason_messages")

STATS_KEYS = (
    "statistics",
    "stats",
    "performance_statistics",
    "backtest_statistics",
)

EXPORT_LOADED_MARKER = "SIGNALFORGE_EXPORT_LOADED"
DECISION_MARKER = "SIGNALFORGE_DECISION"


def build_quantconnect_result_import(source: Any) -> dict[str, Any]:
    """Build a deterministic SignalForge import artifact from QuantConnect results.

    This builder does not call QuantConnect, brokers, market-data services,
    order-routing systems, live-trading APIs, fill engines, or slippage engines.
    It only normalizes manually supplied QuantConnect backtest logs/statistics.
    """

    if not isinstance(source, Mapping):
        return _blocked_invalid_shape("source must be a mapping/dict")

    source_copy = deepcopy(dict(source))

    logs = _extract_logs(source_copy)
    source_status = _extract_status(source_copy)
    backtest_id = _extract_backtest_id(source_copy, logs)

    export_loaded_events = _extract_marker_events(logs, EXPORT_LOADED_MARKER)
    decision_events = _extract_decision_events(logs)

    warnings = _collect_text_values(source_copy, WARNING_KEYS)
    warnings.extend(_extract_warning_lines(logs))

    errors = _collect_text_values(source_copy, ERROR_KEYS)
    errors.extend(_extract_error_lines(logs))

    blocked_reasons = _collect_text_values(source_copy, BLOCKED_REASON_KEYS)

    performance_summary = _extract_performance_summary(source_copy)

    if not export_loaded_events:
        warnings.append("missing SIGNALFORGE_EXPORT_LOADED log marker")

    if not decision_events:
        warnings.append("missing SIGNALFORGE_DECISION log markers")

    if not _has_performance_statistics(performance_summary):
        warnings.append("performance statistics were not provided")

    warnings = _sorted_unique_text(warnings)
    errors = _sorted_unique_text(errors)
    blocked_reasons = _sorted_unique_text(blocked_reasons)

    status = _classify_import_status(
        source_status=source_status,
        export_loaded_event_count=len(export_loaded_events),
        decision_event_count=len(decision_events),
        has_performance_statistics=_has_performance_statistics(performance_summary),
        error_count=len(errors),
        blocked_reason_count=len(blocked_reasons),
    )

    strategy_ids = _unique_text(
        event.get("strategy_id")
        for event in decision_events
        if isinstance(event.get("strategy_id"), str)
    )
    symbols = _unique_text(
        event.get("symbol")
        for event in decision_events
        if isinstance(event.get("symbol"), str)
    )

    reported_strategy_count = _reported_strategy_count(export_loaded_events)

    return {
        "schema_version": SCHEMA_VERSION,
        "source_platform": SOURCE_PLATFORM,
        "import_type": IMPORT_TYPE,
        "status": status,
        "summary": {
            "backtest_id": backtest_id,
            "source_status": source_status,
            "log_line_count": len(logs),
            "export_loaded_event_count": len(export_loaded_events),
            "decision_event_count": len(decision_events),
            "reported_strategy_count": reported_strategy_count,
            "unique_strategy_count": len(strategy_ids),
            "unique_symbol_count": len(symbols),
            "performance_metric_count": _performance_metric_count(
                performance_summary
            ),
            "warning_count": len(warnings),
            "error_count": len(errors),
            "blocked_reason_count": len(blocked_reasons),
        },
        "performance_summary": performance_summary,
        "signalforge_events": {
            "export_loaded": export_loaded_events,
            "decisions": decision_events,
        },
        "warnings": warnings,
        "errors": errors,
        "blocked_reasons": blocked_reasons,
        "source_log_summary": {
            "first_log_line": logs[0] if logs else None,
            "last_log_line": logs[-1] if logs else None,
        },
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _blocked_invalid_shape(reason: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "source_platform": SOURCE_PLATFORM,
        "import_type": IMPORT_TYPE,
        "status": "blocked",
        "summary": {
            "backtest_id": None,
            "source_status": "invalid_shape",
            "log_line_count": 0,
            "export_loaded_event_count": 0,
            "decision_event_count": 0,
            "reported_strategy_count": 0,
            "unique_strategy_count": 0,
            "unique_symbol_count": 0,
            "performance_metric_count": 0,
            "warning_count": 0,
            "error_count": 0,
            "blocked_reason_count": 1,
        },
        "performance_summary": _empty_performance_summary(),
        "signalforge_events": {
            "export_loaded": [],
            "decisions": [],
        },
        "warnings": [],
        "errors": [],
        "blocked_reasons": [reason],
        "source_log_summary": {
            "first_log_line": None,
            "last_log_line": None,
        },
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _extract_status(source: Mapping[str, Any]) -> str:
    for key in ("status", "backtest_status", "result_status"):
        value = source.get(key)
        if isinstance(value, str) and value.strip():
            return _normalize_status(value)

    return "needs_review"


def _normalize_status(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")

    if normalized in {"ready", "needs_review", "blocked"}:
        return normalized
    if normalized in {"completed", "complete", "success", "successful", "passed", "ok"}:
        return "ready"
    if normalized in {"failed", "fail", "error", "runtime_error", "invalid"}:
        return "blocked"
    if normalized in {"review", "warning", "warn"}:
        return "needs_review"

    return normalized


def _extract_logs(source: Mapping[str, Any]) -> list[str]:
    logs: list[str] = []

    for key in LOG_KEYS:
        logs.extend(_as_text_lines(source.get(key)))

    result = source.get("result")
    if isinstance(result, Mapping):
        for key in LOG_KEYS:
            logs.extend(_as_text_lines(result.get(key)))

    return [line for line in logs if line.strip()]


def _as_text_lines(value: Any) -> list[str]:
    if value is None:
        return []

    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]

    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]

    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]

    return [str(value).strip()] if str(value).strip() else []


def _collect_text_values(source: Mapping[str, Any], keys: tuple[str, ...]) -> list[str]:
    values: list[str] = []

    for key in keys:
        values.extend(_as_text_values(source.get(key)))

    result = source.get("result")
    if isinstance(result, Mapping):
        for key in keys:
            values.extend(_as_text_values(result.get(key)))

    return values


def _as_text_values(value: Any) -> list[str]:
    if value is None:
        return []

    if isinstance(value, str):
        return [value.strip()] if value.strip() else []

    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]

    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]

    return [str(value).strip()] if str(value).strip() else []


def _extract_warning_lines(logs: list[str]) -> list[str]:
    return [line for line in logs if "Warning:" in line or "WARNING:" in line]


def _extract_error_lines(logs: list[str]) -> list[str]:
    error_patterns = (
        "Runtime Error",
        "Error:",
        "ERROR:",
        "Exception",
        "Traceback",
    )

    return [
        line
        for line in logs
        if any(pattern in line for pattern in error_patterns)
    ]


def _extract_marker_events(logs: list[str], marker: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []

    for index, line in enumerate(logs):
        payload = _extract_payload_after_marker(line, marker)
        if payload is None:
            continue

        event = {
            "sequence": len(events) + 1,
            "log_index": index,
            "raw_log": line,
        }
        event.update(payload)
        events.append(event)

    return events


def _extract_decision_events(logs: list[str]) -> list[dict[str, Any]]:
    events = _extract_marker_events(logs, DECISION_MARKER)

    for event in events:
        event.setdefault("time", None)
        event.setdefault("strategy_id", None)
        event.setdefault("symbol", None)
        event.setdefault("signal", None)
        event.setdefault("fast", None)
        event.setdefault("slow", None)

    return events


def _extract_payload_after_marker(
    line: str,
    marker: str,
) -> dict[str, Any] | None:
    marker_index = line.find(marker)
    if marker_index < 0:
        return None

    payload_text = line[marker_index + len(marker):].lstrip("|")
    payload: dict[str, Any] = {}

    for part in payload_text.split("|"):
        if "=" not in part:
            continue

        key, value = part.split("=", 1)
        key = key.strip()
        value = value.strip()

        if key:
            payload[key] = _coerce_value(value)

    return payload


def _coerce_value(value: str) -> Any:
    if not value:
        return value

    numeric = _optional_number(value)
    if numeric is not None:
        return numeric

    return value


def _extract_backtest_id(
    source: Mapping[str, Any],
    logs: list[str],
) -> str | None:
    for key in ("backtest_id", "id", "algorithm_id", "project_id"):
        value = source.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    for line in logs:
        launch_match = re.search(r"Launching analysis for ([A-Za-z0-9_-]+)", line)
        if launch_match:
            return launch_match.group(1)

        algorithm_match = re.search(r"Algorithm Id:\s*\(([^)]+)\)", line)
        if algorithm_match:
            return algorithm_match.group(1)

    return None


def _extract_performance_summary(source: Mapping[str, Any]) -> dict[str, Any]:
    stats = _extract_stats_mapping(source)

    return {
        "total_trades": _find_number(
            stats,
            ("Total Trades", "total_trades", "trades", "Trade Count"),
        ),
        "win_rate": _find_number(
            stats,
            ("Win Rate", "win_rate", "WinRate", "Winning Rate"),
        ),
        "drawdown": _find_number(
            stats,
            ("Drawdown", "drawdown", "Max Drawdown", "max_drawdown"),
        ),
        "sharpe_ratio": _find_number(
            stats,
            ("Sharpe Ratio", "sharpe_ratio", "Sharpe"),
        ),
        "probabilistic_sharpe_ratio": _find_number(
            stats,
            (
                "Probabilistic Sharpe Ratio",
                "probabilistic_sharpe_ratio",
                "PSR",
            ),
        ),
        "net_profit": _find_number(
            stats,
            ("Net Profit", "net_profit", "Compounding Annual Return"),
        ),
        "raw_statistics": _json_safe_mapping(stats),
    }


def _extract_stats_mapping(source: Mapping[str, Any]) -> dict[str, Any]:
    for key in STATS_KEYS:
        value = source.get(key)
        if isinstance(value, Mapping):
            return dict(value)

    result = source.get("result")
    if isinstance(result, Mapping):
        for key in STATS_KEYS:
            value = result.get(key)
            if isinstance(value, Mapping):
                return dict(value)

    return {}


def _empty_performance_summary() -> dict[str, Any]:
    return {
        "total_trades": None,
        "win_rate": None,
        "drawdown": None,
        "sharpe_ratio": None,
        "probabilistic_sharpe_ratio": None,
        "net_profit": None,
        "raw_statistics": {},
    }


def _find_number(
    values: Mapping[str, Any],
    aliases: tuple[str, ...],
) -> int | float | None:
    for alias in aliases:
        if alias in values:
            return _optional_number(values[alias])

    normalized_values = {
        str(key).strip().lower().replace(" ", "_"): value
        for key, value in values.items()
    }

    for alias in aliases:
        normalized_alias = alias.strip().lower().replace(" ", "_")
        if normalized_alias in normalized_values:
            return _optional_number(normalized_values[normalized_alias])

    return None


def _optional_number(value: Any) -> int | float | None:
    if value is None or isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        return value

    text = str(value).strip()
    if not text:
        return None

    text = text.replace(",", "")
    text = text.replace("%", "")

    try:
        number = float(text)
    except ValueError:
        return None

    if number.is_integer():
        return int(number)

    return number


def _has_performance_statistics(performance_summary: Mapping[str, Any]) -> bool:
    raw = performance_summary.get("raw_statistics")
    if isinstance(raw, Mapping) and raw:
        return True

    for key, value in performance_summary.items():
        if key == "raw_statistics":
            continue
        if value is not None:
            return True

    return False


def _performance_metric_count(performance_summary: Mapping[str, Any]) -> int:
    return sum(
        1
        for key, value in performance_summary.items()
        if key != "raw_statistics" and value is not None
    )


def _reported_strategy_count(events: list[Mapping[str, Any]]) -> int:
    counts = [
        _optional_number(event.get("strategy_count"))
        for event in events
    ]

    numeric_counts = [count for count in counts if isinstance(count, int)]

    if not numeric_counts:
        return 0

    return max(numeric_counts)


def _classify_import_status(
    *,
    source_status: str,
    export_loaded_event_count: int,
    decision_event_count: int,
    has_performance_statistics: bool,
    error_count: int,
    blocked_reason_count: int,
) -> str:
    if source_status == "blocked" or error_count > 0 or blocked_reason_count > 0:
        return "blocked"

    if export_loaded_event_count == 0:
        return "needs_review"

    if decision_event_count == 0:
        return "needs_review"

    if not has_performance_statistics:
        return "needs_review"

    return "ready"


def _json_safe_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}

    for key, item in value.items():
        if isinstance(item, Mapping):
            safe[str(key)] = _json_safe_mapping(item)
        elif isinstance(item, list):
            safe[str(key)] = [_json_safe_value(child) for child in item]
        elif isinstance(item, tuple):
            safe[str(key)] = [_json_safe_value(child) for child in item]
        elif isinstance(item, (str, int, float, bool)) or item is None:
            safe[str(key)] = item
        else:
            safe[str(key)] = str(item)

    return safe


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _json_safe_mapping(value)
    if isinstance(value, list):
        return [_json_safe_value(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _sorted_unique_text(values: list[str]) -> list[str]:
    return sorted({value.strip() for value in values if value and value.strip()})


def _unique_text(values: Any) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})
