from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Sequence

from src.paper_trading.ibkr_option_contract_resolver_export import (
    DEFAULT_TIMEOUT_SECONDS,
    EXPLICIT_EXCLUSIONS,
    export_ibkr_option_contract_resolver,
)


ADAPTER_TYPE = "ibkr_option_contract_resolver_operation"

OPERATION_RECORD_ARTIFACT_TYPE = (
    "signalforge_ibkr_option_contract_resolver_operation_record"
)
OPERATION_LOG_ARTIFACT_TYPE = "signalforge_ibkr_option_contract_resolver_operation_log"
AUDIT_ARTIFACT_TYPE = "signalforge_ibkr_option_contract_resolver_operation_audit_report"
HEALTH_ARTIFACT_TYPE = "signalforge_ibkr_option_contract_resolver_operation_health_report"
WRITE_RESULT_ARTIFACT_TYPE = "ibkr_option_contract_resolver_operation_write_result"

OPERATION_RECORD_FILENAME = "signalforge_ibkr_option_contract_resolver_operation_record.json"
OPERATION_LOG_FILENAME = "signalforge_ibkr_option_contract_resolver_operation_log.jsonl"
AUDIT_FILENAME = "signalforge_ibkr_option_contract_resolver_operation_audit.json"
HEALTH_FILENAME = "signalforge_ibkr_option_contract_resolver_operation_health.json"

EXECUTION_DISABLED_FIELDS = {
    "automatic_action": None,
    "automatic_close_order": None,
    "automatic_defense_order": None,
    "automatic_parameter_change": None,
    "automatic_pause_action": None,
    "automatic_roll_order": None,
    "automatic_strategy_change": None,
}

OptionChainFetcher = Callable[[str, str, int, int, float], Mapping[str, Any]]


