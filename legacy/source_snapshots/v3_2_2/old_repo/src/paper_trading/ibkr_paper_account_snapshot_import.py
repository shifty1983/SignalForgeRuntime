from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Sequence


ADAPTER_TYPE = "ibkr_paper_account_snapshot_import_operation"

SNAPSHOT_ARTIFACT_TYPE = "signalforge_ibkr_paper_account_snapshot_import"
SUMMARY_ARTIFACT_TYPE = "signalforge_ibkr_paper_account_snapshot_import_summary"
OPERATION_RECORD_ARTIFACT_TYPE = (
    "signalforge_ibkr_paper_account_snapshot_import_operation_record"
)
OPERATION_LOG_ARTIFACT_TYPE = "signalforge_ibkr_paper_account_snapshot_import_operation_log"
AUDIT_ARTIFACT_TYPE = "signalforge_ibkr_paper_account_snapshot_import_operation_audit_report"
HEALTH_ARTIFACT_TYPE = "signalforge_ibkr_paper_account_snapshot_import_operation_health_report"
WRITE_RESULT_ARTIFACT_TYPE = "ibkr_paper_account_snapshot_import_operation_write_result"

SNAPSHOT_FILENAME = "signalforge_ibkr_paper_account_snapshot_import.json"
SUMMARY_FILENAME = "signalforge_ibkr_paper_account_snapshot_import_summary.json"
OPERATION_RECORD_FILENAME = (
    "signalforge_ibkr_paper_account_snapshot_import_operation_record.json"
)
OPERATION_LOG_FILENAME = "signalforge_ibkr_paper_account_snapshot_import_operation_log.jsonl"
AUDIT_FILENAME = "signalforge_ibkr_paper_account_snapshot_import_operation_audit.json"
HEALTH_FILENAME = "signalforge_ibkr_paper_account_snapshot_import_operation_health.json"

DEFAULT_TIMEOUT_SECONDS = 8.0
ACCOUNT_SUMMARY_TAGS = (
    "NetLiquidation,"
    "TotalCashValue,"
    "BuyingPower,"
    "AvailableFunds,"
    "ExcessLiquidity,"
    "MaintMarginReq,"
    "GrossPositionValue,"
    "UnrealizedPnL,"
    "RealizedPnL,"
    "Currency"
)

EXPLICIT_EXCLUSIONS = [
    "order_routing",
    "order_submission",
    "fills",
    "live_execution",
    "slippage_modeling",
    "market_data_request",
    "open_order_request",
    "automatic_close_orders",
    "automatic_roll_orders",
    "automatic_defense_orders",
    "automatic_strategy_changes",
    "automatic_parameter_changes",
    "automatic_pause_actions",
]

EXECUTION_DISABLED_FIELDS = {
    "automatic_action": None,
    "automatic_close_order": None,
    "automatic_defense_order": None,
    "automatic_parameter_change": None,
    "automatic_pause_action": None,
    "automatic_roll_order": None,
    "automatic_strategy_change": None,
}

SnapshotFetcher = Callable[[str, int, int, float], Mapping[str, Any]]


def load_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8-sig") as file:
        return json.load(file)


