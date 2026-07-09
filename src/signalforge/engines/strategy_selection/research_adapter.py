from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, is_dataclass
from math import isfinite
from typing import Any


REQUIRED_STRATEGY_CANDIDATE_FIELDS = (
    "candidate_id",
    "symbol",
    "direction",
    "target_weight",
    "diagnostics",
    "metadata",
    "performance_context",
)

VALID_DIRECTIONS = {"LONG", "SHORT", "FLAT"}

DIRECTION_ALIASES = {
    "BUY": "LONG",
    "SELL": "SHORT",
    "HOLD": "FLAT",
}


class StrategySelectionInputContractError(ValueError):
    """Raised when research/backtest output cannot be adapted for strategy selection."""


@dataclass(frozen=True)
class StrategyCandidateInputRow:
    candidate_id: str
    symbol: str
    direction: str
    target_weight: float
    diagnostics: Mapping[str, Any]
    metadata: Mapping[str, Any]
    performance_context: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "symbol": self.symbol,
            "direction": self.direction,
            "target_weight": self.target_weight,
            "diagnostics": dict(self.diagnostics),
            "metadata": dict(self.metadata),
            "performance_context": dict(self.performance_context),
        }


@dataclass(frozen=True)
class StrategySelectionInputValidationReport:
    passed: bool
    row_count: int
    errors: tuple[str, ...]


def adapt_research_backtest_to_strategy_candidates(
    handoff_result: Any,
) -> list[dict[str, Any]]:
    """
    Convert an accepted research/backtest handoff result into strategy-selection-ready
    candidate input rows.

    This adapter intentionally does not score, rank, select, or reject strategies.
    It only translates and validates the downstream contract.
    """
    _block_invalid_handoff(handoff_result)

    rows = [
        row.to_dict()
        for row in _build_strategy_candidate_rows(handoff_result)
    ]

    validation = validate_strategy_candidate_input_rows(rows)
    if not validation.passed:
        raise StrategySelectionInputContractError(
            "Strategy selection input contract failed: "
            + "; ".join(validation.errors)
        )

    return rows


def validate_strategy_candidate_input_rows(
    rows: Sequence[Mapping[str, Any]],
) -> StrategySelectionInputValidationReport:
    errors: list[str] = []

    if not rows:
        errors.append("strategy candidate input rows are empty")

    for row_index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            errors.append(f"row {row_index} is not a mapping")
            continue

        for field in REQUIRED_STRATEGY_CANDIDATE_FIELDS:
            if field not in row:
                errors.append(f"row {row_index} missing required field: {field}")

        if "candidate_id" in row and not _non_empty_string(row["candidate_id"]):
            errors.append(f"row {row_index} has invalid candidate_id")

        if "symbol" in row and not _non_empty_string(row["symbol"]):
            errors.append(f"row {row_index} has invalid symbol")

        if "direction" in row:
            direction = row["direction"]
            if direction not in VALID_DIRECTIONS:
                errors.append(
                    f"row {row_index} has invalid direction: {direction!r}"
                )

        if "target_weight" in row and not _valid_number(row["target_weight"]):
            errors.append(f"row {row_index} has invalid target_weight")

        for mapping_field in ("diagnostics", "metadata", "performance_context"):
            if mapping_field in row and not isinstance(row[mapping_field], Mapping):
                errors.append(f"row {row_index} has invalid {mapping_field}")

    return StrategySelectionInputValidationReport(
        passed=not errors,
        row_count=len(rows),
        errors=tuple(errors),
    )


