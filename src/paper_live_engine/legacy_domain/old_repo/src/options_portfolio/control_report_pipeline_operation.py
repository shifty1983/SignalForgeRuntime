from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from os import PathLike
from pathlib import Path
from typing import Any

from src.options_portfolio.control_report_pipeline_file_writer import (
    PIPELINE_SUMMARY_FILENAME,
    PIPELINE_TYPE,
    write_options_portfolio_control_report_pipeline_files,
)


OPERATION_SCHEMA_VERSION = "options_portfolio_control_report_pipeline_operation.v1"
EVENT_SCHEMA_VERSION = "options_portfolio_control_report_pipeline_operation_event.v1"
AUDIT_SCHEMA_VERSION = "options_portfolio_control_report_pipeline_audit.v1"
HEALTH_SCHEMA_VERSION = "options_portfolio_control_report_pipeline_health.v1"

OPERATION_TYPE = "options_portfolio_control_report_pipeline_operation"
VALID_PIPELINE_STATUSES = {"ready", "needs_review", "blocked"}

REQUIRED_EXCLUSIONS = (
    "broker_api_calls",
    "order_routing",
    "order_submission",
    "fills",
    "live_execution",
    "slippage_modeling",
    "automatic_close_orders",
    "automatic_roll_orders",
    "automatic_defense_orders",
    "automatic_strategy_changes",
    "automatic_parameter_changes",
    "automatic_pause_actions",
)


def run_options_portfolio_control_report_pipeline_operation(
    source: Mapping[str, Any] | None,
    *,
    output_dir: str | PathLike[str],
    base_dir: str | PathLike[str] | None = None,
    report_date: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    event_log_path: str | PathLike[str] | None = None,
) -> dict[str, Any]:
    """Run and validate the full file-driven options portfolio control report pipeline."""

    pipeline_summary = write_options_portfolio_control_report_pipeline_files(
        source or {},
        output_dir=output_dir,
        base_dir=base_dir,
        report_date=report_date,
    )
    audit_report = build_options_portfolio_control_report_pipeline_audit_report(
        pipeline_summary
    )
    health_report = build_options_portfolio_control_report_pipeline_health_report(
        pipeline_summary
    )

    operation_status = _classify_operation_status(
        pipeline_status=str(pipeline_summary.get("status", "needs_review")),
        audit_status=str(audit_report.get("status", "needs_review")),
        health_status=str(health_report.get("status", "needs_review")),
    )

    events = [
        _build_event(
            pipeline_summary=pipeline_summary,
            event_type="options_portfolio_control_report_pipeline_operation_started",
            sequence=1,
            status=operation_status,
        ),
        _build_event(
            pipeline_summary=pipeline_summary,
            event_type="options_portfolio_control_report_pipeline_operation_completed",
            sequence=2,
            status=operation_status,
        ),
    ]

    normalized_log_path = _normalize_event_log_path(event_log_path)
    if normalized_log_path is not None:
        _write_jsonl_event_log(normalized_log_path, events)

    operation_record = _build_operation_record(
        pipeline_summary=pipeline_summary,
        audit_report=audit_report,
        health_report=health_report,
        operation_status=operation_status,
        output_dir=output_dir,
        base_dir=base_dir,
        event_log_path=normalized_log_path,
        metadata=metadata,
    )

    return {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": operation_status,
        "operation_record": operation_record,
        "audit_report": audit_report,
        "health_report": health_report,
        "pipeline_summary": pipeline_summary,
        "events": events,
        "event_log_path": str(normalized_log_path) if normalized_log_path else None,
        "explicit_exclusions": list(pipeline_summary.get("explicit_exclusions", [])),
    }


