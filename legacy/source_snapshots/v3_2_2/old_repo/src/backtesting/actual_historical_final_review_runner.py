# src/backtesting/actual_historical_final_review_runner.py

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from src.backtesting.actual_historical_validation_runner import (
    run_actual_historical_validation,
)
from src.backtesting.historical_data_readiness_adapter import EXPLICIT_EXCLUSIONS
from src.backtesting.historical_research_final_review_pipeline_operation_runner import (
    run_historical_research_final_review_pipeline_operation,
)
from src.backtesting.historical_research_handoff_runner import (
    run_historical_research_handoff_operation,
)
from src.backtesting.historical_research_plan_export_runner import (
    run_historical_research_plan_export_operation,
)
from src.backtesting.historical_research_plan_snapshot import (
    build_historical_research_plan_snapshot,
)
from src.backtesting.historical_research_planning_runner import (
    run_historical_research_planning_operation,
)
from src.backtesting.historical_research_priority_runner import (
    run_historical_research_priority_operation,
)
from src.backtesting.historical_research_review_artifact_runner import (
    run_historical_research_review_artifact_operation,
)
from src.backtesting.historical_review_decision_snapshot import (
    build_historical_review_decision_snapshot,
)
from src.backtesting.historical_review_queue_runner import (
    run_historical_review_queue_operation,
)


OPERATION_TYPE = "actual_historical_final_review_runner"


