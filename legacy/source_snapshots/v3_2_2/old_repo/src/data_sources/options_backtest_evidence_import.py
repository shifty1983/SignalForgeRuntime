from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from src.data_sources.data_source_contract_validator import (
    validate_signalforge_data_source_contract_payload,
)
from src.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS


IMPORT_SCHEMA_VERSION = "signalforge_options_backtest_evidence_import.v1"

CONTRACT_NAME = "backtest_evidence"


FIELD_ALIASES = {
    "strategy_name": [
        "strategy_name",
        "strategy",
        "strategy_id",
        "algorithm_name",
        "name",
    ],
    "symbol_universe": [
        "symbol_universe",
        "symbols",
        "tickers",
        "securities",
        "universe",
    ],
    "test_start": [
        "test_start",
        "start_date",
        "backtest_start",
        "from",
    ],
    "test_end": [
        "test_end",
        "end_date",
        "backtest_end",
        "to",
    ],
    "trade_count": [
        "trade_count",
        "trades",
        "total_trades",
        "number_of_trades",
    ],
    "source": [
        "source",
        "source_name",
        "provider",
        "backtest_source",
    ],
    "win_rate": [
        "win_rate",
        "winning_rate",
        "percent_profitable",
    ],
    "average_win": [
        "average_win",
        "avg_win",
        "average_winner",
    ],
    "average_loss": [
        "average_loss",
        "avg_loss",
        "average_loser",
    ],
    "expectancy": [
        "expectancy",
        "expected_value",
        "ev",
    ],
    "max_drawdown": [
        "max_drawdown",
        "maximum_drawdown",
        "drawdown",
    ],
    "profit_factor": [
        "profit_factor",
    ],
    "total_return": [
        "total_return",
        "return",
        "net_return",
        "compounding_return",
    ],
    "equity_curve": [
        "equity_curve",
        "equity",
        "portfolio_value_series",
    ],
    "trade_list": [
        "trade_list",
        "trades_list",
        "orders",
        "fills",
    ],
    "parameter_set": [
        "parameter_set",
        "parameters",
        "params",
    ],
    "warnings": [
        "warnings",
        "import_warnings",
        "notes",
    ],
    "sharpe": [
        "sharpe",
        "sharpe_ratio",
    ],
    "sortino": [
        "sortino",
        "sortino_ratio",
    ],
    "benchmark_return": [
        "benchmark_return",
        "benchmark",
    ],
    "regime_tags": [
        "regime_tags",
        "regimes",
    ],
    "setup_tags": [
        "setup_tags",
        "setups",
    ],
    "source_backtest_id": [
        "source_backtest_id",
        "backtest_id",
        "quantconnect_backtest_id",
    ],
    "source_project_id": [
        "source_project_id",
        "project_id",
        "quantconnect_project_id",
    ],
}


