from __future__ import annotations

import json
from os import PathLike
from pathlib import Path
from typing import Any, Mapping

from src.backtesting.quantconnect_api_config.builder import (
    build_quantconnect_api_config,
)


OPERATION_SCHEMA_VERSION = "quantconnect_api_config_operation.v1"
EVENT_SCHEMA_VERSION = "quantconnect_api_config_operation_event.v1"
AUDIT_SCHEMA_VERSION = "quantconnect_api_config_audit.v1"
HEALTH_SCHEMA_VERSION = "quantconnect_api_config_health.v1"

OPERATION_TYPE = "quantconnect_api_config_operation"


def run_quantconnect_api_config_operation(
    source: Any,
    *,
    environment: Mapping[str, str] | None = None,
    event_log_path: str | PathLike[str] | None = None,
) -> dict[str, Any]:
    """Run a deterministic QuantConnect API config operation.

    This operation does not call QuantConnect, brokers, market-data services,
    order-routing systems, live-trading APIs, fill engines, slippage engines,
    or external data warehouses. It only validates local API configuration and
    records safe metadata. API token values are never written to artifacts.
    """

    api_config = build_quantconnect_api_config(source, environment=environment)
    audit_report = build_quantconnect_api_config_audit_report(api_config)
    health_report = build_quantconnect_api_config_health_report(api_config)

    events = [
        _build_event(
            api_config=api_config,
            event_type="quantconnect_api_config_operation_started",
            sequence=1,
        ),
        _build_event(
            api_config=api_config,
            event_type="quantconnect_api_config_operation_completed",
            sequence=2,
        ),
    ]

    normalized_log_path = _normalize_event_log_path(event_log_path)
    if normalized_log_path is not None:
        _write_jsonl_event_log(normalized_log_path, events)

    operation_record = _build_operation_record(
        api_config=api_config,
        audit_report=audit_report,
        health_report=health_report,
        event_log_path=normalized_log_path,
    )

    return {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": api_config["status"],
        "operation_record": operation_record,
        "audit_report": audit_report,
        "health_report": health_report,
        "api_config": api_config,
        "events": events,
        "event_log_path": str(normalized_log_path) if normalized_log_path else None,
        "explicit_exclusions": list(api_config.get("explicit_exclusions", [])),
    }


def build_quantconnect_api_config_audit_report(
    api_config: Mapping[str, Any],
) -> dict[str, Any]:
    checks = [
        _check(
            name="api_config_schema_version_present",
            passed=bool(api_config.get("schema_version")),
            severity="blocker",
            message="API config schema version is present",
            failure_message="API config schema version is missing",
        ),
        _check(
            name="config_type_is_quantconnect_backtest_result_api_config",
            passed=api_config.get("config_type")
            == "quantconnect_backtest_result_api_config",
            severity="blocker",
            message="config type is QuantConnect backtest-result API config",
            failure_message="unexpected config type detected",
        ),
        _check(
            name="explicit_exclusions_present",
            passed=_has_required_exclusions(api_config),
            severity="blocker",
            message="manual-only exclusions are present",
            failure_message="one or more required exclusions are missing",
        ),
        _check(
            name="api_base_url_is_http",
            passed=_api_base_url_is_http(api_config),
            severity="blocker",
            message="API base URL is http/https",
            failure_message="API base URL must be http or https",
        ),
        _check(
            name="request_timeout_positive",
            passed=_request_timeout_positive(api_config),
            severity="blocker",
            message="request timeout is positive",
            failure_message="request timeout must be greater than zero",
        ),
        _check(
            name="max_retries_non_negative",
            passed=_max_retries_non_negative(api_config),
            severity="blocker",
            message="max retries is zero or greater",
            failure_message="max retries must be zero or greater",
        ),
        _check(
            name="user_id_present",
            passed=_credential_flag(api_config, "user_id_present"),
            severity="warning",
            message="QuantConnect user id is present",
            failure_message="QuantConnect user id is missing",
        ),
        _check(
            name="api_token_present",
            passed=_credential_flag(api_config, "api_token_present"),
            severity="warning",
            message="QuantConnect API token environment variable is present",
            failure_message="QuantConnect API token environment variable is missing",
        ),
        _check(
            name="api_token_value_not_persisted",
            passed=_token_not_persisted(api_config),
            severity="blocker",
            message="API token value is not persisted",
            failure_message="API token value persistence was detected",
        ),
        _check(
            name="requested_api_capabilities_present",
            passed=_capabilities_present(api_config),
            severity="warning",
            message="requested API capabilities are present",
            failure_message="requested API capabilities are missing",
        ),
    ]

    audit_summary = _summarize_checks(checks)

    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_audit_status(
            config_status=str(api_config.get("status", "needs_review")),
            checks=checks,
        ),
        "summary": audit_summary,
        "checks": checks,
        "explicit_exclusions": list(api_config.get("explicit_exclusions", [])),
    }


