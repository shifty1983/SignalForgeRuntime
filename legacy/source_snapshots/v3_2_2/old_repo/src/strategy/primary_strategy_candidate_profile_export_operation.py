from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

from src.strategy.primary_strategy_candidate_profile_export import (
    EXPLICIT_EXCLUSIONS,
    export_primary_strategy_candidate_profile,
)


ADAPTER_TYPE = "primary_strategy_candidate_profile_export_operation"

OPERATION_RECORD_ARTIFACT_TYPE = (
    "signalforge_primary_strategy_candidate_profile_export_operation_record"
)
OPERATION_LOG_ARTIFACT_TYPE = (
    "signalforge_primary_strategy_candidate_profile_export_operation_log"
)
AUDIT_ARTIFACT_TYPE = (
    "signalforge_primary_strategy_candidate_profile_export_operation_audit_report"
)
HEALTH_ARTIFACT_TYPE = (
    "signalforge_primary_strategy_candidate_profile_export_operation_health_report"
)
WRITE_RESULT_ARTIFACT_TYPE = (
    "primary_strategy_candidate_profile_export_operation_write_result"
)

OPERATION_RECORD_FILENAME = (
    "signalforge_primary_strategy_candidate_profile_export_operation_record.json"
)
OPERATION_LOG_FILENAME = (
    "signalforge_primary_strategy_candidate_profile_export_operation_log.jsonl"
)
AUDIT_FILENAME = (
    "signalforge_primary_strategy_candidate_profile_export_operation_audit.json"
)
HEALTH_FILENAME = (
    "signalforge_primary_strategy_candidate_profile_export_operation_health.json"
)


