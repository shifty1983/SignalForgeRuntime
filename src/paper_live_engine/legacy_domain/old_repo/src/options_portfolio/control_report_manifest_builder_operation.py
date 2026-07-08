from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from os import PathLike
from pathlib import Path
from typing import Any

from src.options_portfolio.control_report_manifest_builder import (
    EXPLICIT_EXCLUSIONS,
    build_options_portfolio_control_report_artifact_manifest,
)


OPERATION_SCHEMA_VERSION = "options_portfolio_control_report_manifest_builder_operation.v1"
EVENT_SCHEMA_VERSION = "options_portfolio_control_report_manifest_builder_event.v1"
AUDIT_SCHEMA_VERSION = "options_portfolio_control_report_manifest_builder_audit.v1"
HEALTH_SCHEMA_VERSION = "options_portfolio_control_report_manifest_builder_health.v1"

OPERATION_TYPE = "options_portfolio_control_report_manifest_builder_operation"
VALID_MANIFEST_STATUSES = {"ready", "needs_review", "blocked"}
REQUIRED_EXCLUSIONS = tuple(EXPLICIT_EXCLUSIONS)


def run_options_portfolio_control_report_manifest_builder_operation(
    source: Mapping[str, Any] | None,
    *,
    base_dir: str | PathLike[str] | None = None,
    metadata: Mapping[str, Any] | None = None,
    event_log_path: str | PathLike[str] | None = None,
) -> dict[str, Any]:
    manifest_artifact = build_options_portfolio_control_report_artifact_manifest(
        source or {},
        base_dir=base_dir,
    )
    audit_report = build_options_portfolio_control_report_manifest_builder_audit_report(
        manifest_artifact
    )
    health_report = build_options_portfolio_control_report_manifest_builder_health_report(
        manifest_artifact
    )

    operation_status = _classify_operation_status(
        manifest_status=str(manifest_artifact.get("status", "needs_review")),
        audit_status=str(audit_report.get("status", "needs_review")),
        health_status=str(health_report.get("status", "needs_review")),
    )

    events = [
        _build_event(
            manifest_artifact=manifest_artifact,
            event_type="options_portfolio_control_report_manifest_builder_started",
            sequence=1,
            status=operation_status,
        ),
        _build_event(
            manifest_artifact=manifest_artifact,
            event_type="options_portfolio_control_report_manifest_builder_completed",
            sequence=2,
            status=operation_status,
        ),
    ]

    normalized_log_path = _normalize_event_log_path(event_log_path)
    if normalized_log_path is not None:
        _write_jsonl_event_log(normalized_log_path, events)

    operation_record = _build_operation_record(
        manifest_artifact=manifest_artifact,
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
        "options_portfolio_control_report_artifact_manifest": manifest_artifact,
        "events": events,
        "event_log_path": str(normalized_log_path) if normalized_log_path else None,
        "explicit_exclusions": list(manifest_artifact.get("explicit_exclusions", [])),
    }