def build_quantconnect_api_config_health_report(
    api_config: Mapping[str, Any],
) -> dict[str, Any]:
    config_status = str(api_config.get("status", "needs_review"))
    summary = _as_mapping(api_config.get("summary"))
    credentials = _as_mapping(api_config.get("credentials"))
    backtest_context = _as_mapping(api_config.get("backtest_context"))

    indicators = {
        "config_status": config_status,
        "api_base_url": summary.get("api_base_url"),
        "user_id_present": bool(summary.get("user_id_present")),
        "api_token_present": bool(summary.get("api_token_present")),
        "api_token_value_persisted": bool(
            credentials.get("api_token_value_persisted")
        ),
        "project_id_present": bool(backtest_context.get("project_id_present")),
        "backtest_id_present": bool(backtest_context.get("backtest_id_present")),
        "request_timeout_seconds": _safe_int(
            summary.get("request_timeout_seconds")
        ),
        "max_retries": _safe_int(summary.get("max_retries")),
        "warning_count": _safe_int(summary.get("warning_count")),
        "blocked_reason_count": _safe_int(summary.get("blocked_reason_count")),
    }

    recommendations = _build_health_recommendations(indicators)

    return {
        "schema_version": HEALTH_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_health_status(config_status),
        "indicators": indicators,
        "recommendations": recommendations,
        "explicit_exclusions": list(api_config.get("explicit_exclusions", [])),
    }


def _build_operation_record(
    *,
    api_config: Mapping[str, Any],
    audit_report: Mapping[str, Any],
    health_report: Mapping[str, Any],
    event_log_path: Path | None,
) -> dict[str, Any]:
    summary = _as_mapping(api_config.get("summary"))
    backtest_context = _as_mapping(api_config.get("backtest_context"))

    operation_id = _build_operation_id(backtest_context)

    return {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "operation_id": operation_id,
        "status": api_config.get("status", "needs_review"),
        "summary": {
            "config_status": api_config.get("status", "needs_review"),
            "audit_status": audit_report.get("status", "needs_review"),
            "health_status": health_report.get("status", "degraded"),
            "api_base_url": summary.get("api_base_url"),
            "user_id_present": bool(summary.get("user_id_present")),
            "api_token_present": bool(summary.get("api_token_present")),
            "project_id_present": bool(summary.get("project_id_present")),
            "backtest_id_present": bool(summary.get("backtest_id_present")),
            "request_timeout_seconds": _safe_int(
                summary.get("request_timeout_seconds")
            ),
            "max_retries": _safe_int(summary.get("max_retries")),
            "warning_count": _safe_int(summary.get("warning_count")),
            "blocked_reason_count": _safe_int(summary.get("blocked_reason_count")),
        },
        "event_log_path": str(event_log_path) if event_log_path else None,
        "explicit_exclusions": list(api_config.get("explicit_exclusions", [])),
    }


def _build_event(
    *,
    api_config: Mapping[str, Any],
    event_type: str,
    sequence: int,
) -> dict[str, Any]:
    summary = _as_mapping(api_config.get("summary"))

    return {
        "schema_version": EVENT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "event_type": event_type,
        "sequence": sequence,
        "status": api_config.get("status", "needs_review"),
        "summary": {
            "config_status": api_config.get("status", "needs_review"),
            "api_base_url": summary.get("api_base_url"),
            "user_id_present": bool(summary.get("user_id_present")),
            "api_token_present": bool(summary.get("api_token_present")),
            "project_id_present": bool(summary.get("project_id_present")),
            "backtest_id_present": bool(summary.get("backtest_id_present")),
            "warning_count": _safe_int(summary.get("warning_count")),
            "blocked_reason_count": _safe_int(summary.get("blocked_reason_count")),
        },
        "explicit_exclusions": list(api_config.get("explicit_exclusions", [])),
    }