def run_ibkr_option_contract_resolver_operation(
    *,
    paper_order_intent_operation_path: str | Path,
    account_snapshot_operation_path: str | Path,
    output_dir: str | Path,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    option_chain_fetcher: Optional[OptionChainFetcher] = None,
) -> Dict[str, Any]:
    output_dir_obj = Path(output_dir)
    output_dir_obj.mkdir(parents=True, exist_ok=True)

    operation_record_path = output_dir_obj / OPERATION_RECORD_FILENAME
    operation_log_path = output_dir_obj / OPERATION_LOG_FILENAME
    audit_path = output_dir_obj / AUDIT_FILENAME
    health_path = output_dir_obj / HEALTH_FILENAME

    try:
        export_result = export_ibkr_option_contract_resolver(
            paper_order_intent_operation_path=paper_order_intent_operation_path,
            account_snapshot_operation_path=account_snapshot_operation_path,
            output_dir=output_dir_obj,
            timeout_seconds=timeout_seconds,
            option_chain_fetcher=option_chain_fetcher,
        )
        export_result = hydrate_resolver_export_result_details(export_result)
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        export_result = _blocked_export_result(
            paper_order_intent_operation_path=paper_order_intent_operation_path,
            account_snapshot_operation_path=account_snapshot_operation_path,
            output_dir=output_dir_obj,
            blocked_reasons=[
                "ibkr_option_contract_resolver_export_failed",
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

    operation_record = build_ibkr_option_contract_resolver_operation_record(
        export_result,
        paper_order_intent_operation_path=str(paper_order_intent_operation_path),
        account_snapshot_operation_path=str(account_snapshot_operation_path),
        output_dir=str(output_dir_obj),
        operation_paths=operation_paths,
    )

    audit_report = build_ibkr_option_contract_resolver_operation_audit(
        operation_record
    )
    health_report = build_ibkr_option_contract_resolver_operation_health(
        operation_record
    )
    log_event = build_ibkr_option_contract_resolver_operation_log_event(
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
        "contract_resolution_state": operation_record["contract_resolution_state"],
        "paper_trading_mode": operation_record["paper_trading_mode"],
        "order_submission_enabled": operation_record["order_submission_enabled"],
        "requires_manual_approval": operation_record["requires_manual_approval"],
        "symbol": operation_record["symbol"],
        "strategy_direction": operation_record["strategy_direction"],
        "spread_type": operation_record["spread_type"],
        "expiration": operation_record["expiration"],
        "underlying_price": operation_record["underlying_price"],
        "long_leg": operation_record["long_leg"],
        "short_leg": operation_record["short_leg"],
        "option_chain_count": operation_record["option_chain_count"],
        "liquidity_checks_supported": operation_record["liquidity_checks_supported"],
        "blocked_reasons": operation_record["blocked_reasons"],
        "warnings": operation_record["warnings"],
        "informational_messages": operation_record["informational_messages"],
        "export_path": export_result.get("export_path"),
        "summary_path": export_result.get("summary_path"),
        "operation_record_path": str(operation_record_path),
        "operation_log_path": str(operation_log_path),
        "audit_path": str(audit_path),
        "health_path": str(health_path),
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def build_ibkr_option_contract_resolver_operation_record(
    export_result: Any,
    *,
    paper_order_intent_operation_path: Optional[str],
    account_snapshot_operation_path: Optional[str],
    output_dir: Optional[str],
    operation_paths: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    if not isinstance(export_result, Mapping):
        export_result = _blocked_export_result(
            paper_order_intent_operation_path=paper_order_intent_operation_path,
            account_snapshot_operation_path=account_snapshot_operation_path,
            output_dir=output_dir,
            blocked_reasons=[
                "ibkr_option_contract_resolver_export_result_invalid_shape",
                "ibkr_option_contract_resolver_export_result_must_be_json_object",
            ],
        )

    contract_resolution_state = str(
        export_result.get("contract_resolution_state") or "blocked"
    )
    operation_state = _classify_operation_state(contract_resolution_state)

    blocked_reasons = _dedupe_strings(export_result.get("blocked_reasons", []))
    warnings = _dedupe_strings(export_result.get("warnings", []))
    informational_messages = _dedupe_strings(
        export_result.get("informational_messages", [])
    )

    operation_id = _stable_operation_id(
        {
            "adapter_type": ADAPTER_TYPE,
            "contract_resolution_state": contract_resolution_state,
            "symbol": export_result.get("symbol"),
            "strategy_direction": export_result.get("strategy_direction"),
            "spread_type": export_result.get("spread_type"),
            "expiration": export_result.get("expiration"),
            "underlying_price": export_result.get("underlying_price"),
            "long_leg": export_result.get("long_leg"),
            "short_leg": export_result.get("short_leg"),
            "blocked_reasons": blocked_reasons,
            "warnings": warnings,
        }
    )

    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": OPERATION_RECORD_ARTIFACT_TYPE,
        "operation_id": operation_id,
        "operation_state": operation_state,
        "contract_resolution_state": contract_resolution_state,
        "paper_trading_mode": export_result.get("paper_trading_mode") is True,
        "order_submission_enabled": False,
        "requires_manual_approval": True,
        "broker": export_result.get("broker"),
        "trading_mode": export_result.get("trading_mode"),
        "host": export_result.get("host"),
        "port": export_result.get("port"),
        "client_id": export_result.get("client_id"),
        "symbol": export_result.get("symbol"),
        "instrument_type": export_result.get("instrument_type"),
        "strategy_direction": export_result.get("strategy_direction"),
        "spread_type": export_result.get("spread_type"),
        "selected_window_days": export_result.get("selected_window_days"),
        "expiration": export_result.get("expiration"),
        "underlying_price": export_result.get("underlying_price"),
        "long_leg": export_result.get("long_leg"),
        "short_leg": export_result.get("short_leg"),
        "max_trade_risk_amount": export_result.get("max_trade_risk_amount"),
        "max_contract_quantity": export_result.get("max_contract_quantity"),
        "option_chain_count": export_result.get("option_chain_count", 0),
        "liquidity_checks_supported": bool(
            export_result.get("liquidity_checks_supported")
        ),
        "broker_api_protocol_handshake_attempted": bool(
            export_result.get("broker_api_protocol_handshake_attempted")
        ),
        "option_chain_request_attempted": bool(
            export_result.get("option_chain_request_attempted")
        ),
        "market_data_request_attempted": bool(
            export_result.get("market_data_request_attempted")
        ),
        "order_submission_attempted": False,
        "paper_order_intent_operation_path": paper_order_intent_operation_path,
        "account_snapshot_operation_path": account_snapshot_operation_path,
        "operation_scope": "ibkr_option_contract_resolver",
        "depends_on_artifacts": [
            "signalforge_primary_strategy_paper_order_intent_operation_record",
            "signalforge_ibkr_paper_account_snapshot_import_operation_record",
            "signalforge_ibkr_option_contract_resolver_export",
            "signalforge_ibkr_option_contract_resolver_export_summary",
        ],
        "produced_artifacts": [
            OPERATION_RECORD_ARTIFACT_TYPE,
            OPERATION_LOG_ARTIFACT_TYPE,
            AUDIT_ARTIFACT_TYPE,
            HEALTH_ARTIFACT_TYPE,
        ],
        "output_dir": output_dir,
        "output_files": dict(operation_paths or {}),
        "blocked_reasons": blocked_reasons,
        "warnings": warnings,
        "informational_messages": informational_messages,
        **EXECUTION_DISABLED_FIELDS,
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def build_ibkr_option_contract_resolver_operation_log_event(
    operation_record: Mapping[str, Any],
) -> Dict[str, Any]:
    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": OPERATION_LOG_ARTIFACT_TYPE,
        "event_type": "ibkr_option_contract_resolver_operation_completed",
        "operation_id": operation_record.get("operation_id"),
        "operation_state": operation_record.get("operation_state"),
        "contract_resolution_state": operation_record.get(
            "contract_resolution_state"
        ),
        "paper_trading_mode": operation_record.get("paper_trading_mode"),
        "order_submission_enabled": operation_record.get("order_submission_enabled"),
        "requires_manual_approval": operation_record.get("requires_manual_approval"),
        "symbol": operation_record.get("symbol"),
        "strategy_direction": operation_record.get("strategy_direction"),
        "spread_type": operation_record.get("spread_type"),
        "expiration": operation_record.get("expiration"),
        "underlying_price": operation_record.get("underlying_price"),
        "option_chain_count": operation_record.get("option_chain_count", 0),
        "liquidity_checks_supported": operation_record.get(
            "liquidity_checks_supported"
        ),
        "blocked_reasons": operation_record.get("blocked_reasons", []),
        "warnings": operation_record.get("warnings", []),
        "informational_message_count": len(
            operation_record.get("informational_messages", [])
        ),
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def build_ibkr_option_contract_resolver_operation_audit(
    operation_record: Mapping[str, Any],
) -> Dict[str, Any]:
    output_files = operation_record.get("output_files") or {}

    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": AUDIT_ARTIFACT_TYPE,
        "operation_id": operation_record.get("operation_id"),
        "audit_state": operation_record.get("operation_state"),
        "contract_resolution_state": operation_record.get(
            "contract_resolution_state"
        ),
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
            "symbol_present": bool(operation_record.get("symbol")),
            "strategy_direction_present": bool(
                operation_record.get("strategy_direction")
            ),
            "spread_type_present": bool(operation_record.get("spread_type")),
            "expiration_present": bool(operation_record.get("expiration")),
            "underlying_price_present": operation_record.get("underlying_price")
            is not None,
            "long_leg_present": isinstance(operation_record.get("long_leg"), Mapping),
            "short_leg_present": isinstance(operation_record.get("short_leg"), Mapping),
            "option_chain_count_positive": operation_record.get(
                "option_chain_count", 0
            )
            > 0,
            "broker_api_protocol_handshake_attempted": operation_record.get(
                "broker_api_protocol_handshake_attempted"
            )
            is True,
            "option_chain_request_attempted": operation_record.get(
                "option_chain_request_attempted"
            )
            is True,
            "market_data_request_attempted": operation_record.get(
                "market_data_request_attempted"
            )
            is True,
            "order_submission_not_attempted": operation_record.get(
                "order_submission_attempted"
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
        "informational_messages": operation_record.get("informational_messages", []),
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def build_ibkr_option_contract_resolver_operation_health(
    operation_record: Mapping[str, Any],
) -> Dict[str, Any]:
    operation_state = operation_record.get("operation_state")
    blocked_reasons = operation_record.get("blocked_reasons", [])
    warnings = operation_record.get("warnings", [])
    informational_messages = operation_record.get("informational_messages", [])

    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": HEALTH_ARTIFACT_TYPE,
        "operation_id": operation_record.get("operation_id"),
        "health_state": operation_state,
        "is_ready": operation_state == "ready",
        "needs_review": operation_state == "needs_review",
        "is_blocked": operation_state == "blocked",
        "contract_resolution_state": operation_record.get(
            "contract_resolution_state"
        ),
        "paper_trading_mode": operation_record.get("paper_trading_mode"),
        "order_submission_enabled": operation_record.get("order_submission_enabled"),
        "requires_manual_approval": operation_record.get("requires_manual_approval"),
        "symbol": operation_record.get("symbol"),
        "strategy_direction": operation_record.get("strategy_direction"),
        "spread_type": operation_record.get("spread_type"),
        "expiration": operation_record.get("expiration"),
        "underlying_price": operation_record.get("underlying_price"),
        "long_leg": operation_record.get("long_leg"),
        "short_leg": operation_record.get("short_leg"),
        "option_chain_count": operation_record.get("option_chain_count", 0),
        "liquidity_checks_supported": operation_record.get(
            "liquidity_checks_supported"
        ),
        "blocked_reason_count": len(blocked_reasons),
        "warning_count": len(warnings),
        "informational_message_count": len(informational_messages),
        "blocked_reasons": blocked_reasons,
        "warnings": warnings,
        "informational_messages": informational_messages,
        "next_recommended_action": _next_recommended_action(operation_state),
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def hydrate_resolver_export_result_details(export_result: Any) -> Any:
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
        "contract_resolution_state",
        "paper_trading_mode",
        "order_submission_enabled",
        "requires_manual_approval",
        "broker",
        "trading_mode",
        "host",
        "port",
        "client_id",
        "symbol",
        "instrument_type",
        "strategy_direction",
        "spread_type",
        "selected_window_days",
        "expiration",
        "underlying_price",
        "long_leg",
        "short_leg",
        "max_trade_risk_amount",
        "max_contract_quantity",
        "broker_api_protocol_handshake_attempted",
        "option_chain_request_attempted",
        "market_data_request_attempted",
        "order_submission_attempted",
        "option_chain_count",
        "liquidity_checks_supported",
        "informational_messages",
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
    account_snapshot_operation_path: str | Path | None,
    output_dir: str | Path | None,
    blocked_reasons: Sequence[str],
) -> Dict[str, Any]:
    return {
        "adapter_type": "ibkr_option_contract_resolver_export",
        "artifact_type": "ibkr_option_contract_resolver_export_write_result",
        "contract_resolution_state": "blocked",
        "paper_trading_mode": True,
        "order_submission_enabled": False,
        "requires_manual_approval": True,
        "symbol": None,
        "instrument_type": None,
        "strategy_direction": None,
        "spread_type": None,
        "selected_window_days": None,
        "expiration": None,
        "underlying_price": None,
        "long_leg": None,
        "short_leg": None,
        "max_trade_risk_amount": None,
        "max_contract_quantity": None,
        "option_chain_count": 0,
        "liquidity_checks_supported": False,
        "broker_api_protocol_handshake_attempted": False,
        "option_chain_request_attempted": False,
        "market_data_request_attempted": False,
        "order_submission_attempted": False,
        "blocked_reasons": _dedupe_strings(blocked_reasons),
        "warnings": [],
        "informational_messages": [],
        "export_path": None,
        "summary_path": None,
        "paper_order_intent_operation_path": (
            str(paper_order_intent_operation_path)
            if paper_order_intent_operation_path is not None
            else None
        ),
        "account_snapshot_operation_path": (
            str(account_snapshot_operation_path)
            if account_snapshot_operation_path is not None
            else None
        ),
        "output_dir": str(output_dir) if output_dir is not None else None,
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def _classify_operation_state(contract_resolution_state: str) -> str:
    if contract_resolution_state in {"ready", "needs_review", "blocked"}:
        return contract_resolution_state

    return "blocked"


def _next_recommended_action(operation_state: Any) -> str:
    if operation_state == "ready":
        return "build_ibkr_option_quote_validation_before_paper_order_preview"

    if operation_state == "needs_review":
        return "build_ibkr_option_quote_validation_to_resolve_contract_warnings"

    return "resolve_ibkr_option_contract_resolution_blockers_before_quote_validation"


def _stable_operation_id(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, default=str)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return f"ibkr_option_contract_resolver_operation_{digest}"


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