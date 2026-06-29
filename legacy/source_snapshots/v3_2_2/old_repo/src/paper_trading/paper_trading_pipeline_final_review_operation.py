from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

from src.paper_trading.paper_trading_pipeline_final_review_summary import (
    EXPLICIT_EXCLUSIONS,
    export_paper_trading_pipeline_final_review_summary,
)


ADAPTER_TYPE = "paper_trading_pipeline_final_review_operation"

OPERATION_RECORD_ARTIFACT_TYPE = (
    "signalforge_paper_trading_pipeline_final_review_operation_record"
)
OPERATION_LOG_ARTIFACT_TYPE = (
    "signalforge_paper_trading_pipeline_final_review_operation_log"
)
AUDIT_ARTIFACT_TYPE = (
    "signalforge_paper_trading_pipeline_final_review_operation_audit_report"
)
HEALTH_ARTIFACT_TYPE = (
    "signalforge_paper_trading_pipeline_final_review_operation_health_report"
)
WRITE_RESULT_ARTIFACT_TYPE = "paper_trading_pipeline_final_review_operation_write_result"

OPERATION_RECORD_FILENAME = (
    "signalforge_paper_trading_pipeline_final_review_operation_record.json"
)
OPERATION_LOG_FILENAME = (
    "signalforge_paper_trading_pipeline_final_review_operation_log.jsonl"
)
AUDIT_FILENAME = "signalforge_paper_trading_pipeline_final_review_operation_audit.json"
HEALTH_FILENAME = "signalforge_paper_trading_pipeline_final_review_operation_health.json"

EXECUTION_DISABLED_FIELDS = {
    "automatic_action": None,
    "automatic_close_order": None,
    "automatic_defense_order": None,
    "automatic_parameter_change": None,
    "automatic_pause_action": None,
    "automatic_roll_order": None,
    "automatic_strategy_change": None,
}