def build_signalforge_options_backtest_evidence_import(
    source: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize manual/QuantConnect-style backtest evidence into SignalForge shape.

    This adapter only transforms local JSON provided by the user. It does not call
    QuantConnect, brokers, route orders, submit orders, model fills, perform live
    execution, model slippage, create automatic close/roll/defense orders, change
    strategies automatically, update parameters automatically, or pause strategies
    automatically.
    """

    if source is not None and not isinstance(source, Mapping):
        return _blocked_result("source must be a mapping")

    source = source or {}
    raw_payload = _raw_payload(source)

    if raw_payload is not None and not isinstance(raw_payload, Mapping):
        return _blocked_result("raw backtest payload must be a mapping")

    raw_payload = raw_payload or source

    normalized_payload = _normalize_backtest_payload(raw_payload)

    validation = validate_signalforge_data_source_contract_payload(
        {
            "contract": CONTRACT_NAME,
            "payload": normalized_payload,
        }
    )

    status = str(validation.get("status", "needs_review"))

    return {
        "artifact_type": "signalforge_options_backtest_evidence_import",
        "schema_version": IMPORT_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "contract": CONTRACT_NAME,
        "adapter_type": "backtest_evidence_import",
        "source_kind": _source_kind(source),
        "normalized_payload": normalized_payload,
        "normalized_payload_summary": _normalized_payload_summary(normalized_payload),
        "validation_artifact": validation,
        "blocker_items": list(_as_list(validation.get("blocker_items"))),
        "warning_items": list(_as_list(validation.get("warning_items"))),
        "missing_required_fields": list(_as_list(validation.get("missing_required_fields"))),
        "missing_preferred_fields": list(_as_list(validation.get("missing_preferred_fields"))),
        "backtest_summary": _backtest_summary(normalized_payload),
        "raw_payload_summary": _raw_payload_summary(raw_payload),
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _raw_payload(source: Mapping[str, Any]) -> Any:
    if "backtest_result" in source:
        return source.get("backtest_result")
    if "quantconnect_result" in source:
        return source.get("quantconnect_result")
    if "payload" in source:
        return source.get("payload")
    return None


def _source_kind(source: Mapping[str, Any]) -> str:
    if "quantconnect_result" in source:
        return "quantconnect_manual_export"
    if "backtest_result" in source:
        return "manual_backtest_result"
    if "payload" in source:
        return "normalized_payload_candidate"
    return "flat_manual_source"


def _normalize_backtest_payload(raw_payload: Mapping[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}

    fields = [
        "strategy_name",
        "symbol_universe",
        "test_start",
        "test_end",
        "trade_count",
        "source",
        "win_rate",
        "average_win",
        "average_loss",
        "expectancy",
        "max_drawdown",
        "profit_factor",
        "total_return",
        "equity_curve",
        "trade_list",
        "parameter_set",
        "warnings",
        "sharpe",
        "sortino",
        "benchmark_return",
        "regime_tags",
        "setup_tags",
        "source_backtest_id",
        "source_project_id",
    ]

    for field in fields:
        value = _first_present(raw_payload, FIELD_ALIASES[field])
        if value is not None:
            normalized[field] = _normalize_field_value(field, value)

    if "warnings" not in normalized:
        normalized["warnings"] = []

    return normalized


def _first_present(payload: Mapping[str, Any], aliases: Sequence[str]) -> Any:
    for alias in aliases:
        if alias in payload and payload.get(alias) is not None:
            return payload.get(alias)
    return None


def _normalize_field_value(field: str, value: Any) -> Any:
    if field in {"symbol_universe", "regime_tags", "setup_tags"}:
        return _normalize_list(value)

    if field == "warnings":
        return _normalize_list(value)

    if field == "trade_count":
        return _safe_int(value)

    if field in {
        "win_rate",
        "average_win",
        "average_loss",
        "expectancy",
        "max_drawdown",
        "profit_factor",
        "total_return",
        "sharpe",
        "sortino",
        "benchmark_return",
    }:
        return _safe_float_or_original(value)

    return value


def _normalize_list(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    if value is None:
        return []
    return [value]


def _normalized_payload_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "field_count": len(payload),
        "has_strategy_name": "strategy_name" in payload,
        "has_symbol_universe": "symbol_universe" in payload,
        "has_test_window": "test_start" in payload and "test_end" in payload,
        "has_trade_count": "trade_count" in payload,
        "has_expectancy": "expectancy" in payload,
        "has_trade_list": "trade_list" in payload,
        "has_equity_curve": "equity_curve" in payload,
        "top_level_fields": sorted(str(key) for key in payload.keys()),
    }


def _backtest_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "strategy_name": payload.get("strategy_name"),
        "symbol_count": len(_as_list(payload.get("symbol_universe"))),
        "test_start": payload.get("test_start"),
        "test_end": payload.get("test_end"),
        "trade_count": _safe_int(payload.get("trade_count")),
        "win_rate": payload.get("win_rate"),
        "expectancy": payload.get("expectancy"),
        "max_drawdown": payload.get("max_drawdown"),
        "profit_factor": payload.get("profit_factor"),
        "total_return": payload.get("total_return"),
        "source": payload.get("source"),
    }


def _raw_payload_summary(raw_payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "field_count": len(raw_payload),
        "top_level_fields": sorted(str(key) for key in raw_payload.keys()),
    }


def _blocked_result(reason: str) -> dict[str, Any]:
    return {
        "artifact_type": "signalforge_options_backtest_evidence_import",
        "schema_version": IMPORT_SCHEMA_VERSION,
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "contract": CONTRACT_NAME,
        "adapter_type": "backtest_evidence_import",
        "blocker_items": [{"reason": reason}],
        "warning_items": [],
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return []


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _safe_float_or_original(value: Any) -> Any:
    try:
        return float(value)
    except (TypeError, ValueError):
        return value

