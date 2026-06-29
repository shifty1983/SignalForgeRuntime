from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Sequence

from src.paper_trading.ibkr_option_quote_validation_export import (
    DEFAULT_TIMEOUT_SECONDS,
    EXPLICIT_EXCLUSIONS,
    export_ibkr_option_quote_validation,
)


ADAPTER_TYPE = "ibkr_option_quote_validation_operation"

OPERATION_RECORD_ARTIFACT_TYPE = (
    "signalforge_ibkr_option_quote_validation_operation_record"
)
OPERATION_LOG_ARTIFACT_TYPE = "signalforge_ibkr_option_quote_validation_operation_log"
AUDIT_ARTIFACT_TYPE = "signalforge_ibkr_option_quote_validation_operation_audit_report"
HEALTH_ARTIFACT_TYPE = "signalforge_ibkr_option_quote_validation_operation_health_report"
WRITE_RESULT_ARTIFACT_TYPE = "ibkr_option_quote_validation_operation_write_result"

OPERATION_RECORD_FILENAME = "signalforge_ibkr_option_quote_validation_operation_record.json"
OPERATION_LOG_FILENAME = "signalforge_ibkr_option_quote_validation_operation_log.jsonl"
AUDIT_FILENAME = "signalforge_ibkr_option_quote_validation_operation_audit.json"
HEALTH_FILENAME = "signalforge_ibkr_option_quote_validation_operation_health.json"

EXECUTION_DISABLED_FIELDS = {
    "automatic_action": None,
    "automatic_close_order": None,
    "automatic_defense_order": None,
    "automatic_parameter_change": None,
    "automatic_pause_action": None,
    "automatic_roll_order": None,
    "automatic_strategy_change": None,
}

OptionQuoteFetcher = Callable[
    [Mapping[str, Any], Mapping[str, Any], str, int, int, float],
    Mapping[str, Any],
]


