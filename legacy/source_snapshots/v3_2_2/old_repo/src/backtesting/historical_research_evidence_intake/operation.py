from __future__ import annotations

import json
from os import PathLike
from pathlib import Path
from typing import Any, Mapping

from src.backtesting.historical_research_evidence_intake.builder import (
    build_historical_research_evidence_intake,
)


OPERATION_SCHEMA_VERSION = "historical_research_evidence_intake_operation.v1"
EVENT_SCHEMA_VERSION = "historical_research_evidence_intake_operation_event.v1"
AUDIT_SCHEMA_VERSION = "historical_research_evidence_intake_audit.v1"
HEALTH_SCHEMA_VERSION = "historical_research_evidence_intake_health.v1"

OPERATION_TYPE = "historical_research_evidence_intake_operation"


def run_historical_research_evidence_intake_operation(
    source: Any,
    *,
    event_log_path: str | PathLike[str] | None = None,
) -> dict[str, Any]:
    """Run a deterministic historical research evidence intake operation.

    This operation does not call QuantConnect, brokers, market-data services,
    order-routing systems, live-trading APIs, fill engines, slippage engines,
    or external data warehouses. It only wraps an existing local historical
    research evidence input with operation, audit, and health artifacts.
    """

    intake_bundle = build_historical_research_evidence_intake(source)
    audit_report = build_historical_research_evidence_intake_audit_report(
        intake_bundle
    )
    health_report = build_historical_research_evidence_intake_health_report(
        intake_bundle
    )

    events = [
        _build_event(
            intake_bundle=intake_bundle,
            event_type="historical_research_evidence_intake_operation_started",
            sequence=1,
        ),
        _build_event(
            intake_bundle=intake_bundle,
            event_type="historical_research_evidence_intake_operation_completed",
            sequence=2,
        ),
    ]

    normalized_log_path = _normalize_event_log_path(event_log_path)
    if normalized_log_path is not None:
        _write_jsonl_event_log(normalized_log_path, events)

    operation_record = _build_operation_record(
        intake_bundle=intake_bundle,
        audit_report=audit_report,
        health_report=health_report,
        event_log_path=normalized_log_path,
    )

    return {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": intake_bundle["status"],
        "operation_record": operation_record,
        "audit_report": audit_report,
        "health_report": health_report,
        "intake_bundle": intake_bundle,
        "events": events,
        "event_log_path": str(normalized_log_path) if normalized_log_path else None,
        "explicit_exclusions": list(intake_bundle.get("explicit_exclusions", [])),
    }


def build_historical_research_evidence_intake_audit_report(
    intake_bundle: Mapping[str, Any],
) -> dict[str, Any]:
    ready_evidence = _as_list(intake_bundle.get("ready_evidence"))
    needs_review_evidence = _as_list(intake_bundle.get("needs_review_evidence"))
    blocked_evidence = _as_list(intake_bundle.get("blocked_evidence"))

    checks = [
        _check(
            name="intake_schema_version_present",
            passed=bool(intake_bundle.get("schema_version")),
            severity="blocker",
            message="intake schema version is present",
            failure_message="intake schema version is missing",
        ),
        _check(
            name="intake_type_is_normalized_historical_research_evidence_intake",
            passed=intake_bundle.get("intake_type")
            == "normalized_historical_research_evidence_intake",
            severity="blocker",
            message="intake type is normalized historical research evidence intake",
            failure_message="unexpected intake type detected",
        ),
        _check(
            name="explicit_exclusions_present",
            passed=_has_required_exclusions(intake_bundle),
            severity="blocker",
            message="manual-only exclusions are present",
            failure_message="one or more required manual-only exclusions are missing",
        ),
        _check(
            name="evidence_count_matches_summary",
            passed=_evidence_count_matches_summary(intake_bundle),
            severity="blocker",
            message="evidence count matches intake summary",
            failure_message="evidence count does not match intake summary",
        ),
        _check(
            name="ready_intake_has_ready_evidence",
            passed=len(ready_evidence) > 0
            if intake_bundle.get("status") == "ready"
            else True,
            severity="blocker",
            message="ready intake has ready evidence",
            failure_message="ready intake is missing ready evidence",
        ),
        _check(
            name="ready_evidence_has_expected_payload_type",
            passed=_evidence_has_payload_type(
                ready_evidence,
                "historical_research_evidence",
            ),
            severity="blocker",
            message="ready evidence has expected intake payload type",
            failure_message="one or more ready evidence payloads have unexpected type",
        ),
        _check(
            name="ready_evidence_has_backtest_id",
            passed=_evidence_has_backtest_id(ready_evidence)
            if intake_bundle.get("status") == "ready"
            else True,
            severity="warning",
            message="ready evidence has backtest ids",
            failure_message="one or more ready evidence payloads are missing backtest ids",
        ),
        _check(
            name="ready_evidence_has_decision_events",
            passed=_evidence_has_positive_count(
                ready_evidence,
                "decision_event_count",
            )
            if intake_bundle.get("status") == "ready"
            else True,
            severity="warning",
            message="ready evidence has decision events",
            failure_message="one or more ready evidence payloads are missing decision events",
        ),
        _check(
            name="ready_evidence_has_performance_metrics",
            passed=_evidence_has_positive_count(
                ready_evidence,
                "performance_metric_count",
            )
            if intake_bundle.get("status") == "ready"
            else True,
            severity="warning",
            message="ready evidence has performance metrics",
            failure_message="one or more ready evidence payloads are missing performance metrics",
        ),
        _check(
            name="needs_review_evidence_is_separated",
            passed=len(needs_review_evidence) == 0
            if intake_bundle.get("status") == "ready"
            else True,
            severity="warning",
            message="needs-review evidence is separated",
            failure_message="ready intake contains needs-review evidence",
        ),
        _check(
            name="blocked_intake_has_reason",
            passed=_blocked_intake_has_reason(intake_bundle),
            severity="warning",
            message="blocked intake reason handling is valid",
            failure_message="blocked intake is missing blocked reasons",
        ),
    ]

    audit_summary = _summarize_checks(checks)

    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_audit_status(
            intake_status=str(intake_bundle.get("status", "needs_review")),
            checks=checks,
        ),
        "summary": audit_summary,
        "checks": checks,
        "evidence_counts": {
            "ready": len(ready_evidence),
            "needs_review": len(needs_review_evidence),
            "blocked": len(blocked_evidence),
        },
        "explicit_exclusions": list(intake_bundle.get("explicit_exclusions", [])),
    }


