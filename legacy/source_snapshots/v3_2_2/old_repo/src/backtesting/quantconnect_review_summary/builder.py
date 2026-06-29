from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any, Mapping


SCHEMA_VERSION = "quantconnect_review_summary.v1"
REVIEW_TYPE = "manual_quantconnect_backtest_review"

EXPLICIT_EXCLUSIONS = [
    "quantconnect_api_calls",
    "broker_api_calls",
    "order_routing",
    "order_submission",
    "fills",
    "live_execution",
    "local_fill_simulation",
    "local_slippage_modeling",
    "external_data_warehouse_access",
]


def build_quantconnect_review_summary(
    export_operation_result: Any,
    result_import_operation_result: Any,
) -> dict[str, Any]:
    """Build a compact review summary for a manual QuantConnect backtest loop.

    This builder does not call QuantConnect, brokers, market-data services,
    order-routing systems, live-trading APIs, fill engines, slippage engines,
    or external data warehouses. It only compares an existing local export
    operation result with an existing local QuantConnect result import.
    """

    if not isinstance(export_operation_result, Mapping):
        return _blocked_invalid_shape("export_operation_result must be a mapping/dict")

    if not isinstance(result_import_operation_result, Mapping):
        return _blocked_invalid_shape(
            "result_import_operation_result must be a mapping/dict"
        )

    export_operation = deepcopy(dict(export_operation_result))
    import_operation = deepcopy(dict(result_import_operation_result))

    export = _extract_export(export_operation)
    import_result = _extract_import_result(import_operation)

    if not export:
        return _blocked_invalid_shape("export operation result is missing export payload")

    if not import_result:
        return _blocked_invalid_shape(
            "result import operation result is missing import_result payload"
        )

    export_summary = _build_export_summary(export_operation, export)
    result_summary = _build_result_summary(import_operation, import_result)
    alignment = _build_alignment_summary(export, import_result)
    decision_summary = _build_decision_summary(import_result)

    warnings = []
    warnings.extend(_as_text_list(export.get("warnings")))
    warnings.extend(_as_text_list(import_result.get("warnings")))
    warnings.extend(_alignment_warnings(alignment))

    blocked_reasons = []
    blocked_reasons.extend(_as_text_list(export.get("blocked_reasons")))
    blocked_reasons.extend(_as_text_list(import_result.get("blocked_reasons")))

    status = _classify_review_status(
        export_status=export_summary["export_status"],
        import_status=result_summary["import_status"],
        alignment=alignment,
        result_summary=result_summary,
        blocked_reasons=blocked_reasons,
    )

    if status == "blocked" and not blocked_reasons:
        blocked_reasons.append("QuantConnect review summary blocked")

    warnings = _sorted_unique_text(warnings)
    blocked_reasons = _sorted_unique_text(blocked_reasons)

    return {
        "schema_version": SCHEMA_VERSION,
        "review_type": REVIEW_TYPE,
        "status": status,
        "summary": {
            "export_status": export_summary["export_status"],
            "import_status": result_summary["import_status"],
            "backtest_id": result_summary["backtest_id"],
            "expected_strategy_count": alignment["expected_strategy_count"],
            "observed_strategy_count": alignment["observed_strategy_count"],
            "expected_symbol_count": alignment["expected_symbol_count"],
            "observed_symbol_count": alignment["observed_symbol_count"],
            "decision_event_count": result_summary["decision_event_count"],
            "performance_metric_count": result_summary["performance_metric_count"],
            "warning_count": len(warnings),
            "blocked_reason_count": len(blocked_reasons),
        },
        "export_summary": export_summary,
        "result_summary": result_summary,
        "alignment": alignment,
        "decision_summary": decision_summary,
        "performance_summary": _as_mapping(import_result.get("performance_summary")),
        "warnings": warnings,
        "blocked_reasons": blocked_reasons,
        "source_operation_summaries": {
            "export_operation": _operation_summary(export_operation),
            "result_import_operation": _operation_summary(import_operation),
        },
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _blocked_invalid_shape(reason: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "review_type": REVIEW_TYPE,
        "status": "blocked",
        "summary": {
            "export_status": "invalid_shape",
            "import_status": "invalid_shape",
            "backtest_id": None,
            "expected_strategy_count": 0,
            "observed_strategy_count": 0,
            "expected_symbol_count": 0,
            "observed_symbol_count": 0,
            "decision_event_count": 0,
            "performance_metric_count": 0,
            "warning_count": 0,
            "blocked_reason_count": 1,
        },
        "export_summary": _empty_export_summary(),
        "result_summary": _empty_result_summary(),
        "alignment": _empty_alignment_summary(),
        "decision_summary": _empty_decision_summary(),
        "performance_summary": {},
        "warnings": [],
        "blocked_reasons": [reason],
        "source_operation_summaries": {
            "export_operation": {},
            "result_import_operation": {},
        },
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _extract_export(export_operation: Mapping[str, Any]) -> dict[str, Any]:
    export = export_operation.get("export")
    if isinstance(export, Mapping):
        return dict(export)

    if export_operation.get("schema_version") == "quantconnect_export.v1":
        return dict(export_operation)

    operation_result = export_operation.get("operation_result")
    if isinstance(operation_result, Mapping):
        export = operation_result.get("export")
        if isinstance(export, Mapping):
            return dict(export)

    return {}


def _extract_import_result(import_operation: Mapping[str, Any]) -> dict[str, Any]:
    import_result = import_operation.get("import_result")
    if isinstance(import_result, Mapping):
        return dict(import_result)

    if import_operation.get("schema_version") == "quantconnect_result_import.v1":
        return dict(import_operation)

    operation_result = import_operation.get("operation_result")
    if isinstance(operation_result, Mapping):
        import_result = operation_result.get("import_result")
        if isinstance(import_result, Mapping):
            return dict(import_result)

    return {}


def _build_export_summary(
    export_operation: Mapping[str, Any],
    export: Mapping[str, Any],
) -> dict[str, Any]:
    payloads = _as_mapping(export.get("generated_payloads"))
    strategy_configs = _as_list(payloads.get("strategy_configs"))
    universe = _as_list(payloads.get("universe"))
    manifest = _as_mapping(payloads.get("backtest_manifest"))

    strategy_ids = _strategy_ids_from_configs(strategy_configs)
    symbols = _symbols_from_configs(strategy_configs)

    return {
        "export_status": str(export.get("status", "needs_review")),
        "operation_status": str(export_operation.get("status", "needs_review")),
        "platform": export.get("platform"),
        "engine": export.get("engine"),
        "execution_mode": export.get("execution_mode"),
        "manifest_id": manifest.get("manifest_id"),
        "manifest_strategy_count": _safe_int(manifest.get("strategy_count")),
        "strategy_count": len(strategy_configs),
        "universe_count": len(universe),
        "strategy_ids": strategy_ids,
        "symbols": symbols,
    }


def _build_result_summary(
    import_operation: Mapping[str, Any],
    import_result: Mapping[str, Any],
) -> dict[str, Any]:
    summary = _as_mapping(import_result.get("summary"))

    return {
        "import_status": str(import_result.get("status", "needs_review")),
        "operation_status": str(import_operation.get("status", "needs_review")),
        "backtest_id": summary.get("backtest_id"),
        "source_status": summary.get("source_status"),
        "log_line_count": _safe_int(summary.get("log_line_count")),
        "export_loaded_event_count": _safe_int(
            summary.get("export_loaded_event_count")
        ),
        "decision_event_count": _safe_int(summary.get("decision_event_count")),
        "reported_strategy_count": _safe_int(summary.get("reported_strategy_count")),
        "unique_strategy_count": _safe_int(summary.get("unique_strategy_count")),
        "unique_symbol_count": _safe_int(summary.get("unique_symbol_count")),
        "performance_metric_count": _safe_int(summary.get("performance_metric_count")),
        "warning_count": _safe_int(summary.get("warning_count")),
        "error_count": _safe_int(summary.get("error_count")),
        "blocked_reason_count": _safe_int(summary.get("blocked_reason_count")),
    }


def _build_alignment_summary(
    export: Mapping[str, Any],
    import_result: Mapping[str, Any],
) -> dict[str, Any]:
    payloads = _as_mapping(export.get("generated_payloads"))
    strategy_configs = _as_list(payloads.get("strategy_configs"))

    expected_strategy_ids = _strategy_ids_from_configs(strategy_configs)
    expected_symbols = _symbols_from_configs(strategy_configs)

    signalforge_events = _as_mapping(import_result.get("signalforge_events"))
    export_loaded_events = _as_list(signalforge_events.get("export_loaded"))
    decision_events = _as_list(signalforge_events.get("decisions"))

    observed_strategy_ids = _unique_sorted(
        event.get("strategy_id")
        for event in decision_events
        if isinstance(event, Mapping)
    )
    observed_symbols = _unique_sorted(
        event.get("symbol")
        for event in decision_events
        if isinstance(event, Mapping)
    )

    reported_strategy_count = _reported_strategy_count(export_loaded_events)

    missing_strategy_ids = sorted(set(expected_strategy_ids) - set(observed_strategy_ids))
    unexpected_strategy_ids = sorted(
        set(observed_strategy_ids) - set(expected_strategy_ids)
    )
    missing_symbols = sorted(set(expected_symbols) - set(observed_symbols))
    unexpected_symbols = sorted(set(observed_symbols) - set(expected_symbols))

    return {
        "expected_strategy_ids": expected_strategy_ids,
        "observed_strategy_ids": observed_strategy_ids,
        "missing_decision_strategy_ids": missing_strategy_ids,
        "unexpected_decision_strategy_ids": unexpected_strategy_ids,
        "expected_symbols": expected_symbols,
        "observed_symbols": observed_symbols,
        "missing_symbols": missing_symbols,
        "unexpected_symbols": unexpected_symbols,
        "expected_strategy_count": len(expected_strategy_ids),
        "observed_strategy_count": len(observed_strategy_ids),
        "reported_strategy_count": reported_strategy_count,
        "expected_symbol_count": len(expected_symbols),
        "observed_symbol_count": len(observed_symbols),
        "has_export_loaded_marker": len(export_loaded_events) > 0,
        "has_decision_events": len(decision_events) > 0,
        "strategies_match": not missing_strategy_ids and not unexpected_strategy_ids,
        "symbols_match": not missing_symbols and not unexpected_symbols,
        "reported_count_matches_export": (
            reported_strategy_count == len(expected_strategy_ids)
            if reported_strategy_count > 0
            else False
        ),
    }


def _build_decision_summary(import_result: Mapping[str, Any]) -> dict[str, Any]:
    signalforge_events = _as_mapping(import_result.get("signalforge_events"))
    decision_events = _as_list(signalforge_events.get("decisions"))

    strategy_counts = Counter()
    symbol_counts = Counter()
    signal_counts = Counter()

    for event in decision_events:
        if not isinstance(event, Mapping):
            continue

        strategy_id = event.get("strategy_id")
        symbol = event.get("symbol")
        signal = event.get("signal")

        if strategy_id:
            strategy_counts[str(strategy_id)] += 1
        if symbol:
            symbol_counts[str(symbol)] += 1
        if signal:
            signal_counts[str(signal)] += 1

    return {
        "decision_event_count": len(decision_events),
        "decisions_by_strategy_id": dict(sorted(strategy_counts.items())),
        "decisions_by_symbol": dict(sorted(symbol_counts.items())),
        "decisions_by_signal": dict(sorted(signal_counts.items())),
        "first_decision": _json_safe_mapping(decision_events[0])
        if decision_events and isinstance(decision_events[0], Mapping)
        else None,
        "last_decision": _json_safe_mapping(decision_events[-1])
        if decision_events and isinstance(decision_events[-1], Mapping)
        else None,
    }


def _alignment_warnings(alignment: Mapping[str, Any]) -> list[str]:
    warnings: list[str] = []

    if not alignment.get("has_export_loaded_marker"):
        warnings.append("missing SIGNALFORGE_EXPORT_LOADED marker")

    if not alignment.get("has_decision_events"):
        warnings.append("missing SIGNALFORGE_DECISION events")

    if alignment.get("missing_decision_strategy_ids"):
        warnings.append("one or more exported strategies did not emit decisions")

    if alignment.get("unexpected_decision_strategy_ids"):
        warnings.append("result import contains decision strategies not present in export")

    if alignment.get("missing_symbols"):
        warnings.append("one or more exported symbols did not emit decisions")

    if alignment.get("unexpected_symbols"):
        warnings.append("result import contains decision symbols not present in export")

    if not alignment.get("reported_count_matches_export"):
        warnings.append("reported strategy count does not match exported strategy count")

    return warnings


def _classify_review_status(
    *,
    export_status: str,
    import_status: str,
    alignment: Mapping[str, Any],
    result_summary: Mapping[str, Any],
    blocked_reasons: list[str],
) -> str:
    if export_status == "blocked" or import_status == "blocked" or blocked_reasons:
        return "blocked"

    if export_status != "ready" or import_status != "ready":
        return "needs_review"

    if not alignment.get("has_export_loaded_marker"):
        return "needs_review"

    if not alignment.get("has_decision_events"):
        return "needs_review"

    if not alignment.get("strategies_match"):
        return "needs_review"

    if not alignment.get("symbols_match"):
        return "needs_review"

    if not alignment.get("reported_count_matches_export"):
        return "needs_review"

    if _safe_int(result_summary.get("performance_metric_count")) == 0:
        return "needs_review"

    if _safe_int(result_summary.get("error_count")) > 0:
        return "blocked"

    return "ready"


def _operation_summary(operation_result: Mapping[str, Any]) -> dict[str, Any]:
    operation_record = operation_result.get("operation_record")
    if isinstance(operation_record, Mapping):
        summary = operation_record.get("summary")
        if isinstance(summary, Mapping):
            return _json_safe_mapping(summary)

    summary = operation_result.get("summary")
    if isinstance(summary, Mapping):
        return _json_safe_mapping(summary)

    return {}


def _empty_export_summary() -> dict[str, Any]:
    return {
        "export_status": "invalid_shape",
        "operation_status": "invalid_shape",
        "platform": None,
        "engine": None,
        "execution_mode": None,
        "manifest_id": None,
        "manifest_strategy_count": 0,
        "strategy_count": 0,
        "universe_count": 0,
        "strategy_ids": [],
        "symbols": [],
    }


def _empty_result_summary() -> dict[str, Any]:
    return {
        "import_status": "invalid_shape",
        "operation_status": "invalid_shape",
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
        "blocked_reason_count": 0,
    }


def _empty_alignment_summary() -> dict[str, Any]:
    return {
        "expected_strategy_ids": [],
        "observed_strategy_ids": [],
        "missing_decision_strategy_ids": [],
        "unexpected_decision_strategy_ids": [],
        "expected_symbols": [],
        "observed_symbols": [],
        "missing_symbols": [],
        "unexpected_symbols": [],
        "expected_strategy_count": 0,
        "observed_strategy_count": 0,
        "reported_strategy_count": 0,
        "expected_symbol_count": 0,
        "observed_symbol_count": 0,
        "has_export_loaded_marker": False,
        "has_decision_events": False,
        "strategies_match": False,
        "symbols_match": False,
        "reported_count_matches_export": False,
    }


def _empty_decision_summary() -> dict[str, Any]:
    return {
        "decision_event_count": 0,
        "decisions_by_strategy_id": {},
        "decisions_by_symbol": {},
        "decisions_by_signal": {},
        "first_decision": None,
        "last_decision": None,
    }


def _strategy_ids_from_configs(strategy_configs: list[Any]) -> list[str]:
    return _unique_sorted(
        config.get("strategy_id")
        for config in strategy_configs
        if isinstance(config, Mapping)
    )


def _symbols_from_configs(strategy_configs: list[Any]) -> list[str]:
    return _unique_sorted(
        config.get("symbol")
        for config in strategy_configs
        if isinstance(config, Mapping)
    )


def _reported_strategy_count(export_loaded_events: list[Any]) -> int:
    counts = [
        _safe_int(event.get("strategy_count"))
        for event in export_loaded_events
        if isinstance(event, Mapping)
    ]

    if not counts:
        return 0

    return max(counts)


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _as_text_list(value: Any) -> list[str]:
    if value is None:
        return []

    if isinstance(value, str):
        return [value.strip()] if value.strip() else []

    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]

    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]

    return [str(value).strip()] if str(value).strip() else []


def _unique_sorted(values: Any) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})


def _sorted_unique_text(values: list[str]) -> list[str]:
    return sorted({value.strip() for value in values if value and value.strip()})


def _safe_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


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
