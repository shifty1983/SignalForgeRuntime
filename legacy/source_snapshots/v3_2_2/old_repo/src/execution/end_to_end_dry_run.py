from __future__ import annotations

import hashlib
import importlib
import json
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from typing import Any


BROKER_OR_LIVE_EXECUTION_FIELDS = {
    "broker",
    "broker_account_id",
    "broker_order_id",
    "broker_payload",
    "broker_route",
    "broker_route_id",
    "route_id",
    "routing_destination",
    "submitted",
    "submitted_at",
    "submission_id",
    "order_submission_id",
    "live_order_id",
    "external_order_id",
    "fill_id",
    "filled",
    "filled_at",
    "fill_price",
    "average_fill_price",
    "execution_price",
    "slippage",
    "slippage_bps",
}

BLOCKED_STAGE_STATUSES = {
    "blocked",
    "failed",
    "failure",
    "error",
    "invalid",
    "rejected",
}

ALLOWED_DIRECTIONS = {"long", "short", "neutral"}

DRY_RUN_DISPATCH_STATUSES = {
    "dry_run_ready",
    "dry_run_validated",
    "dry_run_recorded",
    "dry_run_blocked",
    "dry_run_no_action",
    "dry_run_only",
    "not_applicable",
    "blocked",
}


ExecutionStageRunner = Callable[[Sequence[Mapping[str, Any]]], Any]


_EXECUTION_INPUT_RUNNERS = (
    ("src.execution.input_contract", "build_execution_input_contract"),
    ("src.execution.input_contract", "build_execution_intent_rows"),
    ("src.execution.execution_input_contract", "build_execution_input_contract"),
    ("src.execution.execution_input_contract", "build_execution_intent_rows"),
)

_EXECUTION_PLANNING_RUNNERS = (
    ("src.execution.operation_runner", "run_execution_planning_operation"),
    ("src.execution.operation_runner", "run_execution_planning_runner"),
    ("src.execution.planning_runner", "run_execution_planning_operation"),
    ("src.execution.planning_runner", "run_execution_planning_runner"),
    ("src.execution.execution_planning_runner", "run_execution_planning_operation"),
)

_DISPATCH_RUNNERS = (
    ("src.execution.dispatch_runner", "run_execution_dispatch_operation"),
    ("src.execution.dispatch_runner", "run_execution_dispatch_runner"),
    ("src.execution.dispatch_runner", "run_dispatch_operation"),
    ("src.execution.dispatch_runner", "run_dispatch_runner"),
)