def run_primary_strategy_candidate_profile_export_operation(
    *,
    source_path: str | Path,
    output_dir: str | Path,
    selected_window_days: int = 21,
) -> Dict[str, Any]:
    output_dir_obj = Path(output_dir)
    output_dir_obj.mkdir(parents=True, exist_ok=True)

    operation_record_path = output_dir_obj / OPERATION_RECORD_FILENAME
    operation_log_path = output_dir_obj / OPERATION_LOG_FILENAME
    audit_path = output_dir_obj / AUDIT_FILENAME
    health_path = output_dir_obj / HEALTH_FILENAME

    try:
        export_result = export_primary_strategy_candidate_profile(
            source_path=source_path,
            output_dir=output_dir_obj,
            selected_window_days=selected_window_days,
        )
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        export_result = _blocked_export_result(
            source_path=source_path,
            output_dir=output_dir_obj,
            selected_window_days=selected_window_days,
            blocked_reasons=[
                "primary_strategy_candidate_profile_export_failed",
                f"{type(exc).__name__}: {exc}",
            ],
        )

    operation_paths = {
        "operation_record": str(operation_record_path),
        "operation_log": str(operation_log_path),
        "audit": str(audit_path),
        "health": str(health_path),
        "export": export_result.get("export_path"),
        "summary": export_result.get("summary_path"),
    }

    operation_record = build_primary_strategy_candidate_profile_export_operation_record(
        export_result,
        source_path=str(source_path),
        output_dir=str(output_dir_obj),
        selected_window_days=selected_window_days,
        operation_paths=operation_paths,
    )

    audit_report = build_primary_strategy_candidate_profile_export_operation_audit(
        operation_record
    )
    health_report = build_primary_strategy_candidate_profile_export_operation_health(
        operation_record
    )
    operation_log_event = build_primary_strategy_candidate_profile_export_operation_log_event(
        operation_record
    )

    _write_json(operation_record_path, operation_record)
    _write_json(audit_path, audit_report)
    _write_json(health_path, health_report)
    _write_jsonl(operation_log_path, [operation_log_event])

    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": WRITE_RESULT_ARTIFACT_TYPE,
        "operation_id": operation_record["operation_id"],
        "operation_state": operation_record["operation_state"],
        "profile_export_state": operation_record["profile_export_state"],
        "selected_window_days": selected_window_days,
        "source_path": str(source_path),
        "output_dir": str(output_dir_obj),
        "primary_candidate_id": operation_record["primary_candidate_id"],
        "primary_symbol": operation_record["primary_symbol"],
        "primary_strategy_family": operation_record["primary_strategy_family"],
        "candidate_profile_count": operation_record["candidate_profile_count"],
        "blocked_reasons": operation_record["blocked_reasons"],
        "warnings": operation_record["warnings"],
        "operation_record_path": str(operation_record_path),
        "operation_log_path": str(operation_log_path),
        "audit_path": str(audit_path),
        "health_path": str(health_path),
        "export_path": export_result.get("export_path"),
        "summary_path": export_result.get("summary_path"),
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def build_primary_strategy_candidate_profile_export_operation_record(
    export_result: Any,
    *,
    source_path: Optional[str],
    output_dir: Optional[str],
    selected_window_days: int,
    operation_paths: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    if not isinstance(export_result, Mapping):
        export_result = _blocked_export_result(
            source_path=source_path,
            output_dir=output_dir,
            selected_window_days=selected_window_days,
            blocked_reasons=[
                "export_result_invalid_shape",
                "export_result_must_be_json_object",
            ],
        )

    profile_export_state = str(export_result.get("profile_export_state") or "blocked")
    operation_state = _classify_operation_state(profile_export_state)

    blocked_reasons = _dedupe_strings(export_result.get("blocked_reasons", []))
    warnings = _dedupe_strings(export_result.get("warnings", []))

    operation_id = _stable_operation_id(
        {
            "adapter_type": ADAPTER_TYPE,
            "source_path": source_path,
            "selected_window_days": selected_window_days,
            "profile_export_state": profile_export_state,
            "primary_candidate_id": export_result.get("primary_candidate_id"),
            "primary_strategy_family": export_result.get("primary_strategy_family"),
            "candidate_profile_count": export_result.get("candidate_profile_count", 0),
            "blocked_reasons": blocked_reasons,
            "warnings": warnings,
        }
    )

    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": OPERATION_RECORD_ARTIFACT_TYPE,
        "operation_id": operation_id,
        "operation_state": operation_state,
        "profile_export_state": profile_export_state,
        "selected_window_days": selected_window_days,
        "source_path": source_path,
        "output_dir": output_dir,
        "primary_candidate_id": export_result.get("primary_candidate_id"),
        "primary_symbol": export_result.get("primary_symbol"),
        "primary_strategy_family": export_result.get("primary_strategy_family"),
        "candidate_profile_count": export_result.get("candidate_profile_count", 0),
        "blocked_reasons": blocked_reasons,
        "warnings": warnings,
        "operation_scope": "primary_strategy_candidate_profile_export",
        "depends_on_artifacts": [
            "signalforge_portfolio_candidate_selection_summary",
        ],
        "produced_artifacts": [
            "signalforge_primary_strategy_candidate_profile_export",
            "signalforge_primary_strategy_candidate_profile_export_summary",
            OPERATION_RECORD_ARTIFACT_TYPE,
            OPERATION_LOG_ARTIFACT_TYPE,
            AUDIT_ARTIFACT_TYPE,
            HEALTH_ARTIFACT_TYPE,
        ],
        "output_files": dict(operation_paths or {}),
        "automatic_action": None,
        "automatic_close_order": None,
        "automatic_defense_order": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "automatic_roll_order": None,
        "automatic_strategy_change": None,
        "requires_manual_approval": False,
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def build_primary_strategy_candidate_profile_export_operation_log_event(
    operation_record: Mapping[str, Any],
) -> Dict[str, Any]:
    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": OPERATION_LOG_ARTIFACT_TYPE,
        "event_type": "primary_strategy_candidate_profile_export_operation_completed",
        "operation_id": operation_record.get("operation_id"),
        "operation_state": operation_record.get("operation_state"),
        "profile_export_state": operation_record.get("profile_export_state"),
        "selected_window_days": operation_record.get("selected_window_days"),
        "primary_candidate_id": operation_record.get("primary_candidate_id"),
        "primary_symbol": operation_record.get("primary_symbol"),
        "primary_strategy_family": operation_record.get("primary_strategy_family"),
        "candidate_profile_count": operation_record.get("candidate_profile_count", 0),
        "blocked_reasons": operation_record.get("blocked_reasons", []),
        "warnings": operation_record.get("warnings", []),
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def build_primary_strategy_candidate_profile_export_operation_audit(
    operation_record: Mapping[str, Any],
) -> Dict[str, Any]:
    output_files = operation_record.get("output_files") or {}

    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": AUDIT_ARTIFACT_TYPE,
        "operation_id": operation_record.get("operation_id"),
        "audit_state": operation_record.get("operation_state"),
        "profile_export_state": operation_record.get("profile_export_state"),
        "selected_window_days": operation_record.get("selected_window_days"),
        "primary_candidate_id": operation_record.get("primary_candidate_id"),
        "primary_strategy_family": operation_record.get("primary_strategy_family"),
        "checks": {
            "source_path_present": bool(operation_record.get("source_path")),
            "selected_window_days_present": operation_record.get("selected_window_days")
            is not None,
            "primary_candidate_present": bool(
                operation_record.get("primary_candidate_id")
            ),
            "operation_record_path_present": bool(output_files.get("operation_record")),
            "operation_log_path_present": bool(output_files.get("operation_log")),
            "audit_path_present": bool(output_files.get("audit")),
            "health_path_present": bool(output_files.get("health")),
            "export_path_present": bool(output_files.get("export")),
            "summary_path_present": bool(output_files.get("summary")),
            "explicit_exclusions_preserved": operation_record.get("explicit_exclusions")
            == EXPLICIT_EXCLUSIONS,
            "no_broker_or_live_execution_fields_enabled": _no_execution_fields_enabled(
                operation_record
            ),
        },
        "blocked_reasons": operation_record.get("blocked_reasons", []),
        "warnings": operation_record.get("warnings", []),
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def build_primary_strategy_candidate_profile_export_operation_health(
    operation_record: Mapping[str, Any],
) -> Dict[str, Any]:
    operation_state = operation_record.get("operation_state")
    blocked_reasons = operation_record.get("blocked_reasons", [])
    warnings = operation_record.get("warnings", [])

    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": HEALTH_ARTIFACT_TYPE,
        "operation_id": operation_record.get("operation_id"),
        "health_state": operation_state,
        "is_ready": operation_state == "ready",
        "needs_review": operation_state == "needs_review",
        "is_blocked": operation_state == "blocked",
        "selected_window_days": operation_record.get("selected_window_days"),
        "primary_candidate_id": operation_record.get("primary_candidate_id"),
        "primary_symbol": operation_record.get("primary_symbol"),
        "primary_strategy_family": operation_record.get("primary_strategy_family"),
        "candidate_profile_count": operation_record.get("candidate_profile_count", 0),
        "blocked_reason_count": len(blocked_reasons),
        "warning_count": len(warnings),
        "blocked_reasons": blocked_reasons,
        "warnings": warnings,
        "next_recommended_action": _next_recommended_action(operation_state),
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def _blocked_export_result(
    *,
    source_path: str | Path | None,
    output_dir: str | Path | None,
    selected_window_days: int,
    blocked_reasons: Sequence[str],
) -> Dict[str, Any]:
    return {
        "adapter_type": "primary_strategy_candidate_profile_export",
        "artifact_type": "primary_strategy_candidate_profile_export_write_result",
        "profile_export_state": "blocked",
        "selected_window_days": selected_window_days,
        "source_path": str(source_path) if source_path is not None else None,
        "output_dir": str(output_dir) if output_dir is not None else None,
        "export_path": None,
        "summary_path": None,
        "primary_candidate_id": None,
        "primary_symbol": None,
        "primary_strategy_family": None,
        "candidate_profile_count": 0,
        "blocked_reasons": _dedupe_strings(blocked_reasons),
        "warnings": [],
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def _classify_operation_state(profile_export_state: str) -> str:
    if profile_export_state in {"ready", "needs_review", "blocked"}:
        return profile_export_state

    return "blocked"


def _stable_operation_id(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, default=str)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return f"primary_strategy_candidate_profile_export_operation_{digest}"


def _dedupe_strings(values: Any) -> list[str]:
    if values is None:
        return []

    if isinstance(values, str):
        values = [values]

    if not isinstance(values, Sequence):
        return [str(values)]

    deduped: list[str] = []
    seen: set[str] = set()

    for value in values:
        clean_value = str(value).strip()
        if clean_value and clean_value not in seen:
            seen.add(clean_value)
            deduped.append(clean_value)

    return deduped


def _no_execution_fields_enabled(operation_record: Mapping[str, Any]) -> bool:
    execution_fields = [
        "automatic_action",
        "automatic_close_order",
        "automatic_defense_order",
        "automatic_parameter_change",
        "automatic_pause_action",
        "automatic_roll_order",
        "automatic_strategy_change",
    ]

    return all(operation_record.get(field) is None for field in execution_fields)


def _next_recommended_action(operation_state: Any) -> str:
    if operation_state == "ready":
        return "use_primary_strategy_candidate_profile_export_as_downstream_strategy_input"

    if operation_state == "needs_review":
        return "review_primary_strategy_candidate_profile_export_warnings_before_downstream_use"

    return "resolve_primary_strategy_candidate_profile_export_blockers_before_downstream_use"


def _write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, sort_keys=True)
        file.write("\n")


def _write_jsonl(path: str | Path, events: Sequence[Mapping[str, Any]]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as file:
        for event in events:
            file.write(json.dumps(event, sort_keys=True))
            file.write("\n")