from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence


ADAPTER_TYPE = "primary_strategy_paper_order_intent_export"

ARTIFACT_TYPE = "signalforge_primary_strategy_paper_order_intent_export"
SUMMARY_ARTIFACT_TYPE = "signalforge_primary_strategy_paper_order_intent_export_summary"
WRITE_RESULT_ARTIFACT_TYPE = "primary_strategy_paper_order_intent_export_write_result"

EXPORT_FILENAME = "signalforge_primary_strategy_paper_order_intent_export.json"
SUMMARY_FILENAME = "signalforge_primary_strategy_paper_order_intent_export_summary.json"

EXPLICIT_EXCLUSIONS = [
    "broker_api_calls",
    "order_routing",
    "order_submission",
    "fills",
    "live_execution",
    "slippage_modeling",
    "market_data_request",
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


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, sort_keys=True)
        file.write("\n")


def export_primary_strategy_paper_order_intent(
    *,
    strategy_profile_operation_path: str | Path,
    account_snapshot_operation_path: str | Path,
    order_intent_config_path: str | Path,
    output_dir: str | Path,
) -> Dict[str, Any]:
    output_dir_obj = Path(output_dir)
    output_dir_obj.mkdir(parents=True, exist_ok=True)

    export_path = output_dir_obj / EXPORT_FILENAME
    summary_path = output_dir_obj / SUMMARY_FILENAME

    try:
        strategy_profile_operation = load_json(strategy_profile_operation_path)
    except Exception as exc:  # pragma: no cover
        strategy_profile_operation = {
            "operation_state": "blocked",
            "profile_export_state": "blocked",
            "blocked_reasons": [
                "strategy_profile_operation_load_failed",
                f"{type(exc).__name__}: {exc}",
            ],
            "warnings": [],
        }

    try:
        account_snapshot_operation = load_json(account_snapshot_operation_path)
        account_snapshot_operation = hydrate_account_snapshot_operation_details(
            account_snapshot_operation,
            operation_path=account_snapshot_operation_path,
        )
    except Exception as exc:  # pragma: no cover
        account_snapshot_operation = {
            "operation_state": "blocked",
            "snapshot_state": "blocked",
            "blocked_reasons": [
                "account_snapshot_operation_load_failed",
                f"{type(exc).__name__}: {exc}",
            ],
            "warnings": [],
        }

    try:
        order_intent_config = load_json(order_intent_config_path)
    except Exception as exc:  # pragma: no cover
        order_intent_config = {
            "blocked_reasons": [
                "paper_order_intent_config_load_failed",
                f"{type(exc).__name__}: {exc}",
            ],
            "warnings": [],
        }

    export_payload = build_primary_strategy_paper_order_intent_export(
        strategy_profile_operation,
        account_snapshot_operation,
        order_intent_config,
        strategy_profile_operation_path=str(strategy_profile_operation_path),
        account_snapshot_operation_path=str(account_snapshot_operation_path),
        order_intent_config_path=str(order_intent_config_path),
    )

    summary_payload = build_primary_strategy_paper_order_intent_export_summary(
        export_payload,
        export_path=str(export_path),
        summary_path=str(summary_path),
    )

    write_json(export_path, export_payload)
    write_json(summary_path, summary_payload)

    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": WRITE_RESULT_ARTIFACT_TYPE,
        "intent_state": export_payload["intent_state"],
        "paper_trading_mode": export_payload["paper_trading_mode"],
        "order_submission_enabled": export_payload["order_submission_enabled"],
        "requires_manual_approval": export_payload["requires_manual_approval"],
        "primary_candidate_id": export_payload["primary_candidate_id"],
        "primary_strategy_family": export_payload["primary_strategy_family"],
        "symbol": export_payload["symbol"],
        "strategy_direction": export_payload["strategy_direction"],
        "instrument_type": export_payload["instrument_type"],
        "max_trade_risk_amount": export_payload["max_trade_risk_amount"],
        "max_account_allocation_fraction": export_payload[
            "max_account_allocation_fraction"
        ],
        "blocked_reasons": export_payload["blocked_reasons"],
        "warnings": export_payload["warnings"],
        "export_path": str(export_path),
        "summary_path": str(summary_path),
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def build_primary_strategy_paper_order_intent_export(
    strategy_profile_operation: Any,
    account_snapshot_operation: Any,
    order_intent_config: Any,
    *,
    strategy_profile_operation_path: Optional[str] = None,
    account_snapshot_operation_path: Optional[str] = None,
    order_intent_config_path: Optional[str] = None,
) -> Dict[str, Any]:
    blocked_reasons: list[str] = []
    warnings: list[str] = []

    if not isinstance(strategy_profile_operation, Mapping):
        strategy_profile_operation = {}
        blocked_reasons.extend(
            [
                "strategy_profile_operation_invalid_shape",
                "strategy_profile_operation_must_be_json_object",
            ]
        )

    if not isinstance(account_snapshot_operation, Mapping):
        account_snapshot_operation = {}
        blocked_reasons.extend(
            [
                "account_snapshot_operation_invalid_shape",
                "account_snapshot_operation_must_be_json_object",
            ]
        )

    if not isinstance(order_intent_config, Mapping):
        order_intent_config = {}
        blocked_reasons.extend(
            [
                "paper_order_intent_config_invalid_shape",
                "paper_order_intent_config_must_be_json_object",
            ]
        )

    blocked_reasons.extend(
        _dedupe_strings(strategy_profile_operation.get("blocked_reasons", []))
    )
    blocked_reasons.extend(
        _dedupe_strings(account_snapshot_operation.get("blocked_reasons", []))
    )
    blocked_reasons.extend(_dedupe_strings(order_intent_config.get("blocked_reasons", [])))

    warnings.extend(_dedupe_strings(strategy_profile_operation.get("warnings", [])))
    warnings.extend(_dedupe_strings(account_snapshot_operation.get("warnings", [])))
    warnings.extend(_dedupe_strings(order_intent_config.get("warnings", [])))

    strategy_operation_state = strategy_profile_operation.get("operation_state")
    profile_export_state = strategy_profile_operation.get("profile_export_state")
    snapshot_operation_state = account_snapshot_operation.get("operation_state")
    snapshot_state = account_snapshot_operation.get("snapshot_state")

    if strategy_operation_state != "ready":
        blocked_reasons.append("strategy_profile_operation_must_be_ready")

    if profile_export_state != "ready":
        blocked_reasons.append("strategy_profile_export_must_be_ready")

    if snapshot_operation_state != "ready":
        blocked_reasons.append("account_snapshot_operation_must_be_ready")

    if snapshot_state != "ready":
        blocked_reasons.append("account_snapshot_state_must_be_ready")

    primary_candidate_id = strategy_profile_operation.get("primary_candidate_id")
    primary_strategy_family = strategy_profile_operation.get("primary_strategy_family")
    selected_window_days = _as_int(strategy_profile_operation.get("selected_window_days"))

    if not primary_candidate_id:
        blocked_reasons.append("primary_candidate_id_required")

    if not primary_strategy_family:
        blocked_reasons.append("primary_strategy_family_required")

    paper_trading_mode = order_intent_config.get("paper_trading_mode")
    order_submission_enabled = bool(order_intent_config.get("order_submission_enabled"))
    manual_approval_required = order_intent_config.get("manual_approval_required")
    allow_order_intent_without_contract = bool(
        order_intent_config.get("allow_order_intent_without_contract")
    )

    if paper_trading_mode is not True:
        blocked_reasons.append("paper_trading_mode_must_be_true")

    if order_submission_enabled:
        blocked_reasons.append("order_submission_must_be_disabled_for_intent_export")

    if manual_approval_required is not True:
        blocked_reasons.append("manual_approval_required_must_be_true")

    symbol = _clean_string(order_intent_config.get("symbol"))
    instrument_type = _clean_string(order_intent_config.get("instrument_type"))
    strategy_direction = _clean_string(order_intent_config.get("strategy_direction"))
    contract_selection_rules = order_intent_config.get("contract_selection_rules")
    risk_budget = order_intent_config.get("risk_budget")
    order_constraints = order_intent_config.get("order_constraints") or {}

    if not symbol:
        blocked_reasons.append("symbol_required")

    if not instrument_type:
        blocked_reasons.append("instrument_type_required")

    if not strategy_direction:
        blocked_reasons.append("strategy_direction_required")

    if not isinstance(contract_selection_rules, Mapping):
        blocked_reasons.append("contract_selection_rules_required")
        contract_selection_rules = {}

    if not isinstance(risk_budget, Mapping):
        blocked_reasons.append("risk_budget_required")
        risk_budget = {}

    max_trade_risk_amount = _as_float(risk_budget.get("max_trade_risk_amount"))
    max_account_allocation_fraction = _as_float(
        risk_budget.get("max_account_allocation_fraction")
    )
    max_contract_quantity = _as_int(risk_budget.get("max_contract_quantity"))
    net_liquidation_value = _extract_account_metric(
        account_snapshot_operation,
        "NetLiquidation",
    )
    buying_power = _extract_account_metric(
        account_snapshot_operation,
        "BuyingPower",
    )

    if max_trade_risk_amount is None:
        blocked_reasons.append("max_trade_risk_amount_required")
    elif max_trade_risk_amount <= 0:
        blocked_reasons.append("max_trade_risk_amount_must_be_positive")

    if max_account_allocation_fraction is None:
        blocked_reasons.append("max_account_allocation_fraction_required")
    elif not 0 < max_account_allocation_fraction <= 1:
        blocked_reasons.append("max_account_allocation_fraction_must_be_between_0_and_1")

    if max_contract_quantity is None:
        blocked_reasons.append("max_contract_quantity_required")
    elif max_contract_quantity <= 0:
        blocked_reasons.append("max_contract_quantity_must_be_positive")

    if net_liquidation_value is None:
        warnings.append("net_liquidation_value_not_available_from_snapshot")

    if buying_power is None:
        warnings.append("buying_power_not_available_from_snapshot")

    unresolved_contract_reasons = _contract_resolution_blockers(
        instrument_type=instrument_type,
        contract_selection_rules=contract_selection_rules,
    )

    if unresolved_contract_reasons and not allow_order_intent_without_contract:
        blocked_reasons.extend(unresolved_contract_reasons)
    elif unresolved_contract_reasons:
        warnings.extend(unresolved_contract_reasons)

    intent_state = _classify_state(
        blocked_reasons=blocked_reasons,
        warnings=warnings,
    )

    order_intent = {
        "intent_type": "paper_order_intent",
        "paper_trading_mode": True,
        "order_submission_enabled": False,
        "requires_manual_approval": True,
        "symbol": symbol,
        "instrument_type": instrument_type,
        "strategy_direction": strategy_direction,
        "contract_status": (
            "contract_rules_declared"
            if isinstance(contract_selection_rules, Mapping) and contract_selection_rules
            else "contract_rules_missing"
        ),
        "contract_selection_rules": _json_safe(contract_selection_rules),
        "risk_budget": {
            "max_trade_risk_amount": max_trade_risk_amount,
            "max_account_allocation_fraction": max_account_allocation_fraction,
            "max_contract_quantity": max_contract_quantity,
            "net_liquidation_value": net_liquidation_value,
            "buying_power": buying_power,
        },
        "order_constraints": _json_safe(order_constraints),
        "order_action": None,
        "quantity": None,
        "limit_price": None,
        "time_in_force": order_constraints.get("time_in_force"),
        "order_type": order_constraints.get("order_type"),
        "submit_order": False,
    }

    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": ARTIFACT_TYPE,
        "intent_state": intent_state,
        "paper_trading_mode": True,
        "order_submission_enabled": False,
        "requires_manual_approval": True,
        "strategy_profile_operation_state": strategy_operation_state,
        "strategy_profile_export_state": profile_export_state,
        "account_snapshot_operation_state": snapshot_operation_state,
        "account_snapshot_state": snapshot_state,
        "primary_candidate_id": primary_candidate_id,
        "primary_strategy_family": primary_strategy_family,
        "selected_window_days": selected_window_days,
        "symbol": symbol,
        "instrument_type": instrument_type,
        "strategy_direction": strategy_direction,
        "max_trade_risk_amount": max_trade_risk_amount,
        "max_account_allocation_fraction": max_account_allocation_fraction,
        "max_contract_quantity": max_contract_quantity,
        "net_liquidation_value": net_liquidation_value,
        "buying_power": buying_power,
        "managed_account_count": account_snapshot_operation.get(
            "managed_account_count", 0
        ),
        "account_summary_row_count": account_snapshot_operation.get(
            "account_summary_row_count", 0
        ),
        "position_count": account_snapshot_operation.get("position_count", 0),
        "order_intent": order_intent,
        "strategy_profile_operation_path": strategy_profile_operation_path,
        "account_snapshot_operation_path": account_snapshot_operation_path,
        "order_intent_config_path": order_intent_config_path,
        "blocked_reasons": _dedupe_strings(blocked_reasons),
        "warnings": _dedupe_strings(warnings),
        **EXECUTION_DISABLED_FIELDS,
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def build_primary_strategy_paper_order_intent_export_summary(
    export_payload: Mapping[str, Any],
    *,
    export_path: Optional[str] = None,
    summary_path: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": SUMMARY_ARTIFACT_TYPE,
        "intent_state": export_payload.get("intent_state"),
        "paper_trading_mode": export_payload.get("paper_trading_mode"),
        "order_submission_enabled": export_payload.get("order_submission_enabled"),
        "requires_manual_approval": export_payload.get("requires_manual_approval"),
        "primary_candidate_id": export_payload.get("primary_candidate_id"),
        "primary_strategy_family": export_payload.get("primary_strategy_family"),
        "selected_window_days": export_payload.get("selected_window_days"),
        "symbol": export_payload.get("symbol"),
        "instrument_type": export_payload.get("instrument_type"),
        "strategy_direction": export_payload.get("strategy_direction"),
        "max_trade_risk_amount": export_payload.get("max_trade_risk_amount"),
        "max_account_allocation_fraction": export_payload.get(
            "max_account_allocation_fraction"
        ),
        "max_contract_quantity": export_payload.get("max_contract_quantity"),
        "net_liquidation_value": export_payload.get("net_liquidation_value"),
        "buying_power": export_payload.get("buying_power"),
        "managed_account_count": export_payload.get("managed_account_count", 0),
        "account_summary_row_count": export_payload.get(
            "account_summary_row_count", 0
        ),
        "position_count": export_payload.get("position_count", 0),
        "blocked_reason_count": len(export_payload.get("blocked_reasons", [])),
        "warning_count": len(export_payload.get("warnings", [])),
        "blocked_reasons": export_payload.get("blocked_reasons", []),
        "warnings": export_payload.get("warnings", []),
        "output_files": {
            "export": export_path,
            "summary": summary_path,
        },
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }

