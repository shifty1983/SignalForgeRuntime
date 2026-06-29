from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence


ADAPTER_TYPE = "ibkr_paper_trading_readiness_operation"

READINESS_ARTIFACT_TYPE = "signalforge_ibkr_paper_trading_readiness"
SUMMARY_ARTIFACT_TYPE = "signalforge_ibkr_paper_trading_readiness_summary"
OPERATION_RECORD_ARTIFACT_TYPE = "signalforge_ibkr_paper_trading_readiness_operation_record"
OPERATION_LOG_ARTIFACT_TYPE = "signalforge_ibkr_paper_trading_readiness_operation_log"
AUDIT_ARTIFACT_TYPE = "signalforge_ibkr_paper_trading_readiness_operation_audit_report"
HEALTH_ARTIFACT_TYPE = "signalforge_ibkr_paper_trading_readiness_operation_health_report"
WRITE_RESULT_ARTIFACT_TYPE = "ibkr_paper_trading_readiness_operation_write_result"

READINESS_FILENAME = "signalforge_ibkr_paper_trading_readiness.json"
SUMMARY_FILENAME = "signalforge_ibkr_paper_trading_readiness_summary.json"
OPERATION_RECORD_FILENAME = "signalforge_ibkr_paper_trading_readiness_operation_record.json"
OPERATION_LOG_FILENAME = "signalforge_ibkr_paper_trading_readiness_operation_log.jsonl"
AUDIT_FILENAME = "signalforge_ibkr_paper_trading_readiness_operation_audit.json"
HEALTH_FILENAME = "signalforge_ibkr_paper_trading_readiness_operation_health.json"

DEFAULT_ALLOWED_PAPER_PORTS = [7497, 4002]