def run_portfolio_strategy_execution_dry_run(
    strategy_risk_managed_candidates: Sequence[Mapping[str, Any]],
    *,
    dry_run_id: str | None = None,
    execution_input_runner: ExecutionStageRunner | None = None,
    execution_planning_runner: ExecutionStageRunner | None = None,
    dispatch_runner: ExecutionStageRunner | None = None,
    use_existing_runners: bool = True,
    output_dir: str | None = None,
) -> dict[str, Any]:
    """
    Run a deterministic, broker-neutral portfolio/strategy/execution dry run.

    Flow:
        strategy/risk-managed candidates
        -> execution input contract
        -> execution planning runner
        -> dispatch runner
        -> deterministic end-to-end summary

    Explicitly excluded:
        broker APIs, routing, order submission, fills, live execution, and slippage modeling.
    """

    candidates = [dict(row) for row in strategy_risk_managed_candidates]
    dry_run_id = dry_run_id or _build_dry_run_id(candidates)

    candidate_validation_errors = _validate_strategy_risk_managed_candidates(
        candidates
    )
    if candidate_validation_errors:
        return _build_end_to_end_result(
            dry_run_id=dry_run_id,
            status="blocked",
            blocked_stage="execution_input",
            validation_errors=candidate_validation_errors,
            candidates=candidates,
            execution_input_result={},
            execution_intent_rows=[],
            planning_result={},
            planned_order_instructions=[],
            dispatch_result={},
            dispatch_intent_rows=[],
        )

    input_runner = execution_input_runner or _resolve_runner(
        _EXECUTION_INPUT_RUNNERS,
        _fallback_execution_input_runner,
        use_existing_runners=use_existing_runners,
    )
    planning_runner = execution_planning_runner or _resolve_runner(
        _EXECUTION_PLANNING_RUNNERS,
        _fallback_execution_planning_runner,
        use_existing_runners=use_existing_runners,
    )
    dispatch_stage_runner = dispatch_runner or _resolve_runner(
        _DISPATCH_RUNNERS,
        _fallback_dispatch_runner,
        use_existing_runners=use_existing_runners,
    )

    execution_input_result = _call_stage_runner(
        input_runner,
        candidates,
        stage_name="execution_input",
        payload_name="strategy_risk_managed_candidates",
        dry_run_id=dry_run_id,
        output_dir=output_dir,
    )
    execution_intent_rows = _extract_rows(
        execution_input_result,
        row_keys=(
            "execution_intent_rows",
            "execution_intents",
            "intent_rows",
            "rows",
        ),
    )

    execution_input_errors = _collect_stage_errors(
        stage_name="execution_input",
        stage_result=execution_input_result,
        row_label="execution_intent_rows",
        rows=execution_intent_rows,
        rows_required=True,
    )
    if execution_input_errors:
        return _build_end_to_end_result(
            dry_run_id=dry_run_id,
            status="blocked",
            blocked_stage="execution_input",
            validation_errors=execution_input_errors,
            candidates=candidates,
            execution_input_result=execution_input_result,
            execution_intent_rows=execution_intent_rows,
            planning_result={},
            planned_order_instructions=[],
            dispatch_result={},
            dispatch_intent_rows=[],
        )

    planning_result = _call_stage_runner(
        planning_runner,
        execution_intent_rows,
        stage_name="execution_planning",
        payload_name="execution_intent_rows",
        dry_run_id=dry_run_id,
        output_dir=output_dir,
    )
    planned_order_instructions = _extract_rows(
        planning_result,
        row_keys=(
            "planned_order_instructions",
            "planned_instructions",
            "planned_order_rows",
            "instructions",
            "rows",
        ),
    )

    planning_errors = _collect_stage_errors(
        stage_name="execution_planning",
        stage_result=planning_result,
        row_label="planned_order_instructions",
        rows=planned_order_instructions,
        rows_required=True,
    )
    if planning_errors:
        return _build_end_to_end_result(
            dry_run_id=dry_run_id,
            status="blocked",
            blocked_stage="execution_planning",
            validation_errors=planning_errors,
            candidates=candidates,
            execution_input_result=execution_input_result,
            execution_intent_rows=execution_intent_rows,
            planning_result=planning_result,
            planned_order_instructions=planned_order_instructions,
            dispatch_result={},
            dispatch_intent_rows=[],
        )

    dispatch_result = _call_stage_runner(
        dispatch_stage_runner,
        planned_order_instructions,
        stage_name="dispatch",
        payload_name="planned_order_instructions",
        dry_run_id=dry_run_id,
        output_dir=output_dir,
    )
    dispatch_intent_rows = _extract_rows(
        dispatch_result,
        row_keys=(
            "dispatch_intent_rows",
            "dispatch_intents",
            "dispatch_rows",
            "rows",
        ),
    )

    dispatch_errors = _collect_stage_errors(
        stage_name="dispatch",
        stage_result=dispatch_result,
        row_label="dispatch_intent_rows",
        rows=dispatch_intent_rows,
        rows_required=True,
    )
    dispatch_errors.extend(
        _validate_dispatch_dry_run_only(dispatch_intent_rows)
    )

    if dispatch_errors:
        return _build_end_to_end_result(
            dry_run_id=dry_run_id,
            status="blocked",
            blocked_stage="dispatch",
            validation_errors=dispatch_errors,
            candidates=candidates,
            execution_input_result=execution_input_result,
            execution_intent_rows=execution_intent_rows,
            planning_result=planning_result,
            planned_order_instructions=planned_order_instructions,
            dispatch_result=dispatch_result,
            dispatch_intent_rows=dispatch_intent_rows,
        )

    return _build_end_to_end_result(
        dry_run_id=dry_run_id,
        status="completed",
        blocked_stage=None,
        validation_errors=[],
        candidates=candidates,
        execution_input_result=execution_input_result,
        execution_intent_rows=execution_intent_rows,
        planning_result=planning_result,
        planned_order_instructions=planned_order_instructions,
        dispatch_result=dispatch_result,
        dispatch_intent_rows=dispatch_intent_rows,
    )


