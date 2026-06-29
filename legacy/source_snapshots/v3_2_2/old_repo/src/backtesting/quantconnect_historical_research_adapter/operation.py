from __future__ import annotations

import json
from os import PathLike
from pathlib import Path
from typing import Any, Mapping

from src.backtesting.quantconnect_historical_research_adapter.builder import (
    build_quantconnect_historical_research_input,
)


OPERATION_SCHEMA_VERSION = "quantconnect_historical_research_adapter_operation.v1"
EVENT_SCHEMA_VERSION = "quantconnect_historical_research_adapter_operation_event.v1"
AUDIT_SCHEMA_VERSION = "quantconnect_historical_research_adapter_audit.v1"
HEALTH_SCHEMA_VERSION = "quantconnect_historical_research_adapter_health.v1"

OPERATION_TYPE = "quantconnect_historical_research_adapter_operation"


def run_quantconnect_historical_research_adapter_operation(
    final_summary_result: Any,
    *,
    event_log_path: str | PathLike[str] | None = None,
) -> dict[str, Any]:
    """Run a deterministic QuantConnect historical research adapter operation.

    This operation does not call QuantConnect, brokers, market-data services,
    order-routing systems, live-trading APIs, fill engines, slippage engines,
    or external data warehouses. It only wraps an existing local QuantConnect
    final summary with operation, audit, and health artifacts.
    """

    research_input = build_quantconnect_historical_research_input(final_summary_result)
    audit_report = build_quantconnect_historical_research_adapter_audit_report(
        research_input
    )
    health_report = build_quantconnect_historical_research_adapter_health_report(
        research_input
    )

    events = [
        _build_event(
            research_input=research_input,
            event_type="quantconnect_historical_research_adapter_operation_started",
            sequence=1,
        ),
        _build_event(
            research_input=research_input,
            event_type="quantconnect_historical_research_adapter_operation_completed",
            sequence=2,
        ),
    ]

    normalized_log_path = _normalize_event_log_path(event_log_path)
    if normalized_log_path is not None:
        _write_jsonl_event_log(normalized_log_path, events)

    operation_record = _build_operation_record(
        research_input=research_input,
        audit_report=audit_report,
        health_report=health_report,
        event_log_path=normalized_log_path,
    )

    return {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": research_input["status"],
        "operation_record": operation_record,
        "audit_report": audit_report,
        "health_report": health_report,
        "research_input": research_input,
        "events": events,
        "event_log_path": str(normalized_log_path) if normalized_log_path else None,
        "explicit_exclusions": list(research_input.get("explicit_exclusions", [])),
    }


def build_quantconnect_historical_research_adapter_audit_report(
    research_input: Mapping[str, Any],
) -> dict[str, Any]:
    ready_payloads = _as_list(research_input.get("ready_payloads"))
    needs_review_payloads = _as_list(research_input.get("needs_review_payloads"))
    blocked_payloads = _as_list(research_input.get("blocked_payloads"))

    checks = [
        _check(
            name="research_input_schema_version_present",
            passed=bool(research_input.get("schema_version")),
            severity="blocker",
            message="research input schema version is present",
            failure_message="research input schema version is missing",
        ),
        _check(
            name="adapter_type_is_quantconnect_final_summary_to_historical_research_evidence",
            passed=research_input.get("adapter_type")
            == "quantconnect_final_summary_to_historical_research_evidence",
            severity="blocker",
            message="adapter type is QuantConnect final summary to historical research evidence",
            failure_message="unexpected adapter type detected",
        ),
        _check(
            name="explicit_exclusions_present",
            passed=_has_required_exclusions(research_input),
            severity="blocker",
            message="manual-only exclusions are present",
            failure_message="one or more required manual-only exclusions are missing",
        ),
        _check(
            name="payload_count_matches_summary",
            passed=_payload_count_matches_summary(research_input),
            severity="blocker",
            message="payload count matches adapter summary",
            failure_message="payload count does not match adapter summary",
        ),
        _check(
            name="ready_input_has_ready_payload",
            passed=len(ready_payloads) > 0
            if research_input.get("status") == "ready"
            else True,
            severity="blocker",
            message="ready research input has a ready payload",
            failure_message="ready research input is missing ready payload",
        ),
        _check(
            name="ready_payloads_have_historical_research_type",
            passed=_payloads_have_type(
                ready_payloads,
                "historical_research_backtest_evidence",
            ),
            severity="blocker",
            message="ready payloads have historical research evidence type",
            failure_message="one or more ready payloads have unexpected type",
        ),
        _check(
            name="ready_payloads_have_backtest_id",
            passed=_payloads_have_backtest_id(ready_payloads)
            if research_input.get("status") == "ready"
            else True,
            severity="warning",
            message="ready payloads have backtest ids",
            failure_message="one or more ready payloads are missing backtest ids",
        ),
        _check(
            name="ready_payloads_have_decision_evidence",
            passed=_payloads_have_positive_count(ready_payloads, "decision_event_count")
            if research_input.get("status") == "ready"
            else True,
            severity="warning",
            message="ready payloads have decision evidence",
            failure_message="one or more ready payloads are missing decision evidence",
        ),
        _check(
            name="ready_payloads_have_performance_evidence",
            passed=_payloads_have_positive_count(
                ready_payloads,
                "performance_metric_count",
            )
            if research_input.get("status") == "ready"
            else True,
            severity="warning",
            message="ready payloads have performance evidence",
            failure_message="one or more ready payloads are missing performance evidence",
        ),
        _check(
            name="blocked_input_has_reason",
            passed=_blocked_input_has_reason(research_input),
            severity="warning",
            message="blocked research input reason handling is valid",
            failure_message="blocked research input is missing blocked reasons",
        ),
    ]

    audit_summary = _summarize_checks(checks)

    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_audit_status(
            input_status=str(research_input.get("status", "needs_review")),
            checks=checks,
        ),
        "summary": audit_summary,
        "checks": checks,
        "payload_counts": {
            "ready": len(ready_payloads),
            "needs_review": len(needs_review_payloads),
            "blocked": len(blocked_payloads),
        },
        "explicit_exclusions": list(research_input.get("explicit_exclusions", [])),
    }


