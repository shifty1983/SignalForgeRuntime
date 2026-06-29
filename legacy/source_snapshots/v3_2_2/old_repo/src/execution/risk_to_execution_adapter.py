from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, is_dataclass
from hashlib import sha256
import json
from typing import Any


CONTRACT_VERSION = "execution_input_contract_v1"
CONTRACT_TYPE = "execution_input_contract"
CREATED_BY = "risk_management_runner"

_ACCEPTED_RISK_STATUS = "accepted"
_VALID_DIRECTIONS = {"long", "short", "neutral"}
_DIRECTION_TO_SIDE = {
    "long": "buy",
    "short": "sell_short",
    "neutral": "hold",
}

_MISSING = object()


class ExecutionInputContractError(ValueError):
    """Raised when risk-managed output cannot be converted to execution intent."""


@dataclass(frozen=True)
class ExecutionIntentRow:
    execution_intent_id: str
    source_candidate_id: str
    symbol: str
    direction: str
    side: str
    target_weight: float
    max_weight: float | None
    risk_status: str
    strategy_id: str
    regime_id: str | None
    asset_behavior: str | None
    created_by: str
    diagnostics: dict[str, Any]
    metadata: dict[str, Any]
    performance_context: dict[str, Any]


def build_execution_input_contract(
    risk_management_output: Mapping[str, Any] | Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Convert accepted risk-managed candidates into an execution input contract.

    This is intentionally not broker execution. It produces deterministic order-intent
    rows only.
    """

    rows = build_execution_intent_rows(risk_management_output)

    return {
        "contract_type": CONTRACT_TYPE,
        "contract_version": CONTRACT_VERSION,
        "row_count": len(rows),
        "rows": rows,
    }


def build_execution_intent_rows(
    risk_management_output: Mapping[str, Any] | Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    candidates = _extract_candidate_rows(risk_management_output)

    if not candidates:
        raise ExecutionInputContractError(
            "Risk-to-execution handoff must contain at least one accepted candidate."
        )

    rows: list[dict[str, Any]] = []
    errors: list[str] = []

    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, Mapping):
            errors.append(f"candidate[{index}] must be a mapping.")
            continue

        try:
            rows.append(asdict(_build_execution_intent_row(candidate)))
        except ExecutionInputContractError as exc:
            errors.append(f"candidate[{index}]: {exc}")

    if errors:
        raise ExecutionInputContractError("; ".join(errors))

    deterministic_rows = sorted(
        rows,
        key=lambda row: (
            row["symbol"],
            row["source_candidate_id"],
            row["execution_intent_id"],
        ),
    )

    validate_execution_intent_rows(deterministic_rows)

    return deterministic_rows


def validate_execution_intent_rows(rows: Iterable[Mapping[str, Any]]) -> None:
    materialized_rows = list(rows)

    if not materialized_rows:
        raise ExecutionInputContractError(
            "Execution input contract must contain at least one intent row."
        )

    required_fields = {
        "execution_intent_id",
        "source_candidate_id",
        "symbol",
        "direction",
        "side",
        "target_weight",
        "risk_status",
        "strategy_id",
        "created_by",
        "diagnostics",
        "metadata",
        "performance_context",
    }

    errors: list[str] = []

    for index, row in enumerate(materialized_rows):
        missing_fields = sorted(
            field
            for field in required_fields
            if field not in row or row[field] in (None, "")
        )

        if missing_fields:
            errors.append(
                f"row[{index}] missing required fields: {', '.join(missing_fields)}"
            )
            continue

        direction = _normalize_direction(row["direction"])
        side = _normalize_string(row["side"], field_name="side")
        risk_status = _normalize_string(row["risk_status"], field_name="risk_status")
        target_weight = _as_float(row["target_weight"], field_name="target_weight")

        if risk_status != _ACCEPTED_RISK_STATUS:
            errors.append(f"row[{index}] risk_status must be accepted.")
            continue

        expected_side = _side_for_direction(direction)
        if side != expected_side:
            errors.append(
                f"row[{index}] side {side!r} does not match direction {direction!r}; "
                f"expected {expected_side!r}."
            )

        try:
            _validate_direction_and_weight(
                direction=direction,
                target_weight=target_weight,
                max_weight=(
                    None
                    if row.get("max_weight") is None
                    else _as_float(row["max_weight"], field_name="max_weight")
                ),
            )
        except ExecutionInputContractError as exc:
            errors.append(f"row[{index}] {exc}")

        if row["created_by"] != CREATED_BY:
            errors.append(
                f"row[{index}] created_by must be {CREATED_BY!r}; "
                f"got {row['created_by']!r}."
            )

    if errors:
        raise ExecutionInputContractError("; ".join(errors))


def snapshot_execution_input_contract(contract: Mapping[str, Any]) -> dict[str, Any]:
    """Return a stable minimal snapshot for regression tests."""

    rows = list(contract.get("rows", []))

    return {
        "contract_type": contract.get("contract_type"),
        "contract_version": contract.get("contract_version"),
        "row_count": contract.get("row_count"),
        "execution_intent_ids": [row["execution_intent_id"] for row in rows],
        "symbols": [row["symbol"] for row in rows],
        "sides": [row["side"] for row in rows],
        "source_candidate_ids": [row["source_candidate_id"] for row in rows],
    }


def _extract_candidate_rows(
    risk_management_output: Mapping[str, Any] | Iterable[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    if isinstance(risk_management_output, Mapping):
        if "accepted_candidates" in risk_management_output:
            return list(risk_management_output["accepted_candidates"])

        for key in (
            "risk_managed_candidates",
            "candidates",
            "candidate_rows",
            "rows",
            "results",
        ):
            if key in risk_management_output:
                return list(risk_management_output[key])

        raise ExecutionInputContractError(
            "Risk management output must contain accepted_candidates, "
            "risk_managed_candidates, candidates, candidate_rows, rows, or results."
        )

    if isinstance(risk_management_output, Iterable) and not isinstance(
        risk_management_output, (str, bytes)
    ):
        return list(risk_management_output)

    raise ExecutionInputContractError(
        "Risk management output must be a mapping or iterable of candidate mappings."
    )


def _build_execution_intent_row(candidate: Mapping[str, Any]) -> ExecutionIntentRow:
    source_candidate_id = _normalize_string(
        _get_first(
            candidate,
            (
                "source_candidate_id",
                "candidate_id",
                "strategy_candidate_id",
                "id",
            ),
        ),
        field_name="source_candidate_id",
    )

    symbol = _normalize_symbol(_get_first(candidate, ("symbol", "ticker", "asset")))

    direction = _normalize_direction(_get_first(candidate, ("direction", "position")))

    target_weight = _as_float(
        _get_first(
            candidate,
            (
                "target_weight",
                "risk_adjusted_target_weight",
                "final_target_weight",
                "weight",
            ),
        ),
        field_name="target_weight",
    )

    max_weight_value = _get_first(
        candidate,
        (
            "max_weight",
            "risk_max_weight",
            "max_allowed_weight",
            "weight_limit",
        ),
        default=None,
    )
    max_weight = (
        None
        if max_weight_value is None
        else _as_float(max_weight_value, field_name="max_weight")
    )

    risk_status = _normalize_string(
        _get_first(candidate, ("risk_status", "status", "decision")),
        field_name="risk_status",
    )

    if risk_status != _ACCEPTED_RISK_STATUS:
        raise ExecutionInputContractError(
            f"risk_status must be accepted; got {risk_status!r}."
        )

    strategy_id = _normalize_string(
        _get_first(candidate, ("strategy_id", "strategy", "model_id")),
        field_name="strategy_id",
    )

    _validate_direction_and_weight(
        direction=direction,
        target_weight=target_weight,
        max_weight=max_weight,
    )

    side = _side_for_direction(direction)

    regime_id = _optional_string(
        _get_first(candidate, ("regime_id", "market_regime"), default=None)
    )
    asset_behavior = _optional_string(
        _get_first(candidate, ("asset_behavior", "behavior"), default=None)
    )

    diagnostics = _json_safe_mapping(
        _get_first(candidate, ("diagnostics", "risk_diagnostics"), default={})
    )
    metadata = _json_safe_mapping(_get_first(candidate, ("metadata",), default={}))
    performance_context = _json_safe_mapping(
        _get_first(
            candidate,
            ("performance_context", "performance", "backtest_context"),
            default={},
        )
    )

    execution_intent_id = _build_execution_intent_id(
        source_candidate_id=source_candidate_id,
        symbol=symbol,
        direction=direction,
        target_weight=target_weight,
        strategy_id=strategy_id,
    )

    return ExecutionIntentRow(
        execution_intent_id=execution_intent_id,
        source_candidate_id=source_candidate_id,
        symbol=symbol,
        direction=direction,
        side=side,
        target_weight=target_weight,
        max_weight=max_weight,
        risk_status=risk_status,
        strategy_id=strategy_id,
        regime_id=regime_id,
        asset_behavior=asset_behavior,
        created_by=CREATED_BY,
        diagnostics=diagnostics,
        metadata=metadata,
        performance_context=performance_context,
    )


def _validate_direction_and_weight(
    *,
    direction: str,
    target_weight: float,
    max_weight: float | None,
) -> None:
    if direction == "long" and target_weight < 0:
        raise ExecutionInputContractError(
            "long candidates must have target_weight >= 0."
        )

    if direction == "short" and target_weight > 0:
        raise ExecutionInputContractError(
            "short candidates must have target_weight <= 0."
        )

    if direction == "neutral" and target_weight != 0:
        raise ExecutionInputContractError(
            "neutral candidates must have target_weight == 0."
        )

    if max_weight is not None and abs(target_weight) > abs(max_weight):
        raise ExecutionInputContractError(
            f"target_weight {target_weight} exceeds max_weight {max_weight}."
        )


def _build_execution_intent_id(
    *,
    source_candidate_id: str,
    symbol: str,
    direction: str,
    target_weight: float,
    strategy_id: str,
) -> str:
    payload = json.dumps(
        {
            "direction": direction,
            "source_candidate_id": source_candidate_id,
            "strategy_id": strategy_id,
            "symbol": symbol,
            "target_weight": target_weight,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()[:12]
    return f"exec_intent_{symbol}_{digest}"


def _side_for_direction(direction: str) -> str:
    try:
        return _DIRECTION_TO_SIDE[direction]
    except KeyError as exc:
        raise ExecutionInputContractError(
            f"Invalid direction {direction!r}; expected one of {sorted(_VALID_DIRECTIONS)}."
        ) from exc


def _normalize_direction(value: Any) -> str:
    direction = _normalize_string(value, field_name="direction")

    if direction not in _VALID_DIRECTIONS:
        raise ExecutionInputContractError(
            f"Invalid direction {direction!r}; expected one of {sorted(_VALID_DIRECTIONS)}."
        )

    return direction


def _normalize_symbol(value: Any) -> str:
    symbol = _normalize_string(value, field_name="symbol").upper()

    if not symbol:
        raise ExecutionInputContractError("symbol is required.")

    return symbol


def _normalize_string(value: Any, *, field_name: str) -> str:
    if value is None:
        raise ExecutionInputContractError(f"{field_name} is required.")

    normalized = str(value).strip().lower()

    if not normalized:
        raise ExecutionInputContractError(f"{field_name} is required.")

    return normalized


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None

    normalized = str(value).strip()

    return normalized or None


def _as_float(value: Any, *, field_name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ExecutionInputContractError(f"{field_name} must be numeric.") from exc


def _get_first(
    mapping: Mapping[str, Any],
    keys: tuple[str, ...],
    *,
    default: Any = _MISSING,
) -> Any:
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]

    if default is not _MISSING:
        return default

    raise ExecutionInputContractError(
        f"Missing required field. Expected one of: {', '.join(keys)}."
    )


def _json_safe_mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}

    if is_dataclass(value):
        value = asdict(value)

    if not isinstance(value, Mapping):
        raise ExecutionInputContractError("diagnostics, metadata, and performance context must be mappings.")

    return {
        str(key): _json_safe(value)
        for key, value in sorted(value.items(), key=lambda item: str(item[0]))
    }


def _json_safe(value: Any) -> Any:
    if is_dataclass(value):
        return _json_safe(asdict(value))

    if isinstance(value, Mapping):
        return {
            str(key): _json_safe(inner_value)
            for key, inner_value in sorted(value.items(), key=lambda item: str(item[0]))
        }

    if isinstance(value, list | tuple):
        return [_json_safe(item) for item in value]

    if isinstance(value, set):
        safe_items = [_json_safe(item) for item in value]
        return sorted(
            safe_items,
            key=lambda item: json.dumps(item, sort_keys=True, default=str),
        )

    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)
