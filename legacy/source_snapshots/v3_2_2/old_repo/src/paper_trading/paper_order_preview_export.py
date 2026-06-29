from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence


ADAPTER_TYPE = "paper_order_preview_export"

ARTIFACT_TYPE = "signalforge_paper_order_preview_export"
SUMMARY_ARTIFACT_TYPE = "signalforge_paper_order_preview_export_summary"
WRITE_RESULT_ARTIFACT_TYPE = "paper_order_preview_export_write_result"

EXPORT_FILENAME = "signalforge_paper_order_preview_export.json"
SUMMARY_FILENAME = "signalforge_paper_order_preview_export_summary.json"

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


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, sort_keys=True)
        file.write("\n")


def export_paper_order_preview(
    *,
    paper_order_intent_operation_path: str | Path,
    option_contract_resolver_operation_path: str | Path,
    option_quote_validation_operation_path: str | Path,
    output_dir: str | Path,
) -> Dict[str, Any]:
    output_dir_obj = Path(output_dir)
    output_dir_obj.mkdir(parents=True, exist_ok=True)

    export_path = output_dir_obj / EXPORT_FILENAME
    summary_path = output_dir_obj / SUMMARY_FILENAME

    try:
        paper_order_intent_operation = load_json(paper_order_intent_operation_path)
    except Exception as exc:  # pragma: no cover
        paper_order_intent_operation = {
            "operation_state": "blocked",
            "intent_state": "blocked",
            "blocked_reasons": [
                "paper_order_intent_operation_load_failed",
                f"{type(exc).__name__}: {exc}",
            ],
            "warnings": [],
        }

    try:
        option_contract_resolver_operation = load_json(
            option_contract_resolver_operation_path
        )
    except Exception as exc:  # pragma: no cover
        option_contract_resolver_operation = {
            "operation_state": "blocked",
            "contract_resolution_state": "blocked",
            "blocked_reasons": [
                "option_contract_resolver_operation_load_failed",
                f"{type(exc).__name__}: {exc}",
            ],
            "warnings": [],
        }

    try:
        option_quote_validation_operation = load_json(
            option_quote_validation_operation_path
        )
    except Exception as exc:  # pragma: no cover
        option_quote_validation_operation = {
            "operation_state": "blocked",
            "quote_validation_state": "blocked",
            "blocked_reasons": [
                "option_quote_validation_operation_load_failed",
                f"{type(exc).__name__}: {exc}",
            ],
            "warnings": [],
        }

    option_quote_validation_operation = hydrate_operation_details_from_export(
        option_quote_validation_operation,
        operation_path=option_quote_validation_operation_path,
    )
    option_contract_resolver_operation = hydrate_operation_details_from_export(
        option_contract_resolver_operation,
        operation_path=option_contract_resolver_operation_path,
    )

    export_payload = build_paper_order_preview_export(
        paper_order_intent_operation,
        option_contract_resolver_operation,
        option_quote_validation_operation,
        paper_order_intent_operation_path=str(paper_order_intent_operation_path),
        option_contract_resolver_operation_path=str(
            option_contract_resolver_operation_path
        ),
        option_quote_validation_operation_path=str(
            option_quote_validation_operation_path
        ),
    )

    summary_payload = build_paper_order_preview_export_summary(
        export_payload,
        export_path=str(export_path),
        summary_path=str(summary_path),
    )

    write_json(export_path, export_payload)
    write_json(summary_path, summary_payload)

    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": WRITE_RESULT_ARTIFACT_TYPE,
        "paper_order_preview_state": export_payload["paper_order_preview_state"],
        "paper_trading_mode": export_payload["paper_trading_mode"],
        "order_submission_enabled": export_payload["order_submission_enabled"],
        "submit_order": export_payload["submit_order"],
        "requires_manual_approval": export_payload["requires_manual_approval"],
        "symbol": export_payload["symbol"],
        "spread_type": export_payload["spread_type"],
        "expiration": export_payload["expiration"],
        "quantity": export_payload["quantity"],
        "limit_price": export_payload["limit_price"],
        "max_loss_amount": export_payload["max_loss_amount"],
        "blocked_reasons": export_payload["blocked_reasons"],
        "warnings": export_payload["warnings"],
        "export_path": str(export_path),
        "summary_path": str(summary_path),
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def build_paper_order_preview_export(
    paper_order_intent_operation: Any,
    option_contract_resolver_operation: Any,
    option_quote_validation_operation: Any,
    *,
    paper_order_intent_operation_path: Optional[str] = None,
    option_contract_resolver_operation_path: Optional[str] = None,
    option_quote_validation_operation_path: Optional[str] = None,
) -> Dict[str, Any]:
    blocked_reasons: list[str] = []
    warnings: list[str] = []

    if not isinstance(paper_order_intent_operation, Mapping):
        paper_order_intent_operation = {}
        blocked_reasons.extend(
            [
                "paper_order_intent_operation_invalid_shape",
                "paper_order_intent_operation_must_be_json_object",
            ]
        )

    if not isinstance(option_contract_resolver_operation, Mapping):
        option_contract_resolver_operation = {}
        blocked_reasons.extend(
            [
                "option_contract_resolver_operation_invalid_shape",
                "option_contract_resolver_operation_must_be_json_object",
            ]
        )

    if not isinstance(option_quote_validation_operation, Mapping):
        option_quote_validation_operation = {}
        blocked_reasons.extend(
            [
                "option_quote_validation_operation_invalid_shape",
                "option_quote_validation_operation_must_be_json_object",
            ]
        )

    blocked_reasons.extend(
        _dedupe_strings(paper_order_intent_operation.get("blocked_reasons", []))
    )
    blocked_reasons.extend(
        _dedupe_strings(option_contract_resolver_operation.get("blocked_reasons", []))
    )
    blocked_reasons.extend(
        _dedupe_strings(option_quote_validation_operation.get("blocked_reasons", []))
    )

    warnings.extend(_dedupe_strings(paper_order_intent_operation.get("warnings", [])))
    warnings.extend(
        _dedupe_strings(option_contract_resolver_operation.get("warnings", []))
    )
    warnings.extend(_dedupe_strings(option_quote_validation_operation.get("warnings", [])))

    intent_operation_state = paper_order_intent_operation.get("operation_state")
    intent_state = paper_order_intent_operation.get("intent_state")
    resolver_operation_state = option_contract_resolver_operation.get("operation_state")
    contract_resolution_state = option_contract_resolver_operation.get(
        "contract_resolution_state"
    )
    quote_operation_state = option_quote_validation_operation.get("operation_state")
    quote_validation_state = option_quote_validation_operation.get(
        "quote_validation_state"
    )

    if intent_operation_state != "ready":
        blocked_reasons.append("paper_order_intent_operation_must_be_ready")

    if intent_state != "ready":
        blocked_reasons.append("paper_order_intent_state_must_be_ready")

    if resolver_operation_state == "blocked":
        blocked_reasons.append("option_contract_resolver_operation_must_not_be_blocked")
    elif resolver_operation_state not in {"ready", "needs_review"}:
        blocked_reasons.append(
            "option_contract_resolver_operation_must_be_ready_or_needs_review"
        )

    if contract_resolution_state == "blocked":
        blocked_reasons.append("contract_resolution_state_must_not_be_blocked")
    elif contract_resolution_state not in {"ready", "needs_review"}:
        blocked_reasons.append(
            "contract_resolution_state_must_be_ready_or_needs_review"
        )

    if quote_operation_state != "ready":
        blocked_reasons.append("option_quote_validation_operation_must_be_ready")

    if quote_validation_state != "ready":
        blocked_reasons.append("option_quote_validation_state_must_be_ready")

    if paper_order_intent_operation.get("order_submission_enabled") is True:
        blocked_reasons.append("paper_order_intent_order_submission_must_be_disabled")

    if option_contract_resolver_operation.get("order_submission_enabled") is True:
        blocked_reasons.append("contract_resolver_order_submission_must_be_disabled")

    if option_quote_validation_operation.get("order_submission_enabled") is True:
        blocked_reasons.append("quote_validation_order_submission_must_be_disabled")

    symbol = (
        _clean_string(option_quote_validation_operation.get("symbol"))
        or _clean_string(option_contract_resolver_operation.get("symbol"))
        or _clean_string(paper_order_intent_operation.get("symbol"))
    )
    spread_type = (
        _clean_string(option_quote_validation_operation.get("spread_type"))
        or _clean_string(option_contract_resolver_operation.get("spread_type"))
    )
    expiration = (
        _clean_string(option_quote_validation_operation.get("expiration"))
        or _clean_string(option_contract_resolver_operation.get("expiration"))
    )

    long_leg = option_quote_validation_operation.get("long_leg") or (
        option_contract_resolver_operation.get("long_leg")
    )
    short_leg = option_quote_validation_operation.get("short_leg") or (
        option_contract_resolver_operation.get("short_leg")
    )

    if not isinstance(long_leg, Mapping):
        long_leg = {}
        blocked_reasons.append("long_leg_required")

    if not isinstance(short_leg, Mapping):
        short_leg = {}
        blocked_reasons.append("short_leg_required")

    quantity = _as_int(option_quote_validation_operation.get("quantity")) or 1
    conservative_net_debit = _as_float(
        option_quote_validation_operation.get("conservative_net_debit")
    )
    mid_net_debit = _as_float(option_quote_validation_operation.get("mid_net_debit"))
    max_loss_amount = _as_float(
        option_quote_validation_operation.get("max_loss_amount")
    )
    max_profit_amount = _as_float(
        option_quote_validation_operation.get("max_profit_amount")
    )
    max_trade_risk_amount = _as_float(
        option_quote_validation_operation.get("max_trade_risk_amount")
        or option_contract_resolver_operation.get("max_trade_risk_amount")
    )

    if not symbol:
        blocked_reasons.append("symbol_required")

    if spread_type != "bull_call_spread":
        blocked_reasons.append("spread_type_must_be_bull_call_spread")

    if not expiration:
        blocked_reasons.append("expiration_required")

    if conservative_net_debit is None:
        blocked_reasons.append("conservative_net_debit_required")

    if max_loss_amount is None:
        blocked_reasons.append("max_loss_amount_required")

    if max_trade_risk_amount is None:
        blocked_reasons.append("max_trade_risk_amount_required")

    if (
        max_loss_amount is not None
        and max_trade_risk_amount is not None
        and max_loss_amount > max_trade_risk_amount
    ):
        blocked_reasons.append("max_loss_exceeds_max_trade_risk_amount")

    limit_price = conservative_net_debit

    combo_legs = [
        {
            "leg_role": "long_call",
            "action": "BUY",
            "ratio": 1,
            "symbol": long_leg.get("symbol"),
            "sec_type": long_leg.get("sec_type") or long_leg.get("secType"),
            "exchange": long_leg.get("exchange"),
            "currency": long_leg.get("currency"),
            "last_trade_date_or_contract_month": long_leg.get(
                "last_trade_date_or_contract_month"
            )
            or long_leg.get("lastTradeDateOrContractMonth"),
            "right": long_leg.get("right"),
            "strike": long_leg.get("strike"),
            "multiplier": long_leg.get("multiplier"),
            "trading_class": long_leg.get("trading_class")
            or long_leg.get("tradingClass"),
        },
        {
            "leg_role": "short_call",
            "action": "SELL",
            "ratio": 1,
            "symbol": short_leg.get("symbol"),
            "sec_type": short_leg.get("sec_type") or short_leg.get("secType"),
            "exchange": short_leg.get("exchange"),
            "currency": short_leg.get("currency"),
            "last_trade_date_or_contract_month": short_leg.get(
                "last_trade_date_or_contract_month"
            )
            or short_leg.get("lastTradeDateOrContractMonth"),
            "right": short_leg.get("right"),
            "strike": short_leg.get("strike"),
            "multiplier": short_leg.get("multiplier"),
            "trading_class": short_leg.get("trading_class")
            or short_leg.get("tradingClass"),
        },
    ]

    order_preview = {
        "preview_type": "paper_combo_order_preview",
        "paper_trading_mode": True,
        "order_submission_enabled": False,
        "submit_order": False,
        "requires_manual_approval": True,
        "broker": "ibkr",
        "symbol": symbol,
        "spread_type": spread_type,
        "strategy_direction": paper_order_intent_operation.get(
            "strategy_direction"
        )
        or option_contract_resolver_operation.get("strategy_direction"),
        "expiration": expiration,
        "order_action": "BUY",
        "order_type": "LMT",
        "time_in_force": "DAY",
        "quantity": quantity,
        "limit_price": limit_price,
        "price_basis": "conservative_net_debit",
        "currency": "USD",
        "combo_legs": combo_legs,
        "estimated_max_loss_amount": max_loss_amount,
        "estimated_max_profit_amount": max_profit_amount,
        "manual_approval_required_before_submit": True,
    }

    paper_order_preview_state = _classify_state(
        blocked_reasons=blocked_reasons,
        warnings=warnings,
    )

    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": ARTIFACT_TYPE,
        "paper_order_preview_state": paper_order_preview_state,
        "paper_trading_mode": True,
        "order_submission_enabled": False,
        "submit_order": False,
        "requires_manual_approval": True,
        "symbol": symbol,
        "spread_type": spread_type,
        "expiration": expiration,
        "quantity": quantity,
        "limit_price": limit_price,
        "conservative_net_debit": conservative_net_debit,
        "mid_net_debit": mid_net_debit,
        "max_loss_amount": max_loss_amount,
        "max_profit_amount": max_profit_amount,
        "max_trade_risk_amount": max_trade_risk_amount,
        "order_preview": order_preview,
        "paper_order_intent_operation_state": intent_operation_state,
        "paper_order_intent_state": intent_state,
        "option_contract_resolver_operation_state": resolver_operation_state,
        "contract_resolution_state": contract_resolution_state,
        "option_quote_validation_operation_state": quote_operation_state,
        "quote_validation_state": quote_validation_state,
        "paper_order_intent_operation_path": paper_order_intent_operation_path,
        "option_contract_resolver_operation_path": (
            option_contract_resolver_operation_path
        ),
        "option_quote_validation_operation_path": (
            option_quote_validation_operation_path
        ),
        "blocked_reasons": _dedupe_strings(blocked_reasons),
        "warnings": _dedupe_strings(warnings),
        **EXECUTION_DISABLED_FIELDS,
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def build_paper_order_preview_export_summary(
    export_payload: Mapping[str, Any],
    *,
    export_path: Optional[str] = None,
    summary_path: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": SUMMARY_ARTIFACT_TYPE,
        "paper_order_preview_state": export_payload.get("paper_order_preview_state"),
        "paper_trading_mode": export_payload.get("paper_trading_mode"),
        "order_submission_enabled": export_payload.get("order_submission_enabled"),
        "submit_order": export_payload.get("submit_order"),
        "requires_manual_approval": export_payload.get("requires_manual_approval"),
        "symbol": export_payload.get("symbol"),
        "spread_type": export_payload.get("spread_type"),
        "expiration": export_payload.get("expiration"),
        "quantity": export_payload.get("quantity"),
        "limit_price": export_payload.get("limit_price"),
        "conservative_net_debit": export_payload.get("conservative_net_debit"),
        "mid_net_debit": export_payload.get("mid_net_debit"),
        "max_loss_amount": export_payload.get("max_loss_amount"),
        "max_profit_amount": export_payload.get("max_profit_amount"),
        "max_trade_risk_amount": export_payload.get("max_trade_risk_amount"),
        "paper_order_intent_operation_state": export_payload.get(
            "paper_order_intent_operation_state"
        ),
        "option_contract_resolver_operation_state": export_payload.get(
            "option_contract_resolver_operation_state"
        ),
        "option_quote_validation_operation_state": export_payload.get(
            "option_quote_validation_operation_state"
        ),
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


def hydrate_operation_details_from_export(
    operation_payload: Any,
    *,
    operation_path: str | Path,
) -> Any:
    if not isinstance(operation_payload, Mapping):
        return operation_payload

    output_files = operation_payload.get("output_files")

    if not isinstance(output_files, Mapping):
        return operation_payload

    export_path = output_files.get("export")

    if not export_path:
        return operation_payload

    export_path_obj = Path(export_path)

    if not export_path_obj.exists():
        operation_path_obj = Path(operation_path)
        candidate_path = operation_path_obj.parent / export_path_obj.name

        if candidate_path.exists():
            export_path_obj = candidate_path

    if not export_path_obj.exists():
        return operation_payload

    export_payload = load_json(export_path_obj)

    if not isinstance(export_payload, Mapping):
        return operation_payload

    hydrated = dict(operation_payload)

    for key, value in export_payload.items():
        hydrated.setdefault(key, value)

    return hydrated


def _clean_string(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None

    return str(value).strip()


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