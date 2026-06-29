from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

from src.paper_trading.paper_order_preview_export import (
    EXPLICIT_EXCLUSIONS,
    export_paper_order_preview,
)


ADAPTER_TYPE = "paper_order_preview_operation"

OPERATION_RECORD_ARTIFACT_TYPE = "signalforge_paper_order_preview_operation_record"
OPERATION_LOG_ARTIFACT_TYPE = "signalforge_paper_order_preview_operation_log"
AUDIT_ARTIFACT_TYPE = "signalforge_paper_order_preview_operation_audit_report"
HEALTH_ARTIFACT_TYPE = "signalforge_paper_order_preview_operation_health_report"
WRITE_RESULT_ARTIFACT_TYPE = "paper_order_preview_operation_write_result"

OPERATION_RECORD_FILENAME = "signalforge_paper_order_preview_operation_record.json"
OPERATION_LOG_FILENAME = "signalforge_paper_order_preview_operation_log.jsonl"
AUDIT_FILENAME = "signalforge_paper_order_preview_operation_audit.json"
HEALTH_FILENAME = "signalforge_paper_order_preview_operation_health.json"

EXECUTION_DISABLED_FIELDS = {
    "automatic_action": None,
    "automatic_close_order": None,
    "automatic_defense_order": None,
    "automatic_parameter_change": None,
    "automatic_pause_action": None,
    "automatic_roll_order": None,
    "automatic_strategy_change": None,
}