def _write_jsonl_event_log(path: Path, events: list[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        for event in events:
            file.write(json.dumps(event, sort_keys=True))
            file.write("\n")


def _normalize_event_log_path(path: str | PathLike[str] | None) -> Path | None:
    if path is None:
        return None
    return Path(path)


def _check(
    *,
    name: str,
    passed: bool,
    severity: str,
    message: str,
    failure_message: str,
) -> dict[str, Any]:
    if passed:
        return {
            "name": name,
            "status": "passed",
            "severity": severity,
            "message": message,
        }

    failed_status = "failed" if severity == "blocker" else "warning"

    return {
        "name": name,
        "status": failed_status,
        "severity": severity,
        "message": failure_message,
    }


def _summarize_checks(checks: list[Mapping[str, Any]]) -> dict[str, int]:
    return {
        "passed_count": sum(1 for check in checks if check.get("status") == "passed"),
        "warning_count": sum(1 for check in checks if check.get("status") == "warning"),
        "failed_count": sum(1 for check in checks if check.get("status") == "failed"),
        "check_count": len(checks),
    }


def _classify_audit_status(
    *,
    config_status: str,
    checks: list[Mapping[str, Any]],
) -> str:
    if any(check.get("status") == "failed" for check in checks):
        return "blocked"

    if config_status == "blocked":
        return "blocked"

    if config_status == "needs_review":
        return "needs_review"

    if any(check.get("status") == "warning" for check in checks):
        return "needs_review"

    return "ready"


def _classify_health_status(config_status: str) -> str:
    if config_status == "ready":
        return "healthy"
    if config_status == "blocked":
        return "blocked"
    return "degraded"


def _build_health_recommendations(indicators: Mapping[str, Any]) -> list[str]:
    recommendations: list[str] = []

    if not indicators.get("user_id_present"):
        recommendations.append("provide QuantConnect user id")

    if not indicators.get("api_token_present"):
        recommendations.append("provide QuantConnect API token through environment")

    if indicators.get("api_token_value_persisted"):
        recommendations.append("remove persisted API token value from artifacts")

    if _safe_int(indicators.get("blocked_reason_count")) > 0:
        recommendations.append("resolve blocked QuantConnect API config reasons")

    if indicators.get("config_status") == "ready":
        recommendations.append("QuantConnect API config is ready")

    if not indicators.get("project_id_present"):
        recommendations.append("provide project id before pulling a specific backtest")

    if not indicators.get("backtest_id_present"):
        recommendations.append("provide backtest id before pulling a specific backtest")

    if not recommendations:
        recommendations.append("no health actions required")

    return sorted(set(recommendations))


def _has_required_exclusions(api_config: Mapping[str, Any]) -> bool:
    required = {
        "broker_api_calls",
        "order_routing",
        "order_submission",
        "fills",
        "live_execution",
        "local_fill_simulation",
        "local_slippage_modeling",
        "external_data_warehouse_access",
    }

    exclusions = api_config.get("explicit_exclusions")
    if not isinstance(exclusions, list):
        return False

    return required.issubset({str(item) for item in exclusions})


def _api_base_url_is_http(api_config: Mapping[str, Any]) -> bool:
    connection = _as_mapping(api_config.get("connection"))
    api_base_url = str(connection.get("api_base_url", ""))
    return api_base_url.startswith("https://") or api_base_url.startswith("http://")


def _request_timeout_positive(api_config: Mapping[str, Any]) -> bool:
    connection = _as_mapping(api_config.get("connection"))
    return _safe_int(connection.get("request_timeout_seconds")) > 0


def _max_retries_non_negative(api_config: Mapping[str, Any]) -> bool:
    connection = _as_mapping(api_config.get("connection"))
    return _safe_int(connection.get("max_retries")) >= 0


def _credential_flag(api_config: Mapping[str, Any], key: str) -> bool:
    credentials = _as_mapping(api_config.get("credentials"))
    return bool(credentials.get(key))


def _token_not_persisted(api_config: Mapping[str, Any]) -> bool:
    credentials = _as_mapping(api_config.get("credentials"))
    return credentials.get("api_token_value_persisted") is False


def _capabilities_present(api_config: Mapping[str, Any]) -> bool:
    capabilities = api_config.get("requested_api_capabilities")
    return isinstance(capabilities, list) and len(capabilities) > 0


def _build_operation_id(backtest_context: Mapping[str, Any]) -> str:
    project_id = backtest_context.get("project_id") or "missing_project"
    backtest_id = backtest_context.get("backtest_id") or "missing_backtest"
    return f"{OPERATION_TYPE}::{project_id}::{backtest_id}"


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _safe_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