def hydrate_account_snapshot_operation_details(
    account_snapshot_operation: Any,
    *,
    operation_path: str | Path,
) -> Any:
    if not isinstance(account_snapshot_operation, Mapping):
        return account_snapshot_operation

    if account_snapshot_operation.get("account_summary_rows"):
        return account_snapshot_operation

    output_files = account_snapshot_operation.get("output_files")

    if not isinstance(output_files, Mapping):
        return account_snapshot_operation

    snapshot_path = output_files.get("snapshot")

    if not snapshot_path:
        return account_snapshot_operation

    snapshot_path_obj = Path(snapshot_path)

    if not snapshot_path_obj.exists():
        operation_path_obj = Path(operation_path)
        candidate_path = operation_path_obj.parent / snapshot_path_obj.name

        if candidate_path.exists():
            snapshot_path_obj = candidate_path

    if not snapshot_path_obj.exists():
        return account_snapshot_operation

    snapshot_payload = load_json(snapshot_path_obj)

    if not isinstance(snapshot_payload, Mapping):
        return account_snapshot_operation

    hydrated = dict(account_snapshot_operation)

    for key in [
        "managed_accounts_masked",
        "account_summary_rows",
        "positions",
        "managed_account_count",
        "account_summary_row_count",
        "position_count",
    ]:
        if key in snapshot_payload:
            hydrated[key] = snapshot_payload[key]

    return hydrated

