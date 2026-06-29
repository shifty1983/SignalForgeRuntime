from __future__ import annotations

from collections import Counter
from dataclasses import asdict, is_dataclass
from math import isfinite
from typing import Any, Mapping, Sequence


DISPATCH_STATUS_DRY_RUN_ONLY = "dry_run_only"

DIRECTION_TO_SIDE = {
    "long": "buy",
    "short": "sell_short",
    "neutral": "hold",
}

VALID_DIRECTIONS = set(DIRECTION_TO_SIDE)
VALID_SIDES = set(DIRECTION_TO_SIDE.values())

FORBIDDEN_DISPATCH_FIELDS = {
    "broker",
    "broker_id",
    "broker_account",
    "broker_account_id",
    "broker_api",
    "broker_order_id",
    "client_order_id",
    "route",
    "routing_destination",
    "order_id",
    "submitted_at",
    "submitted",
    "filled_at",
    "fill_id",
    "fill_price",
    "average_fill_price",
    "filled_quantity",
    "execution_price",
    "slippage",
    "slippage_bps",
}


REQUIRED_DISPATCH_FIELDS = (
    "dispatch_id",
    "source_instruction_id",
    "symbol",
    "direction",
    "side",
    "order_type_preference",
    "urgency",
    "notional_intent",
    "quantity_placeholder",
    "execution_constraints",
    "dispatch_status",
    "metadata",
)


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)

    if is_dataclass(value):
        return asdict(value)

    if hasattr(value, "to_dict") and callable(value.to_dict):
        converted = value.to_dict()
        if isinstance(converted, Mapping):
            return dict(converted)

    if hasattr(value, "__dict__"):
        return {
            key: item
            for key, item in vars(value).items()
            if not key.startswith("_")
        }

    return {}


def _lookup(payload: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload:
            return payload[key]
    return None


def _normalize_string(value: Any, *, uppercase: bool = False) -> str | None:
    if value is None:
        return None

    normalized = str(value).strip()
    if not normalized:
        return None

    return normalized.upper() if uppercase else normalized


def _normalize_direction(value: Any) -> str | None:
    normalized = _normalize_string(value)
    return normalized.lower() if normalized else None


def _coerce_float(value: Any) -> Any:
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return value


def _is_finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)


def _count_field(rows: Sequence[Mapping[str, Any]], field_name: str) -> dict[str, int]:
    counts: Counter[str] = Counter()

    for row in rows:
        value = row.get(field_name)
        if value is not None:
            counts[str(value)] += 1

    return {key: counts[key] for key in sorted(counts)}


def _find_forbidden_fields(
    payload: Mapping[str, Any],
    *,
    path: str,
) -> list[str]:
    errors: list[str] = []

    for key, value in payload.items():
        current_path = f"{path}.{key}"

        if key in FORBIDDEN_DISPATCH_FIELDS:
            errors.append(
                f"{path} contains broker/live-execution field: {key}"
            )

        if isinstance(value, Mapping):
            errors.extend(_find_forbidden_fields(value, path=current_path))

    return errors


def build_dispatch_intent_row(
    planned_order_instruction: Any,
    *,
    index: int = 0,
) -> dict[str, Any]:
    """
    Convert one planned order instruction into a broker-neutral dispatch intent.

    This function does not submit, route, enrich with broker data, model fills,
    or estimate slippage.
    """
    instruction = _as_mapping(planned_order_instruction)

    source_instruction_id = _lookup(
        instruction,
        "source_instruction_id",
        "instruction_id",
        "planned_instruction_id",
        "planned_order_instruction_id",
        "id",
    )

    normalized_source_instruction_id = _normalize_string(source_instruction_id)

    direction = _normalize_direction(_lookup(instruction, "direction"))
    side = DIRECTION_TO_SIDE.get(direction)

    metadata = _lookup(instruction, "metadata")
    normalized_metadata = dict(metadata) if isinstance(metadata, Mapping) else {}

    if normalized_source_instruction_id:
        dispatch_id = f"dispatch_{normalized_source_instruction_id}"
    else:
        dispatch_id = f"dispatch_missing_source_instruction_{index}"

    execution_constraints = _lookup(instruction, "execution_constraints")
    if execution_constraints is None:
        execution_constraints = {}

    return {
        "dispatch_id": dispatch_id,
        "source_instruction_id": normalized_source_instruction_id,
        "symbol": _normalize_string(_lookup(instruction, "symbol"), uppercase=True),
        "direction": direction,
        "side": side,
        "order_type_preference": _normalize_string(
            _lookup(instruction, "order_type_preference")
        ),
        "urgency": _normalize_string(_lookup(instruction, "urgency")),
        "notional_intent": _coerce_float(_lookup(instruction, "notional_intent")),
        "quantity_placeholder": _lookup(instruction, "quantity_placeholder"),
        "execution_constraints": (
            dict(execution_constraints)
            if isinstance(execution_constraints, Mapping)
            else execution_constraints
        ),
        "dispatch_status": DISPATCH_STATUS_DRY_RUN_ONLY,
        "metadata": normalized_metadata,
    }