def _resolve_runner(
    candidates: Sequence[tuple[str, str]],
    fallback: ExecutionStageRunner,
    *,
    use_existing_runners: bool,
) -> ExecutionStageRunner:
    if not use_existing_runners:
        return fallback

    for module_name, function_name in candidates:
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError:
            continue

        runner = getattr(module, function_name, None)
        if callable(runner):
            return runner

    return fallback


def _call_stage_runner(
    runner: Callable[..., Any],
    payload: Sequence[Mapping[str, Any]],
    *,
    stage_name: str,
    payload_name: str,
    dry_run_id: str,
    output_dir: str | None,
) -> Any:
    attempts: list[tuple[tuple[Any, ...], dict[str, Any]]] = [
        ((payload,), {}),
        ((), {payload_name: payload}),
        ((), {"rows": payload}),
        ((), {"input_rows": payload}),
        ((), {payload_name: payload, "dry_run_id": dry_run_id}),
        ((), {"rows": payload, "dry_run_id": dry_run_id}),
    ]

    if output_dir is not None:
        attempts.extend(
            [
                ((), {payload_name: payload, "output_dir": output_dir}),
                (
                    (),
                    {
                        payload_name: payload,
                        "dry_run_id": dry_run_id,
                        "output_dir": output_dir,
                    },
                ),
            ]
        )

    last_type_error: TypeError | None = None

    for args, kwargs in attempts:
        try:
            return runner(*args, **kwargs)
        except TypeError as exc:
            last_type_error = exc

    return {
        "status": "blocked",
        "is_blocked": True,
        "validation_errors": [
            f"{stage_name} runner could not be called with a supported "
            f"dry-run signature: {last_type_error}"
        ],
    }