def build_options_portfolio_control_report_pipeline_audit_report(
    pipeline_summary: Mapping[str, Any],
) -> dict[str, Any]:
    checks = [
        _check(
            name="pipeline_type_valid",
            passed=pipeline_summary.get("pipeline_type") == PIPELINE_TYPE,
            severity="blocker",
            message="options portfolio control report pipeline type is valid",
            failure_message="options portfolio control report pipeline type is invalid",
        ),
        _check(
            name="pipeline_status_valid",
            passed=pipeline_summary.get("status") in VALID_PIPELINE_STATUSES,
            severity="blocker",
            message="options portfolio control report pipeline status is valid",
            failure_message="options portfolio control report pipeline status is invalid",
        ),
        _check(
            name="source_assembler_status_valid",
            passed=pipeline_summary.get("source_assembler_status") in VALID_PIPELINE_STATUSES,
            severity="blocker",
            message="source assembler status is valid",
            failure_message="source assembler status is invalid",
        ),
        _check(
            name="control_report_status_valid_when_present",
            passed=_control_report_status_valid_when_present(pipeline_summary),
            severity="blocker",
            message="control report status is valid when present",
            failure_message="control report status is invalid",
        ),
        _check(
            name="pipeline_summary_file_reference_present",
            passed=_pipeline_summary_file_reference_present(pipeline_summary),
            severity="blocker",
            message="pipeline summary file reference is present",
            failure_message="pipeline summary file reference is missing",
        ),
        _check(
            name="source_assembler_file_references_present",
            passed=_nested_file_references_present(pipeline_summary, "source_assembler"),
            severity="blocker",
            message="source assembler file references are present",
            failure_message="source assembler file references are missing",
        ),
        _check(
            name="control_report_file_references_present_when_required",
            passed=_control_report_file_references_present_when_required(pipeline_summary),
            severity="blocker",
            message="control report file references are present when required",
            failure_message="control report file references are missing",
        ),
        _check(
            name="referenced_files_exist",
            passed=_referenced_files_exist(pipeline_summary),
            severity="warning",
            message="referenced pipeline files exist",
            failure_message="one or more referenced pipeline files are missing",
        ),
        _check(
            name="explicit_exclusions_present",
            passed=_has_required_exclusions(pipeline_summary),
            severity="blocker",
            message="pipeline exclusions are present",
            failure_message="one or more required pipeline exclusions are missing",
        ),
        _check(
            name="no_order_intents_created",
            passed=not _contains_non_null_key(pipeline_summary, "order_intent"),
            severity="blocker",
            message="pipeline did not create order intents",
            failure_message="pipeline created one or more order intents",
        ),
        _check(
            name="no_broker_order_ids_created",
            passed=not _contains_non_null_key(pipeline_summary, "broker_order_id"),
            severity="blocker",
            message="pipeline did not create broker order ids",
            failure_message="pipeline created one or more broker order ids",
        ),
        _check(
            name="no_automatic_actions_created",
            passed=not _contains_non_null_key(
                pipeline_summary,
                "automatic_action",
                "automatic_strategy_change",
                "automatic_parameter_change",
                "automatic_pause_action",
                "maintenance_action",
                "defense_action",
                "strategy_change",
                "parameter_change",
                "pause_action",
            ),
            severity="blocker",
            message="pipeline did not create automatic actions",
            failure_message="pipeline created one or more automatic actions",
        ),
    ]

    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_audit_status(
            pipeline_status=str(pipeline_summary.get("status", "needs_review")),
            checks=checks,
        ),
        "summary": _summarize_checks(checks),
        "checks": checks,
        "explicit_exclusions": list(pipeline_summary.get("explicit_exclusions", [])),
    }


