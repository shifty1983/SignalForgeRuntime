from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence


EXECUTION_PLANNING_OPERATION_TYPE = "execution_planning"

COMPLETED_STATUS = "completed"
BLOCKED_STATUS = "blocked"

REQUIRED_PLANNED_ORDER_FIELDS = (
    "instruction_id",
    "source_intent_id",
    "symbol",
    "direction",
    "order_type_preference",
    "urgency",
    "notional_intent",
    "quantity_placeholder",
    "execution_constraints",
)

REQUIRED_PLANNED_ORDER_FIELD_ALIASES = {
    "instruction_id": ("instruction_id", "plan_id"),
    "source_intent_id": ("source_intent_id", "intent_id"),
    "symbol": ("symbol",),
    "direction": ("direction", "side"),
    "order_type_preference": ("order_type_preference",),
    "urgency": ("urgency",),
    "notional_intent": ("notional_intent",),
    "quantity_placeholder": ("quantity_placeholder",),
    "execution_constraints": ("execution_constraints",),
}

FORBIDDEN_EXECUTION_FIELDS = (
    "broker",
    "broker_id",
    "broker_order_id",
    "route",
    "routing_destination",
    "submitted_at",
    "submitted_quantity",
    "filled_quantity",
    "fill_price",
    "average_fill_price",
    "execution_id",
    "slippage",
)


@dataclass(frozen=True)
class ExecutionPlanningOperationRecord:
    operation_type: str
    operation_id: str
    status: str
    created_at: str
    summary: dict[str, Any]
    execution_intent_rows: list[dict[str, Any]]
    planned_order_instructions: list[dict[str, Any]]
    validation_errors: list[str]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_execution_planning_operation_record(
    *,
    execution_intent_rows: Sequence[Any],
    planned_order_instructions: Sequence[Any],
    operation_id: str = "execution_planning_operation",
    created_at: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    additional_validation_errors: Sequence[str] | None = None,
) -> ExecutionPlanningOperationRecord:
    """
    Persist execution planning output into an operation-style record.

    This intentionally stops before:
    - broker routing
    - order submission
    - fills
    - fill simulation
    - slippage modeling
    - live execution
    """

    normalized_intents = [_json_safe_record(row) for row in execution_intent_rows]
    normalized_instructions = [
        _json_safe_record(instruction) for instruction in planned_order_instructions
    ]

    validation_errors = _validate_planning_record_inputs(
        execution_intent_rows=normalized_intents,
        planned_order_instructions=normalized_instructions,
    )

    if additional_validation_errors:
        validation_errors.extend(str(error) for error in additional_validation_errors)

    status = BLOCKED_STATUS if validation_errors else COMPLETED_STATUS

    summary = build_execution_planning_summary(
        execution_intent_rows=normalized_intents,
        planned_order_instructions=normalized_instructions,
        status=status,
        validation_errors=validation_errors,
    )

    return ExecutionPlanningOperationRecord(
        operation_type=EXECUTION_PLANNING_OPERATION_TYPE,
        operation_id=operation_id,
        status=status,
        created_at=created_at or _utc_now_iso(),
        summary=summary,
        execution_intent_rows=normalized_intents,
        planned_order_instructions=normalized_instructions,
        validation_errors=validation_errors,
        metadata=_json_safe_dict(metadata or {}),
    )


