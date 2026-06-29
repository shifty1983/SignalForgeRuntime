from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

from src.paper_trading.manual_approval_ticket_export import (
    EXPLICIT_EXCLUSIONS,
    export_manual_approval_ticket,
)


ADAPTER_TYPE = "manual_approval_ticket_operation"

OPERATION_RECORD_ARTIFACT_TYPE = "signalforge_manual_approval_ticket_operation_record"
OPERATION_LOG_ARTIFACT_TYPE = "signalforge_manual_approval_ticket_operation_log"
AUDIT_ARTIFACT_TYPE = "signalforge_manual_approval_ticket_operation_audit_report"
HEALTH_ARTIFACT_TYPE = "signalforge_manual_approval_ticket_operation_health_report"
WRITE_RESULT_ARTIFACT_TYPE = "manual_approval_ticket_operation_write_result"

OPERATION_RECORD_FILENAME = "signalforge_manual_approval_ticket_operation_record.json"
OPERATION_LOG_FILENAME = "signalforge_manual_approval_ticket_operation_log.jsonl"
AUDIT_FILENAME = "signalforge_manual_approval_ticket_operation_audit.json"
HEALTH_FILENAME = "signalforge_manual_approval_ticket_operation_health.json"

EXECUTION_DISABLED_FIELDS = {
    "automatic_action": None,
    "automatic_close_order": None,
    "automatic_defense_order": None,
    "automatic_parameter_change": None,
    "automatic_pause_action": None,
    "automatic_roll_order": None,
    "automatic_strategy_change": None,
}


