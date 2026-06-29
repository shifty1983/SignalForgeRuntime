from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


REQUIRED_EXECUTION_INTENT_FIELDS = {
    "intent_id",
    "symbol",
    "direction",
    "notional_intent",
}


VALID_DIRECTIONS = {"long", "short", "flat", "neutral"}
VALID_SIDES = {"buy", "sell", "none"}


@dataclass(frozen=True)
class ExecutionPlanningError:
    intent_id: str | None
    symbol: str | None
    reason: str


@dataclass(frozen=True)
class PlannedOrderInstruction:
    plan_id: str
    intent_id: str
    symbol: str
    side: str
    order_type_preference: str
    urgency: str
    notional_intent: float
    quantity_placeholder: float | None
    execution_constraints: dict[str, Any]
    planning_status: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "intent_id": self.intent_id,
            "symbol": self.symbol,
            "side": self.side,
            "order_type_preference": self.order_type_preference,
            "urgency": self.urgency,
            "notional_intent": self.notional_intent,
            "quantity_placeholder": self.quantity_placeholder,
            "execution_constraints": dict(self.execution_constraints),
            "planning_status": self.planning_status,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ExecutionPlanningResult:
    accepted: bool
    planned_orders: list[PlannedOrderInstruction]
    errors: list[ExecutionPlanningError]

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "planned_order_count": len(self.planned_orders),
            "planned_orders": [order.to_dict() for order in self.planned_orders],
            "errors": [
                {
                    "intent_id": error.intent_id,
                    "symbol": error.symbol,
                    "reason": error.reason,
                }
                for error in self.errors
            ],
        }


def build_execution_plan(
    execution_intents: Sequence[Mapping[str, Any]],
) -> ExecutionPlanningResult:
    planned_orders: list[PlannedOrderInstruction] = []
    errors: list[ExecutionPlanningError] = []

    for row in execution_intents:
        validation_error = _validate_execution_intent(row)

        if validation_error is not None:
            errors.append(validation_error)
            continue

        planned_orders.append(_build_planned_order_instruction(row))

    return ExecutionPlanningResult(
        accepted=not errors and bool(planned_orders),
        planned_orders=planned_orders,
        errors=errors,
    )


def _validate_execution_intent(
    row: Mapping[str, Any],
) -> ExecutionPlanningError | None:
    missing_fields = sorted(
        field for field in REQUIRED_EXECUTION_INTENT_FIELDS if field not in row
    )

    intent_id = _optional_str(row.get("intent_id"))
    symbol = _optional_str(row.get("symbol"))

    if missing_fields:
        return ExecutionPlanningError(
            intent_id=intent_id,
            symbol=symbol,
            reason=f"missing required fields: {', '.join(missing_fields)}",
        )

    direction = row["direction"]

    if direction not in VALID_DIRECTIONS:
        return ExecutionPlanningError(
            intent_id=intent_id,
            symbol=symbol,
            reason=f"invalid direction: {direction}",
        )

    try:
        notional_intent = float(row["notional_intent"])
    except (TypeError, ValueError):
        return ExecutionPlanningError(
            intent_id=intent_id,
            symbol=symbol,
            reason="notional_intent must be numeric",
        )

    if notional_intent < 0:
        return ExecutionPlanningError(
            intent_id=intent_id,
            symbol=symbol,
            reason="notional_intent must be non-negative",
        )

    return None


def _build_planned_order_instruction(
    row: Mapping[str, Any],
) -> PlannedOrderInstruction:
    intent_id = str(row["intent_id"])
    symbol = str(row["symbol"])
    direction = str(row["direction"])
    notional_intent = float(row["notional_intent"])

    side = _side_from_direction(direction)

    return PlannedOrderInstruction(
        plan_id=f"plan_{intent_id}",
        intent_id=intent_id,
        symbol=symbol,
        side=side,
        order_type_preference=_order_type_preference(row),
        urgency=_urgency(row),
        notional_intent=notional_intent,
        quantity_placeholder=None,
        execution_constraints=_execution_constraints(row),
        planning_status="planned",
        metadata=_metadata(row),
    )


def _side_from_direction(direction: str) -> str:
    if direction == "long":
        return "buy"

    if direction == "short":
        return "sell"

    if direction in {"flat", "neutral"}:
        return "none"

    raise ValueError(f"Unsupported direction: {direction}")


def _order_type_preference(row: Mapping[str, Any]) -> str:
    if row.get("execution_style") == "urgent":
        return "marketable_limit"

    if row.get("execution_style") == "patient":
        return "passive_limit"

    return "marketable_limit"


def _urgency(row: Mapping[str, Any]) -> str:
    if row.get("execution_style") == "urgent":
        return "high"

    if row.get("execution_style") == "patient":
        return "low"

    return "normal"


def _execution_constraints(row: Mapping[str, Any]) -> dict[str, Any]:
    user_constraints = row.get("execution_constraints") or {}

    if not isinstance(user_constraints, Mapping):
        user_constraints = {}

    defaults: dict[str, Any] = {
        "allow_market_order": False,
        "max_participation_rate": 0.10,
        "time_in_force": "day",
        "limit_price_buffer_bps": 25,
    }

    return {
        **defaults,
        **dict(user_constraints),
    }


def _metadata(row: Mapping[str, Any]) -> dict[str, Any]:
    metadata = row.get("metadata") or {}

    if not isinstance(metadata, Mapping):
        metadata = {}

    return {
        **dict(metadata),
        "source_contract": "execution_input",
        "target_contract": "execution_planning",
    }


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None

    return str(value)