def build_options_portfolio_control_report_manifest_builder_audit_report(
    manifest_artifact: Mapping[str, Any],
) -> dict[str, Any]:
    checks = [
        _check(
            name="manifest_artifact_type_valid",
            passed=manifest_artifact.get("artifact_type")
            == "options_portfolio_control_report_artifact_manifest",
            severity="blocker",
            message="control report artifact manifest type is valid",
            failure_message="control report artifact manifest type is invalid",
        ),
        _check(
            name="manifest_status_valid",
            passed=manifest_artifact.get("status") in VALID_MANIFEST_STATUSES,
            severity="blocker",
            message="control report artifact manifest status is valid",
            failure_message="control report artifact manifest status is invalid",
        ),
        _check(
            name="manifest_present",
            passed=isinstance(manifest_artifact.get("manifest"), Mapping),
            severity="blocker",
            message="control report artifact manifest payload is present",
            failure_message="control report artifact manifest payload is missing",
        ),
        _check(
            name="manifest_summary_present",
            passed=isinstance(manifest_artifact.get("manifest_summary"), Mapping),
            severity="blocker",
            message="control report artifact manifest summary is present",
            failure_message="control report artifact manifest summary is missing",
        ),
        _check(
            name="explicit_exclusions_present",
            passed=_has_required_exclusions(manifest_artifact),
            severity="blocker",
            message="control report artifact manifest exclusions are present",
            failure_message="one or more required exclusions are missing",
        ),
        _check(
            name="artifact_paths_shape_valid",
            passed=_artifact_paths_shape_valid(manifest_artifact),
            severity="blocker",
            message="control report artifact paths shape is valid",
            failure_message="control report artifact paths shape is invalid",
        ),
        _check(
            name="blocked_items_have_reasons",
            passed=_items_have_reasons(manifest_artifact, "blocked_items"),
            severity="warning",
            message="blocked manifest items include reasons",
            failure_message="one or more blocked manifest items are missing reasons",
        ),
        _check(
            name="missing_artifacts_have_reasons",
            passed=_items_have_reasons(manifest_artifact, "missing_artifacts"),
            severity="warning",
            message="missing manifest artifacts include reasons",
            failure_message="one or more missing manifest artifacts are missing reasons",
        ),
        _check(
            name="ambiguous_artifacts_have_reasons",
            passed=_items_have_reasons(manifest_artifact, "ambiguous_artifacts"),
            severity="warning",
            message="ambiguous manifest artifacts include reasons",
            failure_message="one or more ambiguous manifest artifacts are missing reasons",
        ),
        _check(
            name="no_order_intents_created",
            passed=not _contains_non_null_key(manifest_artifact, "order_intent"),
            severity="blocker",
            message="manifest builder did not create order intents",
            failure_message="manifest builder created one or more order intents",
        ),
        _check(
            name="no_broker_order_ids_created",
            passed=not _contains_non_null_key(manifest_artifact, "broker_order_id"),
            severity="blocker",
            message="manifest builder did not create broker order ids",
            failure_message="manifest builder created one or more broker order ids",
        ),
        _check(
            name="no_automatic_actions_created",
            passed=not _contains_non_null_key(
                manifest_artifact,
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
            message="manifest builder did not create automatic actions",
            failure_message="manifest builder created one or more automatic actions",
        ),
    ]

    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": _classify_audit_status(
            manifest_status=str(manifest_artifact.get("status", "needs_review")),
            checks=checks,
        ),
        "summary": _summarize_checks(checks),
        "checks": checks,
        "explicit_exclusions": list(manifest_artifact.get("explicit_exclusions", [])),
    }


def build_options_portfolio_control_report_manifest_builder_health_report(
    manifest_artifact: Mapping[str, Any],
) -> dict[str, Any]:
    manifest_status = str(manifest_artifact.get("status", "needs_review"))
    manifest_summary = _as_mapping(manifest_artifact.get("manifest_summary"))
    manifest = _as_mapping(manifest_artifact.get("manifest"))
    artifact_paths = _as_mapping(manifest.get("artifact_paths"))

    indicators = {
        "manifest_status": manifest_status,
        "report_date": _string_or_none(manifest_artifact.get("report_date")),
        "control_section_count": _safe_int(manifest_summary.get("control_section_count")),
        "found_artifact_count": _safe_int(manifest_summary.get("found_artifact_count")),
        "preferred_artifact_count": _safe_int(manifest_summary.get("preferred_artifact_count")),
        "discovered_artifact_count": _safe_int(manifest_summary.get("discovered_artifact_count")),
        "missing_artifact_count": _safe_int(manifest_summary.get("missing_artifact_count")),
        "ambiguous_artifact_count": _safe_int(manifest_summary.get("ambiguous_artifact_count")),
        "blocked_item_count": _safe_int(manifest_summary.get("blocked_item_count")),
        "artifact_path_count": len(artifact_paths),
        "has_artifact_paths": bool(artifact_paths),
        "has_missing_artifacts": bool(_as_list(manifest_artifact.get("missing_artifacts"))),
        "has_ambiguous_artifacts": bool(_as_list(manifest_artifact.get("ambiguous_artifacts"))),
        "has_blocked_items": bool(_as_list(manifest_artifact.get("blocked_items"))),
        "has_order_intent": _contains_non_null_key(manifest_artifact, "order_intent"),
        "has_broker_order_id": _contains_non_null_key(manifest_artifact, "broker_order_id"),
        "has_automatic_action": _contains_non_null_key(
            manifest_artifact,
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
            manifest_status=manifest_status,
            indicators=indicators,
        ),
        "indicators": indicators,
        "explicit_exclusions": list(manifest_artifact.get("explicit_exclusions", [])),
    }


