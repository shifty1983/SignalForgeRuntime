from __future__ import annotations

import json
from os import PathLike
from pathlib import Path
from typing import Any, Mapping

from src.backtesting.quantconnect_manual_backtest_evidence_pipeline.builder import (
    STAGE_ORDER,
    StageFunction,
    build_quantconnect_manual_backtest_evidence_pipeline,
)


OPERATION_SCHEMA_VERSION = "quantconnect_manual_backtest_evidence_pipeline_operation.v1"
EVENT_SCHEMA_VERSION = "quantconnect_manual_backtest_evidence_pipeline_operation_event.v1"
AUDIT_SCHEMA_VERSION = "quantconnect_manual_backtest_evidence_pipeline_audit.v1"
HEALTH_SCHEMA_VERSION = "quantconnect_manual_backtest_evidence_pipeline_health.v1"

OPERATION_TYPE = "quantconnect_manual_backtest_evidence_pipeline_operation"


def run_quantconnect_manual_backtest_evidence_pipeline_operation(
    source: Any,
    *,
    stage_functions: Mapping[str, StageFunction] | None = None,
    event_log_path: str | PathLike[str] | None = None,
) -> dict[str, Any]:
    """Run the manual QuantConnect backtest evidence pipeline operation.

    This operation does not call QuantConnect, brokers, market-data services,
    order-routing systems, live-trading APIs, fill engines, slippage engines,
    or external data warehouses. It only wraps a local manual QuantConnect
    backtest result import pipeline with operation, audit, and health outputs.
    """

    pipeline_result = build_quantconnect_manual_backtest_evidence_pipeline(
        source,
        stage_functions=stage_functions,
    )
    audit_report = build_quantconnect_manual_backtest_evidence_pipeline_audit_report(
        pipeline_result
    )
    health_report = build_quantconnect_manual_backtest_evidence_pipeline_health_report(
        pipeline_result
    )

    events = [
        _build_event(
            pipeline_result=pipeline_result,
            event_type="quantconnect_manual_backtest_evidence_pipeline_operation_started",
            sequence=1,
        ),
        _build_event(
            pipeline_result=pipeline_result,
            event_type="quantconnect_manual_backtest_evidence_pipeline_operation_completed",
            sequence=2,
        ),
    ]

    normalized_log_path = _normalize_event_log_path(event_log_path)
    if normalized_log_path is not None:
        _write_jsonl_event_log(normalized_log_path, events)

    operation_record = _build_operation_record(
        pipeline_result=pipeline_result,
        audit_report=audit_report,
        health_report=health_report,
        event_log_path=normalized_log_path,
    )
    
    

    return {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": pipeline_result["status"],
        "operation_record": operation_record,
        "audit_report": audit_report,
        "health_report": health_report,
        "pipeline_result": pipeline_result,
        "final_summary": pipeline_result.get("final_summary", {}),
        "promotion_gate": pipeline_result.get("promotion_gate", {}),
        "promotion_handoff": pipeline_result.get("promotion_handoff", {}),
        "downstream_intake": pipeline_result.get("downstream_intake", {}),
        "events": events,
        "event_log_path": str(normalized_log_path) if normalized_log_path else None,
        "explicit_exclusions": list(pipeline_result.get("explicit_exclusions", [])),
    }