def _build_strategy_candidate_rows(
    handoff_result: Any,
) -> list[StrategyCandidateInputRow]:
    symbols = _accepted_symbols(handoff_result)

    directions = _get_any(
        handoff_result,
        "directions",
        "accepted_directions",
        "signal_directions",
        default={},
    )
    target_weights = _get_any(
        handoff_result,
        "target_weights",
        "accepted_target_weights",
        "weights",
        default={},
    )
    diagnostics = _get_any(
        handoff_result,
        "diagnostics",
        "research_diagnostics",
        default={},
    )
    metadata = _get_any(
        handoff_result,
        "metadata",
        "handoff_metadata",
        default={},
    )
    performance_context = _get_any(
        handoff_result,
        "performance_context",
        "performance_summary",
        "backtest_performance",
        default={},
    )
    candidate_ids = _get_any(
        handoff_result,
        "candidate_ids",
        "accepted_candidate_ids",
        default={},
    )

    rows: list[StrategyCandidateInputRow] = []

    for index, symbol in enumerate(symbols):
        direction = _normalize_direction(
            _lookup_by_symbol_or_index(directions, symbol, index)
        )
        target_weight = _lookup_by_symbol_or_index(target_weights, symbol, index)
        candidate_id = _lookup_by_symbol_or_index(candidate_ids, symbol, index)

        if candidate_id is None:
            candidate_id = f"strategy_candidate_{str(symbol).lower()}"

        rows.append(
            StrategyCandidateInputRow(
                candidate_id=str(candidate_id),
                symbol=str(symbol),
                direction=direction,
                target_weight=float(target_weight),
                diagnostics=_mapping_for_symbol(diagnostics, symbol),
                metadata=dict(metadata) if isinstance(metadata, Mapping) else {},
                performance_context=_mapping_for_symbol(
                    performance_context,
                    symbol,
                ),
            )
        )

    return rows


def _block_invalid_handoff(handoff_result: Any) -> None:
    accepted = _get_any(
        handoff_result,
        "accepted",
        "is_accepted",
        "valid",
        "passed",
        default=None,
    )

    if accepted is False:
        raise StrategySelectionInputContractError(
            "Research/backtest handoff was not accepted"
        )

    status = _get_any(
        handoff_result,
        "status",
        "validation_status",
        "health_status",
        default=None,
    )

    if isinstance(status, str) and status.lower() in {
        "failed",
        "fail",
        "invalid",
        "rejected",
        "blocked",
    }:
        raise StrategySelectionInputContractError(
            f"Research/backtest handoff has blocking status: {status}"
        )


def _accepted_symbols(handoff_result: Any) -> list[Any]:
    symbols = _get_any(
        handoff_result,
        "accepted_symbols",
        "symbols",
        "asset_symbols",
        default=None,
    )

    if symbols is None:
        target_weights = _get_any(
            handoff_result,
            "target_weights",
            "accepted_target_weights",
            "weights",
            default=None,
        )
        if isinstance(target_weights, Mapping):
            symbols = sorted(target_weights)

    if not symbols:
        raise StrategySelectionInputContractError(
            "Research/backtest handoff has no accepted symbols"
        )

    if isinstance(symbols, str):
        return [symbols]

    return list(symbols)


def _normalize_direction(direction: Any) -> str:
    if direction is None:
        raise StrategySelectionInputContractError(
            "Strategy candidate direction is missing"
        )

    normalized = str(direction).upper()
    normalized = DIRECTION_ALIASES.get(normalized, normalized)

    if normalized not in VALID_DIRECTIONS:
        raise StrategySelectionInputContractError(
            f"Strategy candidate direction is invalid: {direction!r}"
        )

    return normalized


def _lookup_by_symbol_or_index(source: Any, symbol: Any, index: int) -> Any:
    if isinstance(source, Mapping):
        if symbol in source:
            value = source[symbol]
        elif str(symbol) in source:
            value = source[str(symbol)]
        else:
            return None

        if isinstance(value, Mapping):
            for field in ("value", "direction", "target_weight", "candidate_id"):
                if field in value:
                    return value[field]

        return value

    if isinstance(source, Sequence) and not isinstance(source, str):
        if index >= len(source):
            return None

        value = source[index]
        if isinstance(value, Mapping):
            for field in ("value", "direction", "target_weight", "candidate_id"):
                if field in value:
                    return value[field]

        return value

    return None


def _mapping_for_symbol(source: Any, symbol: Any) -> Mapping[str, Any]:
    if not isinstance(source, Mapping):
        return {}

    if symbol in source and isinstance(source[symbol], Mapping):
        return dict(source[symbol])

    string_symbol = str(symbol)
    if string_symbol in source and isinstance(source[string_symbol], Mapping):
        return dict(source[string_symbol])

    return dict(source)


def _get_any(source: Any, *names: str, default: Any = None) -> Any:
    source = _to_plain_object(source)

    if isinstance(source, Mapping):
        for name in names:
            if name in source:
                return source[name]
        return default

    for name in names:
        if hasattr(source, name):
            return getattr(source, name)

    return default


def _to_plain_object(source: Any) -> Any:
    if is_dataclass(source):
        return asdict(source)

    return source


def _non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _valid_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and isfinite(float(value))
    )