def build_dispatch_intent_rows(
    planned_order_instructions: Sequence[Any],
) -> list[dict[str, Any]]:
    return [
        build_dispatch_intent_row(instruction, index=index)
        for index, instruction in enumerate(planned_order_instructions)
    ]


def validate_dispatch_intent_rows(
    dispatch_intent_rows: Sequence[Mapping[str, Any]],
) -> list[str]:
    errors: list[str] = []

    if not dispatch_intent_rows:
        return ["dispatch_intent_rows must not be empty"]

    seen_dispatch_ids: set[str] = set()
    seen_source_instruction_ids: set[str] = set()

    for index, row in enumerate(dispatch_intent_rows):
        row_path = f"dispatch_intent_rows[{index}]"

        for field_name in REQUIRED_DISPATCH_FIELDS:
            if field_name not in row:
                errors.append(f"{row_path} missing required field: {field_name}")
                continue

            if field_name != "quantity_placeholder" and row.get(field_name) is None:
                errors.append(f"{row_path} required field is empty: {field_name}")

        errors.extend(_find_forbidden_fields(row, path=row_path))

        dispatch_id = row.get("dispatch_id")
        if dispatch_id in seen_dispatch_ids:
            errors.append(f"{row_path} duplicate dispatch_id: {dispatch_id}")
        elif dispatch_id is not None:
            seen_dispatch_ids.add(str(dispatch_id))

        source_instruction_id = row.get("source_instruction_id")
        if source_instruction_id in seen_source_instruction_ids:
            errors.append(
                f"{row_path} duplicate source_instruction_id: "
                f"{source_instruction_id}"
            )
        elif source_instruction_id is not None:
            seen_source_instruction_ids.add(str(source_instruction_id))

        direction = row.get("direction")
        if direction not in VALID_DIRECTIONS:
            errors.append(f"{row_path} invalid direction: {direction}")

        side = row.get("side")
        if side not in VALID_SIDES:
            errors.append(f"{row_path} invalid side: {side}")

        expected_side = DIRECTION_TO_SIDE.get(direction)
        if expected_side is not None and side != expected_side:
            errors.append(
                f"{row_path} side does not match direction: "
                f"direction={direction}, side={side}, expected_side={expected_side}"
            )

        dispatch_status = row.get("dispatch_status")
        if dispatch_status != DISPATCH_STATUS_DRY_RUN_ONLY:
            errors.append(
                f"{row_path} dispatch_status must be "
                f"{DISPATCH_STATUS_DRY_RUN_ONLY}"
            )

        notional_intent = row.get("notional_intent")
        if not _is_finite_number(notional_intent):
            errors.append(f"{row_path} notional_intent must be a finite number")
        elif direction in {"long", "short"} and notional_intent <= 0:
            errors.append(
                f"{row_path} notional_intent must be positive for {direction}"
            )
        elif direction == "neutral" and notional_intent < 0:
            errors.append(
                f"{row_path} notional_intent must not be negative for neutral"
            )

        quantity_placeholder = row.get("quantity_placeholder")
        if quantity_placeholder is not None:
            if not _is_finite_number(quantity_placeholder):
                errors.append(
                    f"{row_path} quantity_placeholder must be null or a finite number"
                )
            elif quantity_placeholder < 0:
                errors.append(
                    f"{row_path} quantity_placeholder must not be negative"
                )

        if not isinstance(row.get("execution_constraints"), Mapping):
            errors.append(f"{row_path} execution_constraints must be a mapping")

        if not isinstance(row.get("metadata"), Mapping):
            errors.append(f"{row_path} metadata must be a mapping")

    return errors


def build_dispatch_summary(
    dispatch_intent_rows: Sequence[Mapping[str, Any]],
    validation_errors: Sequence[str] | None = None,
) -> dict[str, Any]:
    validation_errors = list(validation_errors or [])

    return {
        "dispatch_count": len(dispatch_intent_rows),
        "is_blocked": bool(validation_errors),
        "validation_error_count": len(validation_errors),
        "directions": _count_field(dispatch_intent_rows, "direction"),
        "sides": _count_field(dispatch_intent_rows, "side"),
        "dispatch_statuses": _count_field(dispatch_intent_rows, "dispatch_status"),
        "order_type_preferences": _count_field(
            dispatch_intent_rows,
            "order_type_preference",
        ),
        "urgencies": _count_field(dispatch_intent_rows, "urgency"),
    }


def build_execution_dispatch_contract(
    planned_order_instructions: Sequence[Any],
) -> dict[str, Any]:
    dispatch_intent_rows = build_dispatch_intent_rows(planned_order_instructions)
    validation_errors = validate_dispatch_intent_rows(dispatch_intent_rows)

    return {
        "dispatch_intent_rows": dispatch_intent_rows,
        "validation_errors": validation_errors,
        "summary": build_dispatch_summary(
            dispatch_intent_rows,
            validation_errors,
        ),
        "is_blocked": bool(validation_errors),
    }


# Compatibility aliases for downstream naming preferences.
build_dispatch_contract_from_planned_order_instructions = (
    build_execution_dispatch_contract
)
convert_planned_order_instructions_to_dispatch_intents = build_dispatch_intent_rows
