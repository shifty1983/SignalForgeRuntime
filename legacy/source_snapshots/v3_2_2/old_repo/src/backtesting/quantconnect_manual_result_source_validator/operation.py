from __future__ import annotations

import json
from os import PathLike
from pathlib import Path
from typing import Any, Mapping

from src.backtesting.quantconnect_manual_result_source_validator.builder import (
    build_quantconnect_manual_result_source_validation,
)


OPERATION_SCHEMA_VERSION = (
    "quantconnect_manual_result_source_validation_operation.v1"
)
EVENT_SCHEMA_VERSION = (
    "quantconnect_manual_result_source_validation_operation_event.v1"
)
AUDIT_SCHEMA_VERSION = "quantconnect_manual_result_source_validation_audit.v1"
HEALTH_SCHEMA_VERSION = "quantconnect_manual_result_source_validation_health.v1"

OPERATION_TYPE = "quantconnect_manual_result_source_validation_operation"


def run_quantconnect_manual_result_source_validation_operation(
    source: Any,
    *,
    event_log_path: str | PathLike[str] | None = None,
) -> dict[str, Any]:
    """Run deterministic validation for a local manual QuantConnect source.

    This operation does not call QuantConnect, brokers, market-data services,
    order-routing systems, live-trading APIs, fill engines, slippage engines,
    or external data warehouses.
    """

    validation = build_quantconnect_manual_result_source_validation(source)

    audit_report = build_quantconnect_manual_result_source_validation_audit_report(
        validation
    )
    health_report = (
        build_quantconnect_manual_result_source_validation_health_report(
            validation
        )
    )

    events = [
        _build_event(
            validation=validation,
            event_type=(
                "quantconnect_manual_result_source_validation_operation_started"
            ),
            sequence=1,
        ),
        _build_event(
            validation=validation,
            event_type=(
                "quantconnect_manual_result_source_validation_operation_completed"
            ),
            sequence=2,
        ),
    ]

    normalized_log_path = _normalize_event_log_path(event_log_path)

    if normalized_log_path is not None:
        _write_jsonl_event_log(normalized_log_path, events)

    operation_record = _build_operation_record(
        validation=validation,
        audit_report=audit_report,
        health_report=health_report,
        event_log_path=normalized_log_path,
    )

    return {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": validation.get("status", "needs_review"),
        "operation_record": operation_record,
        "audit_report": audit_report,
        "health_report": health_report,
        "validation": validation,
        "events": events,
        "event_log_path": (
            str(normalized_log_path) if normalized_log_path else None
        ),
        "explicit_exclusions": list(
            validation.get("explicit_exclusions", [])
        ),
    }


def build_quantconnect_manual_result_source_validation_audit_report(
    validation: Mapping[str, Any],
) -> dict[str, Any]:
    checks = [
        _check(
            name="validation_schema_version_present",
            passed=bool(validation.get("schema_version")),
            severity="blocker",
            message="validation schema version is present",
            failure_message="validation schema version is missing",
        ),
        _check(
            name="validation_type_is_expected",
            passed=(
                validation.get("validation_type")
                == "quantconnect_manual_result_source_validation"
            ),
            severity="blocker",
            message="validation type is expected",
            failure_message="unexpected validation type detected",
        ),
        _check(
            name="explicit_exclusions_present",
            passed=_has_required_exclusions(validation),
            severity="blocker",
            message="manual-only exclusions are present",
            failure_message="one or more required exclusions are missing",
        ),
        _check(
            name="placeholder_count_matches_list",
            passed=_count_matches(
                validation,
                summary_key="placeholder_count",
                list_key="placeholders",
            ),
            severity="blocker",
            message="placeholder count matches placeholder list",
            failure_message="placeholder count does not match placeholder list",
        ),
        _check(
            name="sensitive_field_count_matches_list",
            passed=_count_matches(
                validation,
                summary_key="sensitive_field_count",
                list_key="sensitive_fields",
            ),
            severity="blocker",
            message="sensitive field count matches sensitive field list",
            failure_message=(
                "sensitive field count does not match sensitive field list"
            ),
        ),
        _check(
            name="blocked_validation_has_blocked_reasons",
            passed=_blocked_validation_has_reasons(validation),
            severity="blocker",
            message="blocked validation has blocked reasons",
            failure_message="blocked validation is missing blocked reasons",
        ),
        _check(
            name="ready_validation_has_no_placeholders",
            passed=(
                _summary_count(validation, "placeholder_count") == 0
                if validation.get("status") == "ready"
                else True
            ),
            severity="warning",
            message="ready validation has no placeholders",
            failure_message="ready validation still has placeholders",
        ),
        _check(
            name="ready_validation_has_no_sensitive_fields",
            passed=(
                _summary_count(validation, "sensitive_field_count") == 0
                if validation.get("status") == "ready"
                else True
            ),
            severity="warning",
            message="ready validation has no sensitive fields",
            failure_message="ready validation still has sensitive fields",
        ),
        _check(
            name="ready_validation_can_enter_pipeline",
            passed=(
                _summary_flag(
                    validation,
                    "can_enter_manual_backtest_pipeline",
                )
                if validation.get("status") == "ready"
                else True
            ),
            severity="warning",
            message="ready validation can enter manual backtest pipeline",
            failure_message=(
                "ready validation cannot enter manual backtest pipeline"
            ),
        ),
    ]

    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_audit_status(
            validation_status=str(validation.get("status", "needs_review")),
            checks=checks,
        ),
        "summary": _summarize_checks(checks),
        "checks": checks,
        "explicit_exclusions": list(validation.get("explicit_exclusions", [])),
    }


