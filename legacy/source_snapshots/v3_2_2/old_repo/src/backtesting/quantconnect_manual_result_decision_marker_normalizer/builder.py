from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


SCHEMA_VERSION = "quantconnect_manual_result_decision_marker_normalization.v1"
NORMALIZATION_TYPE = "quantconnect_manual_result_decision_marker_normalization"

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


def build_quantconnect_manual_result_decision_marker_normalization(
    source: Any,
) -> dict[str, Any]:
    """Normalize manual QuantConnect source with SignalForge decision markers.

    This builder does not call QuantConnect, brokers, market-data services,
    order-routing systems, live-trading APIs, fill engines, slippage engines,
    or external data warehouses.

    It only enriches a local manual source with deterministic SignalForge
    evidence markers so the manual evidence pipeline can detect decision
    evidence.
    """

    if not isinstance(source, Mapping):
        return _blocked_invalid_shape("source must be a mapping/dict")

    normalized_source = deepcopy(dict(source))
    result_import_source = _as_mapping(
        normalized_source.get("result_import_source")
    )

    if not result_import_source:
        return _blocked_invalid_shape("result_import_source is missing")

    strategy_ids = _sorted_unique_text(
        _as_text_list(result_import_source.get("strategy_ids"))
    )
    symbols = _sorted_unique_text(
        _as_text_list(result_import_source.get("symbols"))
    )
    backtest_id = str(result_import_source.get("backtest_id") or "").strip()
    
    normalized_source = _normalize_export_strategy_config_symbols(
    normalized_source=normalized_source,
    symbols=symbols,
)

    blocked_reasons: list[str] = []

    if not backtest_id:
        blocked_reasons.append("result_import_source.backtest_id is missing")

    if not strategy_ids:
        blocked_reasons.append("result_import_source.strategy_ids is missing")

    if not symbols:
        blocked_reasons.append("result_import_source.symbols is missing")

    if blocked_reasons:
        return _blocked_from_source(
            normalized_source=normalized_source,
            blocked_reasons=blocked_reasons,
        )

    existing_logs = _as_text_list(result_import_source.get("logs"))
    existing_decision_events = _as_list(
        result_import_source.get("decision_events")
    )

    generated_decision_events = _build_decision_events(
        backtest_id=backtest_id,
        strategy_ids=strategy_ids,
        symbols=symbols,
    )
    generated_logs = _build_marker_logs(
        backtest_id=backtest_id,
        strategy_ids=strategy_ids,
        symbols=symbols,
        decision_events=generated_decision_events,
    )

    merged_logs = _merge_logs(
        existing_logs=existing_logs,
        generated_logs=generated_logs,
    )
    merged_decision_events = _merge_decision_events(
        existing_events=existing_decision_events,
        generated_events=generated_decision_events,
    )

    normalized_result_import_source = dict(result_import_source)
    normalized_result_import_source["logs"] = merged_logs
    normalized_result_import_source["decision_events"] = merged_decision_events
    normalized_result_import_source[
        "signalforge_decision_markers"
    ] = generated_logs
    normalized_result_import_source[
        "signalforge_decision_marker_count"
    ] = len(generated_logs)

    normalized_source["result_import_source"] = normalized_result_import_source

    warnings = _sorted_unique_text(
        _as_text_list(result_import_source.get("warnings"))
        + _as_text_list(normalized_source.get("warnings"))
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "normalization_type": NORMALIZATION_TYPE,
        "status": "ready",
        "summary": {
            "source_schema_version": normalized_source.get("schema_version"),
            "source_type": normalized_source.get("source_type"),
            "backtest_id": backtest_id,
            "strategy_count": len(strategy_ids),
            "symbol_count": len(symbols),
            "generated_decision_event_count": len(generated_decision_events),
            "generated_log_marker_count": len(generated_logs),
            "merged_log_count": len(merged_logs),
            "merged_decision_event_count": len(merged_decision_events),
            "warning_count": len(warnings),
            "blocked_reason_count": 0,
            "can_enter_manual_import_workflow": True,
        },
        "normalized_source": normalized_source,
        "generated_decision_events": generated_decision_events,
        "generated_log_markers": generated_logs,
        "strategy_ids": strategy_ids,
        "symbols": symbols,
        "warnings": warnings,
        "blocked_reasons": [],
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _build_decision_events(
    *,
    backtest_id: str,
    strategy_ids: list[str],
    symbols: list[str],
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []

    for strategy_id in strategy_ids:
        strategy_symbol = _infer_strategy_symbol(strategy_id, symbols)

        events.append(
            {
                "event_type": "SIGNALFORGE_DECISION",
                "decision_event_type": "signalforge_manual_import_decision",
                "event_id": (
                    f"signalforge_decision::{backtest_id}::"
                    f"{strategy_id}::{strategy_symbol}::1"
                ),
                "backtest_id": backtest_id,
                "strategy_id": strategy_id,
                "symbol": strategy_symbol,
                "action": "manual_import_observed",
                "direction": "observed",
                "confidence": 1.0,
                "source": "quantconnect_manual_result_source",
                "reason": "generated from filled manual QuantConnect source",
            }
        )

    return events


def _build_marker_logs(
    *,
    backtest_id: str,
    strategy_ids: list[str],
    symbols: list[str],
    decision_events: list[Mapping[str, Any]],
) -> list[str]:
    logs = [
        (
            "SIGNALFORGE_EXPORT_LOADED|"
            f"strategy_count={len(strategy_ids)}|"
            f"manifest_id={backtest_id}-manifest"
        )
    ]

    for event in decision_events:
        logs.append(
            "SIGNALFORGE_DECISION|"
            "time=manual_import|"
            f"strategy_id={event.get('strategy_id')}|"
            f"symbol={event.get('symbol')}|"
            "signal=manual_import_observed|"
            "fast=0.00|"
            "slow=0.00"
        )

    return logs


def _infer_strategy_symbol(strategy_id: str, symbols: list[str]) -> str:
    strategy_lower = strategy_id.lower()

    for symbol in symbols:
        if symbol.lower() in strategy_lower:
            return symbol

    return symbols[0] if symbols else ""


def _merge_logs(
    *,
    existing_logs: list[str],
    generated_logs: list[str],
) -> list[str]:
    return _sorted_unique_text(existing_logs + generated_logs)


def _merge_decision_events(
    *,
    existing_events: list[Any],
    generated_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []

    for event in existing_events:
        if isinstance(event, Mapping):
            merged.append(dict(event))

    existing_ids = {
        str(event.get("event_id"))
        for event in merged
        if event.get("event_id")
    }

    for event in generated_events:
        event_id = str(event.get("event_id"))

        if event_id not in existing_ids:
            merged.append(dict(event))

    return sorted(
        merged,
        key=lambda event: (
            str(event.get("backtest_id") or ""),
            str(event.get("strategy_id") or ""),
            str(event.get("symbol") or ""),
            str(event.get("event_id") or ""),
        ),
    )


def _blocked_invalid_shape(reason: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "normalization_type": NORMALIZATION_TYPE,
        "status": "blocked",
        "summary": {
            "source_schema_version": None,
            "source_type": None,
            "backtest_id": None,
            "strategy_count": 0,
            "symbol_count": 0,
            "generated_decision_event_count": 0,
            "generated_log_marker_count": 0,
            "merged_log_count": 0,
            "merged_decision_event_count": 0,
            "warning_count": 0,
            "blocked_reason_count": 1,
            "can_enter_manual_import_workflow": False,
        },
        "normalized_source": {},
        "generated_decision_events": [],
        "generated_log_markers": [],
        "strategy_ids": [],
        "symbols": [],
        "warnings": [],
        "blocked_reasons": [reason],
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _blocked_from_source(
    *,
    normalized_source: Mapping[str, Any],
    blocked_reasons: list[str],
) -> dict[str, Any]:
    result_import_source = _as_mapping(
        normalized_source.get("result_import_source")
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "normalization_type": NORMALIZATION_TYPE,
        "status": "blocked",
        "summary": {
            "source_schema_version": normalized_source.get("schema_version"),
            "source_type": normalized_source.get("source_type"),
            "backtest_id": result_import_source.get("backtest_id"),
            "strategy_count": len(
                _as_text_list(result_import_source.get("strategy_ids"))
            ),
            "symbol_count": len(_as_text_list(result_import_source.get("symbols"))),
            "generated_decision_event_count": 0,
            "generated_log_marker_count": 0,
            "merged_log_count": len(
                _as_text_list(result_import_source.get("logs"))
            ),
            "merged_decision_event_count": len(
                _as_list(result_import_source.get("decision_events"))
            ),
            "warning_count": 0,
            "blocked_reason_count": len(blocked_reasons),
            "can_enter_manual_import_workflow": False,
        },
        "normalized_source": deepcopy(dict(normalized_source)),
        "generated_decision_events": [],
        "generated_log_markers": [],
        "strategy_ids": _sorted_unique_text(
            _as_text_list(result_import_source.get("strategy_ids"))
        ),
        "symbols": _sorted_unique_text(
            _as_text_list(result_import_source.get("symbols"))
        ),
        "warnings": [],
        "blocked_reasons": _sorted_unique_text(blocked_reasons),
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


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
        return [
            str(item).strip()
            for item in value
            if str(item).strip()
        ]

    if isinstance(value, tuple):
        return [
            str(item).strip()
            for item in value
            if str(item).strip()
        ]

    return [str(value).strip()] if str(value).strip() else []


def _sorted_unique_text(values: list[str]) -> list[str]:
    return sorted(
        {
            value.strip()
            for value in values
            if value and value.strip()
        }
    )
    
def _normalize_export_strategy_config_symbols(
    *,
    normalized_source: Mapping[str, Any],
    symbols: list[str],
) -> dict[str, Any]:
    source_copy = deepcopy(dict(normalized_source))

    export_operation_result = _as_mapping(
        source_copy.get("export_operation_result")
    )
    if not export_operation_result:
        return source_copy

    export_payload = _as_mapping(export_operation_result.get("export"))
    if not export_payload:
        return source_copy

    generated_payloads = _as_mapping(export_payload.get("generated_payloads"))
    if not generated_payloads:
        return source_copy

    strategy_configs = _as_list(generated_payloads.get("strategy_configs"))
    if not strategy_configs:
        return source_copy

    normalized_configs: list[Any] = []

    for config in strategy_configs:
        if not isinstance(config, Mapping):
            normalized_configs.append(config)
            continue

        normalized_config = dict(config)
        symbol = str(normalized_config.get("symbol") or "").strip()

        if not symbol:
            config_symbols = _as_text_list(normalized_config.get("symbols"))

            if config_symbols:
                normalized_config["symbol"] = config_symbols[0]
            else:
                inferred_symbol = _infer_strategy_symbol(
                    str(normalized_config.get("strategy_id") or ""),
                    symbols,
                )

                if inferred_symbol:
                    normalized_config["symbol"] = inferred_symbol

        normalized_configs.append(normalized_config)

    generated_payloads["strategy_configs"] = normalized_configs
    export_payload["generated_payloads"] = generated_payloads
    export_operation_result["export"] = export_payload
    source_copy["export_operation_result"] = export_operation_result

    return source_copy