def build_quantconnect_historical_research_adapter_health_report(
    research_input: Mapping[str, Any],
) -> dict[str, Any]:
    input_status = str(research_input.get("status", "needs_review"))
    summary = _as_mapping(research_input.get("summary"))

    indicators = {
        "input_status": input_status,
        "source_final_status": summary.get("source_final_status"),
        "backtest_id": summary.get("backtest_id"),
        "ready_payload_count": _safe_int(summary.get("ready_payload_count")),
        "needs_review_payload_count": _safe_int(
            summary.get("needs_review_payload_count")
        ),
        "blocked_payload_count": _safe_int(summary.get("blocked_payload_count")),
        "decision_event_count": _safe_int(summary.get("decision_event_count")),
        "performance_metric_count": _safe_int(summary.get("performance_metric_count")),
        "expected_strategy_count": _safe_int(summary.get("expected_strategy_count")),
        "observed_strategy_count": _safe_int(summary.get("observed_strategy_count")),
        "expected_symbol_count": _safe_int(summary.get("expected_symbol_count")),
        "observed_symbol_count": _safe_int(summary.get("observed_symbol_count")),
        "warning_count": _safe_int(summary.get("warning_count")),
        "blocked_reason_count": _safe_int(summary.get("blocked_reason_count")),
    }

    recommendations = _build_health_recommendations(indicators)

    return {
        "schema_version": HEALTH_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_health_status(input_status),
        "indicators": indicators,
        "recommendations": recommendations,
        "explicit_exclusions": list(research_input.get("explicit_exclusions", [])),
    }


def _build_operation_record(
    *,
    research_input: Mapping[str, Any],
    audit_report: Mapping[str, Any],
    health_report: Mapping[str, Any],
    event_log_path: Path | None,
) -> dict[str, Any]:
    summary = _as_mapping(research_input.get("summary"))
    operation_id = _build_operation_id(summary)

    return {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "operation_id": operation_id,
        "status": research_input.get("status", "needs_review"),
        "summary": {
            "source_final_status": summary.get("source_final_status", "needs_review"),
            "backtest_id": summary.get("backtest_id"),
            "input_status": research_input.get("status", "needs_review"),
            "audit_status": audit_report.get("status", "needs_review"),
            "health_status": health_report.get("status", "degraded"),
            "ready_payload_count": _safe_int(summary.get("ready_payload_count")),
            "needs_review_payload_count": _safe_int(
                summary.get("needs_review_payload_count")
            ),
            "blocked_payload_count": _safe_int(summary.get("blocked_payload_count")),
            "decision_event_count": _safe_int(summary.get("decision_event_count")),
            "performance_metric_count": _safe_int(
                summary.get("performance_metric_count")
            ),
            "expected_strategy_count": _safe_int(
                summary.get("expected_strategy_count")
            ),
            "observed_strategy_count": _safe_int(
                summary.get("observed_strategy_count")
            ),
            "expected_symbol_count": _safe_int(summary.get("expected_symbol_count")),
            "observed_symbol_count": _safe_int(summary.get("observed_symbol_count")),
            "warning_count": _safe_int(summary.get("warning_count")),
            "blocked_reason_count": _safe_int(summary.get("blocked_reason_count")),
        },
        "event_log_path": str(event_log_path) if event_log_path else None,
        "explicit_exclusions": list(research_input.get("explicit_exclusions", [])),
    }