def build_quantconnect_manual_result_source_validation_health_report(
    validation: Mapping[str, Any],
) -> dict[str, Any]:
    validation_status = str(validation.get("status", "needs_review"))
    summary = _as_mapping(validation.get("summary"))

    indicators = {
        "validation_status": validation_status,
        "source_schema_version": summary.get("source_schema_version"),
        "source_type": summary.get("source_type"),
        "backtest_id": summary.get("backtest_id"),
        "project_name": summary.get("project_name"),
        "backtest_name": summary.get("backtest_name"),
        "strategy_count": _safe_int(summary.get("strategy_count")),
        "symbol_count": _safe_int(summary.get("symbol_count")),
        "manifest_strategy_count": _safe_int(
            summary.get("manifest_strategy_count")
        ),
        "manifest_symbol_count": _safe_int(
            summary.get("manifest_symbol_count")
        ),
        "placeholder_count": _safe_int(summary.get("placeholder_count")),
        "sensitive_field_count": _safe_int(
            summary.get("sensitive_field_count")
        ),
        "check_count": _safe_int(summary.get("check_count")),
        "passed_check_count": _safe_int(summary.get("passed_check_count")),
        "warning_check_count": _safe_int(summary.get("warning_check_count")),
        "failed_check_count": _safe_int(summary.get("failed_check_count")),
        "blocked_reason_count": _safe_int(
            summary.get("blocked_reason_count")
        ),
        "warning_count": _safe_int(summary.get("warning_count")),
        "can_enter_manual_backtest_pipeline": bool(
            summary.get("can_enter_manual_backtest_pipeline")
        ),
    }

    return {
        "schema_version": HEALTH_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_health_status(validation_status),
        "indicators": indicators,
        "recommendations": _build_health_recommendations(indicators),
        "explicit_exclusions": list(validation.get("explicit_exclusions", [])),
    }


def _build_operation_record(
    *,
    validation: Mapping[str, Any],
    audit_report: Mapping[str, Any],
    health_report: Mapping[str, Any],
    event_log_path: Path | None,
) -> dict[str, Any]:
    summary = _as_mapping(validation.get("summary"))

    return {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "operation_id": _build_operation_id(summary),
        "status": validation.get("status", "needs_review"),
        "summary": {
            "validation_status": validation.get("status", "needs_review"),
            "audit_status": audit_report.get("status", "needs_review"),
            "health_status": health_report.get("status", "degraded"),
            "backtest_id": summary.get("backtest_id"),
            "project_name": summary.get("project_name"),
            "backtest_name": summary.get("backtest_name"),
            "strategy_count": _safe_int(summary.get("strategy_count")),
            "symbol_count": _safe_int(summary.get("symbol_count")),
            "manifest_strategy_count": _safe_int(
                summary.get("manifest_strategy_count")
            ),
            "manifest_symbol_count": _safe_int(
                summary.get("manifest_symbol_count")
            ),
            "placeholder_count": _safe_int(summary.get("placeholder_count")),
            "sensitive_field_count": _safe_int(
                summary.get("sensitive_field_count")
            ),
            "check_count": _safe_int(summary.get("check_count")),
            "passed_check_count": _safe_int(
                summary.get("passed_check_count")
            ),
            "warning_check_count": _safe_int(
                summary.get("warning_check_count")
            ),
            "failed_check_count": _safe_int(
                summary.get("failed_check_count")
            ),
            "blocked_reason_count": _safe_int(
                summary.get("blocked_reason_count")
            ),
            "warning_count": _safe_int(summary.get("warning_count")),
            "can_enter_manual_backtest_pipeline": bool(
                summary.get("can_enter_manual_backtest_pipeline")
            ),
        },
        "event_log_path": str(event_log_path) if event_log_path else None,
        "explicit_exclusions": list(validation.get("explicit_exclusions", [])),
    }