def _fallback_execution_input_runner(
    strategy_risk_managed_candidates: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []

    for index, candidate in enumerate(strategy_risk_managed_candidates, start=1):
        symbol = str(candidate["symbol"]).upper()
        direction = str(candidate["direction"]).lower()
        candidate_id = _candidate_id(candidate, index)

        rows.append(
            {
                "execution_intent_id": f"execution_intent_{index:04d}_{_slug(symbol)}",
                "source_candidate_id": candidate_id,
                "symbol": symbol,
                "direction": direction,
                "target_weight": candidate.get("target_weight"),
                "notional_intent": candidate.get(
                    "notional_intent",
                    candidate.get("target_notional"),
                ),
                "quantity_placeholder": candidate.get(
                    "quantity_placeholder",
                    "not_computed",
                ),
                "order_type_preference": candidate.get(
                    "order_type_preference",
                    "limit",
                ),
                "urgency": candidate.get("urgency", "normal"),
                "execution_constraints": deepcopy(
                    candidate.get("execution_constraints", {})
                ),
                "risk_status": candidate.get(
                    "risk_status",
                    candidate.get("risk_decision", "accepted"),
                ),
                "strategy_id": candidate.get("strategy_id"),
                "metadata": deepcopy(candidate.get("metadata", {})),
            }
        )

    return {
        "status": "completed",
        "is_blocked": False,
        "execution_intent_rows": rows,
        "summary": {
            "candidate_count": len(strategy_risk_managed_candidates),
            "intent_count": len(rows),
            "directions": _count_by_key(rows, "direction"),
            "symbols": sorted({row["symbol"] for row in rows}),
        },
    }


def _fallback_execution_planning_runner(
    execution_intent_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []

    for index, intent in enumerate(execution_intent_rows, start=1):
        direction = str(intent["direction"]).lower()
        symbol = str(intent["symbol"]).upper()
        side = _side_from_direction(direction)

        rows.append(
            {
                "planned_instruction_id": (
                    f"planned_instruction_{index:04d}_"
                    f"{_stable_digest(intent)[:8]}"
                ),
                "source_intent_id": intent.get(
                    "execution_intent_id",
                    intent.get("intent_id"),
                ),
                "symbol": symbol,
                "direction": direction,
                "side": side,
                "order_type_preference": intent.get(
                    "order_type_preference",
                    "limit",
                ),
                "urgency": intent.get("urgency", "normal"),
                "target_weight": intent.get("target_weight"),
                "notional_intent": intent.get("notional_intent"),
                "quantity_placeholder": intent.get(
                    "quantity_placeholder",
                    "not_computed",
                ),
                "execution_constraints": deepcopy(
                    intent.get("execution_constraints", {})
                ),
                "dry_run_only": True,
            }
        )

    return {
        "status": "completed",
        "is_blocked": False,
        "planned_order_instructions": rows,
        "summary": {
            "intent_count": len(execution_intent_rows),
            "planned_instruction_count": len(rows),
            "directions": _count_by_key(rows, "direction"),
            "sides": _count_by_key(rows, "side"),
            "order_type_preferences": _count_by_key(
                rows,
                "order_type_preference",
            ),
        },
    }


def _fallback_dispatch_runner(
    planned_order_instructions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []

    for index, instruction in enumerate(
        planned_order_instructions,
        start=1,
    ):
        side = instruction.get("side")
        dispatch_status = (
            "dry_run_no_action"
            if side == "hold"
            else "dry_run_ready"
        )

        rows.append(
            {
                "dispatch_id": (
                    f"dispatch_intent_{index:04d}_"
                    f"{_stable_digest(instruction)[:8]}"
                ),
                "source_instruction_id": instruction.get(
                    "planned_instruction_id",
                    instruction.get("instruction_id"),
                ),
                "symbol": str(instruction["symbol"]).upper(),
                "direction": str(instruction["direction"]).lower(),
                "side": side,
                "order_type_preference": instruction.get(
                    "order_type_preference",
                    "limit",
                ),
                "urgency": instruction.get("urgency", "normal"),
                "quantity_placeholder": instruction.get(
                    "quantity_placeholder",
                    "not_computed",
                ),
                "notional_intent": instruction.get("notional_intent"),
                "dry_run_only": True,
                "dispatch_status": dispatch_status,
            }
        )

    return {
        "status": "completed",
        "is_blocked": False,
        "dispatch_intent_rows": rows,
        "summary": {
            "planned_instruction_count": len(planned_order_instructions),
            "dispatch_intent_count": len(rows),
            "dispatch_statuses": _count_by_key(rows, "dispatch_status"),
            "sides": _count_by_key(rows, "side"),
        },
    }


def _validate_strategy_risk_managed_candidates(
    candidates: Sequence[Mapping[str, Any]],
) -> list[str]:
    errors: list[str] = []

    if not candidates:
        return ["strategy_risk_managed_candidates must not be empty"]

    for index, candidate in enumerate(candidates):
        for field_name in ("symbol", "direction"):
            if not candidate.get(field_name):
                errors.append(
                    f"strategy_risk_managed_candidates[{index}] missing "
                    f"required field: {field_name}"
                )

        if candidate.get("direction"):
            direction = str(candidate["direction"]).lower()
            if direction not in ALLOWED_DIRECTIONS:
                errors.append(
                    f"strategy_risk_managed_candidates[{index}] has invalid "
                    f"direction: {candidate['direction']}"
                )

        candidate_state = str(
            candidate.get(
                "risk_status",
                candidate.get(
                    "risk_decision",
                    candidate.get("status", "accepted"),
                ),
            )
        ).lower()

        if candidate_state in BLOCKED_STAGE_STATUSES:
            errors.append(
                f"strategy_risk_managed_candidates[{index}] is not "
                f"risk-accepted: {candidate_state}"
            )

        for accepted_flag in ("accepted", "is_accepted", "is_risk_accepted"):
            if candidate.get(accepted_flag) is False:
                errors.append(
                    f"strategy_risk_managed_candidates[{index}] has "
                    f"{accepted_flag}=False"
                )

        for field_name in sorted(BROKER_OR_LIVE_EXECUTION_FIELDS):
            value = candidate.get(field_name)
            if _has_value(value):
                errors.append(
                    f"strategy_risk_managed_candidates[{index}] contains "
                    f"broker/live execution field: {field_name}"
                )

    return errors


def _collect_stage_errors(
    *,
    stage_name: str,
    stage_result: Any,
    row_label: str,
    rows: Sequence[Mapping[str, Any]],
    rows_required: bool,
) -> list[str]:
    errors = _extract_validation_errors(stage_result)

    if _is_stage_blocked(stage_result) and not errors:
        errors.append(f"{stage_name} returned blocked status")

    if rows_required and not rows:
        errors.append(f"{stage_name} produced no {row_label}")

    errors.extend(
        _validate_no_broker_or_live_execution_fields(
            stage_name=stage_name,
            row_label=row_label,
            rows=rows,
        )
    )

    return errors


def _validate_no_broker_or_live_execution_fields(
    *,
    stage_name: str,
    row_label: str,
    rows: Sequence[Mapping[str, Any]],
) -> list[str]:
    errors: list[str] = []

    for index, row in enumerate(rows):
        for field_name in sorted(BROKER_OR_LIVE_EXECUTION_FIELDS):
            value = row.get(field_name)
            if _has_value(value):
                errors.append(
                    f"{stage_name}.{row_label}[{index}] contains "
                    f"broker/live execution field: {field_name}"
                )

    return errors


def _validate_dispatch_dry_run_only(
    dispatch_intent_rows: Sequence[Mapping[str, Any]],
) -> list[str]:
    errors: list[str] = []

    for index, row in enumerate(dispatch_intent_rows):
        if row.get("dry_run_only") is False:
            errors.append(
                f"dispatch.dispatch_intent_rows[{index}] has "
                "dry_run_only=False"
            )

        dispatch_status = row.get("dispatch_status")
        if dispatch_status is not None:
            normalized_status = str(dispatch_status).lower()
            if (
                normalized_status not in DRY_RUN_DISPATCH_STATUSES
                and not normalized_status.startswith("dry_run")
            ):
                errors.append(
                    f"dispatch.dispatch_intent_rows[{index}] has "
                    f"non-dry-run dispatch_status: {dispatch_status}"
                )

    return errors


def _build_end_to_end_result(
    *,
    dry_run_id: str,
    status: str,
    blocked_stage: str | None,
    validation_errors: Sequence[str],
    candidates: Sequence[Mapping[str, Any]],
    execution_input_result: Any,
    execution_intent_rows: Sequence[Mapping[str, Any]],
    planning_result: Any,
    planned_order_instructions: Sequence[Mapping[str, Any]],
    dispatch_result: Any,
    dispatch_intent_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    is_blocked = status == "blocked"

    summary = {
        "dry_run_id": dry_run_id,
        "status": status,
        "is_blocked": is_blocked,
        "blocked_stage": blocked_stage,
        "candidate_count": len(candidates),
        "execution_intent_count": len(execution_intent_rows),
        "planned_instruction_count": len(planned_order_instructions),
        "dispatch_intent_count": len(dispatch_intent_rows),
        "symbols": _sorted_unique_values(
            execution_intent_rows,
            planned_order_instructions,
            dispatch_intent_rows,
            key="symbol",
        ),
        "directions": _count_by_key(
            execution_intent_rows or planned_order_instructions,
            "direction",
        ),
        "sides": _count_by_key(
            dispatch_intent_rows or planned_order_instructions,
            "side",
        ),
        "order_type_preferences": _count_by_key(
            dispatch_intent_rows or planned_order_instructions,
            "order_type_preference",
        ),
        "urgencies": _count_by_key(
            dispatch_intent_rows or planned_order_instructions,
            "urgency",
        ),
        "dispatch_statuses": _count_by_key(
            dispatch_intent_rows,
            "dispatch_status",
        ),
        "validation_error_count": len(validation_errors),
    }

    return _json_safe(
        {
            "dry_run_id": dry_run_id,
            "status": status,
            "is_blocked": is_blocked,
            "blocked_stage": blocked_stage,
            "validation_errors": list(validation_errors),
            "summary": summary,
            "execution_intent_rows": list(execution_intent_rows),
            "planned_order_instructions": list(planned_order_instructions),
            "dispatch_intent_rows": list(dispatch_intent_rows),
            "stage_results": {
                "execution_input": execution_input_result,
                "execution_planning": planning_result,
                "dispatch": dispatch_result,
            },
        }
    )


def _extract_rows(
    result: Any,
    *,
    row_keys: Sequence[str],
) -> list[dict[str, Any]]:
    if isinstance(result, list):
        return [dict(row) for row in result if isinstance(row, Mapping)]

    value = _find_first_value(result, row_keys)

    if isinstance(value, list):
        return [dict(row) for row in value if isinstance(row, Mapping)]

    return []


def _extract_validation_errors(result: Any) -> list[str]:
    value = _find_first_value(
        result,
        (
            "validation_errors",
            "errors",
            "blocking_errors",
            "failure_reasons",
        ),
    )

    if value is None:
        return []

    if isinstance(value, str):
        return [value]

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [str(item) for item in value]

    return [str(value)]


def _is_stage_blocked(result: Any) -> bool:
    if isinstance(result, Mapping):
        if result.get("is_blocked") is True:
            return True

        status = result.get("status")
        if status is not None and str(status).lower() in BLOCKED_STAGE_STATUSES:
            return True

        health_status = _find_first_value(
            result,
            ("health_status", "gate_status"),
        )
        if (
            health_status is not None
            and str(health_status).lower() in BLOCKED_STAGE_STATUSES
        ):
            return True

    return False


def _find_first_value(
    value: Any,
    keys: Sequence[str],
    *,
    depth: int = 0,
    max_depth: int = 4,
) -> Any:
    if depth > max_depth:
        return None

    if isinstance(value, Mapping):
        for key in keys:
            if key in value:
                return value[key]

        for nested_key in (
            "result",
            "payload",
            "data",
            "record",
            "operation_record",
            "attachments",
            "summary",
        ):
            if nested_key in value:
                nested_value = _find_first_value(
                    value[nested_key],
                    keys,
                    depth=depth + 1,
                    max_depth=max_depth,
                )
                if nested_value is not None:
                    return nested_value

    return None


def _build_dry_run_id(candidates: Sequence[Mapping[str, Any]]) -> str:
    return f"portfolio_strategy_execution_dry_run_{_stable_digest(candidates)[:12]}"


def _stable_digest(value: Any) -> str:
    payload = json.dumps(_json_safe(value), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _json_safe(value[key])
            for key in sorted(value.keys(), key=str)
        }

    if isinstance(value, list):
        return [_json_safe(item) for item in value]

    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]

    if isinstance(value, set):
        return sorted(_json_safe(item) for item in value)

    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    return str(value)


def _count_by_key(
    rows: Sequence[Mapping[str, Any]],
    key: str,
) -> dict[str, int]:
    counter: Counter[str] = Counter()

    for row in rows:
        value = row.get(key)
        if value is not None:
            counter[str(value).lower()] += 1

    return dict(sorted(counter.items()))


def _sorted_unique_values(
    *row_groups: Sequence[Mapping[str, Any]],
    key: str,
) -> list[str]:
    values: set[str] = set()

    for rows in row_groups:
        for row in rows:
            value = row.get(key)
            if value is not None:
                values.add(str(value).upper())

    return sorted(values)


def _candidate_id(candidate: Mapping[str, Any], index: int) -> str:
    for key in (
        "candidate_id",
        "strategy_candidate_id",
        "risk_candidate_id",
        "id",
    ):
        if candidate.get(key):
            return str(candidate[key])

    return f"candidate_{index:04d}"


def _side_from_direction(direction: str) -> str:
    normalized = direction.lower()

    if normalized == "long":
        return "buy"

    if normalized == "short":
        return "sell"

    if normalized == "neutral":
        return "hold"

    raise ValueError(f"unsupported execution direction: {direction}")


def _slug(value: str) -> str:
    return (
        value.lower()
        .replace(" ", "_")
        .replace("/", "_")
        .replace("-", "_")
    )


def _has_value(value: Any) -> bool:
    return value not in (None, "", [], {}, ())