def build_historical_research_evidence_intake_health_report(
    intake_bundle: Mapping[str, Any],
) -> dict[str, Any]:
    intake_status = str(intake_bundle.get("status", "needs_review"))
    summary = _as_mapping(intake_bundle.get("summary"))

    indicators = {
        "intake_status": intake_status,
        "source_input_status": summary.get("source_input_status"),
        "source_adapter_type": summary.get("source_adapter_type"),
        "backtest_id": summary.get("backtest_id"),
        "ready_evidence_count": _safe_int(summary.get("ready_evidence_count")),
        "needs_review_evidence_count": _safe_int(
            summary.get("needs_review_evidence_count")
        ),
        "blocked_evidence_count": _safe_int(summary.get("blocked_evidence_count")),
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
        "status": _classify_health_status(intake_status),
        "indicators": indicators,
        "recommendations": recommendations,
        "explicit_exclusions": list(intake_bundle.get("explicit_exclusions", [])),
    }


def _build_operation_record(
    *,
    intake_bundle: Mapping[str, Any],
    audit_report: Mapping[str, Any],
    health_report: Mapping[str, Any],
    event_log_path: Path | None,
) -> dict[str, Any]:
    summary = _as_mapping(intake_bundle.get("summary"))
    operation_id = _build_operation_id(summary)

    return {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "operation_id": operation_id,
        "status": intake_bundle.get("status", "needs_review"),
        "summary": {
            "source_input_status": summary.get("source_input_status", "needs_review"),
            "source_adapter_type": summary.get("source_adapter_type"),
            "backtest_id": summary.get("backtest_id"),
            "intake_status": intake_bundle.get("status", "needs_review"),
            "audit_status": audit_report.get("status", "needs_review"),
            "health_status": health_report.get("status", "degraded"),
            "ready_evidence_count": _safe_int(summary.get("ready_evidence_count")),
            "needs_review_evidence_count": _safe_int(
                summary.get("needs_review_evidence_count")
            ),
            "blocked_evidence_count": _safe_int(summary.get("blocked_evidence_count")),
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
        "explicit_exclusions": list(intake_bundle.get("explicit_exclusions", [])),
    }


def _build_event(
    *,
    intake_bundle: Mapping[str, Any],
    event_type: str,
    sequence: int,
) -> dict[str, Any]:
    summary = _as_mapping(intake_bundle.get("summary"))

    return {
        "schema_version": EVENT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "event_type": event_type,
        "sequence": sequence,
        "status": intake_bundle.get("status", "needs_review"),
        "summary": {
            "source_input_status": summary.get("source_input_status", "needs_review"),
            "backtest_id": summary.get("backtest_id"),
            "intake_status": intake_bundle.get("status", "needs_review"),
            "ready_evidence_count": _safe_int(summary.get("ready_evidence_count")),
            "needs_review_evidence_count": _safe_int(
                summary.get("needs_review_evidence_count")
            ),
            "blocked_evidence_count": _safe_int(summary.get("blocked_evidence_count")),
            "decision_event_count": _safe_int(summary.get("decision_event_count")),
            "performance_metric_count": _safe_int(
                summary.get("performance_metric_count")
            ),
            "warning_count": _safe_int(summary.get("warning_count")),
            "blocked_reason_count": _safe_int(summary.get("blocked_reason_count")),
        },
        "explicit_exclusions": list(intake_bundle.get("explicit_exclusions", [])),
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
    intake_status: str,
    checks: list[Mapping[str, Any]],
) -> str:
    if any(check.get("status") == "failed" for check in checks):
        return "blocked"

    if intake_status == "blocked":
        return "blocked"

    if intake_status == "needs_review":
        return "needs_review"

    if any(check.get("status") == "warning" for check in checks):
        return "needs_review"

    return "ready"


def _classify_health_status(intake_status: str) -> str:
    if intake_status == "ready":
        return "healthy"
    if intake_status == "blocked":
        return "blocked"
    return "degraded"


def _build_health_recommendations(indicators: Mapping[str, Any]) -> list[str]:
    recommendations: list[str] = []

    if _safe_int(indicators.get("ready_evidence_count")) == 0 and indicators.get(
        "intake_status"
    ) == "ready":
        recommendations.append("add ready historical research evidence")

    if _safe_int(indicators.get("needs_review_evidence_count")) > 0:
        recommendations.append("review needs-review historical research evidence")

    if _safe_int(indicators.get("blocked_evidence_count")) > 0:
        recommendations.append("resolve blocked historical research evidence")

    if _safe_int(indicators.get("decision_event_count")) == 0:
        recommendations.append("include decision evidence before research review")

    if _safe_int(indicators.get("performance_metric_count")) == 0:
        recommendations.append("include performance evidence before research review")

    if _safe_int(indicators.get("blocked_reason_count")) > 0:
        recommendations.append("resolve blocked reasons before evidence intake promotion")

    if indicators.get("intake_status") == "ready":
        recommendations.append("historical research evidence intake is ready")

    if not recommendations:
        recommendations.append("no health actions required")

    return sorted(set(recommendations))


def _has_required_exclusions(intake_bundle: Mapping[str, Any]) -> bool:
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

    exclusions = intake_bundle.get("explicit_exclusions")
    if not isinstance(exclusions, list):
        return False

    return required.issubset({str(item) for item in exclusions})


def _evidence_count_matches_summary(intake_bundle: Mapping[str, Any]) -> bool:
    summary = _as_mapping(intake_bundle.get("summary"))

    ready_evidence = _as_list(intake_bundle.get("ready_evidence"))
    needs_review_evidence = _as_list(intake_bundle.get("needs_review_evidence"))
    blocked_evidence = _as_list(intake_bundle.get("blocked_evidence"))

    return (
        len(ready_evidence) == _safe_int(summary.get("ready_evidence_count"))
        and len(needs_review_evidence)
        == _safe_int(summary.get("needs_review_evidence_count"))
        and len(blocked_evidence)
        == _safe_int(summary.get("blocked_evidence_count"))
    )


def _evidence_has_payload_type(evidence: list[Any], payload_type: str) -> bool:
    return all(
        isinstance(item, Mapping) and item.get("intake_payload_type") == payload_type
        for item in evidence
    )


def _evidence_has_backtest_id(evidence: list[Any]) -> bool:
    return all(
        isinstance(item, Mapping) and bool(item.get("backtest_id"))
        for item in evidence
    )


def _evidence_has_positive_count(evidence: list[Any], key: str) -> bool:
    return all(
        isinstance(item, Mapping) and _safe_int(item.get(key)) > 0
        for item in evidence
    )


def _blocked_intake_has_reason(intake_bundle: Mapping[str, Any]) -> bool:
    if intake_bundle.get("status") != "blocked":
        return True

    blocked_reasons = intake_bundle.get("blocked_reasons")
    return isinstance(blocked_reasons, list) and len(blocked_reasons) > 0


def _build_operation_id(summary: Mapping[str, Any]) -> str:
    backtest_id = summary.get("backtest_id") or "historical_research_evidence_intake"
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