def run_paper_trading_pipeline_final_review_operation(
    *,
    primary_strategy_candidate_profile_operation_path: str | Path,
    ibkr_paper_trading_readiness_operation_path: str | Path,
    ibkr_paper_connection_smoke_test_operation_path: str | Path,
    ibkr_paper_account_snapshot_operation_path: str | Path,
    primary_strategy_paper_order_intent_operation_path: str | Path,
    ibkr_option_contract_resolver_operation_path: str | Path,
    ibkr_option_quote_validation_operation_path: str | Path,
    paper_order_preview_operation_path: str | Path,
    manual_approval_ticket_operation_path: str | Path,
    output_dir: str | Path,
) -> Dict[str, Any]:
    output_dir_obj = Path(output_dir)
    output_dir_obj.mkdir(parents=True, exist_ok=True)

    operation_record_path = output_dir_obj / OPERATION_RECORD_FILENAME
    operation_log_path = output_dir_obj / OPERATION_LOG_FILENAME
    audit_path = output_dir_obj / AUDIT_FILENAME
    health_path = output_dir_obj / HEALTH_FILENAME

    try:
        summary_result = export_paper_trading_pipeline_final_review_summary(
            primary_strategy_candidate_profile_operation_path=primary_strategy_candidate_profile_operation_path,
            ibkr_paper_trading_readiness_operation_path=ibkr_paper_trading_readiness_operation_path,
            ibkr_paper_connection_smoke_test_operation_path=ibkr_paper_connection_smoke_test_operation_path,
            ibkr_paper_account_snapshot_operation_path=ibkr_paper_account_snapshot_operation_path,
            primary_strategy_paper_order_intent_operation_path=primary_strategy_paper_order_intent_operation_path,
            ibkr_option_contract_resolver_operation_path=ibkr_option_contract_resolver_operation_path,
            ibkr_option_quote_validation_operation_path=ibkr_option_quote_validation_operation_path,
            paper_order_preview_operation_path=paper_order_preview_operation_path,
            manual_approval_ticket_operation_path=manual_approval_ticket_operation_path,
            output_dir=output_dir_obj,
        )
        summary_result = hydrate_final_review_summary_result_details(summary_result)
    except Exception as exc:  # pragma: no cover
        summary_result = _blocked_summary_result(
            blocked_reasons=[
                "paper_trading_pipeline_final_review_summary_failed",
                f"{type(exc).__name__}: {exc}",
            ],
        )

    source_paths = {
        "primary_strategy_candidate_profile": str(
            primary_strategy_candidate_profile_operation_path
        ),
        "ibkr_paper_trading_readiness": str(
            ibkr_paper_trading_readiness_operation_path
        ),
        "ibkr_paper_connection_smoke_test": str(
            ibkr_paper_connection_smoke_test_operation_path
        ),
        "ibkr_paper_account_snapshot": str(ibkr_paper_account_snapshot_operation_path),
        "primary_strategy_paper_order_intent": str(
            primary_strategy_paper_order_intent_operation_path
        ),
        "ibkr_option_contract_resolver": str(
            ibkr_option_contract_resolver_operation_path
        ),
        "ibkr_option_quote_validation": str(
            ibkr_option_quote_validation_operation_path
        ),
        "paper_order_preview": str(paper_order_preview_operation_path),
        "manual_approval_ticket": str(manual_approval_ticket_operation_path),
    }

    operation_paths = {
        "summary": summary_result.get("summary_path"),
        "operation_record": str(operation_record_path),
        "operation_log": str(operation_log_path),
        "audit": str(audit_path),
        "health": str(health_path),
    }

    operation_record = build_paper_trading_pipeline_final_review_operation_record(
        summary_result,
        source_paths=source_paths,
        output_dir=str(output_dir_obj),
        operation_paths=operation_paths,
    )

    audit_report = build_paper_trading_pipeline_final_review_operation_audit(
        operation_record
    )
    health_report = build_paper_trading_pipeline_final_review_operation_health(
        operation_record
    )
    log_event = build_paper_trading_pipeline_final_review_operation_log_event(
        operation_record
    )

    _write_json(operation_record_path, operation_record)
    _write_json(audit_path, audit_report)
    _write_json(health_path, health_report)
    _write_jsonl(operation_log_path, [log_event])

    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": WRITE_RESULT_ARTIFACT_TYPE,
        "operation_id": operation_record["operation_id"],
        "operation_state": operation_record["operation_state"],
        "final_review_state": operation_record["final_review_state"],
        "pipeline_ready_for_order_submission": operation_record[
            "pipeline_ready_for_order_submission"
        ],
        "safe_stop_required": operation_record["safe_stop_required"],
        "safe_stop_stage": operation_record["safe_stop_stage"],
        "safe_stop_reason": operation_record["safe_stop_reason"],
        "blocked_stage_count": operation_record["blocked_stage_count"],
        "needs_review_stage_count": operation_record["needs_review_stage_count"],
        "ready_stage_count": operation_record["ready_stage_count"],
        "total_stage_count": operation_record["total_stage_count"],
        "order_submission_enabled": operation_record["order_submission_enabled"],
        "submit_order": operation_record["submit_order"],
        "manual_approval_granted": operation_record["manual_approval_granted"],
        "blocked_reasons": operation_record["blocked_reasons"],
        "warnings": operation_record["warnings"],
        "summary_path": summary_result.get("summary_path"),
        "operation_record_path": str(operation_record_path),
        "operation_log_path": str(operation_log_path),
        "audit_path": str(audit_path),
        "health_path": str(health_path),
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def build_paper_trading_pipeline_final_review_operation_record(
    summary_result: Any,
    *,
    source_paths: Optional[Mapping[str, str]] = None,
    output_dir: Optional[str],
    operation_paths: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    if not isinstance(summary_result, Mapping):
        summary_result = _blocked_summary_result(
            blocked_reasons=[
                "paper_trading_pipeline_final_review_summary_result_invalid_shape",
                "paper_trading_pipeline_final_review_summary_result_must_be_json_object",
            ],
        )

    final_review_state = str(summary_result.get("final_review_state") or "blocked")
    operation_state = _classify_operation_state(final_review_state)

    blocked_reasons = _dedupe_strings(summary_result.get("blocked_reasons", []))
    warnings = _dedupe_strings(summary_result.get("warnings", []))

    operation_id = _stable_operation_id(
        {
            "adapter_type": ADAPTER_TYPE,
            "final_review_state": final_review_state,
            "safe_stop_stage": summary_result.get("safe_stop_stage"),
            "safe_stop_reason": summary_result.get("safe_stop_reason"),
            "blocked_stage_count": summary_result.get("blocked_stage_count"),
            "needs_review_stage_count": summary_result.get(
                "needs_review_stage_count"
            ),
            "ready_stage_count": summary_result.get("ready_stage_count"),
            "pipeline_ready_for_order_submission": summary_result.get(
                "pipeline_ready_for_order_submission"
            ),
            "blocked_reasons": blocked_reasons,
            "warnings": warnings,
        }
    )

    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": OPERATION_RECORD_ARTIFACT_TYPE,
        "operation_id": operation_id,
        "operation_state": operation_state,
        "final_review_state": final_review_state,
        "pipeline_ready_for_order_submission": bool(
            summary_result.get("pipeline_ready_for_order_submission")
        ),
        "safe_stop_required": bool(summary_result.get("safe_stop_required")),
        "safe_stop_stage": summary_result.get("safe_stop_stage"),
        "safe_stop_reason": summary_result.get("safe_stop_reason"),
        "paper_trading_mode": summary_result.get("paper_trading_mode") is True,
        "order_submission_enabled": False,
        "submit_order": False,
        "manual_approval_granted": False,
        "manual_approval_required": True,
        "blocked_stage_count": summary_result.get("blocked_stage_count"),
        "needs_review_stage_count": summary_result.get("needs_review_stage_count"),
        "ready_stage_count": summary_result.get("ready_stage_count"),
        "total_stage_count": summary_result.get("total_stage_count"),
        "stage_summaries": summary_result.get("stage_summaries", []),
        "pipeline_milestones": summary_result.get("pipeline_milestones", {}),
        "source_paths": dict(source_paths or {}),
        "operation_scope": "paper_trading_pipeline_final_review",
        "depends_on_artifacts": [
            "signalforge_primary_strategy_candidate_profile_export_operation_record",
            "signalforge_ibkr_paper_trading_readiness_operation_record",
            "signalforge_ibkr_paper_connection_smoke_test_operation_record",
            "signalforge_ibkr_paper_account_snapshot_import_operation_record",
            "signalforge_primary_strategy_paper_order_intent_operation_record",
            "signalforge_ibkr_option_contract_resolver_operation_record",
            "signalforge_ibkr_option_quote_validation_operation_record",
            "signalforge_paper_order_preview_operation_record",
            "signalforge_manual_approval_ticket_operation_record",
            "signalforge_paper_trading_pipeline_final_review_summary",
        ],
        "produced_artifacts": [
            OPERATION_RECORD_ARTIFACT_TYPE,
            OPERATION_LOG_ARTIFACT_TYPE,
            AUDIT_ARTIFACT_TYPE,
            HEALTH_ARTIFACT_TYPE,
        ],
        "output_dir": output_dir,
        "output_files": dict(operation_paths or {}),
        "broker_api_calls_attempted": False,
        "order_routing_attempted": False,
        "order_submission_attempted": False,
        "fills_import_attempted": False,
        "blocked_reasons": blocked_reasons,
        "warnings": warnings,
        **EXECUTION_DISABLED_FIELDS,
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def build_paper_trading_pipeline_final_review_operation_log_event(
    operation_record: Mapping[str, Any],
) -> Dict[str, Any]:
    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": OPERATION_LOG_ARTIFACT_TYPE,
        "event_type": "paper_trading_pipeline_final_review_operation_completed",
        "operation_id": operation_record.get("operation_id"),
        "operation_state": operation_record.get("operation_state"),
        "final_review_state": operation_record.get("final_review_state"),
        "pipeline_ready_for_order_submission": operation_record.get(
            "pipeline_ready_for_order_submission"
        ),
        "safe_stop_required": operation_record.get("safe_stop_required"),
        "safe_stop_stage": operation_record.get("safe_stop_stage"),
        "safe_stop_reason": operation_record.get("safe_stop_reason"),
        "blocked_stage_count": operation_record.get("blocked_stage_count"),
        "needs_review_stage_count": operation_record.get("needs_review_stage_count"),
        "ready_stage_count": operation_record.get("ready_stage_count"),
        "order_submission_enabled": operation_record.get("order_submission_enabled"),
        "submit_order": operation_record.get("submit_order"),
        "manual_approval_granted": operation_record.get("manual_approval_granted"),
        "blocked_reasons": operation_record.get("blocked_reasons", []),
        "warnings": operation_record.get("warnings", []),
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def build_paper_trading_pipeline_final_review_operation_audit(
    operation_record: Mapping[str, Any],
) -> Dict[str, Any]:
    output_files = operation_record.get("output_files") or {}
    pipeline_milestones = operation_record.get("pipeline_milestones") or {}
    stage_summaries = operation_record.get("stage_summaries") or []

    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": AUDIT_ARTIFACT_TYPE,
        "operation_id": operation_record.get("operation_id"),
        "audit_state": operation_record.get("operation_state"),
        "final_review_state": operation_record.get("final_review_state"),
        "checks": {
            "paper_trading_mode_enabled": operation_record.get("paper_trading_mode")
            is True,
            "order_submission_disabled": operation_record.get(
                "order_submission_enabled"
            )
            is False,
            "submit_order_false": operation_record.get("submit_order") is False,
            "manual_approval_not_granted": operation_record.get(
                "manual_approval_granted"
            )
            is False,
            "manual_approval_required": operation_record.get(
                "manual_approval_required"
            )
            is True,
            "safe_stop_present_when_blocked": (
                operation_record.get("operation_state") != "blocked"
                or bool(operation_record.get("safe_stop_stage"))
            ),
            "pipeline_not_ready_when_blocked": (
                operation_record.get("operation_state") != "blocked"
                or operation_record.get("pipeline_ready_for_order_submission") is False
            ),
            "stage_summaries_present": isinstance(stage_summaries, Sequence)
            and len(stage_summaries) > 0,
            "pipeline_milestones_present": isinstance(pipeline_milestones, Mapping)
            and len(pipeline_milestones) > 0,
            "order_submission_disabled_milestone": pipeline_milestones.get(
                "order_submission_disabled"
            )
            is True,
            "manual_approval_not_granted_milestone": pipeline_milestones.get(
                "manual_approval_not_granted"
            )
            is True,
            "broker_api_calls_not_attempted": operation_record.get(
                "broker_api_calls_attempted"
            )
            is False,
            "order_routing_not_attempted": operation_record.get(
                "order_routing_attempted"
            )
            is False,
            "order_submission_not_attempted": operation_record.get(
                "order_submission_attempted"
            )
            is False,
            "fills_import_not_attempted": operation_record.get(
                "fills_import_attempted"
            )
            is False,
            "summary_path_present": bool(output_files.get("summary")),
            "operation_record_path_present": bool(output_files.get("operation_record")),
            "operation_log_path_present": bool(output_files.get("operation_log")),
            "audit_path_present": bool(output_files.get("audit")),
            "health_path_present": bool(output_files.get("health")),
            "explicit_exclusions_preserved": operation_record.get(
                "explicit_exclusions"
            )
            == EXPLICIT_EXCLUSIONS,
            "execution_fields_disabled": _execution_fields_disabled(operation_record),
        },
        "blocked_reasons": operation_record.get("blocked_reasons", []),
        "warnings": operation_record.get("warnings", []),
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def build_paper_trading_pipeline_final_review_operation_health(
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
        "final_review_state": operation_record.get("final_review_state"),
        "pipeline_ready_for_order_submission": operation_record.get(
            "pipeline_ready_for_order_submission"
        ),
        "safe_stop_required": operation_record.get("safe_stop_required"),
        "safe_stop_stage": operation_record.get("safe_stop_stage"),
        "safe_stop_reason": operation_record.get("safe_stop_reason"),
        "paper_trading_mode": operation_record.get("paper_trading_mode"),
        "order_submission_enabled": operation_record.get("order_submission_enabled"),
        "submit_order": operation_record.get("submit_order"),
        "manual_approval_granted": operation_record.get("manual_approval_granted"),
        "manual_approval_required": operation_record.get("manual_approval_required"),
        "blocked_stage_count": operation_record.get("blocked_stage_count"),
        "needs_review_stage_count": operation_record.get("needs_review_stage_count"),
        "ready_stage_count": operation_record.get("ready_stage_count"),
        "total_stage_count": operation_record.get("total_stage_count"),
        "pipeline_milestones": operation_record.get("pipeline_milestones", {}),
        "blocked_reason_count": len(blocked_reasons),
        "warning_count": len(warnings),
        "blocked_reasons": blocked_reasons,
        "warnings": warnings,
        "next_recommended_action": _next_recommended_action(operation_state),
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def hydrate_final_review_summary_result_details(summary_result: Any) -> Any:
    if not isinstance(summary_result, Mapping):
        return summary_result

    summary_path = summary_result.get("summary_path")

    if not summary_path:
        return summary_result

    summary_path_obj = Path(summary_path)

    if not summary_path_obj.exists():
        return summary_result

    summary_payload = _load_json(summary_path_obj)

    if not isinstance(summary_payload, Mapping):
        return summary_result

    hydrated = dict(summary_result)

    for key in [
        "final_review_state",
        "pipeline_ready_for_order_submission",
        "safe_stop_required",
        "safe_stop_stage",
        "safe_stop_reason",
        "paper_trading_mode",
        "order_submission_enabled",
        "submit_order",
        "manual_approval_granted",
        "manual_approval_required",
        "blocked_stage_count",
        "needs_review_stage_count",
        "ready_stage_count",
        "total_stage_count",
        "stage_summaries",
        "pipeline_milestones",
        "blocked_reasons",
        "warnings",
        "explicit_exclusions",
    ]:
        if key in summary_payload:
            hydrated[key] = summary_payload[key]

    return hydrated


def _blocked_summary_result(*, blocked_reasons: Sequence[str]) -> Dict[str, Any]:
    return {
        "adapter_type": "paper_trading_pipeline_final_review_summary",
        "artifact_type": "paper_trading_pipeline_final_review_summary_write_result",
        "final_review_state": "blocked",
        "pipeline_ready_for_order_submission": False,
        "safe_stop_required": True,
        "safe_stop_stage": "paper_trading_pipeline_final_review_summary",
        "safe_stop_reason": _dedupe_strings(blocked_reasons)[0]
        if _dedupe_strings(blocked_reasons)
        else "summary_failed",
        "paper_trading_mode": True,
        "order_submission_enabled": False,
        "submit_order": False,
        "manual_approval_granted": False,
        "manual_approval_required": True,
        "blocked_stage_count": None,
        "needs_review_stage_count": None,
        "ready_stage_count": None,
        "total_stage_count": None,
        "stage_summaries": [],
        "pipeline_milestones": {
            "order_submission_disabled": True,
            "manual_approval_not_granted": True,
        },
        "blocked_reasons": _dedupe_strings(blocked_reasons),
        "warnings": [],
        "summary_path": None,
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def _classify_operation_state(final_review_state: str) -> str:
    if final_review_state in {"ready", "needs_review", "blocked"}:
        return final_review_state

    return "blocked"


def _next_recommended_action(operation_state: Any) -> str:
    if operation_state == "ready":
        return "paper_trading_pipeline_final_review_ready_no_order_submission_enabled"

    if operation_state == "needs_review":
        return "review_pipeline_warnings_before_any_manual_approval_or_execution_work"

    return "resolve_pipeline_safe_stop_before_any_manual_approval_or_execution_work"


def _stable_operation_id(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, default=str)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return f"paper_trading_pipeline_final_review_operation_{digest}"


def _dedupe_strings(values: Any) -> list[str]:
    if values is None:
        return []

    if isinstance(values, str):
        values = [values]

    deduped: list[str] = []
    seen: set[str] = set()

    for value in values:
        clean_value = str(value).strip()
        if clean_value and clean_value not in seen:
            seen.add(clean_value)
            deduped.append(clean_value)

    return deduped


def _execution_fields_disabled(operation_record: Mapping[str, Any]) -> bool:
    return all(
        operation_record.get(field) is None for field in EXECUTION_DISABLED_FIELDS
    )


def _load_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8-sig") as file:
        return json.load(file)


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