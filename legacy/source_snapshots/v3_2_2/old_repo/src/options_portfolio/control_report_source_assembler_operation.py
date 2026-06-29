from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from os import PathLike
from pathlib import Path
from typing import Any

from src.options_portfolio.control_report_source_assembler import (
    EXPLICIT_EXCLUSIONS,
    assemble_options_portfolio_control_report_source,
)


OPERATION_SCHEMA_VERSION = "options_portfolio_control_report_source_assembler_operation.v1"
EVENT_SCHEMA_VERSION = "options_portfolio_control_report_source_assembler_event.v1"
AUDIT_SCHEMA_VERSION = "options_portfolio_control_report_source_assembler_audit.v1"
HEALTH_SCHEMA_VERSION = "options_portfolio_control_report_source_assembler_health.v1"

OPERATION_TYPE = "options_portfolio_control_report_source_assembler_operation"
VALID_SOURCE_STATUSES = {"ready", "needs_review", "blocked"}
REQUIRED_EXCLUSIONS = tuple(EXPLICIT_EXCLUSIONS)


def run_options_portfolio_control_report_source_assembler_operation(
    source: Mapping[str, Any] | None,
    *,
    base_dir: str | PathLike[str] | None = None,
    metadata: Mapping[str, Any] | None = None,
    event_log_path: str | PathLike[str] | None = None,
) -> dict[str, Any]:
    assembled_source = assemble_options_portfolio_control_report_source(
        source or {},
        base_dir=base_dir,
    )
    audit_report = build_options_portfolio_control_report_source_assembler_audit_report(
        assembled_source
    )
    health_report = build_options_portfolio_control_report_source_assembler_health_report(
        assembled_source
    )

    operation_status = _classify_operation_status(
        source_status=str(assembled_source.get("status", "needs_review")),
        audit_status=str(audit_report.get("status", "needs_review")),
        health_status=str(health_report.get("status", "needs_review")),
    )

    events = [
        _build_event(
            assembled_source=assembled_source,
            event_type="options_portfolio_control_report_source_assembler_started",
            sequence=1,
            status=operation_status,
        ),
        _build_event(
            assembled_source=assembled_source,
            event_type="options_portfolio_control_report_source_assembler_completed",
            sequence=2,
            status=operation_status,
        ),
    ]

    normalized_log_path = _normalize_event_log_path(event_log_path)
    if normalized_log_path is not None:
        _write_jsonl_event_log(normalized_log_path, events)

    operation_record = _build_operation_record(
        assembled_source=assembled_source,
        audit_report=audit_report,
        health_report=health_report,
        operation_status=operation_status,
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
        "options_portfolio_control_report_source": assembled_source,
        "events": events,
        "event_log_path": str(normalized_log_path) if normalized_log_path else None,
        "explicit_exclusions": list(assembled_source.get("explicit_exclusions", [])),
    }


def build_options_portfolio_control_report_source_assembler_audit_report(
    assembled_source: Mapping[str, Any],
) -> dict[str, Any]:
    checks = [
        _check(
            name="source_artifact_type_valid",
            passed=assembled_source.get("artifact_type") == "options_portfolio_control_report_source",
            severity="blocker",
            message="control report source artifact type is valid",
            failure_message="control report source artifact type is invalid",
        ),
        _check(
            name="source_status_valid",
            passed=assembled_source.get("status") in VALID_SOURCE_STATUSES,
            severity="blocker",
            message="control report source status is valid",
            failure_message="control report source status is invalid",
        ),
        _check(
            name="assembled_source_present",
            passed=isinstance(assembled_source.get("assembled_source"), Mapping),
            severity="blocker",
            message="assembled control report source is present",
            failure_message="assembled control report source is missing",
        ),
        _check(
            name="source_summary_present",
            passed=isinstance(assembled_source.get("source_summary"), Mapping),
            severity="blocker",
            message="control report source summary is present",
            failure_message="control report source summary is missing",
        ),
        _check(
            name="explicit_exclusions_present",
            passed=_has_required_exclusions(assembled_source),
            severity="blocker",
            message="control report source assembler exclusions are present",
            failure_message="one or more required exclusions are missing",
        ),
        _check(
            name="no_order_intents_created",
            passed=not _contains_non_null_key(assembled_source, "order_intent"),
            severity="blocker",
            message="control report source assembler did not create order intents",
            failure_message="control report source assembler created one or more order intents",
        ),
        _check(
            name="no_broker_order_ids_created",
            passed=not _contains_non_null_key(assembled_source, "broker_order_id"),
            severity="blocker",
            message="control report source assembler did not create broker order ids",
            failure_message="control report source assembler created one or more broker order ids",
        ),
        _check(
            name="no_automatic_actions_created",
            passed=not _contains_non_null_key(
                assembled_source,
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
            message="control report source assembler did not create automatic actions",
            failure_message="control report source assembler created one or more automatic actions",
        ),
        _check(
            name="blocked_items_have_reasons",
            passed=_blocked_items_have_reasons(assembled_source),
            severity="warning",
            message="blocked source assembler items include reasons",
            failure_message="one or more blocked source assembler items are missing reasons",
        ),
    ]

    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_audit_status(
            source_status=str(assembled_source.get("status", "needs_review")),
            checks=checks,
        ),
        "summary": _summarize_checks(checks),
        "checks": checks,
        "explicit_exclusions": list(assembled_source.get("explicit_exclusions", [])),
    }