def _build_event(
    *,
    research_input: Mapping[str, Any],
    event_type: str,
    sequence: int,
) -> dict[str, Any]:
    summary = _as_mapping(research_input.get("summary"))

    return {
        "schema_version": EVENT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "event_type": event_type,
        "sequence": sequence,
        "status": research_input.get("status", "needs_review"),
        "summary": {
            "source_final_status": summary.get("source_final_status", "needs_review"),
            "backtest_id": summary.get("backtest_id"),
            "input_status": research_input.get("status", "needs_review"),
            "ready_payload_count": _safe_int(summary.get("ready_payload_count")),
            "needs_review_payload_count": _safe_int(
                summary.get("needs_review_payload_count")
            ),
            "blocked_payload_count": _safe_int(summary.get("blocked_payload_count")),
            "decision_event_count": _safe_int(summary.get("decision_event_count")),
            "performance_metric_count": _safe_int(
                summary.get("performance_metric_count")
            ),
            "warning_count": _safe_int(summary.get("warning_count")),
            "blocked_reason_count": _safe_int(summary.get("blocked_reason_count")),
        },
        "explicit_exclusions": list(research_input.get("explicit_exclusions", [])),
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
    input_status: str,
    checks: list[Mapping[str, Any]],
) -> str:
    if any(check.get("status") == "failed" for check in checks):
        return "blocked"

    if input_status == "blocked":
        return "blocked"

    if input_status == "needs_review":
        return "needs_review"

    if any(check.get("status") == "warning" for check in checks):
        return "needs_review"

    return "ready"


def _classify_health_status(input_status: str) -> str:
    if input_status == "ready":
        return "healthy"
    if input_status == "blocked":
        return "blocked"
    return "degraded"


def _build_health_recommendations(indicators: Mapping[str, Any]) -> list[str]:
    recommendations: list[str] = []

    if _safe_int(indicators.get("ready_payload_count")) == 0 and indicators.get(
        "input_status"
    ) == "ready":
        recommendations.append("add ready historical research evidence payload")

    if _safe_int(indicators.get("needs_review_payload_count")) > 0:
        recommendations.append("review historical research evidence warnings")

    if _safe_int(indicators.get("blocked_payload_count")) > 0:
        recommendations.append("resolve blocked historical research evidence")

    if _safe_int(indicators.get("decision_event_count")) == 0:
        recommendations.append("include SignalForge decision evidence")

    if _safe_int(indicators.get("performance_metric_count")) == 0:
        recommendations.append("include QuantConnect performance evidence")

    if _safe_int(indicators.get("blocked_reason_count")) > 0:
        recommendations.append("resolve blocked reasons before historical research")

    if indicators.get("input_status") == "ready":
        recommendations.append("historical research input is ready")

    if not recommendations:
        recommendations.append("no health actions required")

    return sorted(set(recommendations))


def _has_required_exclusions(research_input: Mapping[str, Any]) -> bool:
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

    exclusions = research_input.get("explicit_exclusions")
    if not isinstance(exclusions, list):
        return False

    return required.issubset({str(item) for item in exclusions})


def _payload_count_matches_summary(research_input: Mapping[str, Any]) -> bool:
    summary = _as_mapping(research_input.get("summary"))
    ready_payloads = _as_list(research_input.get("ready_payloads"))
    needs_review_payloads = _as_list(research_input.get("needs_review_payloads"))
    blocked_payloads = _as_list(research_input.get("blocked_payloads"))

    return (
        len(ready_payloads) == _safe_int(summary.get("ready_payload_count"))
        and len(needs_review_payloads)
        == _safe_int(summary.get("needs_review_payload_count"))
        and len(blocked_payloads) == _safe_int(summary.get("blocked_payload_count"))
    )


def _payloads_have_type(payloads: list[Any], payload_type: str) -> bool:
    return all(
        isinstance(payload, Mapping) and payload.get("payload_type") == payload_type
        for payload in payloads
    )


def _payloads_have_backtest_id(payloads: list[Any]) -> bool:
    return all(
        isinstance(payload, Mapping) and bool(payload.get("backtest_id"))
        for payload in payloads
    )


def _payloads_have_positive_count(payloads: list[Any], key: str) -> bool:
    return all(
        isinstance(payload, Mapping) and _safe_int(payload.get(key)) > 0
        for payload in payloads
    )


def _blocked_input_has_reason(research_input: Mapping[str, Any]) -> bool:
    if research_input.get("status") != "blocked":
        return True

    blocked_reasons = research_input.get("blocked_reasons")
    return isinstance(blocked_reasons, list) and len(blocked_reasons) > 0


def _build_operation_id(summary: Mapping[str, Any]) -> str:
    backtest_id = summary.get("backtest_id") or "quantconnect_historical_research_input"
    return f"{OPERATION_TYPE}::{backtest_id}"


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _safe_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
