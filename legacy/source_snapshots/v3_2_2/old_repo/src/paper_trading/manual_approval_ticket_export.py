from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence


ADAPTER_TYPE = "manual_approval_ticket_export"

ARTIFACT_TYPE = "signalforge_manual_approval_ticket_export"
SUMMARY_ARTIFACT_TYPE = "signalforge_manual_approval_ticket_export_summary"
WRITE_RESULT_ARTIFACT_TYPE = "manual_approval_ticket_export_write_result"

EXPORT_FILENAME = "signalforge_manual_approval_ticket_export.json"
SUMMARY_FILENAME = "signalforge_manual_approval_ticket_export_summary.json"

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


def export_manual_approval_ticket(
    *,
    paper_order_preview_operation_path: str | Path,
    output_dir: str | Path,
) -> Dict[str, Any]:
    output_dir_obj = Path(output_dir)
    output_dir_obj.mkdir(parents=True, exist_ok=True)

    export_path = output_dir_obj / EXPORT_FILENAME
    summary_path = output_dir_obj / SUMMARY_FILENAME

    try:
        paper_order_preview_operation = load_json(paper_order_preview_operation_path)
        paper_order_preview_operation = hydrate_preview_operation_details(
            paper_order_preview_operation,
            operation_path=paper_order_preview_operation_path,
        )
    except Exception as exc:  # pragma: no cover
        paper_order_preview_operation = {
            "operation_state": "blocked",
            "paper_order_preview_state": "blocked",
            "blocked_reasons": [
                "paper_order_preview_operation_load_failed",
                f"{type(exc).__name__}: {exc}",
            ],
            "warnings": [],
        }

    export_payload = build_manual_approval_ticket_export(
        paper_order_preview_operation,
        paper_order_preview_operation_path=str(paper_order_preview_operation_path),
    )

    summary_payload = build_manual_approval_ticket_export_summary(
        export_payload,
        export_path=str(export_path),
        summary_path=str(summary_path),
    )

    write_json(export_path, export_payload)
    write_json(summary_path, summary_payload)

    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": WRITE_RESULT_ARTIFACT_TYPE,
        "manual_approval_ticket_state": export_payload[
            "manual_approval_ticket_state"
        ],
        "approval_state": export_payload["approval_state"],
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