def run_actual_historical_final_review(
    candidate_records: Iterable[Mapping[str, Any]],
    price_records: Iterable[Mapping[str, Any]],
    *,
    forward_windows: Sequence[int] = (1,),
    neutral_bands: Sequence[float] = (0.01,),
    candidate_field_map: Mapping[str, str] | None = None,
    price_field_map: Mapping[str, str] | None = None,
    operation_name: str = OPERATION_TYPE,
    actual_validation_operation_name: str | None = None,
    adapter_operation_name: str | None = None,
    validation_operation_name: str | None = None,
    promotion_operation_name: str | None = None,
    summary_export_name: str | None = None,
    review_queue_operation_name: str | None = None,
    review_snapshot_name: str | None = None,
    priority_operation_name: str | None = None,
    priority_report_name: str | None = None,
    handoff_operation_name: str | None = None,
    handoff_bundle_name: str | None = None,
    planning_operation_name: str | None = None,
    planning_queue_name: str | None = None,
    plan_snapshot_name: str | None = None,
    plan_export_operation_name: str | None = None,
    plan_export_name: str | None = None,
    review_artifact_operation_name: str | None = None,
    review_artifact_name: str | None = None,
    final_review_pipeline_operation_name: str | None = None,
    final_review_pipeline_name: str | None = None,
    final_summary_operation_name: str | None = None,
    final_summary_name: str | None = None,
    final_export_operation_name: str | None = None,
    final_export_name: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    adapter_log_path: str | Path | None = None,
    final_summary_log_path: str | Path | None = None,
    final_export_log_path: str | Path | None = None,
    final_pipeline_operation_log_path: str | Path | None = None,
) -> dict[str, Any]:
    metadata_dict = dict(metadata or {})

    resolved_actual_validation_operation_name = (
        actual_validation_operation_name or f"{operation_name}.actual_validation"
    )
    resolved_review_queue_operation_name = (
        review_queue_operation_name or f"{operation_name}.review_queue"
    )
    resolved_review_snapshot_name = (
        review_snapshot_name or f"{operation_name}.review_snapshot"
    )
    resolved_priority_operation_name = (
        priority_operation_name or f"{operation_name}.priority"
    )
    resolved_priority_report_name = (
        priority_report_name or f"{operation_name}.priority_report"
    )
    resolved_handoff_operation_name = (
        handoff_operation_name or f"{operation_name}.handoff"
    )
    resolved_handoff_bundle_name = (
        handoff_bundle_name or f"{operation_name}.handoff_bundle"
    )
    resolved_planning_operation_name = (
        planning_operation_name or f"{operation_name}.planning"
    )
    resolved_planning_queue_name = (
        planning_queue_name or f"{operation_name}.planning_queue"
    )
    resolved_plan_snapshot_name = (
        plan_snapshot_name or f"{operation_name}.plan_snapshot"
    )
    resolved_plan_export_operation_name = (
        plan_export_operation_name or f"{operation_name}.plan_export"
    )
    resolved_plan_export_name = (
        plan_export_name or f"{operation_name}.plan_export_payload"
    )
    resolved_review_artifact_operation_name = (
        review_artifact_operation_name or f"{operation_name}.review_artifact"
    )
    resolved_review_artifact_name = (
        review_artifact_name or f"{operation_name}.review_artifact_payload"
    )
    resolved_final_review_pipeline_operation_name = (
        final_review_pipeline_operation_name or f"{operation_name}.final_pipeline"
    )
    resolved_final_review_pipeline_name = (
        final_review_pipeline_name or f"{operation_name}.final_pipeline_result"
    )

    actual_validation_result = run_actual_historical_validation(
        candidate_records,
        price_records,
        forward_windows=forward_windows,
        neutral_bands=neutral_bands,
        candidate_field_map=candidate_field_map,
        price_field_map=price_field_map,
        operation_name=resolved_actual_validation_operation_name,
        adapter_operation_name=adapter_operation_name,
        validation_operation_name=validation_operation_name,
        promotion_operation_name=promotion_operation_name,
        summary_export_name=summary_export_name,
        metadata=metadata_dict,
        adapter_log_path=adapter_log_path,
    )

    review_queue_result = run_historical_review_queue_operation(
        [actual_validation_result["summary_export"]],
        operation_name=resolved_review_queue_operation_name,
    )

    review_decision_snapshot = build_historical_review_decision_snapshot(
        review_queue_result,
        snapshot_name=resolved_review_snapshot_name,
    )

    research_priority_operation = run_historical_research_priority_operation(
        review_decision_snapshot,
        operation_name=resolved_priority_operation_name,
        report_name=resolved_priority_report_name,
    )

    research_handoff_operation = run_historical_research_handoff_operation(
        research_priority_operation,
        operation_name=resolved_handoff_operation_name,
        bundle_name=resolved_handoff_bundle_name,
    )

    research_planning_operation = run_historical_research_planning_operation(
        research_handoff_operation,
        operation_name=resolved_planning_operation_name,
        planning_queue_name=resolved_planning_queue_name,
    )

    research_plan_snapshot = build_historical_research_plan_snapshot(
        research_planning_operation,
        snapshot_name=resolved_plan_snapshot_name,
    )

    research_plan_export_operation = run_historical_research_plan_export_operation(
        research_plan_snapshot,
        operation_name=resolved_plan_export_operation_name,
        export_name=resolved_plan_export_name,
    )

    research_review_artifact_operation = run_historical_research_review_artifact_operation(
        research_plan_export_operation,
        operation_name=resolved_review_artifact_operation_name,
        artifact_name=resolved_review_artifact_name,
    )

    final_review_pipeline_operation = run_historical_research_final_review_pipeline_operation(
        research_review_artifact_operation,
        operation_name=resolved_final_review_pipeline_operation_name,
        pipeline_name=resolved_final_review_pipeline_name,
        summary_operation_name=final_summary_operation_name,
        summary_name=final_summary_name,
        export_operation_name=final_export_operation_name,
        export_name=final_export_name,
        metadata=metadata_dict,
        summary_log_path=final_summary_log_path,
        export_log_path=final_export_log_path,
        operation_log_path=final_pipeline_operation_log_path,
    )

    warnings = _collect_warnings(
        actual_validation_result,
        review_queue_result,
        review_decision_snapshot,
        research_priority_operation,
        research_handoff_operation,
        research_planning_operation,
        research_plan_snapshot,
        research_plan_export_operation,
        research_review_artifact_operation,
        final_review_pipeline_operation,
    )

    blocked_reasons = _collect_blocked_reasons(
        actual_validation_result,
        review_queue_result,
        review_decision_snapshot,
        research_priority_operation,
        research_handoff_operation,
        research_planning_operation,
        research_plan_snapshot,
        research_plan_export_operation,
        research_review_artifact_operation,
        final_review_pipeline_operation,
    )

    is_blocked = bool(
        _stage_is_blocked(actual_validation_result)
        or _stage_is_blocked(review_queue_result)
        or _stage_is_blocked(review_decision_snapshot)
        or _stage_is_blocked(research_priority_operation)
        or _stage_is_blocked(research_handoff_operation)
        or _stage_is_blocked(research_planning_operation)
        or _stage_is_blocked(research_plan_snapshot)
        or _stage_is_blocked(research_plan_export_operation)
        or _stage_is_blocked(research_review_artifact_operation)
        or _stage_is_blocked(final_review_pipeline_operation)
        or blocked_reasons
    )

    runner_status = "blocked" if is_blocked else "completed"

    actual_validation_summary = dict(actual_validation_result.get("summary", {}))
    final_review_summary = dict(final_review_pipeline_operation.get("summary", {}))

    return {
        "operation_type": OPERATION_TYPE,
        "operation_name": operation_name,
        "runner_status": runner_status,
        "is_blocked": is_blocked,
        "actual_validation_result": actual_validation_result,
        "review_queue_result": review_queue_result,
        "review_decision_snapshot": review_decision_snapshot,
        "research_priority_operation": research_priority_operation,
        "research_handoff_operation": research_handoff_operation,
        "research_planning_operation": research_planning_operation,
        "research_plan_snapshot": research_plan_snapshot,
        "research_plan_export_operation": research_plan_export_operation,
        "research_review_artifact_operation": research_review_artifact_operation,
        "final_review_pipeline_operation": final_review_pipeline_operation,
        "warnings": warnings,
        "blocked_reasons": blocked_reasons,
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
        "summary": {
            "actual_validation_runner_status": actual_validation_result.get(
                "runner_status"
            ),
            "adapter_status": actual_validation_summary.get("adapter_status"),
            "validation_status": actual_validation_summary.get("validation_status"),
            "promotion_status": actual_validation_summary.get("promotion_status"),
            "summary_export_status": actual_validation_summary.get(
                "summary_export_status"
            ),
            "review_queue_runner_status": review_queue_result.get("runner_status"),
            "review_snapshot_status": _get_stage_status(
                review_decision_snapshot,
                preferred_keys=("snapshot_status", "status"),
            ),
            "priority_runner_status": research_priority_operation.get("runner_status"),
            "handoff_runner_status": research_handoff_operation.get("runner_status"),
            "planning_runner_status": research_planning_operation.get("runner_status"),
            "plan_snapshot_status": _get_stage_status(
                research_plan_snapshot,
                preferred_keys=("snapshot_status", "plan_status", "status"),
            ),
            "plan_export_runner_status": research_plan_export_operation.get(
                "runner_status"
            ),
            "review_artifact_runner_status": research_review_artifact_operation.get(
                "runner_status"
            ),
            "final_review_pipeline_runner_status": (
                final_review_pipeline_operation.get("runner_status")
            ),
            "final_review_pipeline_status": final_review_summary.get(
                "pipeline_status"
            ),
            "final_review_operation_status": final_review_summary.get(
                "operation_status"
            ),
            "final_review_health_status": final_review_summary.get("health_status"),
            "candidate_count": actual_validation_summary.get("candidate_count", 0),
            "price_row_count": actual_validation_summary.get("price_row_count", 0),
            "accepted_candidate_count": actual_validation_summary.get(
                "accepted_candidate_count",
                0,
            ),
            "rejected_candidate_count": actual_validation_summary.get(
                "rejected_candidate_count",
                0,
            ),
            "ready_count": final_review_summary.get("ready_count", 0),
            "needs_review_count": final_review_summary.get("needs_review_count", 0),
            "blocked_count": final_review_summary.get("blocked_count", 0),
            "total_count": final_review_summary.get("total_count", 0),
            "warning_count": len(warnings),
            "blocked_reason_count": len(blocked_reasons),
        },
        "metadata": metadata_dict,
    }


