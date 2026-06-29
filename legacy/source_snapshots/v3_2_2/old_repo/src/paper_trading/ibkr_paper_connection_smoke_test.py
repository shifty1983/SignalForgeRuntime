from __future__ import annotations

import hashlib
import json
import socket
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Sequence, Tuple


ADAPTER_TYPE = "ibkr_paper_connection_smoke_test_operation"

SMOKE_TEST_ARTIFACT_TYPE = "signalforge_ibkr_paper_connection_smoke_test"
SUMMARY_ARTIFACT_TYPE = "signalforge_ibkr_paper_connection_smoke_test_summary"
OPERATION_RECORD_ARTIFACT_TYPE = (
    "signalforge_ibkr_paper_connection_smoke_test_operation_record"
)
OPERATION_LOG_ARTIFACT_TYPE = "signalforge_ibkr_paper_connection_smoke_test_operation_log"
AUDIT_ARTIFACT_TYPE = "signalforge_ibkr_paper_connection_smoke_test_operation_audit_report"
HEALTH_ARTIFACT_TYPE = "signalforge_ibkr_paper_connection_smoke_test_operation_health_report"
WRITE_RESULT_ARTIFACT_TYPE = "ibkr_paper_connection_smoke_test_operation_write_result"

SMOKE_TEST_FILENAME = "signalforge_ibkr_paper_connection_smoke_test.json"
SUMMARY_FILENAME = "signalforge_ibkr_paper_connection_smoke_test_summary.json"
OPERATION_RECORD_FILENAME = (
    "signalforge_ibkr_paper_connection_smoke_test_operation_record.json"
)
OPERATION_LOG_FILENAME = (
    "signalforge_ibkr_paper_connection_smoke_test_operation_log.jsonl"
)
AUDIT_FILENAME = "signalforge_ibkr_paper_connection_smoke_test_operation_audit.json"
HEALTH_FILENAME = "signalforge_ibkr_paper_connection_smoke_test_operation_health.json"

DEFAULT_TIMEOUT_SECONDS = 3.0
ALLOWED_PAPER_PORTS = [7497, 4002]