def build_options_portfolio_control_report_source_assembler_health_report(
    assembled_source: Mapping[str, Any],
) -> dict[str, Any]:
    source_status = str(assembled_source.get("status", "needs_review"))
    source_summary = _as_mapping(assembled_source.get("source_summary"))
    loaded_artifacts = _as_list(assembled_source.get("loaded_artifacts"))
    missing_artifacts = _as_list(assembled_source.get("missing_artifacts"))
    blocked_items = _as_list(assembled_source.get("blocked_items"))

    indicators = {
        "source_status": source_status,
        "report_date": _string_or_none(assembled_source.get("report_date")),
        "control_section_count": _safe_int(source_summary.get("control_section_count")),
        "loaded_artifact_count": _safe_int(source_summary.get("loaded_artifact_count")),
        "file_artifact_count": _safe_int(source_summary.get("file_artifact_count")),
        "direct_artifact_count": _safe_int(source_summary.get("direct_artifact_count")),
        "missing_artifact_count": len(missing_artifacts),
        "blocked_item_count": len(blocked_items),
        "ready_artifact_count": _safe_int(source_summary.get("ready_artifact_count")),
        "needs_review_artifact_count": _safe_int(
            source_summary.get("needs_review_artifact_count")
        ),
        "blocked_artifact_count": _safe_int(source_summary.get("blocked_artifact_count")),
        "loaded_record_count": len(loaded_artifacts),
        "has_loaded_artifacts": bool(loaded_artifacts),
        "has_missing_artifacts": bool(missing_artifacts),
        "has_blocked_items": bool(blocked_items),
        "has_order_intent": _contains_non_null_key(assembled_source, "order_intent"),
        "has_broker_order_id": _contains_non_null_key(assembled_source, "broker_order_id"),
        "has_automatic_action": _contains_non_null_key(
            assembled_source,
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
            source_status=source_status,
            indicators=indicators,
        ),
        "indicators": indicators,
        "explicit_exclusions": list(assembled_source.get("explicit_exclusions", [])),
    }