def build_execution_planning_summary(
    *,
    execution_intent_rows: Sequence[Mapping[str, Any]],
    planned_order_instructions: Sequence[Mapping[str, Any]],
    status: str,
    validation_errors: Sequence[str],
) -> dict[str, Any]:
    symbols = sorted(
        {
            str(instruction.get("symbol"))
            for instruction in planned_order_instructions
            if instruction.get("symbol") not in (None, "")
        }
    )

    directions = Counter(
        str(_get_first(instruction, "direction", "side"))
        for instruction in planned_order_instructions
        if _get_first(instruction, "direction", "side") not in (None, "")
    )

    order_type_preferences = Counter(
        str(instruction.get("order_type_preference"))
        for instruction in planned_order_instructions
        if instruction.get("order_type_preference") not in (None, "")
    )

    urgency_counts = Counter(
        str(instruction.get("urgency"))
        for instruction in planned_order_instructions
        if instruction.get("urgency") not in (None, "")
    )

    total_notional_intent = sum(
        _numeric_or_zero(instruction.get("notional_intent"))
        for instruction in planned_order_instructions
    )

    return {
        "status": status,
        "intent_count": len(execution_intent_rows),
        "planned_instruction_count": len(planned_order_instructions),
        "symbol_count": len(symbols),
        "symbols": symbols,
        "directions": dict(sorted(directions.items())),
        "order_type_preferences": dict(sorted(order_type_preferences.items())),
        "urgency_counts": dict(sorted(urgency_counts.items())),
        "total_notional_intent": total_notional_intent,
        "validation_error_count": len(validation_errors),
        "is_blocked": status == BLOCKED_STATUS,
    }


def _validate_planning_record_inputs(
    *,
    execution_intent_rows: Sequence[Mapping[str, Any]],
    planned_order_instructions: Sequence[Mapping[str, Any]],
) -> list[str]:
    errors: list[str] = []

    if not execution_intent_rows:
        errors.append("execution_intent_rows must not be empty")

    if not planned_order_instructions:
        errors.append("planned_order_instructions must not be empty")

    for index, instruction in enumerate(planned_order_instructions):
        errors.extend(_validate_planned_order_instruction(index, instruction))

    return errors


def _validate_planned_order_instruction(
    index: int,
    instruction: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []

    for canonical_field, aliases in REQUIRED_PLANNED_ORDER_FIELD_ALIASES.items():
        if not any(alias in instruction for alias in aliases):
            allowed_names = "/".join(aliases)
            errors.append(
                f"planned_order_instructions[{index}] missing required field: {allowed_names}"
            )

    for field in FORBIDDEN_EXECUTION_FIELDS:
        if field in instruction:
            errors.append(
                f"planned_order_instructions[{index}] contains broker/execution field: {field}"
            )

    symbol = instruction.get("symbol")
    if symbol is not None and not str(symbol).strip():
        errors.append(f"planned_order_instructions[{index}] symbol must not be blank")

    notional_intent = instruction.get("notional_intent")
    if notional_intent is not None:
        try:
            numeric_notional = float(notional_intent)
        except TypeError:
            errors.append(
                f"planned_order_instructions[{index}] notional_intent must be numeric"
            )
        except ValueError:
            errors.append(
                f"planned_order_instructions[{index}] notional_intent must be numeric"
            )
        else:
            if numeric_notional < 0:
                errors.append(
                    f"planned_order_instructions[{index}] notional_intent must be non-negative"
                )

    constraints = instruction.get("execution_constraints")
    if constraints is not None and not isinstance(constraints, Mapping):
        errors.append(
            f"planned_order_instructions[{index}] execution_constraints must be a mapping"
        )

    return errors


def _numeric_or_zero(value: Any) -> float:
    try:
        return float(value)
    except TypeError:
        return 0.0
    except ValueError:
        return 0.0


def _json_safe_record(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return _json_safe_dict(value)

    if is_dataclass(value) and not isinstance(value, type):
        return _json_safe_dict(asdict(value))

    if hasattr(value, "to_dict") and callable(value.to_dict):
        return _json_safe_record(value.to_dict())

    if hasattr(value, "__dict__"):
        return _json_safe_dict(vars(value))

    raise TypeError(f"Unsupported record type: {type(value).__name__}")

def _json_safe_dict(value: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): _json_safe(item) for key, item in value.items()}


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _json_safe_dict(value)

    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]

    if isinstance(value, list):
        return [_json_safe(item) for item in value]

    if isinstance(value, set):
        return sorted(_json_safe(item) for item in value)

    if isinstance(value, datetime):
        return value.isoformat()

    return value


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _get_first(value: Mapping[str, Any], *fields: str) -> Any:
    for field in fields:
        if field in value:
            return value[field]
    return None
