from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

from src.paper_trading.primary_strategy_paper_order_intent_export import (
    EXPLICIT_EXCLUSIONS,
    export_primary_strategy_paper_order_intent,
)


ADAPTER_TYPE = "primary_strategy_paper_order_intent_operation"

OPERATION_RECORD_ARTIFACT_TYPE = (
    "signalforge_primary_strategy_paper_order_intent_operation_record"
)
OPERATION_LOG_ARTIFACT_TYPE = (
    "signalforge_primary_strategy_paper_order_intent_operation_log"
)
AUDIT_ARTIFACT_TYPE = (
    "signalforge_primary_strategy_paper_order_intent_operation_audit_report"
)
HEALTH_ARTIFACT_TYPE = (
    "signalforge_primary_strategy_paper_order_intent_operation_health_report"
)
WRITE_RESULT_ARTIFACT_TYPE = "primary_strategy_paper_order_intent_operation_write_result"

OPERATION_RECORD_FILENAME = (
    "signalforge_primary_strategy_paper_order_intent_operation_record.json"
)
OPERATION_LOG_FILENAME = (
    "signalforge_primary_strategy_paper_order_intent_operation_log.jsonl"
)
AUDIT_FILENAME = "signalforge_primary_strategy_paper_order_intent_operation_audit.json"
HEALTH_FILENAME = "signalforge_primary_strategy_paper_order_intent_operation_health.json"

EXECUTION_DISABLED_FIELDS = {
    "automatic_action": None,
    "automatic_close_order": None,
    "automatic_defense_order": None,
    "automatic_parameter_change": None,
    "automatic_pause_action": None,
    "automatic_roll_order": None,
    "automatic_strategy_change": None,
}