def run_manual_approval_ticket_operation(
    *,
    paper_order_preview_operation_path: str | Path,
    output_dir: str | Path,
) -> Dict[str, Any]:
    output_dir_obj = Path(output_dir)
    output_dir_obj.mkdir(parents=True, exist_ok=True)

    operation_record_path = output_dir_obj / OPERATION_RECORD_FILENAME
    operation_log_path = output_dir_obj / OPERATION_LOG_FILENAME
    audit_path = output_dir_obj / AUDIT_FILENAME
    health_path = output_dir_obj / HEALTH_FILENAME

    try:
        export_result = export_manual_approval_ticket(
            paper_order_preview_operation_path=paper_order_preview_operation_path,
            output_dir=output_dir_obj,
        )
        export_result = hydrate_manual_approval_ticket_export_result_details(
            export_result
        )
    except Exception as exc:  # pragma: no cover
        export_result = _blocked_export_result(
            paper_order_preview_operation_path=paper_order_preview_operation_path,
            output_dir=output_dir_obj,
            blocked_reasons=[
                "manual_approval_ticket_export_failed",
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

    operation_record = build_manual_approval_ticket_operation_record(
        export_result,
        paper_order_preview_operation_path=str(paper_order_preview_operation_path),
        output_dir=str(output_dir_obj),
        operation_paths=operation_paths,
    )

    audit_report = build_manual_approval_ticket_operation_audit(operation_record)
    health_report = build_manual_approval_ticket_operation_health(operation_record)
    log_event = build_manual_approval_ticket_operation_log_event(operation_record)

    _write_json(operation_record_path, operation_record)
    _write_json(audit_path, audit_report)
    _write_json(health_path, health_report)
    _write_jsonl(operation_log_path, [log_event])

    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": WRITE_RESULT_ARTIFACT_TYPE,
        "operation_id": operation_record["operation_id"],
        "operation_state": operation_record["operation_state"],
        "manual_approval_ticket_state": operation_record[
            "manual_approval_ticket_state"
        ],
        "approval_state": operation_record["approval_state"],
        "ticket_id": operation_record["ticket_id"],
        "paper_trading_mode": operation_record["paper_trading_mode"],
        "order_submission_enabled": operation_record["order_submission_enabled"],
        "submit_order": operation_record["submit_order"],
        "requires_manual_approval": operation_record["requires_manual_approval"],
        "manual_approval_granted": operation_record["manual_approval_granted"],
        "symbol": operation_record["symbol"],
        "spread_type": operation_record["spread_type"],
        "expiration": operation_record["expiration"],
        "quantity": operation_record["quantity"],
        "limit_price": operation_record["limit_price"],
        "max_loss_amount": operation_record["max_loss_amount"],
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


def build_manual_approval_ticket_operation_record(
    export_result: Any,
    *,
    paper_order_preview_operation_path: Optional[str],
    output_dir: Optional[str],
    operation_paths: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    if not isinstance(export_result, Mapping):
        export_result = _blocked_export_result(
            paper_order_preview_operation_path=paper_order_preview_operation_path,
            output_dir=output_dir,
            blocked_reasons=[
                "manual_approval_ticket_export_result_invalid_shape",
                "manual_approval_ticket_export_result_must_be_json_object",
            ],
        )

    manual_approval_ticket_state = str(
        export_result.get("manual_approval_ticket_state") or "blocked"
    )
    operation_state = _classify_operation_state(manual_approval_ticket_state)

    blocked_reasons = _dedupe_strings(export_result.get("blocked_reasons", []))
    warnings = _dedupe_strings(export_result.get("warnings", []))

    operation_id = _stable_operation_id(
        {
            "adapter_type": ADAPTER_TYPE,
            "manual_approval_ticket_state": manual_approval_ticket_state,
            "approval_state": export_result.get("approval_state"),
            "ticket_id": export_result.get("ticket_id"),
            "symbol": export_result.get("symbol"),
            "spread_type": export_result.get("spread_type"),
            "expiration": export_result.get("expiration"),
            "quantity": export_result.get("quantity"),
            "limit_price": export_result.get("limit_price"),
            "max_loss_amount": export_result.get("max_loss_amount"),
            "manual_approval_granted": export_result.get("manual_approval_granted"),
            "blocked_reasons": blocked_reasons,
            "warnings": warnings,
        }
    )

    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": OPERATION_RECORD_ARTIFACT_TYPE,
        "operation_id": operation_id,
        "operation_state": operation_state,
        "manual_approval_ticket_state": manual_approval_ticket_state,
        "approval_state": export_result.get("approval_state"),
        "ticket_id": export_result.get("ticket_id"),
        "paper_trading_mode": export_result.get("paper_trading_mode") is True,
        "order_submission_enabled": False,
        "submit_order": False,
        "requires_manual_approval": True,
        "manual_approval_granted": bool(
            export_result.get("manual_approval_granted")
        ),
        "symbol": export_result.get("symbol"),
        "spread_type": export_result.get("spread_type"),
        "expiration": export_result.get("expiration"),
        "quantity": export_result.get("quantity"),
        "limit_price": export_result.get("limit_price"),
        "max_loss_amount": export_result.get("max_loss_amount"),
        "max_profit_amount": export_result.get("max_profit_amount"),
        "max_trade_risk_amount": export_result.get("max_trade_risk_amount"),
        "ticket": export_result.get("ticket"),
        "paper_order_preview_operation_state": export_result.get(
            "paper_order_preview_operation_state"
        ),
        "paper_order_preview_state": export_result.get("paper_order_preview_state"),
        "paper_order_preview_operation_path": paper_order_preview_operation_path,
        "operation_scope": "manual_approval_ticket",
        "depends_on_artifacts": [
            "signalforge_paper_order_preview_operation_record",
            "signalforge_manual_approval_ticket_export",
            "signalforge_manual_approval_ticket_export_summary",
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


def build_manual_approval_ticket_operation_log_event(
    operation_record: Mapping[str, Any],
) -> Dict[str, Any]:
    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": OPERATION_LOG_ARTIFACT_TYPE,
        "event_type": "manual_approval_ticket_operation_completed",
        "operation_id": operation_record.get("operation_id"),
        "operation_state": operation_record.get("operation_state"),
        "manual_approval_ticket_state": operation_record.get(
            "manual_approval_ticket_state"
        ),
        "approval_state": operation_record.get("approval_state"),
        "ticket_id": operation_record.get("ticket_id"),
        "paper_trading_mode": operation_record.get("paper_trading_mode"),
        "order_submission_enabled": operation_record.get("order_submission_enabled"),
        "submit_order": operation_record.get("submit_order"),
        "requires_manual_approval": operation_record.get("requires_manual_approval"),
        "manual_approval_granted": operation_record.get("manual_approval_granted"),
        "symbol": operation_record.get("symbol"),
        "spread_type": operation_record.get("spread_type"),
        "expiration": operation_record.get("expiration"),
        "quantity": operation_record.get("quantity"),
        "limit_price": operation_record.get("limit_price"),
        "max_loss_amount": operation_record.get("max_loss_amount"),
        "blocked_reasons": operation_record.get("blocked_reasons", []),
        "warnings": operation_record.get("warnings", []),
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def build_manual_approval_ticket_operation_audit(
    operation_record: Mapping[str, Any],
) -> Dict[str, Any]:
    output_files = operation_record.get("output_files") or {}
    ticket = operation_record.get("ticket")

    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": AUDIT_ARTIFACT_TYPE,
        "operation_id": operation_record.get("operation_id"),
        "audit_state": operation_record.get("operation_state"),
        "manual_approval_ticket_state": operation_record.get(
            "manual_approval_ticket_state"
        ),
        "approval_state": operation_record.get("approval_state"),
        "checks": {
            "paper_trading_mode_enabled": operation_record.get("paper_trading_mode")
            is True,
            "order_submission_disabled": operation_record.get(
                "order_submission_enabled"
            )
            is False,
            "submit_order_false": operation_record.get("submit_order") is False,
            "manual_approval_required": operation_record.get(
                "requires_manual_approval"
            )
            is True,
            "manual_approval_not_granted": operation_record.get(
                "manual_approval_granted"
            )
            is False,
            "ticket_id_present": bool(operation_record.get("ticket_id")),
            "approval_state_present": bool(operation_record.get("approval_state")),
            "symbol_present": bool(operation_record.get("symbol")),
            "spread_type_present": bool(operation_record.get("spread_type")),
            "expiration_present": bool(operation_record.get("expiration")),
            "quantity_present": operation_record.get("quantity") is not None,
            "limit_price_present": operation_record.get("limit_price") is not None,
            "max_loss_amount_present": operation_record.get("max_loss_amount")
            is not None,
            "ticket_present": isinstance(ticket, Mapping),
            "ticket_submit_order_false": (
                isinstance(ticket, Mapping) and ticket.get("submit_order") is False
            ),
            "ticket_manual_approval_not_granted": (
                isinstance(ticket, Mapping)
                and ticket.get("manual_approval_granted") is False
            ),
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


def build_manual_approval_ticket_operation_health(
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
        "manual_approval_ticket_state": operation_record.get(
            "manual_approval_ticket_state"
        ),
        "approval_state": operation_record.get("approval_state"),
        "ticket_id": operation_record.get("ticket_id"),
        "paper_trading_mode": operation_record.get("paper_trading_mode"),
        "order_submission_enabled": operation_record.get("order_submission_enabled"),
        "submit_order": operation_record.get("submit_order"),
        "requires_manual_approval": operation_record.get("requires_manual_approval"),
        "manual_approval_granted": operation_record.get("manual_approval_granted"),
        "symbol": operation_record.get("symbol"),
        "spread_type": operation_record.get("spread_type"),
        "expiration": operation_record.get("expiration"),
        "quantity": operation_record.get("quantity"),
        "limit_price": operation_record.get("limit_price"),
        "max_loss_amount": operation_record.get("max_loss_amount"),
        "max_profit_amount": operation_record.get("max_profit_amount"),
        "paper_order_preview_operation_state": operation_record.get(
            "paper_order_preview_operation_state"
        ),
        "paper_order_preview_state": operation_record.get(
            "paper_order_preview_state"
        ),
        "blocked_reason_count": len(blocked_reasons),
        "warning_count": len(warnings),
        "blocked_reasons": blocked_reasons,
        "warnings": warnings,
        "next_recommended_action": _next_recommended_action(operation_state),
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def hydrate_manual_approval_ticket_export_result_details(export_result: Any) -> Any:
    if not isinstance(export_result, Mapping):
        return export_result

    export_path = export_result.get("export_path")

    if not export_path:
        return export_result

    export_path_obj = Path(export_path)

    if not export_path_obj.exists():
        return export_result

    export_payload = _load_json(export_path_obj)

    if not isinstance(export_payload, Mapping):
        return export_result

    hydrated = dict(export_result)

    for key in [
        "manual_approval_ticket_state",
        "approval_state",
        "ticket_id",
        "paper_trading_mode",
        "order_submission_enabled",
        "submit_order",
        "requires_manual_approval",
        "manual_approval_granted",
        "symbol",
        "spread_type",
        "expiration",
        "quantity",
        "limit_price",
        "max_loss_amount",
        "max_profit_amount",
        "max_trade_risk_amount",
        "paper_order_preview_operation_state",
        "paper_order_preview_state",
        "ticket",
        "blocked_reasons",
        "warnings",
        "explicit_exclusions",
    ]:
        if key in export_payload:
            hydrated[key] = export_payload[key]

    return hydrated


def _blocked_export_result(
    *,
    paper_order_preview_operation_path: str | Path | None,
    output_dir: str | Path | None,
    blocked_reasons: Sequence[str],
) -> Dict[str, Any]:
    return {
        "adapter_type": "manual_approval_ticket_export",
        "artifact_type": "manual_approval_ticket_export_write_result",
        "manual_approval_ticket_state": "blocked",
        "approval_state": "blocked_before_manual_review",
        "ticket_id": None,
        "paper_trading_mode": True,
        "order_submission_enabled": False,
        "submit_order": False,
        "requires_manual_approval": True,
        "manual_approval_granted": False,
        "symbol": None,
        "spread_type": None,
        "expiration": None,
        "quantity": None,
        "limit_price": None,
        "max_loss_amount": None,
        "max_profit_amount": None,
        "max_trade_risk_amount": None,
        "ticket": None,
        "blocked_reasons": _dedupe_strings(blocked_reasons),
        "warnings": [],
        "export_path": None,
        "summary_path": None,
        "paper_order_preview_operation_path": (
            str(paper_order_preview_operation_path)
            if paper_order_preview_operation_path is not None
            else None
        ),
        "output_dir": str(output_dir) if output_dir is not None else None,
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def _classify_operation_state(manual_approval_ticket_state: str) -> str:
    if manual_approval_ticket_state in {"ready", "needs_review", "blocked"}:
        return manual_approval_ticket_state

    return "blocked"


def _next_recommended_action(operation_state: Any) -> str:
    if operation_state == "ready":
        return "manual_approval_ticket_ready_but_approval_not_granted"

    if operation_state == "needs_review":
        return "review_manual_approval_ticket_warnings_before_approval"

    return "resolve_manual_approval_ticket_blockers_before_approval"


def _stable_operation_id(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, default=str)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return f"manual_approval_ticket_operation_{digest}"


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