def build_quantconnect_manual_backtest_evidence_pipeline_audit_report(
    pipeline_result: Mapping[str, Any],
) -> dict[str, Any]:
    stage_statuses = _as_mapping(pipeline_result.get("stage_statuses"))
    final_summary = _as_mapping(pipeline_result.get("final_summary"))

    checks = [
        _check(
            name="pipeline_schema_version_present",
            passed=bool(pipeline_result.get("schema_version")),
            severity="blocker",
            message="pipeline schema version is present",
            failure_message="pipeline schema version is missing",
        ),
        _check(
            name="pipeline_type_is_quantconnect_manual_backtest_evidence_pipeline",
            passed=pipeline_result.get("pipeline_type")
            == "quantconnect_manual_backtest_evidence_pipeline",
            severity="blocker",
            message="pipeline type is QuantConnect manual backtest evidence pipeline",
            failure_message="unexpected pipeline type detected",
        ),
        _check(
            name="explicit_exclusions_present",
            passed=_has_required_exclusions(pipeline_result),
            severity="blocker",
            message="manual-only exclusions are present",
            failure_message="one or more required exclusions are missing",
        ),
        _check(
            name="stage_order_is_complete",
            passed=_stage_order_is_complete(pipeline_result),
            severity="blocker",
            message="pipeline stage order is complete",
            failure_message="pipeline stage order is incomplete",
        ),
        _check(
            name="stage_statuses_match_completed_stage_count",
            passed=_stage_statuses_match_completed_count(pipeline_result),
            severity="blocker",
            message="stage statuses match completed stage count",
            failure_message="stage statuses do not match completed stage count",
        ),
        _check(
            name="ready_pipeline_completed_all_stages",
            passed=len(stage_statuses) == len(STAGE_ORDER)
            if pipeline_result.get("status") == "ready"
            else True,
            severity="blocker",
            message="ready pipeline completed all stages",
            failure_message="ready pipeline did not complete all stages",
        ),
        _check(
            name="ready_pipeline_has_final_summary",
            passed=bool(final_summary)
            if pipeline_result.get("status") == "ready"
            else True,
            severity="blocker",
            message="ready pipeline has final summary",
            failure_message="ready pipeline is missing final summary",
        ),
        _check(
            name="ready_final_summary_has_ready_status",
            passed=final_summary.get("status") == "ready"
            if pipeline_result.get("status") == "ready"
            else True,
            severity="warning",
            message="ready pipeline final summary is ready",
            failure_message="ready pipeline final summary is not ready",
        ),
        _check(
            name="ready_pipeline_has_final_items",
            passed=_summary_positive_count(
                final_summary,
                "ready_final_item_count",
            )
            if pipeline_result.get("status") == "ready"
            else True,
            severity="warning",
            message="ready pipeline has ready final items",
            failure_message="ready pipeline is missing ready final items",
        ),
        _check(
            name="blocked_pipeline_has_reason",
            passed=_blocked_pipeline_has_reason(pipeline_result),
            severity="warning",
            message="blocked pipeline reason handling is valid",
            failure_message="blocked pipeline is missing blocked reasons",
        ),
    ]

    audit_summary = _summarize_checks(checks)

    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_audit_status(
            pipeline_status=str(pipeline_result.get("status", "needs_review")),
            checks=checks,
        ),
        "summary": audit_summary,
        "checks": checks,
        "stage_counts": {
            "expected": len(STAGE_ORDER),
            "completed": len(stage_statuses),
            "ready": sum(1 for status in stage_statuses.values() if status == "ready"),
            "needs_review": sum(
                1 for status in stage_statuses.values() if status == "needs_review"
            ),
            "blocked": sum(
                1 for status in stage_statuses.values() if status == "blocked"
            ),
        },
        "explicit_exclusions": list(pipeline_result.get("explicit_exclusions", [])),
    }