EXPLICIT_EXCLUSIONS = [
    "order_routing",
    "order_submission",
    "fills",
    "live_execution",
    "slippage_modeling",
    "market_data_request",
    "account_data_request",
    "position_request",
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


SocketProbe = Callable[[str, int, float], Tuple[bool, Optional[str]]]


def load_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8-sig") as file:
        return json.load(file)


def run_ibkr_paper_connection_smoke_test_operation(
    *,
    readiness_operation_path: str | Path,
    output_dir: str | Path,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    socket_probe: Optional[SocketProbe] = None,
) -> Dict[str, Any]:
    output_dir_obj = Path(output_dir)
    output_dir_obj.mkdir(parents=True, exist_ok=True)

    smoke_test_path = output_dir_obj / SMOKE_TEST_FILENAME
    summary_path = output_dir_obj / SUMMARY_FILENAME
    operation_record_path = output_dir_obj / OPERATION_RECORD_FILENAME
    operation_log_path = output_dir_obj / OPERATION_LOG_FILENAME
    audit_path = output_dir_obj / AUDIT_FILENAME
    health_path = output_dir_obj / HEALTH_FILENAME

    try:
        readiness_operation = load_json(readiness_operation_path)
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        readiness_operation = {
            "operation_state": "blocked",
            "readiness_state": "blocked",
            "blocked_reasons": [
                "readiness_operation_load_failed",
                f"{type(exc).__name__}: {exc}",
            ],
            "warnings": [],
        }

    smoke_test_payload = build_ibkr_paper_connection_smoke_test(
        readiness_operation,
        readiness_operation_path=str(readiness_operation_path),
        timeout_seconds=timeout_seconds,
        socket_probe=socket_probe,
    )

    summary_payload = build_ibkr_paper_connection_smoke_test_summary(
        smoke_test_payload,
        smoke_test_path=str(smoke_test_path),
        summary_path=str(summary_path),
    )

    operation_paths = {
        "smoke_test": str(smoke_test_path),
        "summary": str(summary_path),
        "operation_record": str(operation_record_path),
        "operation_log": str(operation_log_path),
        "audit": str(audit_path),
        "health": str(health_path),
    }

    operation_record = build_ibkr_paper_connection_smoke_test_operation_record(
        smoke_test_payload,
        output_dir=str(output_dir_obj),
        operation_paths=operation_paths,
    )

    audit_report = build_ibkr_paper_connection_smoke_test_operation_audit(
        operation_record
    )
    health_report = build_ibkr_paper_connection_smoke_test_operation_health(
        operation_record
    )
    log_event = build_ibkr_paper_connection_smoke_test_operation_log_event(
        operation_record
    )

    _write_json(smoke_test_path, smoke_test_payload)
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
        "smoke_test_state": smoke_test_payload["smoke_test_state"],
        "readiness_state": smoke_test_payload["readiness_state"],
        "broker": smoke_test_payload["broker"],
        "trading_mode": smoke_test_payload["trading_mode"],
        "ibkr_client": smoke_test_payload["ibkr_client"],
        "host": smoke_test_payload["host"],
        "port": smoke_test_payload["port"],
        "client_id": smoke_test_payload["client_id"],
        "timeout_seconds": smoke_test_payload["timeout_seconds"],
        "socket_connection_attempted": smoke_test_payload[
            "socket_connection_attempted"
        ],
        "socket_connection_succeeded": smoke_test_payload[
            "socket_connection_succeeded"
        ],
        "broker_api_protocol_handshake_attempted": smoke_test_payload[
            "broker_api_protocol_handshake_attempted"
        ],
        "market_data_request_attempted": smoke_test_payload[
            "market_data_request_attempted"
        ],
        "account_data_request_attempted": smoke_test_payload[
            "account_data_request_attempted"
        ],
        "order_submission_attempted": smoke_test_payload[
            "order_submission_attempted"
        ],
        "primary_candidate_id": smoke_test_payload["primary_candidate_id"],
        "primary_strategy_family": smoke_test_payload["primary_strategy_family"],
        "blocked_reasons": smoke_test_payload["blocked_reasons"],
        "warnings": smoke_test_payload["warnings"],
        "smoke_test_path": str(smoke_test_path),
        "summary_path": str(summary_path),
        "operation_record_path": str(operation_record_path),
        "operation_log_path": str(operation_log_path),
        "audit_path": str(audit_path),
        "health_path": str(health_path),
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def build_ibkr_paper_connection_smoke_test(
    readiness_operation: Any,
    *,
    readiness_operation_path: Optional[str] = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    socket_probe: Optional[SocketProbe] = None,
) -> Dict[str, Any]:
    blocked_reasons: list[str] = []
    warnings: list[str] = []

    if not isinstance(readiness_operation, Mapping):
        readiness_operation = {}
        blocked_reasons.extend(
            [
                "readiness_operation_invalid_shape",
                "readiness_operation_must_be_json_object",
            ]
        )

    blocked_reasons.extend(_dedupe_strings(readiness_operation.get("blocked_reasons", [])))
    warnings.extend(_dedupe_strings(readiness_operation.get("warnings", [])))

    readiness_state = readiness_operation.get("readiness_state")
    operation_state = readiness_operation.get("operation_state")
    broker = readiness_operation.get("broker")
    trading_mode = readiness_operation.get("trading_mode")
    ibkr_client = readiness_operation.get("ibkr_client")
    host = readiness_operation.get("host")
    port = _as_int(readiness_operation.get("port"))
    client_id = _as_int(readiness_operation.get("client_id"))
    primary_candidate_id = readiness_operation.get("primary_candidate_id")
    primary_strategy_family = readiness_operation.get("primary_strategy_family")
    order_submission_enabled = bool(readiness_operation.get("order_submission_enabled"))
    manual_approval_required = readiness_operation.get("manual_approval_required")

    if readiness_state != "ready":
        blocked_reasons.append("ibkr_paper_readiness_state_must_be_ready")

    if operation_state != "ready":
        blocked_reasons.append("ibkr_paper_readiness_operation_must_be_ready")

    if broker != "ibkr":
        blocked_reasons.append("broker_must_be_ibkr")

    if trading_mode != "paper":
        blocked_reasons.append("trading_mode_must_be_paper")

    if port is None:
        blocked_reasons.append("port_required")
    elif port not in ALLOWED_PAPER_PORTS:
        blocked_reasons.append("paper_port_must_be_7497_or_4002")

    if not host:
        blocked_reasons.append("host_required")

    if client_id is None:
        blocked_reasons.append("client_id_required")

    if order_submission_enabled:
        blocked_reasons.append("order_submission_must_be_disabled_for_smoke_test")

    if manual_approval_required is not True:
        blocked_reasons.append("manual_approval_required_must_be_true")

    if not primary_candidate_id:
        blocked_reasons.append("primary_candidate_id_required")

    if not primary_strategy_family:
        blocked_reasons.append("primary_strategy_family_required")

    socket_connection_attempted = False
    socket_connection_succeeded = False
    socket_error = None

    if not blocked_reasons:
        probe = socket_probe or _default_socket_probe
        socket_connection_attempted = True
        socket_connection_succeeded, socket_error = probe(
            str(host),
            int(port),
            float(timeout_seconds),
        )

        if not socket_connection_succeeded:
            blocked_reasons.append("ibkr_paper_socket_connection_failed")
            if socket_error:
                warnings.append(socket_error)

    smoke_test_state = _classify_state(
        blocked_reasons=blocked_reasons,
        warnings=warnings,
    )

    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": SMOKE_TEST_ARTIFACT_TYPE,
        "smoke_test_state": smoke_test_state,
        "readiness_state": readiness_state,
        "readiness_operation_state": operation_state,
        "broker": broker,
        "trading_mode": trading_mode,
        "ibkr_client": ibkr_client,
        "host": host,
        "port": port,
        "client_id": client_id,
        "timeout_seconds": float(timeout_seconds),
        "socket_connection_attempted": socket_connection_attempted,
        "socket_connection_succeeded": socket_connection_succeeded,
        "socket_error": socket_error,
        "broker_api_protocol_handshake_attempted": False,
        "market_data_request_attempted": False,
        "account_data_request_attempted": False,
        "position_request_attempted": False,
        "open_order_request_attempted": False,
        "order_submission_attempted": False,
        "primary_candidate_id": primary_candidate_id,
        "primary_strategy_family": primary_strategy_family,
        "order_submission_enabled": order_submission_enabled,
        "manual_approval_required": manual_approval_required is True,
        "readiness_operation_path": readiness_operation_path,
        "blocked_reasons": _dedupe_strings(blocked_reasons),
        "warnings": _dedupe_strings(warnings),
        "requires_manual_approval": True,
        **EXECUTION_DISABLED_FIELDS,
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def build_ibkr_paper_connection_smoke_test_summary(
    smoke_test_payload: Mapping[str, Any],
    *,
    smoke_test_path: Optional[str] = None,
    summary_path: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": SUMMARY_ARTIFACT_TYPE,
        "smoke_test_state": smoke_test_payload.get("smoke_test_state"),
        "readiness_state": smoke_test_payload.get("readiness_state"),
        "broker": smoke_test_payload.get("broker"),
        "trading_mode": smoke_test_payload.get("trading_mode"),
        "ibkr_client": smoke_test_payload.get("ibkr_client"),
        "host": smoke_test_payload.get("host"),
        "port": smoke_test_payload.get("port"),
        "client_id": smoke_test_payload.get("client_id"),
        "timeout_seconds": smoke_test_payload.get("timeout_seconds"),
        "socket_connection_attempted": smoke_test_payload.get(
            "socket_connection_attempted"
        ),
        "socket_connection_succeeded": smoke_test_payload.get(
            "socket_connection_succeeded"
        ),
        "broker_api_protocol_handshake_attempted": smoke_test_payload.get(
            "broker_api_protocol_handshake_attempted"
        ),
        "market_data_request_attempted": smoke_test_payload.get(
            "market_data_request_attempted"
        ),
        "account_data_request_attempted": smoke_test_payload.get(
            "account_data_request_attempted"
        ),
        "order_submission_attempted": smoke_test_payload.get(
            "order_submission_attempted"
        ),
        "primary_candidate_id": smoke_test_payload.get("primary_candidate_id"),
        "primary_strategy_family": smoke_test_payload.get("primary_strategy_family"),
        "blocked_reason_count": len(smoke_test_payload.get("blocked_reasons", [])),
        "warning_count": len(smoke_test_payload.get("warnings", [])),
        "blocked_reasons": smoke_test_payload.get("blocked_reasons", []),
        "warnings": smoke_test_payload.get("warnings", []),
        "output_files": {
            "smoke_test": smoke_test_path,
            "summary": summary_path,
        },
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def build_ibkr_paper_connection_smoke_test_operation_record(
    smoke_test_payload: Any,
    *,
    output_dir: Optional[str],
    operation_paths: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    if not isinstance(smoke_test_payload, Mapping):
        smoke_test_payload = {
            "smoke_test_state": "blocked",
            "blocked_reasons": [
                "smoke_test_payload_invalid_shape",
                "smoke_test_payload_must_be_json_object",
            ],
            "warnings": [],
        }

    smoke_test_state = str(smoke_test_payload.get("smoke_test_state") or "blocked")
    operation_state = _classify_operation_state(smoke_test_state)
    blocked_reasons = _dedupe_strings(smoke_test_payload.get("blocked_reasons", []))
    warnings = _dedupe_strings(smoke_test_payload.get("warnings", []))

    operation_id = _stable_operation_id(
        {
            "adapter_type": ADAPTER_TYPE,
            "smoke_test_state": smoke_test_state,
            "host": smoke_test_payload.get("host"),
            "port": smoke_test_payload.get("port"),
            "client_id": smoke_test_payload.get("client_id"),
            "socket_connection_succeeded": smoke_test_payload.get(
                "socket_connection_succeeded"
            ),
            "primary_candidate_id": smoke_test_payload.get("primary_candidate_id"),
            "primary_strategy_family": smoke_test_payload.get(
                "primary_strategy_family"
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
        "smoke_test_state": smoke_test_state,
        "readiness_state": smoke_test_payload.get("readiness_state"),
        "readiness_operation_state": smoke_test_payload.get(
            "readiness_operation_state"
        ),
        "broker": smoke_test_payload.get("broker"),
        "trading_mode": smoke_test_payload.get("trading_mode"),
        "ibkr_client": smoke_test_payload.get("ibkr_client"),
        "host": smoke_test_payload.get("host"),
        "port": smoke_test_payload.get("port"),
        "client_id": smoke_test_payload.get("client_id"),
        "timeout_seconds": smoke_test_payload.get("timeout_seconds"),
        "socket_connection_attempted": smoke_test_payload.get(
            "socket_connection_attempted"
        ),
        "socket_connection_succeeded": smoke_test_payload.get(
            "socket_connection_succeeded"
        ),
        "socket_error": smoke_test_payload.get("socket_error"),
        "broker_api_protocol_handshake_attempted": False,
        "market_data_request_attempted": False,
        "account_data_request_attempted": False,
        "position_request_attempted": False,
        "open_order_request_attempted": False,
        "order_submission_attempted": False,
        "primary_candidate_id": smoke_test_payload.get("primary_candidate_id"),
        "primary_strategy_family": smoke_test_payload.get("primary_strategy_family"),
        "order_submission_enabled": smoke_test_payload.get("order_submission_enabled"),
        "manual_approval_required": smoke_test_payload.get("manual_approval_required"),
        "blocked_reasons": blocked_reasons,
        "warnings": warnings,
        "operation_scope": "ibkr_paper_connection_smoke_test",
        "depends_on_artifacts": [
            "signalforge_ibkr_paper_trading_readiness_operation_record",
            "signalforge_ibkr_paper_trading_readiness",
            "signalforge_ibkr_paper_trading_readiness_summary",
        ],
        "produced_artifacts": [
            SMOKE_TEST_ARTIFACT_TYPE,
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


def build_ibkr_paper_connection_smoke_test_operation_log_event(
    operation_record: Mapping[str, Any],
) -> Dict[str, Any]:
    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": OPERATION_LOG_ARTIFACT_TYPE,
        "event_type": "ibkr_paper_connection_smoke_test_operation_completed",
        "operation_id": operation_record.get("operation_id"),
        "operation_state": operation_record.get("operation_state"),
        "smoke_test_state": operation_record.get("smoke_test_state"),
        "readiness_state": operation_record.get("readiness_state"),
        "host": operation_record.get("host"),
        "port": operation_record.get("port"),
        "client_id": operation_record.get("client_id"),
        "socket_connection_attempted": operation_record.get(
            "socket_connection_attempted"
        ),
        "socket_connection_succeeded": operation_record.get(
            "socket_connection_succeeded"
        ),
        "broker_api_protocol_handshake_attempted": operation_record.get(
            "broker_api_protocol_handshake_attempted"
        ),
        "market_data_request_attempted": operation_record.get(
            "market_data_request_attempted"
        ),
        "account_data_request_attempted": operation_record.get(
            "account_data_request_attempted"
        ),
        "order_submission_attempted": operation_record.get(
            "order_submission_attempted"
        ),
        "primary_candidate_id": operation_record.get("primary_candidate_id"),
        "primary_strategy_family": operation_record.get("primary_strategy_family"),
        "blocked_reasons": operation_record.get("blocked_reasons", []),
        "warnings": operation_record.get("warnings", []),
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def build_ibkr_paper_connection_smoke_test_operation_audit(
    operation_record: Mapping[str, Any],
) -> Dict[str, Any]:
    output_files = operation_record.get("output_files") or {}

    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": AUDIT_ARTIFACT_TYPE,
        "operation_id": operation_record.get("operation_id"),
        "audit_state": operation_record.get("operation_state"),
        "smoke_test_state": operation_record.get("smoke_test_state"),
        "checks": {
            "readiness_operation_ready": operation_record.get(
                "readiness_operation_state"
            )
            == "ready",
            "readiness_state_ready": operation_record.get("readiness_state")
            == "ready",
            "broker_is_ibkr": operation_record.get("broker") == "ibkr",
            "trading_mode_is_paper": operation_record.get("trading_mode") == "paper",
            "paper_port_is_allowed": operation_record.get("port")
            in ALLOWED_PAPER_PORTS,
            "client_id_present": operation_record.get("client_id") is not None,
            "socket_connection_attempted": operation_record.get(
                "socket_connection_attempted"
            )
            is True,
            "socket_connection_succeeded": operation_record.get(
                "socket_connection_succeeded"
            )
            is True,
            "broker_api_protocol_handshake_not_attempted": operation_record.get(
                "broker_api_protocol_handshake_attempted"
            )
            is False,
            "market_data_request_not_attempted": operation_record.get(
                "market_data_request_attempted"
            )
            is False,
            "account_data_request_not_attempted": operation_record.get(
                "account_data_request_attempted"
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
            "smoke_test_path_present": bool(output_files.get("smoke_test")),
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


def build_ibkr_paper_connection_smoke_test_operation_health(
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
        "host": operation_record.get("host"),
        "port": operation_record.get("port"),
        "client_id": operation_record.get("client_id"),
        "socket_connection_attempted": operation_record.get(
            "socket_connection_attempted"
        ),
        "socket_connection_succeeded": operation_record.get(
            "socket_connection_succeeded"
        ),
        "socket_error": operation_record.get("socket_error"),
        "primary_candidate_id": operation_record.get("primary_candidate_id"),
        "primary_strategy_family": operation_record.get("primary_strategy_family"),
        "blocked_reason_count": len(blocked_reasons),
        "warning_count": len(warnings),
        "blocked_reasons": blocked_reasons,
        "warnings": warnings,
        "next_recommended_action": _next_recommended_action(operation_state),
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def _default_socket_probe(host: str, port: int, timeout_seconds: float) -> Tuple[bool, Optional[str]]:
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return True, None
    except OSError as exc:
        return False, f"{type(exc).__name__}: {exc}"


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


def _classify_operation_state(smoke_test_state: str) -> str:
    if smoke_test_state in {"ready", "needs_review", "blocked"}:
        return smoke_test_state

    return "blocked"


def _next_recommended_action(operation_state: Any) -> str:
    if operation_state == "ready":
        return "build_ibkr_paper_account_snapshot_import_without_order_submission"

    if operation_state == "needs_review":
        return "review_ibkr_paper_connection_smoke_test_warnings_before_account_snapshot"

    return "resolve_ibkr_paper_connection_smoke_test_blockers_before_account_snapshot"


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
    return f"ibkr_paper_connection_smoke_test_operation_{digest}"


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