def _contract_resolution_blockers(
    *,
    instrument_type: Optional[str],
    contract_selection_rules: Mapping[str, Any],
) -> list[str]:
    if not instrument_type:
        return []

    normalized = instrument_type.lower()
    blockers: list[str] = []

    if normalized in {"option", "options", "option_strategy"}:
        required_keys = [
            "expiration_selection",
            "strike_selection",
            "right",
            "max_bid_ask_spread",
            "min_open_interest",
        ]

        for key in required_keys:
            if contract_selection_rules.get(key) in (None, ""):
                blockers.append(f"{key}_required")

    elif normalized in {"stock", "equity"}:
        return []

    else:
        blockers.append("unsupported_instrument_type")

    return blockers


def _extract_account_metric(
    account_snapshot_operation: Mapping[str, Any],
    tag: str,
) -> Optional[float]:
    rows = account_snapshot_operation.get("account_summary_rows")

    if not isinstance(rows, Sequence) or isinstance(rows, str):
        return None

    for row in rows:
        if not isinstance(row, Mapping):
            continue

        if row.get("tag") == tag:
            return _as_float(row.get("value"))

    return None


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


def _as_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        try:
            return float(cleaned)
        except ValueError:
            return None

    return None


def _clean_string(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None

    return str(value).strip()


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


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))