def build_quantconnect_manual_backtest_evidence_pipeline_health_report(
    pipeline_result: Mapping[str, Any],
) -> dict[str, Any]:
    pipeline_status = str(pipeline_result.get("status", "needs_review"))
    summary = _as_mapping(pipeline_result.get("summary"))

    indicators = {
        "pipeline_status": pipeline_status,
        "stage_count": _safe_int(summary.get("stage_count")),
        "completed_stage_count": _safe_int(summary.get("completed_stage_count")),
        "ready_stage_count": _safe_int(summary.get("ready_stage_count")),
        "needs_review_stage_count": _safe_int(
            summary.get("needs_review_stage_count")
        ),
        "blocked_stage_count": _safe_int(summary.get("blocked_stage_count")),
        "blocked_stage_name": summary.get("blocked_stage_name"),
        "final_status": summary.get("final_status"),
        "backtest_id": summary.get("backtest_id"),
        "ready_final_item_count": _safe_int(summary.get("ready_final_item_count")),
        "needs_review_final_item_count": _safe_int(
            summary.get("needs_review_final_item_count")
        ),
        "blocked_final_item_count": _safe_int(
            summary.get("blocked_final_item_count")
        ),
        "decision_event_count": _safe_int(summary.get("decision_event_count")),
        "performance_metric_count": _safe_int(summary.get("performance_metric_count")),
        "promotion_handoff_status": summary.get("promotion_handoff_status"),
        "promoted_item_count": _safe_int(summary.get("promoted_item_count")),
        "downstream_strategy_count": _safe_int(
            summary.get("downstream_strategy_count")
        ),
        "downstream_symbol_count": _safe_int(
            summary.get("downstream_symbol_count")
        ),
        "downstream_backtest_count": _safe_int(
            summary.get("downstream_backtest_count")
        ),
        "downstream_evidence_count": _safe_int(
            summary.get("downstream_evidence_count")
        ),
        "can_enter_downstream_historical_research": bool(
            summary.get("can_enter_downstream_historical_research")
        ),
        "downstream_intake_status": summary.get("downstream_intake_status"),
        "downstream_intake_item_count": _safe_int(
            summary.get("downstream_intake_item_count")
        ),
        "expected_value_ready_item_count": _safe_int(
            summary.get("expected_value_ready_item_count")
        ),
        "expected_value_needs_review_item_count": _safe_int(
            summary.get("expected_value_needs_review_item_count")
        ),
        "expected_value_blocked_item_count": _safe_int(
            summary.get("expected_value_blocked_item_count")
        ),
        "can_enter_expected_value_research": bool(
            summary.get("can_enter_expected_value_research")
        ),
        "can_enter_strategy_selection": bool(
            summary.get("can_enter_strategy_selection")
        ),
        "warning_count": _safe_int(summary.get("warning_count")),
        "blocked_reason_count": _safe_int(summary.get("blocked_reason_count")),
    }

    recommendations = _build_health_recommendations(indicators)

    return {
        "schema_version": HEALTH_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_health_status(pipeline_status),
        "indicators": indicators,
        "recommendations": recommendations,
        "explicit_exclusions": list(pipeline_result.get("explicit_exclusions", [])),
    }


def _build_operation_record(
    *,
    pipeline_result: Mapping[str, Any],
    audit_report: Mapping[str, Any],
    health_report: Mapping[str, Any],
    event_log_path: Path | None,
) -> dict[str, Any]:
    summary = _as_mapping(pipeline_result.get("summary"))
    operation_id = _build_operation_id(summary)

    return {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "operation_id": operation_id,
        "status": pipeline_result.get("status", "needs_review"),
        "summary": {
            "pipeline_status": pipeline_result.get("status", "needs_review"),
            "audit_status": audit_report.get("status", "needs_review"),
            "health_status": health_report.get("status", "degraded"),
            "stage_count": _safe_int(summary.get("stage_count")),
            "completed_stage_count": _safe_int(
                summary.get("completed_stage_count")
            ),
            "ready_stage_count": _safe_int(summary.get("ready_stage_count")),
            "needs_review_stage_count": _safe_int(
                summary.get("needs_review_stage_count")
            ),
            "blocked_stage_count": _safe_int(
                summary.get("blocked_stage_count")
            ),
            "blocked_stage_name": summary.get("blocked_stage_name"),
            "final_status": summary.get("final_status"),
            "promotion_gate_status": summary.get("promotion_gate_status"),
            "backtest_id": summary.get("backtest_id"),
            "ready_final_item_count": _safe_int(
                summary.get("ready_final_item_count")
            ),
            "needs_review_final_item_count": _safe_int(
                summary.get("needs_review_final_item_count")
            ),
            "blocked_final_item_count": _safe_int(
                summary.get("blocked_final_item_count")
            ),
            "promotable_evidence_count": _safe_int(
                summary.get("promotable_evidence_count")
            ),
            "promotion_needs_review_evidence_count": _safe_int(
                summary.get("promotion_needs_review_evidence_count")
            ),
            "promotion_blocked_evidence_count": _safe_int(
                summary.get("promotion_blocked_evidence_count")
            ),
            "decision_event_count": _safe_int(
                summary.get("decision_event_count")
            ),
            "performance_metric_count": _safe_int(
                summary.get("performance_metric_count")
            ),
            "promotion_handoff_status": summary.get("promotion_handoff_status"),
            "promoted_item_count": _safe_int(summary.get("promoted_item_count")),
            "downstream_strategy_count": _safe_int(
                summary.get("downstream_strategy_count")
            ),
            "downstream_symbol_count": _safe_int(
                summary.get("downstream_symbol_count")
            ),
            "downstream_backtest_count": _safe_int(
                summary.get("downstream_backtest_count")
            ),
            "downstream_evidence_count": _safe_int(
                summary.get("downstream_evidence_count")
            ),
            "can_enter_downstream_historical_research": bool(
                summary.get("can_enter_downstream_historical_research")
            ),
            "downstream_intake_status": summary.get("downstream_intake_status"),
            "downstream_intake_item_count": _safe_int(
                summary.get("downstream_intake_item_count")
            ),
            "expected_value_ready_item_count": _safe_int(
                summary.get("expected_value_ready_item_count")
            ),
            "expected_value_needs_review_item_count": _safe_int(
                summary.get("expected_value_needs_review_item_count")
            ),
            "expected_value_blocked_item_count": _safe_int(
                summary.get("expected_value_blocked_item_count")
            ),
            "can_enter_expected_value_research": bool(
                summary.get("can_enter_expected_value_research")
            ),
            "can_enter_strategy_selection": bool(
                summary.get("can_enter_strategy_selection")
            ),
            "warning_count": _safe_int(summary.get("warning_count")),
            "blocked_reason_count": _safe_int(
                summary.get("blocked_reason_count")
            ),
        },
        "event_log_path": str(event_log_path) if event_log_path else None,
        "explicit_exclusions": list(
            pipeline_result.get("explicit_exclusions", [])
        ),
    }


