# src/backtesting/historical_records_file_final_review_runner.py

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from src.backtesting.actual_historical_final_review_runner import (
    run_actual_historical_final_review,
)
from src.backtesting.historical_records_file_loader import (
    EXPLICIT_EXCLUSIONS,
    load_historical_records_from_files,
)


OPERATION_TYPE = "historical_records_file_final_review_runner"


def run_historical_records_file_final_review(
    candidate_file_path: str | Path,
    price_file_path: str | Path,
    *,
    candidate_format: str | None = None,
    price_format: str | None = None,
    candidate_read_options: Mapping[str, Any] | None = None,
    price_read_options: Mapping[str, Any] | None = None,
    forward_windows: Sequence[int] = (1,),
    neutral_bands: Sequence[float] = (0.01,),
    candidate_field_map: Mapping[str, str] | None = None,
    price_field_map: Mapping[str, str] | None = None,
    operation_name: str = OPERATION_TYPE,
    actual_final_review_operation_name: str | None = None,
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

    loader_result = load_historical_records_from_files(
        candidate_file_path,
        price_file_path,
        candidate_format=candidate_format,
        price_format=price_format,
        candidate_read_options=candidate_read_options,
        price_read_options=price_read_options,
        metadata=metadata_dict,
    )

    resolved_actual_final_review_operation_name = (
        actual_final_review_operation_name or f"{operation_name}.actual_final_review"
    )

    if loader_result.get("is_blocked") is True:
        warnings = _collect_warnings(loader_result)
        blocked_reasons = _collect_blocked_reasons(loader_result)

        actual_final_review_result = _build_skipped_actual_final_review_result(
            operation_name=resolved_actual_final_review_operation_name,
            warnings=warnings,
            blocked_reasons=blocked_reasons,
            metadata=metadata_dict,
        )

        return _build_runner_result(
            operation_name=operation_name,
            loader_result=loader_result,
            actual_final_review_result=actual_final_review_result,
            metadata=metadata_dict,
        )

    actual_final_review_result = run_actual_historical_final_review(
        loader_result.get("candidate_records", []),
        loader_result.get("price_records", []),
        forward_windows=forward_windows,
        neutral_bands=neutral_bands,
        candidate_field_map=candidate_field_map,
        price_field_map=price_field_map,
        operation_name=resolved_actual_final_review_operation_name,
        actual_validation_operation_name=actual_validation_operation_name,
        adapter_operation_name=adapter_operation_name,
        validation_operation_name=validation_operation_name,
        promotion_operation_name=promotion_operation_name,
        summary_export_name=summary_export_name,
        review_queue_operation_name=review_queue_operation_name,
        review_snapshot_name=review_snapshot_name,
        priority_operation_name=priority_operation_name,
        priority_report_name=priority_report_name,
        handoff_operation_name=handoff_operation_name,
        handoff_bundle_name=handoff_bundle_name,
        planning_operation_name=planning_operation_name,
        planning_queue_name=planning_queue_name,
        plan_snapshot_name=plan_snapshot_name,
        plan_export_operation_name=plan_export_operation_name,
        plan_export_name=plan_export_name,
        review_artifact_operation_name=review_artifact_operation_name,
        review_artifact_name=review_artifact_name,
        final_review_pipeline_operation_name=final_review_pipeline_operation_name,
        final_review_pipeline_name=final_review_pipeline_name,
        final_summary_operation_name=final_summary_operation_name,
        final_summary_name=final_summary_name,
        final_export_operation_name=final_export_operation_name,
        final_export_name=final_export_name,
        metadata=metadata_dict,
        adapter_log_path=adapter_log_path,
        final_summary_log_path=final_summary_log_path,
        final_export_log_path=final_export_log_path,
        final_pipeline_operation_log_path=final_pipeline_operation_log_path,
    )

    return _build_runner_result(
        operation_name=operation_name,
        loader_result=loader_result,
        actual_final_review_result=actual_final_review_result,
        metadata=metadata_dict,
    )


def _build_runner_result(
    *,
    operation_name: str,
    loader_result: Mapping[str, Any],
    actual_final_review_result: Mapping[str, Any],
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    warnings = _collect_warnings(loader_result, actual_final_review_result)
    blocked_reasons = _collect_blocked_reasons(loader_result, actual_final_review_result)

    is_blocked = bool(
        _stage_is_blocked(loader_result)
        or _stage_is_blocked(actual_final_review_result)
        or blocked_reasons
    )

    runner_status = "blocked" if is_blocked else "completed"

    file_summary = dict(loader_result.get("file_summary", {}))
    actual_summary = dict(actual_final_review_result.get("summary", {}))

    return {
        "operation_type": OPERATION_TYPE,
        "operation_name": operation_name,
        "runner_status": runner_status,
        "is_blocked": is_blocked,
        "loader_result": dict(loader_result),
        "actual_final_review_result": dict(actual_final_review_result),
        "warnings": warnings,
        "blocked_reasons": blocked_reasons,
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
        "summary": {
            "loader_status": loader_result.get("loader_status"),
            "candidate_file_path": file_summary.get("candidate_file_path"),
            "price_file_path": file_summary.get("price_file_path"),
            "candidate_format": file_summary.get("candidate_format"),
            "price_format": file_summary.get("price_format"),
            "candidate_record_count": file_summary.get("candidate_record_count", 0),
            "price_record_count": file_summary.get("price_record_count", 0),
            "actual_final_review_runner_status": actual_final_review_result.get(
                "runner_status"
            ),
            "actual_final_review_is_blocked": actual_final_review_result.get(
                "is_blocked"
            ),
            "adapter_status": actual_summary.get("adapter_status"),
            "validation_status": actual_summary.get("validation_status"),
            "promotion_status": actual_summary.get("promotion_status"),
            "summary_export_status": actual_summary.get("summary_export_status"),
            "final_review_pipeline_runner_status": actual_summary.get(
                "final_review_pipeline_runner_status"
            ),
            "final_review_pipeline_status": actual_summary.get(
                "final_review_pipeline_status"
            ),
            "final_review_health_status": actual_summary.get(
                "final_review_health_status"
            ),
            "candidate_count": actual_summary.get("candidate_count", 0),
            "price_row_count": actual_summary.get("price_row_count", 0),
            "accepted_candidate_count": actual_summary.get(
                "accepted_candidate_count",
                0,
            ),
            "rejected_candidate_count": actual_summary.get(
                "rejected_candidate_count",
                0,
            ),
            "ready_count": actual_summary.get("ready_count", 0),
            "needs_review_count": actual_summary.get("needs_review_count", 0),
            "blocked_count": actual_summary.get("blocked_count", 0),
            "total_count": actual_summary.get("total_count", 0),
            "warning_count": len(warnings),
            "blocked_reason_count": len(blocked_reasons),
        },
        "metadata": dict(metadata),
    }


def _build_skipped_actual_final_review_result(
    *,
    operation_name: str,
    warnings: list[str],
    blocked_reasons: list[str],
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "operation_type": "actual_historical_final_review_runner",
        "operation_name": operation_name,
        "runner_status": "blocked",
        "is_blocked": True,
        "actual_validation_result": {
            "runner_status": "skipped",
            "is_blocked": True,
            "summary": {
                "skip_reason": "historical records file loader is blocked",
            },
        },
        "final_review_pipeline_operation": {
            "runner_status": "skipped",
            "is_blocked": True,
            "summary": {
                "pipeline_status": "skipped",
                "health_status": "skipped",
                "skip_reason": "historical records file loader is blocked",
            },
        },
        "warnings": list(warnings),
        "blocked_reasons": list(blocked_reasons),
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
        "summary": {
            "actual_validation_runner_status": "skipped",
            "adapter_status": "skipped",
            "validation_status": "skipped",
            "promotion_status": "skipped",
            "summary_export_status": "skipped",
            "final_review_pipeline_runner_status": "skipped",
            "final_review_pipeline_status": "skipped",
            "final_review_operation_status": "skipped",
            "final_review_health_status": "skipped",
            "candidate_count": 0,
            "price_row_count": 0,
            "accepted_candidate_count": 0,
            "rejected_candidate_count": 0,
            "ready_count": 0,
            "needs_review_count": 0,
            "blocked_count": 0,
            "total_count": 0,
            "warning_count": len(warnings),
            "blocked_reason_count": len(blocked_reasons),
        },
        "metadata": dict(metadata),
    }


def _stage_is_blocked(stage_result: Mapping[str, Any]) -> bool:
    if stage_result.get("is_blocked") is True:
        return True

    for status_key in [
        "runner_status",
        "operation_status",
        "loader_status",
        "adapter_status",
        "validation_status",
        "promotion_status",
        "export_status",
        "summary_status",
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
            "loader_status",
            "adapter_status",
            "validation_status",
            "promotion_status",
            "export_status",
            "summary_status",
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