def run_paper_order_preview_operation(
    *,
    paper_order_intent_operation_path: str | Path,
    option_contract_resolver_operation_path: str | Path,
    option_quote_validation_operation_path: str | Path,
    output_dir: str | Path,
) -> Dict[str, Any]:
    output_dir_obj = Path(output_dir)
    output_dir_obj.mkdir(parents=True, exist_ok=True)

    operation_record_path = output_dir_obj / OPERATION_RECORD_FILENAME
    operation_log_path = output_dir_obj / OPERATION_LOG_FILENAME
    audit_path = output_dir_obj / AUDIT_FILENAME
    health_path = output_dir_obj / HEALTH_FILENAME

    try:
        export_result = export_paper_order_preview(
            paper_order_intent_operation_path=paper_order_intent_operation_path,
            option_contract_resolver_operation_path=option_contract_resolver_operation_path,
            option_quote_validation_operation_path=option_quote_validation_operation_path,
            output_dir=output_dir_obj,
        )
        export_result = hydrate_paper_order_preview_export_result_details(export_result)
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        export_result = _blocked_export_result(
            paper_order_intent_operation_path=paper_order_intent_operation_path,
            option_contract_resolver_operation_path=option_contract_resolver_operation_path,
            option_quote_validation_operation_path=option_quote_validation_operation_path,
            output_dir=output_dir_obj,
            blocked_reasons=[
                "paper_order_preview_export_failed",
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

    operation_record = build_paper_order_preview_operation_record(
        export_result,
        paper_order_intent_operation_path=str(paper_order_intent_operation_path),
        option_contract_resolver_operation_path=str(
            option_contract_resolver_operation_path
        ),
        option_quote_validation_operation_path=str(
            option_quote_validation_operation_path
        ),
        output_dir=str(output_dir_obj),
        operation_paths=operation_paths,
    )

    audit_report = build_paper_order_preview_operation_audit(operation_record)
    health_report = build_paper_order_preview_operation_health(operation_record)
    log_event = build_paper_order_preview_operation_log_event(operation_record)

    _write_json(operation_record_path, operation_record)
    _write_json(audit_path, audit_report)
    _write_json(health_path, health_report)
    _write_jsonl(operation_log_path, [log_event])

    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": WRITE_RESULT_ARTIFACT_TYPE,
        "operation_id": operation_record["operation_id"],
        "operation_state": operation_record["operation_state"],
        "paper_order_preview_state": operation_record["paper_order_preview_state"],
        "paper_trading_mode": operation_record["paper_trading_mode"],
        "order_submission_enabled": operation_record["order_submission_enabled"],
        "submit_order": operation_record["submit_order"],
        "requires_manual_approval": operation_record["requires_manual_approval"],
        "symbol": operation_record["symbol"],
        "spread_type": operation_record["spread_type"],
        "expiration": operation_record["expiration"],
        "quantity": operation_record["quantity"],
        "limit_price": operation_record["limit_price"],
        "max_loss_amount": operation_record["max_loss_amount"],
        "max_profit_amount": operation_record["max_profit_amount"],
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


def build_paper_order_preview_operation_record(
    export_result: Any,
    *,
    paper_order_intent_operation_path: Optional[str],
    option_contract_resolver_operation_path: Optional[str],
    option_quote_validation_operation_path: Optional[str],
    output_dir: Optional[str],
    operation_paths: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    if not isinstance(export_result, Mapping):
        export_result = _blocked_export_result(
            paper_order_intent_operation_path=paper_order_intent_operation_path,
            option_contract_resolver_operation_path=option_contract_resolver_operation_path,
            option_quote_validation_operation_path=option_quote_validation_operation_path,
            output_dir=output_dir,
            blocked_reasons=[
                "paper_order_preview_export_result_invalid_shape",
                "paper_order_preview_export_result_must_be_json_object",
            ],
        )

    paper_order_preview_state = str(
        export_result.get("paper_order_preview_state") or "blocked"
    )
    operation_state = _classify_operation_state(paper_order_preview_state)

    blocked_reasons = _dedupe_strings(export_result.get("blocked_reasons", []))
    warnings = _dedupe_strings(export_result.get("warnings", []))

    operation_id = _stable_operation_id(
        {
            "adapter_type": ADAPTER_TYPE,
            "paper_order_preview_state": paper_order_preview_state,
            "symbol": export_result.get("symbol"),
            "spread_type": export_result.get("spread_type"),
            "expiration": export_result.get("expiration"),
            "quantity": export_result.get("quantity"),
            "limit_price": export_result.get("limit_price"),
            "max_loss_amount": export_result.get("max_loss_amount"),
            "blocked_reasons": blocked_reasons,
            "warnings": warnings,
        }
    )

    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": OPERATION_RECORD_ARTIFACT_TYPE,
        "operation_id": operation_id,
        "operation_state": operation_state,
        "paper_order_preview_state": paper_order_preview_state,
        "paper_trading_mode": export_result.get("paper_trading_mode") is True,
        "order_submission_enabled": False,
        "submit_order": False,
        "requires_manual_approval": True,
        "symbol": export_result.get("symbol"),
        "spread_type": export_result.get("spread_type"),
        "expiration": export_result.get("expiration"),
        "quantity": export_result.get("quantity"),
        "limit_price": export_result.get("limit_price"),
        "conservative_net_debit": export_result.get("conservative_net_debit"),
        "mid_net_debit": export_result.get("mid_net_debit"),
        "max_loss_amount": export_result.get("max_loss_amount"),
        "max_profit_amount": export_result.get("max_profit_amount"),
        "max_trade_risk_amount": export_result.get("max_trade_risk_amount"),
        "order_preview": export_result.get("order_preview"),
        "paper_order_intent_operation_state": export_result.get(
            "paper_order_intent_operation_state"
        ),
        "paper_order_intent_state": export_result.get("paper_order_intent_state"),
        "option_contract_resolver_operation_state": export_result.get(
            "option_contract_resolver_operation_state"
        ),
        "contract_resolution_state": export_result.get("contract_resolution_state"),
        "option_quote_validation_operation_state": export_result.get(
            "option_quote_validation_operation_state"
        ),
        "quote_validation_state": export_result.get("quote_validation_state"),
        "paper_order_intent_operation_path": paper_order_intent_operation_path,
        "option_contract_resolver_operation_path": (
            option_contract_resolver_operation_path
        ),
        "option_quote_validation_operation_path": option_quote_validation_operation_path,
        "operation_scope": "paper_order_preview",
        "depends_on_artifacts": [
            "signalforge_primary_strategy_paper_order_intent_operation_record",
            "signalforge_ibkr_option_contract_resolver_operation_record",
            "signalforge_ibkr_option_quote_validation_operation_record",
            "signalforge_paper_order_preview_export",
            "signalforge_paper_order_preview_export_summary",
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


def build_paper_order_preview_operation_log_event(
    operation_record: Mapping[str, Any],
) -> Dict[str, Any]:
    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": OPERATION_LOG_ARTIFACT_TYPE,
        "event_type": "paper_order_preview_operation_completed",
        "operation_id": operation_record.get("operation_id"),
        "operation_state": operation_record.get("operation_state"),
        "paper_order_preview_state": operation_record.get(
            "paper_order_preview_state"
        ),
        "paper_trading_mode": operation_record.get("paper_trading_mode"),
        "order_submission_enabled": operation_record.get("order_submission_enabled"),
        "submit_order": operation_record.get("submit_order"),
        "requires_manual_approval": operation_record.get("requires_manual_approval"),
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


def build_paper_order_preview_operation_audit(
    operation_record: Mapping[str, Any],
) -> Dict[str, Any]:
    output_files = operation_record.get("output_files") or {}
    order_preview = operation_record.get("order_preview")

    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": AUDIT_ARTIFACT_TYPE,
        "operation_id": operation_record.get("operation_id"),
        "audit_state": operation_record.get("operation_state"),
        "paper_order_preview_state": operation_record.get(
            "paper_order_preview_state"
        ),
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
            "symbol_present": bool(operation_record.get("symbol")),
            "spread_type_present": bool(operation_record.get("spread_type")),
            "expiration_present": bool(operation_record.get("expiration")),
            "quantity_present": operation_record.get("quantity") is not None,
            "limit_price_present": operation_record.get("limit_price") is not None,
            "max_loss_amount_present": operation_record.get("max_loss_amount")
            is not None,
            "order_preview_present": isinstance(order_preview, Mapping),
            "order_preview_submit_order_false": (
                isinstance(order_preview, Mapping)
                and order_preview.get("submit_order") is False
            ),
            "order_preview_manual_approval_required": (
                isinstance(order_preview, Mapping)
                and order_preview.get("manual_approval_required_before_submit") is True
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


def build_paper_order_preview_operation_health(
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
        "paper_order_preview_state": operation_record.get(
            "paper_order_preview_state"
        ),
        "paper_trading_mode": operation_record.get("paper_trading_mode"),
        "order_submission_enabled": operation_record.get("order_submission_enabled"),
        "submit_order": operation_record.get("submit_order"),
        "requires_manual_approval": operation_record.get("requires_manual_approval"),
        "symbol": operation_record.get("symbol"),
        "spread_type": operation_record.get("spread_type"),
        "expiration": operation_record.get("expiration"),
        "quantity": operation_record.get("quantity"),
        "limit_price": operation_record.get("limit_price"),
        "max_loss_amount": operation_record.get("max_loss_amount"),
        "max_profit_amount": operation_record.get("max_profit_amount"),
        "paper_order_intent_operation_state": operation_record.get(
            "paper_order_intent_operation_state"
        ),
        "option_contract_resolver_operation_state": operation_record.get(
            "option_contract_resolver_operation_state"
        ),
        "option_quote_validation_operation_state": operation_record.get(
            "option_quote_validation_operation_state"
        ),
        "blocked_reason_count": len(blocked_reasons),
        "warning_count": len(warnings),
        "blocked_reasons": blocked_reasons,
        "warnings": warnings,
        "next_recommended_action": _next_recommended_action(operation_state),
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def hydrate_paper_order_preview_export_result_details(export_result: Any) -> Any:
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
        "paper_order_preview_state",
        "paper_trading_mode",
        "order_submission_enabled",
        "submit_order",
        "requires_manual_approval",
        "symbol",
        "spread_type",
        "expiration",
        "quantity",
        "limit_price",
        "conservative_net_debit",
        "mid_net_debit",
        "max_loss_amount",
        "max_profit_amount",
        "max_trade_risk_amount",
        "order_preview",
        "paper_order_intent_operation_state",
        "paper_order_intent_state",
        "option_contract_resolver_operation_state",
        "contract_resolution_state",
        "option_quote_validation_operation_state",
        "quote_validation_state",
        "blocked_reasons",
        "warnings",
        "explicit_exclusions",
    ]:
        if key in export_payload:
            hydrated[key] = export_payload[key]

    return hydrated


def _blocked_export_result(
    *,
    paper_order_intent_operation_path: str | Path | None,
    option_contract_resolver_operation_path: str | Path | None,
    option_quote_validation_operation_path: str | Path | None,
    output_dir: str | Path | None,
    blocked_reasons: Sequence[str],
) -> Dict[str, Any]:
    return {
        "adapter_type": "paper_order_preview_export",
        "artifact_type": "paper_order_preview_export_write_result",
        "paper_order_preview_state": "blocked",
        "paper_trading_mode": True,
        "order_submission_enabled": False,
        "submit_order": False,
        "requires_manual_approval": True,
        "symbol": None,
        "spread_type": None,
        "expiration": None,
        "quantity": None,
        "limit_price": None,
        "conservative_net_debit": None,
        "mid_net_debit": None,
        "max_loss_amount": None,
        "max_profit_amount": None,
        "max_trade_risk_amount": None,
        "order_preview": None,
        "blocked_reasons": _dedupe_strings(blocked_reasons),
        "warnings": [],
        "export_path": None,
        "summary_path": None,
        "paper_order_intent_operation_path": (
            str(paper_order_intent_operation_path)
            if paper_order_intent_operation_path is not None
            else None
        ),
        "option_contract_resolver_operation_path": (
            str(option_contract_resolver_operation_path)
            if option_contract_resolver_operation_path is not None
            else None
        ),
        "option_quote_validation_operation_path": (
            str(option_quote_validation_operation_path)
            if option_quote_validation_operation_path is not None
            else None
        ),
        "output_dir": str(output_dir) if output_dir is not None else None,
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def _classify_operation_state(paper_order_preview_state: str) -> str:
    if paper_order_preview_state in {"ready", "needs_review", "blocked"}:
        return paper_order_preview_state

    return "blocked"


def _next_recommended_action(operation_state: Any) -> str:
    if operation_state == "ready":
        return "build_manual_approval_ticket_before_order_submission"

    if operation_state == "needs_review":
        return "review_paper_order_preview_warnings_before_manual_approval_ticket"

    return "resolve_paper_order_preview_blockers_before_manual_approval_ticket"


def _stable_operation_id(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, default=str)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return f"paper_order_preview_operation_{digest}"


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