def _build_event(
    *,
    validation: Mapping[str, Any],
    event_type: str,
    sequence: int,
) -> dict[str, Any]:
    summary = _as_mapping(validation.get("summary"))

    return {
        "schema_version": EVENT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "event_type": event_type,
        "sequence": sequence,
        "status": validation.get("status", "needs_review"),
        "summary": {
            "validation_status": validation.get("status", "needs_review"),
            "backtest_id": summary.get("backtest_id"),
            "project_name": summary.get("project_name"),
            "strategy_count": _safe_int(summary.get("strategy_count")),
            "symbol_count": _safe_int(summary.get("symbol_count")),
            "placeholder_count": _safe_int(summary.get("placeholder_count")),
            "sensitive_field_count": _safe_int(
                summary.get("sensitive_field_count")
            ),
            "failed_check_count": _safe_int(
                summary.get("failed_check_count")
            ),
            "warning_check_count": _safe_int(
                summary.get("warning_check_count")
            ),
            "can_enter_manual_backtest_pipeline": bool(
                summary.get("can_enter_manual_backtest_pipeline")
            ),
        },
        "explicit_exclusions": list(validation.get("explicit_exclusions", [])),
    }


def _write_jsonl_event_log(
    path: Path,
    events: list[Mapping[str, Any]],
) -> None:
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

    return {
        "name": name,
        "status": "failed" if severity == "blocker" else "warning",
        "severity": severity,
        "message": failure_message,
    }


def _summarize_checks(checks: list[Mapping[str, Any]]) -> dict[str, int]:
    return {
        "passed_count": sum(
            1 for check in checks if check.get("status") == "passed"
        ),
        "warning_count": sum(
            1 for check in checks if check.get("status") == "warning"
        ),
        "failed_count": sum(
            1 for check in checks if check.get("status") == "failed"
        ),
        "check_count": len(checks),
    }


def _classify_audit_status(
    *,
    validation_status: str,
    checks: list[Mapping[str, Any]],
) -> str:
    if any(check.get("status") == "failed" for check in checks):
        return "blocked"

    if validation_status == "blocked":
        return "blocked"

    if validation_status == "needs_review":
        return "needs_review"

    if any(check.get("status") == "warning" for check in checks):
        return "needs_review"

    return "ready"


def _classify_health_status(validation_status: str) -> str:
    if validation_status == "ready":
        return "healthy"

    if validation_status == "blocked":
        return "blocked"

    return "degraded"


def _build_health_recommendations(
    indicators: Mapping[str, Any],
) -> list[str]:
    recommendations: list[str] = []

    if _safe_int(indicators.get("placeholder_count")) > 0:
        recommendations.append(
            "replace all REPLACE_WITH placeholders before running pipeline"
        )

    if _safe_int(indicators.get("sensitive_field_count")) > 0:
        recommendations.append(
            "remove credential-like fields before running pipeline"
        )

    if _safe_int(indicators.get("failed_check_count")) > 0:
        recommendations.append(
            "resolve failed validation checks before running pipeline"
        )

    if _safe_int(indicators.get("warning_check_count")) > 0:
        recommendations.append(
            "review validation warnings before running pipeline"
        )

    if _safe_int(indicators.get("strategy_count")) == 0:
        recommendations.append("add strategy IDs before running pipeline")

    if _safe_int(indicators.get("symbol_count")) == 0:
        recommendations.append("add symbols before running pipeline")

    if (
        indicators.get("validation_status") == "ready"
        and indicators.get("can_enter_manual_backtest_pipeline")
    ):
        recommendations.append(
            "QuantConnect manual result source is ready for pipeline"
        )

    if not recommendations:
        recommendations.append("no health actions required")

    return sorted(set(recommendations))


def _has_required_exclusions(validation: Mapping[str, Any]) -> bool:
    required = {
        "quantconnect_api_calls",
        "broker_api_calls",
        "order_routing",
        "order_submission",
        "fills",
        "live_execution",
        "local_fill_simulation",
        "local_slippage_modeling",
        "external_data_warehouse_access",
    }

    exclusions = validation.get("explicit_exclusions")

    if not isinstance(exclusions, list):
        return False

    return required.issubset({str(item) for item in exclusions})


def _count_matches(
    validation: Mapping[str, Any],
    *,
    summary_key: str,
    list_key: str,
) -> bool:
    summary = _as_mapping(validation.get("summary"))
    values = validation.get(list_key)

    if not isinstance(values, list):
        return False

    return len(values) == _safe_int(summary.get(summary_key))


def _blocked_validation_has_reasons(validation: Mapping[str, Any]) -> bool:
    if validation.get("status") != "blocked":
        return True

    blocked_reasons = validation.get("blocked_reasons")

    return isinstance(blocked_reasons, list) and len(blocked_reasons) > 0


def _summary_flag(validation: Mapping[str, Any], key: str) -> bool:
    summary = _as_mapping(validation.get("summary"))

    return bool(summary.get(key))


def _summary_count(validation: Mapping[str, Any], key: str) -> int:
    summary = _as_mapping(validation.get("summary"))

    return _safe_int(summary.get(key))


def _build_operation_id(summary: Mapping[str, Any]) -> str:
    backtest_id = summary.get("backtest_id") or "manual_result_source"

    return f"{OPERATION_TYPE}::{backtest_id}"


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