def _build_operation_record(
    *,
    manifest_artifact: Mapping[str, Any],
    audit_report: Mapping[str, Any],
    health_report: Mapping[str, Any],
    operation_status: str,
    base_dir: str | PathLike[str] | None,
    event_log_path: Path | None,
    metadata: Mapping[str, Any] | None,
) -> dict[str, Any]:
    manifest_summary = _as_mapping(manifest_artifact.get("manifest_summary"))

    return {
        "operation_type": OPERATION_TYPE,
        "schema_version": OPERATION_SCHEMA_VERSION,
        "status": operation_status,
        "report_date": _string_or_none(manifest_artifact.get("report_date")),
        "base_dir": str(base_dir) if base_dir is not None else None,
        "operation_summary": {
            "control_section_count": _safe_int(manifest_summary.get("control_section_count")),
            "found_artifact_count": _safe_int(manifest_summary.get("found_artifact_count")),
            "preferred_artifact_count": _safe_int(manifest_summary.get("preferred_artifact_count")),
            "discovered_artifact_count": _safe_int(manifest_summary.get("discovered_artifact_count")),
            "missing_artifact_count": _safe_int(manifest_summary.get("missing_artifact_count")),
            "ambiguous_artifact_count": _safe_int(manifest_summary.get("ambiguous_artifact_count")),
            "blocked_item_count": _safe_int(manifest_summary.get("blocked_item_count")),
            "audit_status": audit_report.get("status"),
            "health_status": health_report.get("status"),
        },
        "event_log_path": str(event_log_path) if event_log_path else None,
        "metadata": dict(metadata or {}),
        "explicit_exclusions": list(manifest_artifact.get("explicit_exclusions", [])),
    }


def _build_event(
    *,
    manifest_artifact: Mapping[str, Any],
    event_type: str,
    sequence: int,
    status: str,
) -> dict[str, Any]:
    manifest_summary = _as_mapping(manifest_artifact.get("manifest_summary"))

    return {
        "schema_version": EVENT_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "event_type": event_type,
        "sequence": sequence,
        "status": status,
        "manifest_status": manifest_artifact.get("status"),
        "report_date": _string_or_none(manifest_artifact.get("report_date")),
        "found_artifact_count": _safe_int(manifest_summary.get("found_artifact_count")),
        "missing_artifact_count": _safe_int(manifest_summary.get("missing_artifact_count")),
        "ambiguous_artifact_count": _safe_int(manifest_summary.get("ambiguous_artifact_count")),
        "blocked_item_count": _safe_int(manifest_summary.get("blocked_item_count")),
    }


def _artifact_paths_shape_valid(manifest_artifact: Mapping[str, Any]) -> bool:
    manifest = _as_mapping(manifest_artifact.get("manifest"))
    artifact_paths = manifest.get("artifact_paths")
    if not isinstance(artifact_paths, Mapping):
        return False
    return all(isinstance(key, str) and isinstance(value, str) for key, value in artifact_paths.items())


def _has_required_exclusions(manifest_artifact: Mapping[str, Any]) -> bool:
    exclusions = set(_as_list(manifest_artifact.get("explicit_exclusions")))
    return all(item in exclusions for item in REQUIRED_EXCLUSIONS)


def _items_have_reasons(manifest_artifact: Mapping[str, Any], key: str) -> bool:
    return all(bool(_as_mapping(item).get("reason")) for item in _as_list(manifest_artifact.get(key)))


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
    manifest_status: str,
    audit_status: str,
    health_status: str,
) -> str:
    if "blocked" in {manifest_status, audit_status, health_status}:
        return "blocked"
    if "needs_review" in {manifest_status, audit_status, health_status}:
        return "needs_review"
    return "ready"


def _classify_audit_status(
    *,
    manifest_status: str,
    checks: Sequence[Mapping[str, Any]],
) -> str:
    if any(check.get("passed") is not True and check.get("severity") == "blocker" for check in checks):
        return "blocked"
    if manifest_status == "blocked":
        return "blocked"
    if manifest_status == "needs_review" or any(check.get("passed") is not True for check in checks):
        return "needs_review"
    return "ready"


def _classify_health_status(
    *,
    manifest_status: str,
    indicators: Mapping[str, Any],
) -> str:
    if (
        indicators.get("has_order_intent")
        or indicators.get("has_broker_order_id")
        or indicators.get("has_automatic_action")
    ):
        return "blocked"
    if manifest_status == "blocked" or indicators.get("has_blocked_items"):
        return "blocked"
    if (
        manifest_status == "needs_review"
        or indicators.get("has_missing_artifacts")
        or indicators.get("has_ambiguous_artifacts")
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