def _build_operation_record(
    *,
    assembled_source: Mapping[str, Any],
    audit_report: Mapping[str, Any],
    health_report: Mapping[str, Any],
    operation_status: str,
    base_dir: str | PathLike[str] | None,
    event_log_path: Path | None,
    metadata: Mapping[str, Any] | None,
) -> dict[str, Any]:
    source_summary = _as_mapping(assembled_source.get("source_summary"))

    return {
        "operation_type": OPERATION_TYPE,
        "schema_version": OPERATION_SCHEMA_VERSION,
        "status": operation_status,
        "report_date": _string_or_none(assembled_source.get("report_date")),
        "base_dir": str(base_dir) if base_dir is not None else None,
        "operation_summary": {
            "control_section_count": _safe_int(source_summary.get("control_section_count")),
            "loaded_artifact_count": _safe_int(source_summary.get("loaded_artifact_count")),
            "file_artifact_count": _safe_int(source_summary.get("file_artifact_count")),
            "direct_artifact_count": _safe_int(source_summary.get("direct_artifact_count")),
            "missing_artifact_count": _safe_int(source_summary.get("missing_artifact_count")),
            "blocked_item_count": _safe_int(source_summary.get("blocked_item_count")),
            "ready_artifact_count": _safe_int(source_summary.get("ready_artifact_count")),
            "needs_review_artifact_count": _safe_int(
                source_summary.get("needs_review_artifact_count")
            ),
            "blocked_artifact_count": _safe_int(source_summary.get("blocked_artifact_count")),
            "audit_status": audit_report.get("status"),
            "health_status": health_report.get("status"),
        },
        "event_log_path": str(event_log_path) if event_log_path else None,
        "metadata": dict(metadata or {}),
        "explicit_exclusions": list(assembled_source.get("explicit_exclusions", [])),
    }


def _build_event(
    *,
    assembled_source: Mapping[str, Any],
    event_type: str,
    sequence: int,
    status: str,
) -> dict[str, Any]:
    source_summary = _as_mapping(assembled_source.get("source_summary"))

    return {
        "schema_version": EVENT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "event_type": event_type,
        "sequence": sequence,
        "status": status,
        "report_date": _string_or_none(assembled_source.get("report_date")),
        "loaded_artifact_count": _safe_int(source_summary.get("loaded_artifact_count")),
        "missing_artifact_count": _safe_int(source_summary.get("missing_artifact_count")),
        "blocked_item_count": _safe_int(source_summary.get("blocked_item_count")),
    }


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
    source_status: str,
    audit_status: str,
    health_status: str,
) -> str:
    if "blocked" in {source_status, audit_status, health_status}:
        return "blocked"
    if "needs_review" in {source_status, audit_status, health_status}:
        return "needs_review"
    return "ready"


def _classify_audit_status(
    *,
    source_status: str,
    checks: Sequence[Mapping[str, Any]],
) -> str:
    if any(check.get("passed") is not True and check.get("severity") == "blocker" for check in checks):
        return "blocked"
    if source_status == "blocked":
        return "blocked"
    if source_status == "needs_review" or any(check.get("passed") is not True for check in checks):
        return "needs_review"
    return "ready"


def _classify_health_status(
    *,
    source_status: str,
    indicators: Mapping[str, Any],
) -> str:
    if (
        indicators.get("has_order_intent")
        or indicators.get("has_broker_order_id")
        or indicators.get("has_automatic_action")
    ):
        return "blocked"
    if source_status == "blocked" or indicators.get("has_blocked_items"):
        return "blocked"
    if source_status == "needs_review" or indicators.get("has_missing_artifacts"):
        return "needs_review"
    return "ready"


def _has_required_exclusions(assembled_source: Mapping[str, Any]) -> bool:
    exclusions = set(_as_list(assembled_source.get("explicit_exclusions")))
    return all(item in exclusions for item in REQUIRED_EXCLUSIONS)


def _blocked_items_have_reasons(assembled_source: Mapping[str, Any]) -> bool:
    return all(
        bool(_as_mapping(item).get("reason"))
        for item in _as_list(assembled_source.get("blocked_items"))
    )


def _contains_non_null_key(value: Any, *keys: str) -> bool:
    if isinstance(value, Mapping):
        for key in keys:
            if key in value and value.get(key) is not None:
                return True
        return any(_contains_non_null_key(item, *keys) for item in value.values())

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_non_null_key(item, *keys) for item in value)

    return False


def _normalize_event_log_path(path: str | PathLike[str] | None) -> Path | None:
    if path is None:
        return None
    normalized = Path(path)
    normalized.parent.mkdir(parents=True, exist_ok=True)
    return normalized


def _write_jsonl_event_log(path: Path, events: Sequence[Mapping[str, Any]]) -> None:
    path = Path(path)
    parent = path.parent
    os.makedirs(parent, exist_ok=True)

    # Force Windows to materialize the directory before opening the JSONL.
    sentinel = parent / ".write_check"
    sentinel.write_text("", encoding="utf-8")
    sentinel.unlink(missing_ok=True)

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