def build_options_portfolio_control_report_pipeline_health_report(
    pipeline_summary: Mapping[str, Any],
) -> dict[str, Any]:
    pipeline_status = str(pipeline_summary.get("status", "needs_review"))
    source_assembler_summary = _as_mapping(pipeline_summary.get("source_assembler_summary"))
    control_report_summary = _as_mapping(pipeline_summary.get("control_report_summary"))
    files = _as_mapping(pipeline_summary.get("files"))

    indicators = {
        "pipeline_status": pipeline_status,
        "report_date": _string_or_none(pipeline_summary.get("report_date")),
        "source_assembler_status": _string_or_none(
            pipeline_summary.get("source_assembler_status")
        ),
        "control_report_status": _string_or_none(
            pipeline_summary.get("control_report_status")
        ),
        "source_assembler_loaded_artifact_count": _safe_int(
            source_assembler_summary.get("loaded_artifact_count")
        ),
        "source_assembler_missing_artifact_count": _safe_int(
            source_assembler_summary.get("missing_artifact_count")
        ),
        "source_assembler_blocked_item_count": _safe_int(
            source_assembler_summary.get("blocked_item_count")
        ),
        "control_report_present_section_count": _safe_int(
            control_report_summary.get("present_section_count")
        ),
        "control_report_missing_section_count": _safe_int(
            control_report_summary.get("missing_section_count")
        ),
        "control_report_blocked_item_count": _safe_int(
            control_report_summary.get("blocked_item_count")
        ),
        "control_report_needs_review_item_count": _safe_int(
            control_report_summary.get("needs_review_item_count")
        ),
        "control_report_total_item_count": _safe_int(
            control_report_summary.get("total_item_count")
        ),
        "control_report_total_manual_action_count": _safe_int(
            control_report_summary.get("total_manual_action_count")
        ),
        "can_consider_new_trades": control_report_summary.get("can_consider_new_trades") is True,
        "human_decision_logged": control_report_summary.get("human_decision_logged") is True,
        "has_pipeline_summary_file": bool(
            _as_mapping(files).get("pipeline_summary")
        ),
        "has_source_assembler_files": bool(
            _as_mapping(files).get("source_assembler")
        ),
        "has_control_report_files": bool(
            _as_mapping(files).get("control_report")
        ),
        "referenced_file_count": len(_collect_file_paths(pipeline_summary)),
        "missing_referenced_file_count": len(_missing_referenced_files(pipeline_summary)),
        "has_order_intent": _contains_non_null_key(pipeline_summary, "order_intent"),
        "has_broker_order_id": _contains_non_null_key(pipeline_summary, "broker_order_id"),
        "has_automatic_action": _contains_non_null_key(
            pipeline_summary,
            "automatic_action",
            "automatic_strategy_change",
            "automatic_parameter_change",
            "automatic_pause_action",
            "maintenance_action",
            "defense_action",
            "strategy_change",
            "parameter_change",
            "pause_action",
        ),
    }

    return {
        "schema_version": HEALTH_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_health_status(
            pipeline_status=pipeline_status,
            indicators=indicators,
        ),
        "indicators": indicators,
        "explicit_exclusions": list(pipeline_summary.get("explicit_exclusions", [])),
    }