def build_manual_approval_ticket_export(
    paper_order_preview_operation: Any,
    *,
    paper_order_preview_operation_path: Optional[str] = None,
) -> Dict[str, Any]:
    blocked_reasons: list[str] = []
    warnings: list[str] = []

    if not isinstance(paper_order_preview_operation, Mapping):
        paper_order_preview_operation = {}
        blocked_reasons.extend(
            [
                "paper_order_preview_operation_invalid_shape",
                "paper_order_preview_operation_must_be_json_object",
            ]
        )

    blocked_reasons.extend(
        _dedupe_strings(paper_order_preview_operation.get("blocked_reasons", []))
    )
    warnings.extend(_dedupe_strings(paper_order_preview_operation.get("warnings", [])))

    preview_operation_state = paper_order_preview_operation.get("operation_state")
    paper_order_preview_state = paper_order_preview_operation.get(
        "paper_order_preview_state"
    )

    if preview_operation_state == "blocked":
        blocked_reasons.append("paper_order_preview_operation_must_not_be_blocked")
    elif preview_operation_state not in {"ready", "needs_review"}:
        blocked_reasons.append(
            "paper_order_preview_operation_must_be_ready_or_needs_review"
        )

    if paper_order_preview_state == "blocked":
        blocked_reasons.append("paper_order_preview_state_must_not_be_blocked")
    elif paper_order_preview_state not in {"ready", "needs_review"}:
        blocked_reasons.append("paper_order_preview_state_must_be_ready_or_needs_review")

    if paper_order_preview_operation.get("order_submission_enabled") is True:
        blocked_reasons.append("paper_order_preview_order_submission_must_be_disabled")

    if paper_order_preview_operation.get("submit_order") is True:
        blocked_reasons.append("paper_order_preview_submit_order_must_be_false")

    if paper_order_preview_operation.get("requires_manual_approval") is not True:
        blocked_reasons.append("requires_manual_approval_must_be_true")

    symbol = _clean_string(paper_order_preview_operation.get("symbol"))
    spread_type = _clean_string(paper_order_preview_operation.get("spread_type"))
    expiration = _clean_string(paper_order_preview_operation.get("expiration"))
    quantity = _as_int(paper_order_preview_operation.get("quantity"))
    limit_price = _as_float(paper_order_preview_operation.get("limit_price"))
    max_loss_amount = _as_float(paper_order_preview_operation.get("max_loss_amount"))
    max_profit_amount = _as_float(
        paper_order_preview_operation.get("max_profit_amount")
    )
    max_trade_risk_amount = _as_float(
        paper_order_preview_operation.get("max_trade_risk_amount")
    )

    order_preview = paper_order_preview_operation.get("order_preview")

    if not symbol:
        blocked_reasons.append("symbol_required")

    if not spread_type:
        blocked_reasons.append("spread_type_required")

    if not expiration:
        blocked_reasons.append("expiration_required")

    if quantity is None:
        blocked_reasons.append("quantity_required")

    if limit_price is None:
        blocked_reasons.append("limit_price_required")

    if max_loss_amount is None:
        blocked_reasons.append("max_loss_amount_required")

    if not isinstance(order_preview, Mapping):
        blocked_reasons.append("order_preview_required")
        order_preview = {}

    ticket_id = _stable_ticket_id(
        {
            "symbol": symbol,
            "spread_type": spread_type,
            "expiration": expiration,
            "quantity": quantity,
            "limit_price": limit_price,
            "max_loss_amount": max_loss_amount,
            "paper_order_preview_state": paper_order_preview_state,
            "blocked_reasons": _dedupe_strings(blocked_reasons),
            "warnings": _dedupe_strings(warnings),
        }
    )

    approval_state = "blocked_before_manual_review" if blocked_reasons else "pending_manual_approval"

    ticket = {
        "ticket_id": ticket_id,
        "ticket_type": "manual_approval_required_before_paper_order_submit",
        "approval_state": approval_state,
        "paper_trading_mode": True,
        "order_submission_enabled": False,
        "submit_order": False,
        "requires_manual_approval": True,
        "manual_approval_granted": False,
        "manual_approval_granted_by": None,
        "manual_approval_timestamp": None,
        "symbol": symbol,
        "spread_type": spread_type,
        "expiration": expiration,
        "quantity": quantity,
        "limit_price": limit_price,
        "max_loss_amount": max_loss_amount,
        "max_profit_amount": max_profit_amount,
        "max_trade_risk_amount": max_trade_risk_amount,
        "review_prompts": [
            "Confirm the strategy intent still matches current market conditions.",
            "Confirm option quotes are current and complete.",
            "Confirm max loss is within approved risk budget.",
            "Confirm order quantity, limit price, expiration, and strikes.",
            "Confirm this is paper trading only.",
        ],
        "order_preview": _json_safe(order_preview),
    }

    manual_approval_ticket_state = _classify_state(
        blocked_reasons=blocked_reasons,
        warnings=warnings,
    )

    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": ARTIFACT_TYPE,
        "manual_approval_ticket_state": manual_approval_ticket_state,
        "approval_state": approval_state,
        "ticket_id": ticket_id,
        "paper_trading_mode": True,
        "order_submission_enabled": False,
        "submit_order": False,
        "requires_manual_approval": True,
        "manual_approval_granted": False,
        "symbol": symbol,
        "spread_type": spread_type,
        "expiration": expiration,
        "quantity": quantity,
        "limit_price": limit_price,
        "max_loss_amount": max_loss_amount,
        "max_profit_amount": max_profit_amount,
        "max_trade_risk_amount": max_trade_risk_amount,
        "paper_order_preview_operation_state": preview_operation_state,
        "paper_order_preview_state": paper_order_preview_state,
        "ticket": ticket,
        "paper_order_preview_operation_path": paper_order_preview_operation_path,
        "blocked_reasons": _dedupe_strings(blocked_reasons),
        "warnings": _dedupe_strings(warnings),
        **EXECUTION_DISABLED_FIELDS,
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def build_manual_approval_ticket_export_summary(
    export_payload: Mapping[str, Any],
    *,
    export_path: Optional[str] = None,
    summary_path: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": SUMMARY_ARTIFACT_TYPE,
        "manual_approval_ticket_state": export_payload.get(
            "manual_approval_ticket_state"
        ),
        "approval_state": export_payload.get("approval_state"),
        "ticket_id": export_payload.get("ticket_id"),
        "paper_trading_mode": export_payload.get("paper_trading_mode"),
        "order_submission_enabled": export_payload.get("order_submission_enabled"),
        "submit_order": export_payload.get("submit_order"),
        "requires_manual_approval": export_payload.get("requires_manual_approval"),
        "manual_approval_granted": export_payload.get("manual_approval_granted"),
        "symbol": export_payload.get("symbol"),
        "spread_type": export_payload.get("spread_type"),
        "expiration": export_payload.get("expiration"),
        "quantity": export_payload.get("quantity"),
        "limit_price": export_payload.get("limit_price"),
        "max_loss_amount": export_payload.get("max_loss_amount"),
        "max_profit_amount": export_payload.get("max_profit_amount"),
        "max_trade_risk_amount": export_payload.get("max_trade_risk_amount"),
        "paper_order_preview_operation_state": export_payload.get(
            "paper_order_preview_operation_state"
        ),
        "paper_order_preview_state": export_payload.get("paper_order_preview_state"),
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


def hydrate_preview_operation_details(
    operation_payload: Any,
    *,
    operation_path: str | Path,
) -> Any:
    if not isinstance(operation_payload, Mapping):
        return operation_payload

    if isinstance(operation_payload.get("order_preview"), Mapping):
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


def _stable_ticket_id(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, default=str)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return f"manual_approval_ticket_{digest}"


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


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))