def run_ibkr_option_quote_validation_operation(
    *,
    option_contract_resolver_operation_path: str | Path,
    account_snapshot_operation_path: str | Path,
    output_dir: str | Path,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    option_quote_fetcher: Optional[OptionQuoteFetcher] = None,
) -> Dict[str, Any]:
    output_dir_obj = Path(output_dir)
    output_dir_obj.mkdir(parents=True, exist_ok=True)

    operation_record_path = output_dir_obj / OPERATION_RECORD_FILENAME
    operation_log_path = output_dir_obj / OPERATION_LOG_FILENAME
    audit_path = output_dir_obj / AUDIT_FILENAME
    health_path = output_dir_obj / HEALTH_FILENAME

    try:
        export_result = export_ibkr_option_quote_validation(
            option_contract_resolver_operation_path=option_contract_resolver_operation_path,
            account_snapshot_operation_path=account_snapshot_operation_path,
            output_dir=output_dir_obj,
            timeout_seconds=timeout_seconds,
            option_quote_fetcher=option_quote_fetcher,
        )
        export_result = hydrate_quote_validation_export_result_details(export_result)
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        export_result = _blocked_export_result(
            option_contract_resolver_operation_path=option_contract_resolver_operation_path,
            account_snapshot_operation_path=account_snapshot_operation_path,
            output_dir=output_dir_obj,
            blocked_reasons=[
                "ibkr_option_quote_validation_export_failed",
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

    operation_record = build_ibkr_option_quote_validation_operation_record(
        export_result,
        option_contract_resolver_operation_path=str(
            option_contract_resolver_operation_path
        ),
        account_snapshot_operation_path=str(account_snapshot_operation_path),
        output_dir=str(output_dir_obj),
        operation_paths=operation_paths,
    )

    audit_report = build_ibkr_option_quote_validation_operation_audit(operation_record)
    health_report = build_ibkr_option_quote_validation_operation_health(operation_record)
    log_event = build_ibkr_option_quote_validation_operation_log_event(
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
        "quote_validation_state": operation_record["quote_validation_state"],
        "paper_trading_mode": operation_record["paper_trading_mode"],
        "order_submission_enabled": operation_record["order_submission_enabled"],
        "requires_manual_approval": operation_record["requires_manual_approval"],
        "symbol": operation_record["symbol"],
        "spread_type": operation_record["spread_type"],
        "expiration": operation_record["expiration"],
        "underlying_price": operation_record["underlying_price"],
        "conservative_net_debit": operation_record["conservative_net_debit"],
        "mid_net_debit": operation_record["mid_net_debit"],
        "max_loss_amount": operation_record["max_loss_amount"],
        "max_profit_amount": operation_record["max_profit_amount"],
        "market_data_delayed": operation_record["market_data_delayed"],
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


def build_ibkr_option_quote_validation_operation_record(
    export_result: Any,
    *,
    option_contract_resolver_operation_path: Optional[str],
    account_snapshot_operation_path: Optional[str],
    output_dir: Optional[str],
    operation_paths: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    if not isinstance(export_result, Mapping):
        export_result = _blocked_export_result(
            option_contract_resolver_operation_path=option_contract_resolver_operation_path,
            account_snapshot_operation_path=account_snapshot_operation_path,
            output_dir=output_dir,
            blocked_reasons=[
                "ibkr_option_quote_validation_export_result_invalid_shape",
                "ibkr_option_quote_validation_export_result_must_be_json_object",
            ],
        )

    quote_validation_state = str(
        export_result.get("quote_validation_state") or "blocked"
    )
    operation_state = _classify_operation_state(quote_validation_state)

    blocked_reasons = _dedupe_strings(export_result.get("blocked_reasons", []))
    warnings = _dedupe_strings(export_result.get("warnings", []))
    informational_messages = _dedupe_strings(
        export_result.get("informational_messages", [])
    )

    operation_id = _stable_operation_id(
        {
            "adapter_type": ADAPTER_TYPE,
            "quote_validation_state": quote_validation_state,
            "symbol": export_result.get("symbol"),
            "spread_type": export_result.get("spread_type"),
            "expiration": export_result.get("expiration"),
            "conservative_net_debit": export_result.get("conservative_net_debit"),
            "max_loss_amount": export_result.get("max_loss_amount"),
            "market_data_delayed": export_result.get("market_data_delayed"),
            "blocked_reasons": blocked_reasons,
            "warnings": warnings,
        }
    )

    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": OPERATION_RECORD_ARTIFACT_TYPE,
        "operation_id": operation_id,
        "operation_state": operation_state,
        "quote_validation_state": quote_validation_state,
        "paper_trading_mode": export_result.get("paper_trading_mode") is True,
        "order_submission_enabled": False,
        "requires_manual_approval": True,
        "broker": export_result.get("broker"),
        "trading_mode": export_result.get("trading_mode"),
        "host": export_result.get("host"),
        "port": export_result.get("port"),
        "client_id": export_result.get("client_id"),
        "symbol": export_result.get("symbol"),
        "spread_type": export_result.get("spread_type"),
        "expiration": export_result.get("expiration"),
        "underlying_price": export_result.get("underlying_price"),
        "long_leg": export_result.get("long_leg"),
        "short_leg": export_result.get("short_leg"),
        "long_leg_quote": export_result.get("long_leg_quote"),
        "short_leg_quote": export_result.get("short_leg_quote"),
        "quantity": export_result.get("quantity"),
        "multiplier": export_result.get("multiplier"),
        "spread_width": export_result.get("spread_width"),
        "conservative_net_debit": export_result.get("conservative_net_debit"),
        "mid_net_debit": export_result.get("mid_net_debit"),
        "max_loss_amount": export_result.get("max_loss_amount"),
        "max_profit_amount": export_result.get("max_profit_amount"),
        "long_leg_bid_ask_spread": export_result.get("long_leg_bid_ask_spread"),
        "short_leg_bid_ask_spread": export_result.get("short_leg_bid_ask_spread"),
        "max_bid_ask_spread": export_result.get("max_bid_ask_spread"),
        "max_trade_risk_amount": export_result.get("max_trade_risk_amount"),
        "quote_validation_checks": export_result.get("quote_validation_checks", {}),
        "broker_api_protocol_handshake_attempted": bool(
            export_result.get("broker_api_protocol_handshake_attempted")
        ),
        "option_quote_request_attempted": bool(
            export_result.get("option_quote_request_attempted")
        ),
        "market_data_request_attempted": bool(
            export_result.get("market_data_request_attempted")
        ),
        "order_submission_attempted": False,
        "market_data_delayed": bool(export_result.get("market_data_delayed")),
        "option_contract_resolver_operation_path": (
            option_contract_resolver_operation_path
        ),
        "account_snapshot_operation_path": account_snapshot_operation_path,
        "operation_scope": "ibkr_option_quote_validation",
        "depends_on_artifacts": [
            "signalforge_ibkr_option_contract_resolver_operation_record",
            "signalforge_ibkr_paper_account_snapshot_import_operation_record",
            "signalforge_ibkr_option_quote_validation_export",
            "signalforge_ibkr_option_quote_validation_export_summary",
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


def build_ibkr_option_quote_validation_operation_log_event(
    operation_record: Mapping[str, Any],
) -> Dict[str, Any]:
    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": OPERATION_LOG_ARTIFACT_TYPE,
        "event_type": "ibkr_option_quote_validation_operation_completed",
        "operation_id": operation_record.get("operation_id"),
        "operation_state": operation_record.get("operation_state"),
        "quote_validation_state": operation_record.get("quote_validation_state"),
        "paper_trading_mode": operation_record.get("paper_trading_mode"),
        "order_submission_enabled": operation_record.get("order_submission_enabled"),
        "requires_manual_approval": operation_record.get("requires_manual_approval"),
        "symbol": operation_record.get("symbol"),
        "spread_type": operation_record.get("spread_type"),
        "expiration": operation_record.get("expiration"),
        "conservative_net_debit": operation_record.get("conservative_net_debit"),
        "max_loss_amount": operation_record.get("max_loss_amount"),
        "market_data_delayed": operation_record.get("market_data_delayed"),
        "blocked_reasons": operation_record.get("blocked_reasons", []),
        "warnings": operation_record.get("warnings", []),
        "informational_message_count": len(
            operation_record.get("informational_messages", [])
        ),
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def build_ibkr_option_quote_validation_operation_audit(
    operation_record: Mapping[str, Any],
) -> Dict[str, Any]:
    output_files = operation_record.get("output_files") or {}
    checks = operation_record.get("quote_validation_checks") or {}

    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": AUDIT_ARTIFACT_TYPE,
        "operation_id": operation_record.get("operation_id"),
        "audit_state": operation_record.get("operation_state"),
        "quote_validation_state": operation_record.get("quote_validation_state"),
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
            "spread_type_present": bool(operation_record.get("spread_type")),
            "expiration_present": bool(operation_record.get("expiration")),
            "long_leg_present": isinstance(operation_record.get("long_leg"), Mapping),
            "short_leg_present": isinstance(operation_record.get("short_leg"), Mapping),
            "long_leg_quote_present": isinstance(
                operation_record.get("long_leg_quote"), Mapping
            ),
            "short_leg_quote_present": isinstance(
                operation_record.get("short_leg_quote"), Mapping
            ),
            "conservative_net_debit_available": checks.get(
                "conservative_net_debit_available"
            )
            is True,
            "max_loss_amount_available": checks.get("max_loss_amount_available")
            is True,
            "max_loss_within_budget": checks.get("max_loss_within_budget") is True,
            "long_leg_bid_ask_spread_within_limit": checks.get(
                "long_leg_bid_ask_spread_within_limit"
            )
            is True,
            "short_leg_bid_ask_spread_within_limit": checks.get(
                "short_leg_bid_ask_spread_within_limit"
            )
            is True,
            "broker_api_protocol_handshake_attempted": operation_record.get(
                "broker_api_protocol_handshake_attempted"
            )
            is True,
            "option_quote_request_attempted": operation_record.get(
                "option_quote_request_attempted"
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


def build_ibkr_option_quote_validation_operation_health(
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
        "quote_validation_state": operation_record.get("quote_validation_state"),
        "paper_trading_mode": operation_record.get("paper_trading_mode"),
        "order_submission_enabled": operation_record.get("order_submission_enabled"),
        "requires_manual_approval": operation_record.get("requires_manual_approval"),
        "symbol": operation_record.get("symbol"),
        "spread_type": operation_record.get("spread_type"),
        "expiration": operation_record.get("expiration"),
        "underlying_price": operation_record.get("underlying_price"),
        "quantity": operation_record.get("quantity"),
        "spread_width": operation_record.get("spread_width"),
        "conservative_net_debit": operation_record.get("conservative_net_debit"),
        "mid_net_debit": operation_record.get("mid_net_debit"),
        "max_loss_amount": operation_record.get("max_loss_amount"),
        "max_profit_amount": operation_record.get("max_profit_amount"),
        "market_data_delayed": operation_record.get("market_data_delayed"),
        "quote_validation_checks": operation_record.get(
            "quote_validation_checks", {}
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


def hydrate_quote_validation_export_result_details(export_result: Any) -> Any:
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
        "quote_validation_state",
        "paper_trading_mode",
        "order_submission_enabled",
        "requires_manual_approval",
        "broker",
        "trading_mode",
        "host",
        "port",
        "client_id",
        "symbol",
        "spread_type",
        "expiration",
        "underlying_price",
        "long_leg",
        "short_leg",
        "long_leg_quote",
        "short_leg_quote",
        "quantity",
        "multiplier",
        "spread_width",
        "conservative_net_debit",
        "mid_net_debit",
        "max_loss_amount",
        "max_profit_amount",
        "long_leg_bid_ask_spread",
        "short_leg_bid_ask_spread",
        "max_bid_ask_spread",
        "max_trade_risk_amount",
        "quote_validation_checks",
        "broker_api_protocol_handshake_attempted",
        "option_quote_request_attempted",
        "market_data_request_attempted",
        "order_submission_attempted",
        "market_data_delayed",
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
    option_contract_resolver_operation_path: str | Path | None,
    account_snapshot_operation_path: str | Path | None,
    output_dir: str | Path | None,
    blocked_reasons: Sequence[str],
) -> Dict[str, Any]:
    return {
        "adapter_type": "ibkr_option_quote_validation_export",
        "artifact_type": "ibkr_option_quote_validation_export_write_result",
        "quote_validation_state": "blocked",
        "paper_trading_mode": True,
        "order_submission_enabled": False,
        "requires_manual_approval": True,
        "symbol": None,
        "spread_type": None,
        "expiration": None,
        "underlying_price": None,
        "long_leg": None,
        "short_leg": None,
        "long_leg_quote": None,
        "short_leg_quote": None,
        "quantity": None,
        "multiplier": None,
        "spread_width": None,
        "conservative_net_debit": None,
        "mid_net_debit": None,
        "max_loss_amount": None,
        "max_profit_amount": None,
        "long_leg_bid_ask_spread": None,
        "short_leg_bid_ask_spread": None,
        "max_bid_ask_spread": None,
        "max_trade_risk_amount": None,
        "quote_validation_checks": {},
        "broker_api_protocol_handshake_attempted": False,
        "option_quote_request_attempted": False,
        "market_data_request_attempted": False,
        "order_submission_attempted": False,
        "market_data_delayed": False,
        "blocked_reasons": _dedupe_strings(blocked_reasons),
        "warnings": [],
        "informational_messages": [],
        "export_path": None,
        "summary_path": None,
        "option_contract_resolver_operation_path": (
            str(option_contract_resolver_operation_path)
            if option_contract_resolver_operation_path is not None
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


def _classify_operation_state(quote_validation_state: str) -> str:
    if quote_validation_state in {"ready", "needs_review", "blocked"}:
        return quote_validation_state

    return "blocked"


def _next_recommended_action(operation_state: Any) -> str:
    if operation_state == "ready":
        return "build_paper_order_preview_before_manual_approval"

    if operation_state == "needs_review":
        return "review_option_quote_validation_warnings_before_order_preview"

    return "resolve_option_quote_validation_blockers_before_order_preview"


def _stable_operation_id(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, default=str)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return f"ibkr_option_quote_validation_operation_{digest}"


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