def _build_operation_record(
    *,
    pipeline_summary: Mapping[str, Any],
    audit_report: Mapping[str, Any],
    health_report: Mapping[str, Any],
    operation_status: str,
    output_dir: str | PathLike[str],
    base_dir: str | PathLike[str] | None,
    event_log_path: Path | None,
    metadata: Mapping[str, Any] | None,
) -> dict[str, Any]:
    source_assembler_summary = _as_mapping(pipeline_summary.get("source_assembler_summary"))
    control_report_summary = _as_mapping(pipeline_summary.get("control_report_summary"))

    return {
        "operation_type": OPERATION_TYPE,
        "schema_version": OPERATION_SCHEMA_VERSION,
        "status": operation_status,
        "pipeline_type": pipeline_summary.get("pipeline_type"),
        "report_date": _string_or_none(pipeline_summary.get("report_date")),
        "output_dir": str(output_dir),
        "base_dir": str(base_dir) if base_dir is not None else None,
        "operation_summary": {
            "source_assembler_status": pipeline_summary.get("source_assembler_status"),
            "control_report_status": pipeline_summary.get("control_report_status"),
            "source_assembler_loaded_artifact_count": _safe_int(
                source_assembler_summary.get("loaded_artifact_count")
            ),
            "source_assembler_missing_artifact_count": _safe_int(
                source_assembler_summary.get("missing_artifact_count")
            ),
            "source_assembler_blocked_item_count": _safe_int(
                source_assembler_summary.get("blocked_item_count")
            ),
            "control_report_present_section_count": _safe_int(
                control_report_summary.get("present_section_count")
            ),
            "control_report_missing_section_count": _safe_int(
                control_report_summary.get("missing_section_count")
            ),
            "control_report_blocked_item_count": _safe_int(
                control_report_summary.get("blocked_item_count")
            ),
            "control_report_needs_review_item_count": _safe_int(
                control_report_summary.get("needs_review_item_count")
            ),
            "control_report_total_item_count": _safe_int(
                control_report_summary.get("total_item_count")
            ),
            "control_report_total_manual_action_count": _safe_int(
                control_report_summary.get("total_manual_action_count")
            ),
            "can_consider_new_trades": control_report_summary.get("can_consider_new_trades"),
            "human_decision_logged": control_report_summary.get("human_decision_logged"),
            "audit_status": audit_report.get("status"),
            "health_status": health_report.get("status"),
        },
        "event_log_path": str(event_log_path) if event_log_path else None,
        "metadata": dict(metadata or {}),
        "explicit_exclusions": list(pipeline_summary.get("explicit_exclusions", [])),
    }


def _build_event(
    *,
    pipeline_summary: Mapping[str, Any],
    event_type: str,
    sequence: int,
    status: str,
) -> dict[str, Any]:
    source_assembler_summary = _as_mapping(pipeline_summary.get("source_assembler_summary"))
    control_report_summary = _as_mapping(pipeline_summary.get("control_report_summary"))

    return {
        "schema_version": EVENT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "event_type": event_type,
        "sequence": sequence,
        "status": status,
        "pipeline_status": pipeline_summary.get("status"),
        "source_assembler_status": pipeline_summary.get("source_assembler_status"),
        "control_report_status": pipeline_summary.get("control_report_status"),
        "source_assembler_loaded_artifact_count": _safe_int(
            source_assembler_summary.get("loaded_artifact_count")
        ),
        "source_assembler_blocked_item_count": _safe_int(
            source_assembler_summary.get("blocked_item_count")
        ),
        "control_report_present_section_count": _safe_int(
            control_report_summary.get("present_section_count")
        ),
        "control_report_blocked_item_count": _safe_int(
            control_report_summary.get("blocked_item_count")
        ),
    }


def _control_report_status_valid_when_present(pipeline_summary: Mapping[str, Any]) -> bool:
    status = pipeline_summary.get("control_report_status")
    if status is None and pipeline_summary.get("source_assembler_status") == "blocked":
        return True
    return status in VALID_PIPELINE_STATUSES


def _pipeline_summary_file_reference_present(pipeline_summary: Mapping[str, Any]) -> bool:
    files = _as_mapping(pipeline_summary.get("files"))
    value = files.get("pipeline_summary")
    return isinstance(value, str) and value.endswith(PIPELINE_SUMMARY_FILENAME)


def _nested_file_references_present(pipeline_summary: Mapping[str, Any], key: str) -> bool:
    files = _as_mapping(pipeline_summary.get("files"))
    nested = files.get(key)
    return isinstance(nested, Mapping) and bool(nested)


def _control_report_file_references_present_when_required(
    pipeline_summary: Mapping[str, Any],
) -> bool:
    if pipeline_summary.get("source_assembler_status") == "blocked":
        return True
    return _nested_file_references_present(pipeline_summary, "control_report")


def _referenced_files_exist(pipeline_summary: Mapping[str, Any]) -> bool:
    missing = _missing_referenced_files(pipeline_summary)
    return not missing


def _missing_referenced_files(pipeline_summary: Mapping[str, Any]) -> list[str]:
    return [path for path in _collect_file_paths(pipeline_summary) if not Path(path).exists()]


