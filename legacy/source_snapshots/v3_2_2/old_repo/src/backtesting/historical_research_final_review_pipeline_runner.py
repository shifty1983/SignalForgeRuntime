# src/backtesting/historical_research_final_review_pipeline_runner.py

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from src.backtesting.historical_research_final_review_export_runner import (
    run_historical_research_final_review_export_operation,
)
from src.backtesting.historical_research_final_review_summary_runner import (
    run_historical_research_final_review_summary_operation,
)


PIPELINE_TYPE = "historical_research_final_review_pipeline"


def run_historical_research_final_review_pipeline(
    review_artifact_operation_result: Mapping[str, Any],
    *,
    operation_name: str = PIPELINE_TYPE,
    summary_operation_name: str | None = None,
    summary_name: str | None = None,
    export_operation_name: str | None = None,
    export_name: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    summary_log_path: str | Path | None = None,
    export_log_path: str | Path | None = None,
) -> dict[str, Any]:
    metadata_dict = dict(metadata or {})

    resolved_summary_operation_name = (
        summary_operation_name or f"{operation_name}.summary"
    )
    resolved_summary_name = summary_name or f"{operation_name}.summary"

    resolved_export_operation_name = export_operation_name or f"{operation_name}.export"
    resolved_export_name = export_name or f"{operation_name}.export"

    final_review_summary_operation = (
        run_historical_research_final_review_summary_operation(
            review_artifact_operation_result,
            operation_name=resolved_summary_operation_name,
            summary_name=resolved_summary_name,
            metadata=metadata_dict,
            log_path=summary_log_path,
        )
    )

    final_review_export_operation = run_historical_research_final_review_export_operation(
        final_review_summary_operation,
        operation_name=resolved_export_operation_name,
        export_name=resolved_export_name,
        metadata=metadata_dict,
        log_path=export_log_path,
    )

    blocked_reasons = _collect_blocked_reasons(
        final_review_summary_operation,
        final_review_export_operation,
    )
    warnings = _collect_warnings(
        final_review_summary_operation,
        final_review_export_operation,
    )

    is_blocked = bool(
        final_review_summary_operation.get("is_blocked")
        or final_review_export_operation.get("is_blocked")
        or blocked_reasons
    )

    runner_status = "blocked" if is_blocked else "completed"

    summary_operation_summary = dict(final_review_summary_operation.get("summary", {}))
    export_operation_summary = dict(final_review_export_operation.get("summary", {}))

    pipeline_result = {
        "operation_type": PIPELINE_TYPE,
        "operation_name": operation_name,
        "pipeline_id": _stable_pipeline_id(
            operation_name=operation_name,
            metadata=metadata_dict,
            final_review_summary_operation=final_review_summary_operation,
            final_review_export_operation=final_review_export_operation,
        ),
        "runner_status": runner_status,
        "is_blocked": is_blocked,
        "final_review_summary_operation": final_review_summary_operation,
        "final_review_export_operation": final_review_export_operation,
        "warnings": warnings,
        "blocked_reasons": blocked_reasons,
        "summary": {
            "summary_runner_status": final_review_summary_operation.get(
                "runner_status"
            ),
            "export_runner_status": final_review_export_operation.get("runner_status"),
            "summary_status": summary_operation_summary.get("summary_status"),
            "export_status": export_operation_summary.get("export_status"),
            "summary_operation_status": summary_operation_summary.get(
                "operation_status"
            ),
            "export_operation_status": export_operation_summary.get(
                "operation_status"
            ),
            "summary_audit_status": summary_operation_summary.get("audit_status"),
            "export_audit_status": export_operation_summary.get("audit_status"),
            "summary_health_status": summary_operation_summary.get("health_status"),
            "export_health_status": export_operation_summary.get("health_status"),
            "summary_log_status": summary_operation_summary.get("log_status"),
            "export_log_status": export_operation_summary.get("log_status"),
            "ready_count": export_operation_summary.get("ready_count", 0),
            "needs_review_count": export_operation_summary.get(
                "needs_review_count",
                0,
            ),
            "blocked_count": export_operation_summary.get("blocked_count", 0),
            "total_count": export_operation_summary.get("total_count", 0),
            "warning_count": len(warnings),
            "blocked_reason_count": len(blocked_reasons),
        },
        "metadata": metadata_dict,
    }

    return pipeline_result


def _collect_warnings(*operation_results: Mapping[str, Any]) -> list[str]:
    warnings: list[str] = []

    for operation_result in operation_results:
        health_report = operation_result.get("health_report", {})
        operation_record = operation_result.get("operation_record", {})

        if isinstance(health_report, Mapping):
            warnings.extend(str(item) for item in health_report.get("warnings", []))

        if isinstance(operation_record, Mapping):
            warnings.extend(str(item) for item in operation_record.get("warnings", []))

    return _unique_ordered(warnings)


def _collect_blocked_reasons(*operation_results: Mapping[str, Any]) -> list[str]:
    blocked_reasons: list[str] = []

    for operation_result in operation_results:
        health_report = operation_result.get("health_report", {})
        operation_record = operation_result.get("operation_record", {})

        if isinstance(health_report, Mapping):
            blocked_reasons.extend(
                str(item) for item in health_report.get("blocked_reasons", [])
            )

        if isinstance(operation_record, Mapping):
            blocked_reasons.extend(
                str(item) for item in operation_record.get("blocked_reasons", [])
            )

        if operation_result.get("is_blocked") is True:
            blocked_reasons.append(
                f"{operation_result.get('operation_type')} runner is blocked"
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


def _stable_pipeline_id(
    *,
    operation_name: str,
    metadata: Mapping[str, Any],
    final_review_summary_operation: Mapping[str, Any],
    final_review_export_operation: Mapping[str, Any],
) -> str:
    summary_record = final_review_summary_operation.get("operation_record", {})
    export_record = final_review_export_operation.get("operation_record", {})

    payload = {
        "operation_name": operation_name,
        "metadata": metadata,
        "summary_operation_id": (
            summary_record.get("operation_id")
            if isinstance(summary_record, Mapping)
            else None
        ),
        "export_operation_id": (
            export_record.get("operation_id")
            if isinstance(export_record, Mapping)
            else None
        ),
    }

    encoded_payload = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")

    digest = hashlib.sha256(encoded_payload).hexdigest()[:16]

    return f"{PIPELINE_TYPE}:{digest}"