def _build_event(
    *,
    pipeline_result: Mapping[str, Any],
    event_type: str,
    sequence: int,
) -> dict[str, Any]:
    summary = _as_mapping(pipeline_result.get("summary"))

    return {
        "schema_version": EVENT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "event_type": event_type,
        "sequence": sequence,
        "status": pipeline_result.get("status", "needs_review"),
        "summary": {
            "pipeline_status": pipeline_result.get("status", "needs_review"),
            "completed_stage_count": _safe_int(summary.get("completed_stage_count")),
            "blocked_stage_name": summary.get("blocked_stage_name"),
            "final_status": summary.get("final_status"),
            "backtest_id": summary.get("backtest_id"),
            "ready_final_item_count": _safe_int(
                summary.get("ready_final_item_count")
            ),
            "needs_review_final_item_count": _safe_int(
                summary.get("needs_review_final_item_count")
            ),
            "blocked_final_item_count": _safe_int(
                summary.get("blocked_final_item_count")
            ),
            "promotion_handoff_status": summary.get("promotion_handoff_status"),
            "promoted_item_count": _safe_int(summary.get("promoted_item_count")),
            "downstream_strategy_count": _safe_int(
                summary.get("downstream_strategy_count")
            ),
            "downstream_symbol_count": _safe_int(
                summary.get("downstream_symbol_count")
            ),
            "downstream_backtest_count": _safe_int(
                summary.get("downstream_backtest_count")
            ),
            "downstream_evidence_count": _safe_int(
                summary.get("downstream_evidence_count")
            ),
            "can_enter_downstream_historical_research": bool(
                summary.get("can_enter_downstream_historical_research")
            ),
            "downstream_intake_status": summary.get("downstream_intake_status"),
            "downstream_intake_item_count": _safe_int(
                summary.get("downstream_intake_item_count")
            ),
            "expected_value_ready_item_count": _safe_int(
                summary.get("expected_value_ready_item_count")
            ),
            "expected_value_needs_review_item_count": _safe_int(
                summary.get("expected_value_needs_review_item_count")
            ),
            "expected_value_blocked_item_count": _safe_int(
                summary.get("expected_value_blocked_item_count")
            ),
            "can_enter_expected_value_research": bool(
                summary.get("can_enter_expected_value_research")
            ),
            "can_enter_strategy_selection": bool(
                summary.get("can_enter_strategy_selection")
            ),
            "warning_count": _safe_int(summary.get("warning_count")),
            "blocked_reason_count": _safe_int(summary.get("blocked_reason_count")),
        },
        "explicit_exclusions": list(pipeline_result.get("explicit_exclusions", [])),
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
    pipeline_status: str,
    checks: list[Mapping[str, Any]],
) -> str:
    if any(check.get("status") == "failed" for check in checks):
        return "blocked"

    if pipeline_status == "blocked":
        return "blocked"

    if pipeline_status == "needs_review":
        return "needs_review"

    if any(check.get("status") == "warning" for check in checks):
        return "needs_review"

    return "ready"