def _collect_file_paths(pipeline_summary: Mapping[str, Any]) -> list[str]:
    files = _as_mapping(pipeline_summary.get("files"))
    paths: list[str] = []

    for value in files.values():
        if isinstance(value, str):
            paths.append(value)
        elif isinstance(value, Mapping):
            for nested_value in value.values():
                if isinstance(nested_value, str):
                    paths.append(nested_value)

    return sorted(set(paths))


def _has_required_exclusions(pipeline_summary: Mapping[str, Any]) -> bool:
    exclusions = set(_as_list(pipeline_summary.get("explicit_exclusions")))
    return all(item in exclusions for item in REQUIRED_EXCLUSIONS)


def _contains_non_null_key(value: Any, *keys: str) -> bool:
    if isinstance(value, Mapping):
        for key in keys:
            if key in value and value.get(key) is not None:
                return True
        return any(_contains_non_null_key(item, *keys) for item in value.values())

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_non_null_key(item, *keys) for item in value)

    return False


def _check(
    *,
    name: str,
    passed: bool,
    severity: str,
    message: str,
    failure_message: str,
) -> dict[str, Any]:
    return {
        "name": name,
        "passed": bool(passed),
        "severity": severity,
        "message": message if passed else failure_message,
    }


def _summarize_checks(checks: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    passed = sum(1 for check in checks if check.get("passed") is True)
    failed = len(checks) - passed
    blockers = sum(
        1
        for check in checks
        if check.get("passed") is not True and check.get("severity") == "blocker"
    )
    warnings = sum(
        1
        for check in checks
        if check.get("passed") is not True and check.get("severity") != "blocker"
    )
    return {
        "check_count": len(checks),
        "passed_count": passed,
        "failed_count": failed,
        "blocker_count": blockers,
        "warning_count": warnings,
    }


def _classify_operation_status(
    *,
    pipeline_status: str,
    audit_status: str,
    health_status: str,
) -> str:
    if "blocked" in {pipeline_status, audit_status, health_status}:
        return "blocked"
    if "needs_review" in {pipeline_status, audit_status, health_status}:
        return "needs_review"
    return "ready"


def _classify_audit_status(
    *,
    pipeline_status: str,
    checks: Sequence[Mapping[str, Any]],
) -> str:
    if any(check.get("passed") is not True and check.get("severity") == "blocker" for check in checks):
        return "blocked"
    if pipeline_status == "blocked":
        return "blocked"
    if pipeline_status == "needs_review" or any(check.get("passed") is not True for check in checks):
        return "needs_review"
    return "ready"


def _classify_health_status(
    *,
    pipeline_status: str,
    indicators: Mapping[str, Any],
) -> str:
    if (
        indicators.get("has_order_intent")
        or indicators.get("has_broker_order_id")
        or indicators.get("has_automatic_action")
    ):
        return "blocked"
    if pipeline_status == "blocked":
        return "blocked"
    if (
        indicators.get("source_assembler_blocked_item_count", 0) > 0
        or indicators.get("control_report_blocked_item_count", 0) > 0
    ):
        return "blocked"
    if pipeline_status == "needs_review":
        return "needs_review"
    if (
        indicators.get("source_assembler_missing_artifact_count", 0) > 0
        or indicators.get("control_report_missing_section_count", 0) > 0
        or indicators.get("control_report_needs_review_item_count", 0) > 0
        or indicators.get("missing_referenced_file_count", 0) > 0
    ):
        return "needs_review"
    return "ready"


def _normalize_event_log_path(path: str | PathLike[str] | None) -> Path | None:
    if path is None:
        return None
    normalized = Path(path)
    normalized.parent.mkdir(parents=True, exist_ok=True)
    return normalized


def _write_jsonl_event_log(path: Path, events: Sequence[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, sort_keys=True) + "\n")


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return []


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0