def run_ibkr_paper_account_snapshot_import_operation(
    *,
    smoke_test_operation_path: str | Path,
    output_dir: str | Path,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    snapshot_fetcher: Optional[SnapshotFetcher] = None,
) -> Dict[str, Any]:
    output_dir_obj = Path(output_dir)
    output_dir_obj.mkdir(parents=True, exist_ok=True)

    snapshot_path = output_dir_obj / SNAPSHOT_FILENAME
    summary_path = output_dir_obj / SUMMARY_FILENAME
    operation_record_path = output_dir_obj / OPERATION_RECORD_FILENAME
    operation_log_path = output_dir_obj / OPERATION_LOG_FILENAME
    audit_path = output_dir_obj / AUDIT_FILENAME
    health_path = output_dir_obj / HEALTH_FILENAME

    try:
        smoke_test_operation = load_json(smoke_test_operation_path)
    except Exception as exc:  # pragma: no cover
        smoke_test_operation = {
            "operation_state": "blocked",
            "smoke_test_state": "blocked",
            "blocked_reasons": [
                "smoke_test_operation_load_failed",
                f"{type(exc).__name__}: {exc}",
            ],
            "warnings": [],
        }

    snapshot_payload = build_ibkr_paper_account_snapshot_import(
        smoke_test_operation,
        smoke_test_operation_path=str(smoke_test_operation_path),
        timeout_seconds=timeout_seconds,
        snapshot_fetcher=snapshot_fetcher,
    )

    summary_payload = build_ibkr_paper_account_snapshot_import_summary(
        snapshot_payload,
        snapshot_path=str(snapshot_path),
        summary_path=str(summary_path),
    )

    operation_paths = {
        "snapshot": str(snapshot_path),
        "summary": str(summary_path),
        "operation_record": str(operation_record_path),
        "operation_log": str(operation_log_path),
        "audit": str(audit_path),
        "health": str(health_path),
    }

    operation_record = build_ibkr_paper_account_snapshot_import_operation_record(
        snapshot_payload,
        output_dir=str(output_dir_obj),
        operation_paths=operation_paths,
    )

    audit_report = build_ibkr_paper_account_snapshot_import_operation_audit(
        operation_record
    )
    health_report = build_ibkr_paper_account_snapshot_import_operation_health(
        operation_record
    )
    log_event = build_ibkr_paper_account_snapshot_import_operation_log_event(
        operation_record
    )

    _write_json(snapshot_path, snapshot_payload)
    _write_json(summary_path, summary_payload)
    _write_json(operation_record_path, operation_record)
    _write_json(audit_path, audit_report)
    _write_json(health_path, health_report)
    _write_jsonl(operation_log_path, [log_event])

    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": WRITE_RESULT_ARTIFACT_TYPE,
        "operation_id": operation_record["operation_id"],
        "operation_state": operation_record["operation_state"],
        "snapshot_state": snapshot_payload["snapshot_state"],
        "broker": snapshot_payload["broker"],
        "trading_mode": snapshot_payload["trading_mode"],
        "ibkr_client": snapshot_payload["ibkr_client"],
        "host": snapshot_payload["host"],
        "port": snapshot_payload["port"],
        "client_id": snapshot_payload["client_id"],
        "managed_account_count": snapshot_payload["managed_account_count"],
        "account_summary_row_count": snapshot_payload["account_summary_row_count"],
        "position_count": snapshot_payload["position_count"],
        "broker_api_protocol_handshake_attempted": snapshot_payload[
            "broker_api_protocol_handshake_attempted"
        ],
        "account_data_request_attempted": snapshot_payload[
            "account_data_request_attempted"
        ],
        "position_request_attempted": snapshot_payload[
            "position_request_attempted"
        ],
        "market_data_request_attempted": snapshot_payload[
            "market_data_request_attempted"
        ],
        "order_submission_attempted": snapshot_payload[
            "order_submission_attempted"
        ],
        "blocked_reasons": snapshot_payload["blocked_reasons"],
        "warnings": snapshot_payload["warnings"],
        "snapshot_path": str(snapshot_path),
        "summary_path": str(summary_path),
        "operation_record_path": str(operation_record_path),
        "operation_log_path": str(operation_log_path),
        "audit_path": str(audit_path),
        "health_path": str(health_path),
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def build_ibkr_paper_account_snapshot_import(
    smoke_test_operation: Any,
    *,
    smoke_test_operation_path: Optional[str] = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    snapshot_fetcher: Optional[SnapshotFetcher] = None,
) -> Dict[str, Any]:
    blocked_reasons: list[str] = []
    warnings: list[str] = []

    if not isinstance(smoke_test_operation, Mapping):
        smoke_test_operation = {}
        blocked_reasons.extend(
            [
                "smoke_test_operation_invalid_shape",
                "smoke_test_operation_must_be_json_object",
            ]
        )

    blocked_reasons.extend(_dedupe_strings(smoke_test_operation.get("blocked_reasons", [])))
    warnings.extend(_dedupe_strings(smoke_test_operation.get("warnings", [])))

    operation_state = smoke_test_operation.get("operation_state")
    smoke_test_state = smoke_test_operation.get("smoke_test_state")
    broker = smoke_test_operation.get("broker")
    trading_mode = smoke_test_operation.get("trading_mode")
    ibkr_client = smoke_test_operation.get("ibkr_client")
    host = smoke_test_operation.get("host")
    port = _as_int(smoke_test_operation.get("port"))
    client_id = _as_int(smoke_test_operation.get("client_id"))
    socket_connection_succeeded = smoke_test_operation.get("socket_connection_succeeded")
    primary_candidate_id = smoke_test_operation.get("primary_candidate_id")
    primary_strategy_family = smoke_test_operation.get("primary_strategy_family")
    order_submission_enabled = bool(smoke_test_operation.get("order_submission_enabled"))
    manual_approval_required = smoke_test_operation.get("manual_approval_required")

    if operation_state != "ready":
        blocked_reasons.append("smoke_test_operation_must_be_ready")

    if smoke_test_state != "ready":
        blocked_reasons.append("smoke_test_state_must_be_ready")

    if socket_connection_succeeded is not True:
        blocked_reasons.append("socket_connection_must_be_succeeded")

    if broker != "ibkr":
        blocked_reasons.append("broker_must_be_ibkr")

    if trading_mode != "paper":
        blocked_reasons.append("trading_mode_must_be_paper")

    if not host:
        blocked_reasons.append("host_required")

    if port is None:
        blocked_reasons.append("port_required")

    if client_id is None:
        blocked_reasons.append("client_id_required")

    if order_submission_enabled:
        blocked_reasons.append("order_submission_must_be_disabled_for_snapshot_import")

    if manual_approval_required is not True:
        blocked_reasons.append("manual_approval_required_must_be_true")

    if not primary_candidate_id:
        blocked_reasons.append("primary_candidate_id_required")

    if not primary_strategy_family:
        blocked_reasons.append("primary_strategy_family_required")

    fetch_result: Mapping[str, Any] = {}
    broker_api_protocol_handshake_attempted = False
    account_data_request_attempted = False
    position_request_attempted = False
    connection_succeeded = False

    if not blocked_reasons:
        fetcher = snapshot_fetcher or _default_ibkr_snapshot_fetcher

        try:
            fetch_result = fetcher(str(host), int(port), int(client_id), float(timeout_seconds))
        except Exception as exc:  # pragma: no cover
            fetch_result = {
                "connection_succeeded": False,
                "errors": [f"{type(exc).__name__}: {exc}"],
                "warnings": [],
                "managed_accounts": [],
                "account_summary_rows": [],
                "positions": [],
            }

        broker_api_protocol_handshake_attempted = True
        account_data_request_attempted = True
        position_request_attempted = True

        connection_succeeded = bool(fetch_result.get("connection_succeeded"))
        warnings.extend(_dedupe_strings(fetch_result.get("warnings", [])))
        warnings.extend(_dedupe_strings(fetch_result.get("errors", [])))

        informational_messages = _dedupe_strings(
            fetch_result.get("informational_messages", [])
        )

        if not connection_succeeded:
            blocked_reasons.append("ibkr_paper_account_snapshot_connection_failed")
    else:
        informational_messages = []

    managed_accounts = _mask_accounts(fetch_result.get("managed_accounts", []))
    account_summary_rows = _mask_account_summary_rows(
        fetch_result.get("account_summary_rows", [])
    )
    positions = _mask_position_rows(fetch_result.get("positions", []))

    if not blocked_reasons and not account_summary_rows:
        blocked_reasons.append("account_summary_rows_required")

    snapshot_state = _classify_state(
        blocked_reasons=blocked_reasons,
        warnings=warnings,
    )

    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": SNAPSHOT_ARTIFACT_TYPE,
        "snapshot_state": snapshot_state,
        "smoke_test_operation_state": operation_state,
        "smoke_test_state": smoke_test_state,
        "broker": broker,
        "trading_mode": trading_mode,
        "ibkr_client": ibkr_client,
        "host": host,
        "port": port,
        "client_id": client_id,
        "timeout_seconds": float(timeout_seconds),
        "connection_succeeded": connection_succeeded,
        "broker_api_protocol_handshake_attempted": broker_api_protocol_handshake_attempted,
        "account_data_request_attempted": account_data_request_attempted,
        "position_request_attempted": position_request_attempted,
        "market_data_request_attempted": False,
        "open_order_request_attempted": False,
        "order_submission_attempted": False,
        "managed_accounts_masked": managed_accounts,
        "managed_account_count": len(managed_accounts),
        "account_summary_rows": account_summary_rows,
        "account_summary_row_count": len(account_summary_rows),
        "positions": positions,
        "position_count": len(positions),
        "primary_candidate_id": primary_candidate_id,
        "primary_strategy_family": primary_strategy_family,
        "order_submission_enabled": order_submission_enabled,
        "manual_approval_required": manual_approval_required is True,
        "smoke_test_operation_path": smoke_test_operation_path,
        "blocked_reasons": _dedupe_strings(blocked_reasons),
        "warnings": _dedupe_strings(warnings),
        "informational_messages": _dedupe_strings(informational_messages),
        "informational_message_count": len(_dedupe_strings(informational_messages)),
        "requires_manual_approval": True,
        **EXECUTION_DISABLED_FIELDS,
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def build_ibkr_paper_account_snapshot_import_summary(
    snapshot_payload: Mapping[str, Any],
    *,
    snapshot_path: Optional[str] = None,
    summary_path: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": SUMMARY_ARTIFACT_TYPE,
        "snapshot_state": snapshot_payload.get("snapshot_state"),
        "broker": snapshot_payload.get("broker"),
        "trading_mode": snapshot_payload.get("trading_mode"),
        "host": snapshot_payload.get("host"),
        "port": snapshot_payload.get("port"),
        "client_id": snapshot_payload.get("client_id"),
        "managed_account_count": snapshot_payload.get("managed_account_count", 0),
        "account_summary_row_count": snapshot_payload.get("account_summary_row_count", 0),
        "position_count": snapshot_payload.get("position_count", 0),
        "broker_api_protocol_handshake_attempted": snapshot_payload.get(
            "broker_api_protocol_handshake_attempted"
        ),
        "account_data_request_attempted": snapshot_payload.get(
            "account_data_request_attempted"
        ),
        "position_request_attempted": snapshot_payload.get("position_request_attempted"),
        "market_data_request_attempted": snapshot_payload.get(
            "market_data_request_attempted"
        ),
        "order_submission_attempted": snapshot_payload.get("order_submission_attempted"),
        "primary_candidate_id": snapshot_payload.get("primary_candidate_id"),
        "primary_strategy_family": snapshot_payload.get("primary_strategy_family"),
        "blocked_reason_count": len(snapshot_payload.get("blocked_reasons", [])),
        "warning_count": len(snapshot_payload.get("warnings", [])),
        "blocked_reasons": snapshot_payload.get("blocked_reasons", []),
        "warnings": snapshot_payload.get("warnings", []),
        "informational_message_count": snapshot_payload.get(
            "informational_message_count", 0
        ),
        "informational_messages": snapshot_payload.get("informational_messages", []),
        "output_files": {
            "snapshot": snapshot_path,
            "summary": summary_path,
        },
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def build_ibkr_paper_account_snapshot_import_operation_record(
    snapshot_payload: Any,
    *,
    output_dir: Optional[str],
    operation_paths: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    if not isinstance(snapshot_payload, Mapping):
        snapshot_payload = {
            "snapshot_state": "blocked",
            "blocked_reasons": [
                "snapshot_payload_invalid_shape",
                "snapshot_payload_must_be_json_object",
            ],
            "warnings": [],
        }

    snapshot_state = str(snapshot_payload.get("snapshot_state") or "blocked")
    operation_state = _classify_operation_state(snapshot_state)
    blocked_reasons = _dedupe_strings(snapshot_payload.get("blocked_reasons", []))
    warnings = _dedupe_strings(snapshot_payload.get("warnings", []))

    operation_id = _stable_operation_id(
        {
            "adapter_type": ADAPTER_TYPE,
            "snapshot_state": snapshot_state,
            "host": snapshot_payload.get("host"),
            "port": snapshot_payload.get("port"),
            "client_id": snapshot_payload.get("client_id"),
            "managed_account_count": snapshot_payload.get("managed_account_count", 0),
            "account_summary_row_count": snapshot_payload.get(
                "account_summary_row_count", 0
            ),
            "position_count": snapshot_payload.get("position_count", 0),
            "primary_candidate_id": snapshot_payload.get("primary_candidate_id"),
            "primary_strategy_family": snapshot_payload.get("primary_strategy_family"),
            "blocked_reasons": blocked_reasons,
            "warnings": warnings,
        }
    )

    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": OPERATION_RECORD_ARTIFACT_TYPE,
        "operation_id": operation_id,
        "operation_state": operation_state,
        "snapshot_state": snapshot_state,
        "broker": snapshot_payload.get("broker"),
        "trading_mode": snapshot_payload.get("trading_mode"),
        "ibkr_client": snapshot_payload.get("ibkr_client"),
        "host": snapshot_payload.get("host"),
        "port": snapshot_payload.get("port"),
        "client_id": snapshot_payload.get("client_id"),
        "timeout_seconds": snapshot_payload.get("timeout_seconds"),
        "connection_succeeded": snapshot_payload.get("connection_succeeded"),
        "broker_api_protocol_handshake_attempted": snapshot_payload.get(
            "broker_api_protocol_handshake_attempted"
        ),
        "account_data_request_attempted": snapshot_payload.get(
            "account_data_request_attempted"
        ),
        "position_request_attempted": snapshot_payload.get("position_request_attempted"),
        "market_data_request_attempted": snapshot_payload.get(
            "market_data_request_attempted"
        ),
        "open_order_request_attempted": snapshot_payload.get(
            "open_order_request_attempted"
        ),
        "order_submission_attempted": snapshot_payload.get("order_submission_attempted"),
        "managed_account_count": snapshot_payload.get("managed_account_count", 0),
        "account_summary_row_count": snapshot_payload.get("account_summary_row_count", 0),
        "position_count": snapshot_payload.get("position_count", 0),
        "primary_candidate_id": snapshot_payload.get("primary_candidate_id"),
        "primary_strategy_family": snapshot_payload.get("primary_strategy_family"),
        "order_submission_enabled": snapshot_payload.get("order_submission_enabled"),
        "manual_approval_required": snapshot_payload.get("manual_approval_required"),
        "blocked_reasons": blocked_reasons,
        "warnings": warnings,
        "informational_message_count": snapshot_payload.get(
            "informational_message_count", 0
        ),
        "informational_messages": snapshot_payload.get("informational_messages", []),
        "operation_scope": "ibkr_paper_account_snapshot_import",
        "depends_on_artifacts": [
            "signalforge_ibkr_paper_connection_smoke_test_operation_record",
            "signalforge_ibkr_paper_connection_smoke_test",
            "signalforge_ibkr_paper_connection_smoke_test_summary",
        ],
        "produced_artifacts": [
            SNAPSHOT_ARTIFACT_TYPE,
            SUMMARY_ARTIFACT_TYPE,
            OPERATION_RECORD_ARTIFACT_TYPE,
            OPERATION_LOG_ARTIFACT_TYPE,
            AUDIT_ARTIFACT_TYPE,
            HEALTH_ARTIFACT_TYPE,
        ],
        "output_dir": output_dir,
        "output_files": dict(operation_paths or {}),
        "requires_manual_approval": True,
        **EXECUTION_DISABLED_FIELDS,
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def build_ibkr_paper_account_snapshot_import_operation_log_event(
    operation_record: Mapping[str, Any],
) -> Dict[str, Any]:
    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": OPERATION_LOG_ARTIFACT_TYPE,
        "event_type": "ibkr_paper_account_snapshot_import_operation_completed",
        "operation_id": operation_record.get("operation_id"),
        "operation_state": operation_record.get("operation_state"),
        "snapshot_state": operation_record.get("snapshot_state"),
        "host": operation_record.get("host"),
        "port": operation_record.get("port"),
        "client_id": operation_record.get("client_id"),
        "managed_account_count": operation_record.get("managed_account_count", 0),
        "account_summary_row_count": operation_record.get("account_summary_row_count", 0),
        "position_count": operation_record.get("position_count", 0),
        "account_data_request_attempted": operation_record.get(
            "account_data_request_attempted"
        ),
        "position_request_attempted": operation_record.get("position_request_attempted"),
        "market_data_request_attempted": operation_record.get(
            "market_data_request_attempted"
        ),
        "order_submission_attempted": operation_record.get("order_submission_attempted"),
        "blocked_reasons": operation_record.get("blocked_reasons", []),
        "warnings": operation_record.get("warnings", []),
        "informational_message_count": operation_record.get(
            "informational_message_count", 0
        ),
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def build_ibkr_paper_account_snapshot_import_operation_audit(
    operation_record: Mapping[str, Any],
) -> Dict[str, Any]:
    output_files = operation_record.get("output_files") or {}

    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": AUDIT_ARTIFACT_TYPE,
        "operation_id": operation_record.get("operation_id"),
        "audit_state": operation_record.get("operation_state"),
        "snapshot_state": operation_record.get("snapshot_state"),
        "checks": {
            "broker_is_ibkr": operation_record.get("broker") == "ibkr",
            "trading_mode_is_paper": operation_record.get("trading_mode") == "paper",
            "connection_succeeded": operation_record.get("connection_succeeded") is True,
            "account_data_request_attempted": operation_record.get(
                "account_data_request_attempted"
            )
            is True,
            "position_request_attempted": operation_record.get(
                "position_request_attempted"
            )
            is True,
            "account_summary_rows_present": operation_record.get(
                "account_summary_row_count", 0
            )
            > 0,
            "market_data_request_not_attempted": operation_record.get(
                "market_data_request_attempted"
            )
            is False,
            "open_order_request_not_attempted": operation_record.get(
                "open_order_request_attempted"
            )
            is False,
            "order_submission_not_attempted": operation_record.get(
                "order_submission_attempted"
            )
            is False,
            "order_submission_disabled": operation_record.get(
                "order_submission_enabled"
            )
            is False,
            "manual_approval_required": operation_record.get(
                "manual_approval_required"
            )
            is True,
            "operation_record_path_present": bool(output_files.get("operation_record")),
            "operation_log_path_present": bool(output_files.get("operation_log")),
            "audit_path_present": bool(output_files.get("audit")),
            "health_path_present": bool(output_files.get("health")),
            "snapshot_path_present": bool(output_files.get("snapshot")),
            "summary_path_present": bool(output_files.get("summary")),
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


def build_ibkr_paper_account_snapshot_import_operation_health(
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
        "managed_account_count": operation_record.get("managed_account_count", 0),
        "account_summary_row_count": operation_record.get("account_summary_row_count", 0),
        "position_count": operation_record.get("position_count", 0),
        "blocked_reason_count": len(blocked_reasons),
        "warning_count": len(warnings),
        "blocked_reasons": blocked_reasons,
        "warnings": warnings,
        "informational_message_count": operation_record.get(
            "informational_message_count", 0
        ),
        "informational_messages": operation_record.get("informational_messages", []),
        "next_recommended_action": _next_recommended_action(operation_state),
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def _default_ibkr_snapshot_fetcher(
    host: str,
    port: int,
    client_id: int,
    timeout_seconds: float,
) -> Mapping[str, Any]:
    try:
        from ibapi.client import EClient
        from ibapi.wrapper import EWrapper
    except ModuleNotFoundError:
        return {
            "connection_succeeded": False,
            "managed_accounts": [],
            "account_summary_rows": [],
            "positions": [],
            "warnings": [],
            "errors": ["ibapi_package_not_installed"],
        }

    class SnapshotApp(EWrapper, EClient):
        def __init__(self) -> None:
            EWrapper.__init__(self)
            EClient.__init__(self, self)

            self.connected_event = threading.Event()
            self.managed_accounts_event = threading.Event()
            self.account_summary_end_event = threading.Event()
            self.position_end_event = threading.Event()

            self.managed_accounts: list[str] = []
            self.account_summary_rows: list[dict[str, Any]] = []
            self.positions: list[dict[str, Any]] = []
            self.errors: list[str] = []
            self.informational_messages: list[str] = []

        def nextValidId(self, orderId: int) -> None:
            self.connected_event.set()

        def managedAccounts(self, accountsList: str) -> None:
            self.managed_accounts = [
                account.strip()
                for account in accountsList.split(",")
                if account.strip()
            ]
            self.managed_accounts_event.set()

        def accountSummary(
            self,
            reqId: int,
            account: str,
            tag: str,
            value: str,
            currency: str,
        ) -> None:
            self.account_summary_rows.append(
                {
                    "account": account,
                    "tag": tag,
                    "value": value,
                    "currency": currency,
                }
            )

        def accountSummaryEnd(self, reqId: int) -> None:
            self.account_summary_end_event.set()

        def position(self, account: str, contract: Any, position: float, avgCost: float) -> None:
            self.positions.append(
                {
                    "account": account,
                    "symbol": getattr(contract, "symbol", None),
                    "sec_type": getattr(contract, "secType", None),
                    "exchange": getattr(contract, "exchange", None),
                    "currency": getattr(contract, "currency", None),
                    "last_trade_date_or_contract_month": getattr(
                        contract,
                        "lastTradeDateOrContractMonth",
                        None,
                    ),
                    "strike": getattr(contract, "strike", None),
                    "right": getattr(contract, "right", None),
                    "multiplier": getattr(contract, "multiplier", None),
                    "position": position,
                    "avg_cost": avgCost,
                }
            )

        def positionEnd(self) -> None:
            self.position_end_event.set()

        def error(
            self,
            reqId: int,
            errorCode: int,
            errorString: str,
            advancedOrderRejectJson: str = "",
        ) -> None:
            message = f"{errorCode}: {errorString}"

            if _is_ibkr_informational_message(errorCode):
                self.informational_messages.append(message)
                return

            self.errors.append(message)

    app = SnapshotApp()
    warnings: list[str] = []

    try:
        app.connect(host, port, clientId=client_id)

        thread = threading.Thread(target=app.run, daemon=True)
        thread.start()

        connected = app.connected_event.wait(timeout=timeout_seconds)

        if not connected:
            app.disconnect()
            return {
                "connection_succeeded": False,
                "managed_accounts": [],
                "account_summary_rows": [],
                "positions": [],
                "warnings": warnings,
                "errors": ["ibkr_api_next_valid_id_timeout"],
                "informational_messages": [],
            }

        app.reqManagedAccts()
        app.managed_accounts_event.wait(timeout=timeout_seconds)

        app.reqAccountSummary(9101, "All", ACCOUNT_SUMMARY_TAGS)
        account_summary_complete = app.account_summary_end_event.wait(
            timeout=timeout_seconds
        )
        app.cancelAccountSummary(9101)

        if not account_summary_complete:
            warnings.append("account_summary_end_timeout")

        app.reqPositions()
        position_complete = app.position_end_event.wait(timeout=timeout_seconds)
        app.cancelPositions()

        if not position_complete:
            warnings.append("position_end_timeout")

        time.sleep(0.25)
        app.disconnect()

        return {
            "connection_succeeded": True,
            "managed_accounts": app.managed_accounts,
            "account_summary_rows": app.account_summary_rows,
            "positions": app.positions,
            "warnings": warnings,
            "errors": app.errors,
            "informational_messages": app.informational_messages,
        }

    except Exception as exc:  # pragma: no cover
        try:
            app.disconnect()
        except Exception:
            pass

        return {
            "connection_succeeded": False,
            "managed_accounts": [],
            "account_summary_rows": [],
            "positions": [],
            "warnings": warnings,
            "errors": [f"{type(exc).__name__}: {exc}"],
        }


def _mask_accounts(accounts: Any) -> list[str]:
    if not isinstance(accounts, Sequence) or isinstance(accounts, str):
        return []

    return [_mask_account_id(account) for account in accounts if account not in (None, "")]


def _mask_account_summary_rows(rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, Sequence) or isinstance(rows, str):
        return []

    masked_rows: list[dict[str, Any]] = []

    for row in rows:
        if not isinstance(row, Mapping):
            continue

        masked_rows.append(
            {
                "account_masked": _mask_account_id(row.get("account")),
                "tag": row.get("tag"),
                "value": row.get("value"),
                "currency": row.get("currency"),
            }
        )

    return masked_rows


def _mask_position_rows(rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, Sequence) or isinstance(rows, str):
        return []

    masked_rows: list[dict[str, Any]] = []

    for row in rows:
        if not isinstance(row, Mapping):
            continue

        masked_rows.append(
            {
                "account_masked": _mask_account_id(row.get("account")),
                "symbol": row.get("symbol"),
                "sec_type": row.get("sec_type"),
                "exchange": row.get("exchange"),
                "currency": row.get("currency"),
                "last_trade_date_or_contract_month": row.get(
                    "last_trade_date_or_contract_month"
                ),
                "strike": row.get("strike"),
                "right": row.get("right"),
                "multiplier": row.get("multiplier"),
                "position": row.get("position"),
                "avg_cost": row.get("avg_cost"),
            }
        )

    return masked_rows


def _mask_account_id(account_id: Any) -> Optional[str]:
    if account_id in (None, ""):
        return None

    account_text = str(account_id)

    if len(account_text) <= 4:
        return "****"

    return f"{account_text[:2]}****{account_text[-2:]}"


def _classify_state(
    *,
    blocked_reasons: Sequence[str],
    warnings: Sequence[str],
) -> str:
    if blocked_reasons:
        return "blocked"

    if warnings:
        return "needs_review"

    return "ready"


def _classify_operation_state(snapshot_state: str) -> str:
    if snapshot_state in {"ready", "needs_review", "blocked"}:
        return snapshot_state

    return "blocked"


def _next_recommended_action(operation_state: Any) -> str:
    if operation_state == "ready":
        return "build_primary_strategy_paper_order_intent_export_without_submission"

    if operation_state == "needs_review":
        return "review_ibkr_paper_account_snapshot_warnings_before_order_intent_export"

    return "resolve_ibkr_paper_account_snapshot_blockers_before_order_intent_export"


def _as_int(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None

    if isinstance(value, int):
        return value

    if isinstance(value, float) and value.is_integer():
        return int(value)

    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())

    return None


def _stable_operation_id(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, default=str)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return f"ibkr_paper_account_snapshot_import_operation_{digest}"


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


def _is_ibkr_informational_message(error_code: Any) -> bool:
    return _as_int(error_code) in {
        2104,  # Market data farm connection is OK
        2106,  # HMDS / historical data farm connection is OK
        2158,  # Sec-def data farm connection is OK
    }
    
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