def _classify_health_status(pipeline_status: str) -> str:
    if pipeline_status == "ready":
        return "healthy"
    if pipeline_status == "blocked":
        return "blocked"
    return "degraded"


def _build_health_recommendations(indicators: Mapping[str, Any]) -> list[str]:
    recommendations: list[str] = []

    if _safe_int(indicators.get("completed_stage_count")) < _safe_int(
        indicators.get("stage_count")
    ):
        recommendations.append("complete all manual backtest evidence pipeline stages")

    if _safe_int(indicators.get("needs_review_stage_count")) > 0:
        recommendations.append("review needs-review pipeline stages")

    if _safe_int(indicators.get("blocked_stage_count")) > 0:
        recommendations.append("resolve blocked pipeline stage")

    if _safe_int(indicators.get("ready_final_item_count")) == 0 and indicators.get(
        "pipeline_status"
    ) == "ready":
        recommendations.append("add ready final evidence review items")

    if _safe_int(indicators.get("decision_event_count")) == 0:
        recommendations.append("include decision evidence before final pipeline review")

    if _safe_int(indicators.get("performance_metric_count")) == 0:
        recommendations.append(
            "include performance evidence before final pipeline review"
        )

    if _safe_int(indicators.get("blocked_reason_count")) > 0:
        recommendations.append("resolve blocked reasons before pipeline promotion")

    if indicators.get("pipeline_status") == "ready":
        recommendations.append("QuantConnect manual backtest evidence pipeline is ready")

    if not recommendations:
        recommendations.append("no health actions required")
        
    if indicators.get("pipeline_status") == "ready" and not indicators.get(
        "can_enter_downstream_historical_research"
    ):
        recommendations.append(
            "prepare downstream historical research handoff before promotion"
        )

    if (
        indicators.get("pipeline_status") == "ready"
        and _safe_int(indicators.get("promoted_item_count")) == 0
    ):
        recommendations.append(
            "add promoted evidence items before downstream research"
        )

    if indicators.get("pipeline_status") == "ready" and not indicators.get(
        "can_enter_expected_value_research"
    ):
        recommendations.append(
            "prepare downstream intake before expected-value research"
        )

    if indicators.get("pipeline_status") == "ready" and not indicators.get(
        "can_enter_strategy_selection"
    ):
        recommendations.append(
            "prepare downstream intake before strategy selection"
        )

    if (
        indicators.get("pipeline_status") == "ready"
        and _safe_int(indicators.get("downstream_intake_item_count")) == 0
    ):
        recommendations.append(
            "add downstream intake items before expected-value research"
        )

    return sorted(set(recommendations))


def _has_required_exclusions(pipeline_result: Mapping[str, Any]) -> bool:
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

    exclusions = pipeline_result.get("explicit_exclusions")
    if not isinstance(exclusions, list):
        return False

    return required.issubset({str(item) for item in exclusions})


def _stage_order_is_complete(pipeline_result: Mapping[str, Any]) -> bool:
    stage_order = pipeline_result.get("stage_order")
    return stage_order == list(STAGE_ORDER)


def _stage_statuses_match_completed_count(pipeline_result: Mapping[str, Any]) -> bool:
    summary = _as_mapping(pipeline_result.get("summary"))
    stage_statuses = _as_mapping(pipeline_result.get("stage_statuses"))

    return len(stage_statuses) == _safe_int(summary.get("completed_stage_count"))


def _summary_positive_count(final_summary: Mapping[str, Any], key: str) -> bool:
    summary = _as_mapping(final_summary.get("summary"))
    return _safe_int(summary.get(key)) > 0


def _blocked_pipeline_has_reason(pipeline_result: Mapping[str, Any]) -> bool:
    if pipeline_result.get("status") != "blocked":
        return True

    blocked_reasons = pipeline_result.get("blocked_reasons")
    return isinstance(blocked_reasons, list) and len(blocked_reasons) > 0


def _build_operation_id(summary: Mapping[str, Any]) -> str:
    backtest_id = summary.get("backtest_id") or "manual_backtest_evidence_pipeline"
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