def run_primary_strategy_paper_order_intent_operation(
    *,
    strategy_profile_operation_path: str | Path,
    account_snapshot_operation_path: str | Path,
    order_intent_config_path: str | Path,
    output_dir: str | Path,
) -> Dict[str, Any]:
    output_dir_obj = Path(output_dir)
    output_dir_obj.mkdir(parents=True, exist_ok=True)

    operation_record_path = output_dir_obj / OPERATION_RECORD_FILENAME
    operation_log_path = output_dir_obj / OPERATION_LOG_FILENAME
    audit_path = output_dir_obj / AUDIT_FILENAME
    health_path = output_dir_obj / HEALTH_FILENAME

    try:
        export_result = export_primary_strategy_paper_order_intent(
            strategy_profile_operation_path=strategy_profile_operation_path,
            account_snapshot_operation_path=account_snapshot_operation_path,
            order_intent_config_path=order_intent_config_path,
            output_dir=output_dir_obj,
        )
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        export_result = _blocked_export_result(
            strategy_profile_operation_path=strategy_profile_operation_path,
            account_snapshot_operation_path=account_snapshot_operation_path,
            order_intent_config_path=order_intent_config_path,
            output_dir=output_dir_obj,
            blocked_reasons=[
                "primary_strategy_paper_order_intent_export_failed",
                f"{type(exc).__name__}: {exc}",
            ],
        )

    operation_paths = {
        "export": export_result.get("export_path"),
        "summary": export_result.get("summary_path"),
        "operation_record": str(operation_record_path),
        "operation_log": str(operation_log_path),
        "audit": str(audit_path),
        "health": str(health_path),
    }

    operation_record = build_primary_strategy_paper_order_intent_operation_record(
        export_result,
        strategy_profile_operation_path=str(strategy_profile_operation_path),
        account_snapshot_operation_path=str(account_snapshot_operation_path),
        order_intent_config_path=str(order_intent_config_path),
        output_dir=str(output_dir_obj),
        operation_paths=operation_paths,
    )

    audit_report = build_primary_strategy_paper_order_intent_operation_audit(
        operation_record
    )
    health_report = build_primary_strategy_paper_order_intent_operation_health(
        operation_record
    )
    log_event = build_primary_strategy_paper_order_intent_operation_log_event(
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
        "intent_state": operation_record["intent_state"],
        "paper_trading_mode": operation_record["paper_trading_mode"],
        "order_submission_enabled": operation_record["order_submission_enabled"],
        "requires_manual_approval": operation_record["requires_manual_approval"],
        "primary_candidate_id": operation_record["primary_candidate_id"],
        "primary_strategy_family": operation_record["primary_strategy_family"],
        "symbol": operation_record["symbol"],
        "instrument_type": operation_record["instrument_type"],
        "strategy_direction": operation_record["strategy_direction"],
        "max_trade_risk_amount": operation_record["max_trade_risk_amount"],
        "max_account_allocation_fraction": operation_record[
            "max_account_allocation_fraction"
        ],
        "blocked_reasons": operation_record["blocked_reasons"],
        "warnings": operation_record["warnings"],
        "export_path": export_result.get("export_path"),
        "summary_path": export_result.get("summary_path"),
        "operation_record_path": str(operation_record_path),
        "operation_log_path": str(operation_log_path),
        "audit_path": str(audit_path),
        "health_path": str(health_path),
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def build_primary_strategy_paper_order_intent_operation_record(
    export_result: Any,
    *,
    strategy_profile_operation_path: Optional[str],
    account_snapshot_operation_path: Optional[str],
    order_intent_config_path: Optional[str],
    output_dir: Optional[str],
    operation_paths: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    if not isinstance(export_result, Mapping):
        export_result = _blocked_export_result(
            strategy_profile_operation_path=strategy_profile_operation_path,
            account_snapshot_operation_path=account_snapshot_operation_path,
            order_intent_config_path=order_intent_config_path,
            output_dir=output_dir,
            blocked_reasons=[
                "paper_order_intent_export_result_invalid_shape",
                "paper_order_intent_export_result_must_be_json_object",
            ],
        )

    intent_state = str(export_result.get("intent_state") or "blocked")
    operation_state = _classify_operation_state(intent_state)

    blocked_reasons = _dedupe_strings(export_result.get("blocked_reasons", []))
    warnings = _dedupe_strings(export_result.get("warnings", []))

    operation_id = _stable_operation_id(
        {
            "adapter_type": ADAPTER_TYPE,
            "intent_state": intent_state,
            "primary_candidate_id": export_result.get("primary_candidate_id"),
            "primary_strategy_family": export_result.get("primary_strategy_family"),
            "symbol": export_result.get("symbol"),
            "instrument_type": export_result.get("instrument_type"),
            "strategy_direction": export_result.get("strategy_direction"),
            "max_trade_risk_amount": export_result.get("max_trade_risk_amount"),
            "max_account_allocation_fraction": export_result.get(
                "max_account_allocation_fraction"
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
        "intent_state": intent_state,
        "paper_trading_mode": export_result.get("paper_trading_mode") is True,
        "order_submission_enabled": False,
        "requires_manual_approval": True,
        "primary_candidate_id": export_result.get("primary_candidate_id"),
        "primary_strategy_family": export_result.get("primary_strategy_family"),
        "symbol": export_result.get("symbol"),
        "instrument_type": export_result.get("instrument_type"),
        "strategy_direction": export_result.get("strategy_direction"),
        "max_trade_risk_amount": export_result.get("max_trade_risk_amount"),
        "max_account_allocation_fraction": export_result.get(
            "max_account_allocation_fraction"
        ),
        "blocked_reasons": blocked_reasons,
        "warnings": warnings,
        "strategy_profile_operation_path": strategy_profile_operation_path,
        "account_snapshot_operation_path": account_snapshot_operation_path,
        "order_intent_config_path": order_intent_config_path,
        "operation_scope": "primary_strategy_paper_order_intent",
        "depends_on_artifacts": [
            "signalforge_primary_strategy_candidate_profile_export_operation_record",
            "signalforge_ibkr_paper_account_snapshot_import_operation_record",
            "signalforge_primary_strategy_paper_order_intent_export",
            "signalforge_primary_strategy_paper_order_intent_export_summary",
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
        "market_data_request_attempted": False,
        "order_routing_attempted": False,
        "order_submission_attempted": False,
        "fills_import_attempted": False,
        **EXECUTION_DISABLED_FIELDS,
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def build_primary_strategy_paper_order_intent_operation_log_event(
    operation_record: Mapping[str, Any],
) -> Dict[str, Any]:
    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": OPERATION_LOG_ARTIFACT_TYPE,
        "event_type": "primary_strategy_paper_order_intent_operation_completed",
        "operation_id": operation_record.get("operation_id"),
        "operation_state": operation_record.get("operation_state"),
        "intent_state": operation_record.get("intent_state"),
        "paper_trading_mode": operation_record.get("paper_trading_mode"),
        "order_submission_enabled": operation_record.get("order_submission_enabled"),
        "requires_manual_approval": operation_record.get("requires_manual_approval"),
        "primary_candidate_id": operation_record.get("primary_candidate_id"),
        "primary_strategy_family": operation_record.get("primary_strategy_family"),
        "symbol": operation_record.get("symbol"),
        "instrument_type": operation_record.get("instrument_type"),
        "strategy_direction": operation_record.get("strategy_direction"),
        "blocked_reasons": operation_record.get("blocked_reasons", []),
        "warnings": operation_record.get("warnings", []),
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def build_primary_strategy_paper_order_intent_operation_audit(
    operation_record: Mapping[str, Any],
) -> Dict[str, Any]:
    output_files = operation_record.get("output_files") or {}

    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": AUDIT_ARTIFACT_TYPE,
        "operation_id": operation_record.get("operation_id"),
        "audit_state": operation_record.get("operation_state"),
        "intent_state": operation_record.get("intent_state"),
        "checks": {
            "paper_trading_mode_enabled": operation_record.get("paper_trading_mode")
            is True,
            "order_submission_disabled": operation_record.get(
                "order_submission_enabled"
            )
            is False,
            "manual_approval_required": operation_record.get(
                "requires_manual_approval"
            )
            is True,
            "primary_candidate_present": bool(
                operation_record.get("primary_candidate_id")
            ),
            "primary_strategy_family_present": bool(
                operation_record.get("primary_strategy_family")
            ),
            "symbol_present": bool(operation_record.get("symbol")),
            "instrument_type_present": bool(operation_record.get("instrument_type")),
            "strategy_direction_present": bool(
                operation_record.get("strategy_direction")
            ),
            "broker_api_calls_not_attempted": operation_record.get(
                "broker_api_calls_attempted"
            )
            is False,
            "market_data_request_not_attempted": operation_record.get(
                "market_data_request_attempted"
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
            "export_path_present": bool(output_files.get("export")),
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


def build_primary_strategy_paper_order_intent_operation_health(
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
        "intent_state": operation_record.get("intent_state"),
        "paper_trading_mode": operation_record.get("paper_trading_mode"),
        "order_submission_enabled": operation_record.get("order_submission_enabled"),
        "requires_manual_approval": operation_record.get("requires_manual_approval"),
        "primary_candidate_id": operation_record.get("primary_candidate_id"),
        "primary_strategy_family": operation_record.get("primary_strategy_family"),
        "symbol": operation_record.get("symbol"),
        "instrument_type": operation_record.get("instrument_type"),
        "strategy_direction": operation_record.get("strategy_direction"),
        "blocked_reason_count": len(blocked_reasons),
        "warning_count": len(warnings),
        "blocked_reasons": blocked_reasons,
        "warnings": warnings,
        "next_recommended_action": _next_recommended_action(operation_state),
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def _blocked_export_result(
    *,
    strategy_profile_operation_path: str | Path | None,
    account_snapshot_operation_path: str | Path | None,
    order_intent_config_path: str | Path | None,
    output_dir: str | Path | None,
    blocked_reasons: Sequence[str],
) -> Dict[str, Any]:
    return {
        "adapter_type": "primary_strategy_paper_order_intent_export",
        "artifact_type": "primary_strategy_paper_order_intent_export_write_result",
        "intent_state": "blocked",
        "paper_trading_mode": True,
        "order_submission_enabled": False,
        "requires_manual_approval": True,
        "primary_candidate_id": None,
        "primary_strategy_family": None,
        "symbol": None,
        "instrument_type": None,
        "strategy_direction": None,
        "max_trade_risk_amount": None,
        "max_account_allocation_fraction": None,
        "blocked_reasons": _dedupe_strings(blocked_reasons),
        "warnings": [],
        "export_path": None,
        "summary_path": None,
        "strategy_profile_operation_path": (
            str(strategy_profile_operation_path)
            if strategy_profile_operation_path is not None
            else None
        ),
        "account_snapshot_operation_path": (
            str(account_snapshot_operation_path)
            if account_snapshot_operation_path is not None
            else None
        ),
        "order_intent_config_path": (
            str(order_intent_config_path)
            if order_intent_config_path is not None
            else None
        ),
        "output_dir": str(output_dir) if output_dir is not None else None,
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def _classify_operation_state(intent_state: str) -> str:
    if intent_state in {"ready", "needs_review", "blocked"}:
        return intent_state

    return "blocked"


def _next_recommended_action(operation_state: Any) -> str:
    if operation_state == "ready":
        return "build_option_contract_resolver_before_paper_order_preview"

    if operation_state == "needs_review":
        return "review_primary_strategy_paper_order_intent_warnings_before_contract_resolution"

    return "resolve_primary_strategy_paper_order_intent_blockers_before_contract_resolution"


def _stable_operation_id(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, default=str)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return f"primary_strategy_paper_order_intent_operation_{digest}"


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


def _execution_fields_disabled(operation_record: Mapping[str, Any]) -> bool:
    return all(
        operation_record.get(field) is None for field in EXECUTION_DISABLED_FIELDS
    )


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