EXPLICIT_EXCLUSIONS = [
    "broker_api_calls",
    "order_routing",
    "order_submission",
    "fills",
    "live_execution",
    "slippage_modeling",
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


def load_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8-sig") as file:
        return json.load(file)


def run_ibkr_paper_trading_readiness_operation(
    *,
    config_path: str | Path,
    strategy_profile_operation_path: str | Path,
    output_dir: str | Path,
) -> Dict[str, Any]:
    output_dir_obj = Path(output_dir)
    output_dir_obj.mkdir(parents=True, exist_ok=True)

    readiness_path = output_dir_obj / READINESS_FILENAME
    summary_path = output_dir_obj / SUMMARY_FILENAME
    operation_record_path = output_dir_obj / OPERATION_RECORD_FILENAME
    operation_log_path = output_dir_obj / OPERATION_LOG_FILENAME
    audit_path = output_dir_obj / AUDIT_FILENAME
    health_path = output_dir_obj / HEALTH_FILENAME

    try:
        config_payload = load_json(config_path)
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        config_payload = {
            "blocked_reasons": [
                "ibkr_paper_config_load_failed",
                f"{type(exc).__name__}: {exc}",
            ]
        }

    try:
        strategy_profile_operation = load_json(strategy_profile_operation_path)
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        strategy_profile_operation = {
            "blocked_reasons": [
                "strategy_profile_operation_load_failed",
                f"{type(exc).__name__}: {exc}",
            ]
        }

    readiness_payload = build_ibkr_paper_trading_readiness(
        config_payload,
        strategy_profile_operation,
        config_path=str(config_path),
        strategy_profile_operation_path=str(strategy_profile_operation_path),
    )

    summary_payload = build_ibkr_paper_trading_readiness_summary(
        readiness_payload,
        readiness_path=str(readiness_path),
        summary_path=str(summary_path),
    )

    operation_paths = {
        "readiness": str(readiness_path),
        "summary": str(summary_path),
        "operation_record": str(operation_record_path),
        "operation_log": str(operation_log_path),
        "audit": str(audit_path),
        "health": str(health_path),
    }

    operation_record = build_ibkr_paper_trading_readiness_operation_record(
        readiness_payload,
        output_dir=str(output_dir_obj),
        operation_paths=operation_paths,
    )

    audit_report = build_ibkr_paper_trading_readiness_operation_audit(operation_record)
    health_report = build_ibkr_paper_trading_readiness_operation_health(operation_record)
    log_event = build_ibkr_paper_trading_readiness_operation_log_event(operation_record)

    _write_json(readiness_path, readiness_payload)
    _write_json(summary_path, summary_payload)
    _write_json(operation_record_path, operation_record)
    _write_json(audit_path, audit_report)
    _write_json(health_path, health_report)
    _write_jsonl(operation_log_path, [log_event])

    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": WRITE_RESULT_ARTIFACT_TYPE,
        "operation_id": operation_record["operation_id"],
        "readiness_state": readiness_payload["readiness_state"],
        "operation_state": operation_record["operation_state"],
        "broker": readiness_payload["broker"],
        "trading_mode": readiness_payload["trading_mode"],
        "ibkr_client": readiness_payload["ibkr_client"],
        "host": readiness_payload["host"],
        "port": readiness_payload["port"],
        "client_id": readiness_payload["client_id"],
        "account_id_masked": readiness_payload["account_id_masked"],
        "strategy_profile_operation_state": readiness_payload[
            "strategy_profile_operation_state"
        ],
        "primary_candidate_id": readiness_payload["primary_candidate_id"],
        "primary_strategy_family": readiness_payload["primary_strategy_family"],
        "order_submission_enabled": readiness_payload["order_submission_enabled"],
        "manual_approval_required": readiness_payload["manual_approval_required"],
        "blocked_reasons": readiness_payload["blocked_reasons"],
        "warnings": readiness_payload["warnings"],
        "readiness_path": str(readiness_path),
        "summary_path": str(summary_path),
        "operation_record_path": str(operation_record_path),
        "operation_log_path": str(operation_log_path),
        "audit_path": str(audit_path),
        "health_path": str(health_path),
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def build_ibkr_paper_trading_readiness(
    config_payload: Any,
    strategy_profile_operation: Any,
    *,
    config_path: Optional[str] = None,
    strategy_profile_operation_path: Optional[str] = None,
) -> Dict[str, Any]:
    blocked_reasons: list[str] = []
    warnings: list[str] = []

    if not isinstance(config_payload, Mapping):
        config_payload = {}
        blocked_reasons.extend(
            [
                "ibkr_paper_config_invalid_shape",
                "ibkr_paper_config_must_be_json_object",
            ]
        )

    if not isinstance(strategy_profile_operation, Mapping):
        strategy_profile_operation = {}
        blocked_reasons.extend(
            [
                "strategy_profile_operation_invalid_shape",
                "strategy_profile_operation_must_be_json_object",
            ]
        )

    config_blockers = _dedupe_strings(config_payload.get("blocked_reasons", []))
    strategy_blockers = _dedupe_strings(
        strategy_profile_operation.get("blocked_reasons", [])
    )

    blocked_reasons.extend(config_blockers)
    blocked_reasons.extend(strategy_blockers)

    broker = str(config_payload.get("broker") or "ibkr").lower()
    trading_mode = str(config_payload.get("trading_mode") or "").lower()
    ibkr_client = str(config_payload.get("ibkr_client") or "tws").lower()
    host = config_payload.get("host")
    port = _as_int(config_payload.get("port"))
    client_id = _as_int(config_payload.get("client_id"))
    account_id = config_payload.get("account_id")
    market_data_mode = config_payload.get("market_data_mode") or "not_declared"
    api_socket_enabled_confirmed = bool(
        config_payload.get("api_socket_enabled_confirmed")
    )
    order_submission_enabled = bool(config_payload.get("order_submission_enabled"))
    manual_approval_required = config_payload.get("manual_approval_required")

    if broker != "ibkr":
        blocked_reasons.append("broker_must_be_ibkr")

    if trading_mode != "paper":
        blocked_reasons.append("trading_mode_must_be_paper")

    if ibkr_client not in {"tws", "ib_gateway", "gateway"}:
        blocked_reasons.append("ibkr_client_must_be_tws_or_ib_gateway")

    if not host:
        blocked_reasons.append("host_required")

    if port is None:
        blocked_reasons.append("port_required")
    elif port not in DEFAULT_ALLOWED_PAPER_PORTS:
        blocked_reasons.append("paper_port_must_be_7497_or_4002")

    if client_id is None:
        blocked_reasons.append("client_id_required")

    if not api_socket_enabled_confirmed:
        warnings.append("api_socket_enabled_not_confirmed")

    if order_submission_enabled:
        blocked_reasons.append("order_submission_must_remain_disabled_for_readiness")

    if manual_approval_required is not True:
        blocked_reasons.append("manual_approval_required_must_be_true")

    strategy_operation_state = strategy_profile_operation.get("operation_state")
    strategy_profile_state = strategy_profile_operation.get("profile_export_state")

    if strategy_operation_state != "ready":
        blocked_reasons.append("strategy_profile_operation_must_be_ready")

    if strategy_profile_state != "ready":
        blocked_reasons.append("strategy_profile_export_must_be_ready")

    primary_candidate_id = strategy_profile_operation.get("primary_candidate_id")
    primary_strategy_family = strategy_profile_operation.get("primary_strategy_family")

    if not primary_candidate_id:
        blocked_reasons.append("primary_candidate_id_required")

    if not primary_strategy_family:
        blocked_reasons.append("primary_strategy_family_required")

    readiness_state = _classify_readiness_state(
        blocked_reasons=blocked_reasons,
        warnings=warnings,
    )

    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": READINESS_ARTIFACT_TYPE,
        "readiness_state": readiness_state,
        "broker": broker,
        "trading_mode": trading_mode,
        "ibkr_client": ibkr_client,
        "host": host,
        "port": port,
        "client_id": client_id,
        "account_id_masked": _mask_account_id(account_id),
        "market_data_mode": market_data_mode,
        "api_socket_enabled_confirmed": api_socket_enabled_confirmed,
        "order_submission_enabled": order_submission_enabled,
        "manual_approval_required": manual_approval_required is True,
        "strategy_profile_operation_state": strategy_operation_state,
        "strategy_profile_export_state": strategy_profile_state,
        "primary_candidate_id": primary_candidate_id,
        "primary_strategy_family": primary_strategy_family,
        "config_path": config_path,
        "strategy_profile_operation_path": strategy_profile_operation_path,
        "blocked_reasons": _dedupe_strings(blocked_reasons),
        "warnings": _dedupe_strings(warnings),
        "ibkr_connection_attempted": False,
        "broker_api_calls_attempted": False,
        "order_submission_attempted": False,
        "requires_manual_approval": True,
        **EXECUTION_DISABLED_FIELDS,
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def build_ibkr_paper_trading_readiness_summary(
    readiness_payload: Mapping[str, Any],
    *,
    readiness_path: Optional[str] = None,
    summary_path: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": SUMMARY_ARTIFACT_TYPE,
        "readiness_state": readiness_payload.get("readiness_state"),
        "broker": readiness_payload.get("broker"),
        "trading_mode": readiness_payload.get("trading_mode"),
        "ibkr_client": readiness_payload.get("ibkr_client"),
        "host": readiness_payload.get("host"),
        "port": readiness_payload.get("port"),
        "client_id": readiness_payload.get("client_id"),
        "account_id_masked": readiness_payload.get("account_id_masked"),
        "market_data_mode": readiness_payload.get("market_data_mode"),
        "api_socket_enabled_confirmed": readiness_payload.get(
            "api_socket_enabled_confirmed"
        ),
        "strategy_profile_operation_state": readiness_payload.get(
            "strategy_profile_operation_state"
        ),
        "strategy_profile_export_state": readiness_payload.get(
            "strategy_profile_export_state"
        ),
        "primary_candidate_id": readiness_payload.get("primary_candidate_id"),
        "primary_strategy_family": readiness_payload.get("primary_strategy_family"),
        "order_submission_enabled": readiness_payload.get("order_submission_enabled"),
        "manual_approval_required": readiness_payload.get("manual_approval_required"),
        "blocked_reason_count": len(readiness_payload.get("blocked_reasons", [])),
        "warning_count": len(readiness_payload.get("warnings", [])),
        "blocked_reasons": readiness_payload.get("blocked_reasons", []),
        "warnings": readiness_payload.get("warnings", []),
        "output_files": {
            "readiness": readiness_path,
            "summary": summary_path,
        },
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def build_ibkr_paper_trading_readiness_operation_record(
    readiness_payload: Any,
    *,
    output_dir: Optional[str],
    operation_paths: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    if not isinstance(readiness_payload, Mapping):
        readiness_payload = {
            "readiness_state": "blocked",
            "blocked_reasons": [
                "readiness_payload_invalid_shape",
                "readiness_payload_must_be_json_object",
            ],
            "warnings": [],
        }

    readiness_state = str(readiness_payload.get("readiness_state") or "blocked")
    operation_state = _classify_operation_state(readiness_state)

    blocked_reasons = _dedupe_strings(readiness_payload.get("blocked_reasons", []))
    warnings = _dedupe_strings(readiness_payload.get("warnings", []))

    operation_id = _stable_operation_id(
        {
            "adapter_type": ADAPTER_TYPE,
            "readiness_state": readiness_state,
            "broker": readiness_payload.get("broker"),
            "trading_mode": readiness_payload.get("trading_mode"),
            "ibkr_client": readiness_payload.get("ibkr_client"),
            "host": readiness_payload.get("host"),
            "port": readiness_payload.get("port"),
            "client_id": readiness_payload.get("client_id"),
            "primary_candidate_id": readiness_payload.get("primary_candidate_id"),
            "primary_strategy_family": readiness_payload.get(
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
        "readiness_state": readiness_state,
        "broker": readiness_payload.get("broker"),
        "trading_mode": readiness_payload.get("trading_mode"),
        "ibkr_client": readiness_payload.get("ibkr_client"),
        "host": readiness_payload.get("host"),
        "port": readiness_payload.get("port"),
        "client_id": readiness_payload.get("client_id"),
        "account_id_masked": readiness_payload.get("account_id_masked"),
        "market_data_mode": readiness_payload.get("market_data_mode"),
        "api_socket_enabled_confirmed": readiness_payload.get(
            "api_socket_enabled_confirmed"
        ),
        "strategy_profile_operation_state": readiness_payload.get(
            "strategy_profile_operation_state"
        ),
        "strategy_profile_export_state": readiness_payload.get(
            "strategy_profile_export_state"
        ),
        "primary_candidate_id": readiness_payload.get("primary_candidate_id"),
        "primary_strategy_family": readiness_payload.get("primary_strategy_family"),
        "order_submission_enabled": readiness_payload.get("order_submission_enabled"),
        "manual_approval_required": readiness_payload.get("manual_approval_required"),
        "ibkr_connection_attempted": False,
        "broker_api_calls_attempted": False,
        "order_submission_attempted": False,
        "requires_manual_approval": True,
        "blocked_reasons": blocked_reasons,
        "warnings": warnings,
        "operation_scope": "ibkr_paper_trading_readiness",
        "depends_on_artifacts": [
            "signalforge_primary_strategy_candidate_profile_export_operation_record",
            "signalforge_primary_strategy_candidate_profile_export",
            "signalforge_primary_strategy_candidate_profile_export_summary",
        ],
        "produced_artifacts": [
            READINESS_ARTIFACT_TYPE,
            SUMMARY_ARTIFACT_TYPE,
            OPERATION_RECORD_ARTIFACT_TYPE,
            OPERATION_LOG_ARTIFACT_TYPE,
            AUDIT_ARTIFACT_TYPE,
            HEALTH_ARTIFACT_TYPE,
        ],
        "output_dir": output_dir,
        "output_files": dict(operation_paths or {}),
        **EXECUTION_DISABLED_FIELDS,
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def build_ibkr_paper_trading_readiness_operation_log_event(
    operation_record: Mapping[str, Any],
) -> Dict[str, Any]:
    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": OPERATION_LOG_ARTIFACT_TYPE,
        "event_type": "ibkr_paper_trading_readiness_operation_completed",
        "operation_id": operation_record.get("operation_id"),
        "operation_state": operation_record.get("operation_state"),
        "readiness_state": operation_record.get("readiness_state"),
        "broker": operation_record.get("broker"),
        "trading_mode": operation_record.get("trading_mode"),
        "ibkr_client": operation_record.get("ibkr_client"),
        "host": operation_record.get("host"),
        "port": operation_record.get("port"),
        "client_id": operation_record.get("client_id"),
        "account_id_masked": operation_record.get("account_id_masked"),
        "primary_candidate_id": operation_record.get("primary_candidate_id"),
        "primary_strategy_family": operation_record.get("primary_strategy_family"),
        "order_submission_enabled": operation_record.get("order_submission_enabled"),
        "manual_approval_required": operation_record.get("manual_approval_required"),
        "blocked_reasons": operation_record.get("blocked_reasons", []),
        "warnings": operation_record.get("warnings", []),
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def build_ibkr_paper_trading_readiness_operation_audit(
    operation_record: Mapping[str, Any],
) -> Dict[str, Any]:
    output_files = operation_record.get("output_files") or {}

    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": AUDIT_ARTIFACT_TYPE,
        "operation_id": operation_record.get("operation_id"),
        "audit_state": operation_record.get("operation_state"),
        "readiness_state": operation_record.get("readiness_state"),
        "checks": {
            "broker_is_ibkr": operation_record.get("broker") == "ibkr",
            "trading_mode_is_paper": operation_record.get("trading_mode") == "paper",
            "paper_port_is_allowed": operation_record.get("port")
            in DEFAULT_ALLOWED_PAPER_PORTS,
            "client_id_present": operation_record.get("client_id") is not None,
            "strategy_profile_operation_ready": operation_record.get(
                "strategy_profile_operation_state"
            )
            == "ready",
            "strategy_profile_export_ready": operation_record.get(
                "strategy_profile_export_state"
            )
            == "ready",
            "primary_candidate_present": bool(
                operation_record.get("primary_candidate_id")
            ),
            "primary_strategy_family_present": bool(
                operation_record.get("primary_strategy_family")
            ),
            "order_submission_disabled": operation_record.get(
                "order_submission_enabled"
            )
            is False,
            "manual_approval_required": operation_record.get(
                "manual_approval_required"
            )
            is True,
            "ibkr_connection_not_attempted": operation_record.get(
                "ibkr_connection_attempted"
            )
            is False,
            "broker_api_calls_not_attempted": operation_record.get(
                "broker_api_calls_attempted"
            )
            is False,
            "order_submission_not_attempted": operation_record.get(
                "order_submission_attempted"
            )
            is False,
            "operation_record_path_present": bool(output_files.get("operation_record")),
            "operation_log_path_present": bool(output_files.get("operation_log")),
            "audit_path_present": bool(output_files.get("audit")),
            "health_path_present": bool(output_files.get("health")),
            "readiness_path_present": bool(output_files.get("readiness")),
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


def build_ibkr_paper_trading_readiness_operation_health(
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
        "broker": operation_record.get("broker"),
        "trading_mode": operation_record.get("trading_mode"),
        "ibkr_client": operation_record.get("ibkr_client"),
        "host": operation_record.get("host"),
        "port": operation_record.get("port"),
        "client_id": operation_record.get("client_id"),
        "account_id_masked": operation_record.get("account_id_masked"),
        "primary_candidate_id": operation_record.get("primary_candidate_id"),
        "primary_strategy_family": operation_record.get("primary_strategy_family"),
        "order_submission_enabled": operation_record.get("order_submission_enabled"),
        "manual_approval_required": operation_record.get("manual_approval_required"),
        "blocked_reason_count": len(blocked_reasons),
        "warning_count": len(warnings),
        "blocked_reasons": blocked_reasons,
        "warnings": warnings,
        "next_recommended_action": _next_recommended_action(operation_state),
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def _classify_readiness_state(
    *,
    blocked_reasons: Sequence[str],
    warnings: Sequence[str],
) -> str:
    if blocked_reasons:
        return "blocked"

    if warnings:
        return "needs_review"

    return "ready"


def _classify_operation_state(readiness_state: str) -> str:
    if readiness_state in {"ready", "needs_review", "blocked"}:
        return readiness_state

    return "blocked"


def _next_recommended_action(operation_state: Any) -> str:
    if operation_state == "ready":
        return "build_ibkr_paper_connection_smoke_test_without_order_submission"

    if operation_state == "needs_review":
        return "confirm_ibkr_api_socket_settings_before_connection_smoke_test"

    return "resolve_ibkr_paper_trading_readiness_blockers_before_connection_smoke_test"


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


def _mask_account_id(account_id: Any) -> Optional[str]:
    if account_id in (None, ""):
        return None

    account_text = str(account_id)

    if len(account_text) <= 4:
        return "****"

    return f"{account_text[:2]}****{account_text[-2:]}"


def _stable_operation_id(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, default=str)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return f"ibkr_paper_trading_readiness_operation_{digest}"


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