def _get_stage_status(
    stage_result: Mapping[str, Any],
    *,
    preferred_keys: Sequence[str],
) -> str | None:
    for key in preferred_keys:
        value = stage_result.get(key)
        if value is not None:
            return str(value)

    summary = stage_result.get("summary", {})
    if isinstance(summary, Mapping):
        for key in preferred_keys:
            value = summary.get(key)
            if value is not None:
                return str(value)

    return None


def _stage_is_blocked(stage_result: Mapping[str, Any]) -> bool:
    if stage_result.get("is_blocked") is True:
        return True

    for status_key in [
        "runner_status",
        "operation_status",
        "adapter_status",
        "validation_status",
        "promotion_status",
        "export_status",
        "summary_status",
        "snapshot_status",
        "report_status",
        "handoff_status",
        "planning_status",
        "plan_status",
        "artifact_status",
        "pipeline_status",
        "status",
    ]:
        if stage_result.get(status_key) in {"blocked", "failed"}:
            return True

    summary = stage_result.get("summary", {})
    if isinstance(summary, Mapping):
        for status_key in [
            "runner_status",
            "operation_status",
            "adapter_status",
            "validation_status",
            "promotion_status",
            "export_status",
            "summary_status",
            "snapshot_status",
            "report_status",
            "handoff_status",
            "planning_status",
            "plan_status",
            "artifact_status",
            "pipeline_status",
            "status",
        ]:
            if summary.get(status_key) in {"blocked", "failed"}:
                return True

    return False


def _collect_warnings(*stage_results: Mapping[str, Any]) -> list[str]:
    warnings: list[str] = []

    for stage_result in stage_results:
        warnings.extend(str(item) for item in stage_result.get("warnings", []))

        operation_record = stage_result.get("operation_record", {})
        if isinstance(operation_record, Mapping):
            warnings.extend(str(item) for item in operation_record.get("warnings", []))

        health_report = stage_result.get("health_report", {})
        if isinstance(health_report, Mapping):
            warnings.extend(str(item) for item in health_report.get("warnings", []))

    return _unique_ordered(warnings)


def _collect_blocked_reasons(*stage_results: Mapping[str, Any]) -> list[str]:
    blocked_reasons: list[str] = []

    for stage_result in stage_results:
        blocked_reasons.extend(
            str(item) for item in stage_result.get("blocked_reasons", [])
        )
        blocked_reasons.extend(
            str(item) for item in stage_result.get("validation_errors", [])
        )

        operation_record = stage_result.get("operation_record", {})
        if isinstance(operation_record, Mapping):
            blocked_reasons.extend(
                str(item) for item in operation_record.get("blocked_reasons", [])
            )
            blocked_reasons.extend(
                str(item) for item in operation_record.get("validation_errors", [])
            )

        health_report = stage_result.get("health_report", {})
        if isinstance(health_report, Mapping):
            blocked_reasons.extend(
                str(item) for item in health_report.get("blocked_reasons", [])
            )

    return _unique_ordered(blocked_reasons)


def _unique_ordered(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []

    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)

    return result
