from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, is_dataclass
from math import isfinite
from typing import Any


REQUIRED_PORTFOLIO_CONSTRUCTION_INPUT_FIELDS = (
    "portfolio_input_id",
    "candidate_id",
    "symbol",
    "direction",
    "target_weight",
    "selection_rank",
    "selection_score",
    "diagnostics",
    "metadata",
    "performance_context",
)

VALID_DIRECTIONS = {"LONG", "SHORT", "FLAT"}


class PortfolioConstructionInputContractError(ValueError):
    """Raised when strategy selection output cannot enter portfolio construction."""


@dataclass(frozen=True)
class PortfolioConstructionInputRow:
    portfolio_input_id: str
    candidate_id: str
    symbol: str
    direction: str
    target_weight: float
    selection_rank: int
    selection_score: float
    diagnostics: Mapping[str, Any]
    metadata: Mapping[str, Any]
    performance_context: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "portfolio_input_id": self.portfolio_input_id,
            "candidate_id": self.candidate_id,
            "symbol": self.symbol,
            "direction": self.direction,
            "target_weight": self.target_weight,
            "selection_rank": self.selection_rank,
            "selection_score": self.selection_score,
            "diagnostics": dict(self.diagnostics),
            "metadata": dict(self.metadata),
            "performance_context": dict(self.performance_context),
        }


@dataclass(frozen=True)
class PortfolioConstructionInputValidationReport:
    passed: bool
    row_count: int
    errors: tuple[str, ...]


def adapt_strategy_selection_to_portfolio_inputs(
    strategy_selection_result: Any,
) -> list[dict[str, Any]]:
    """
    Convert a passed strategy-selection runner result into portfolio-construction
    input rows.

    This adapter does not optimize, rebalance, size positions, generate orders,
    or mutate target weights.
    """
    payload = _to_mapping(strategy_selection_result)

    _block_invalid_strategy_selection_result(payload)

    candidate_rows = _candidate_rows(payload)
    selection_report = _selection_report(payload)

    selected_candidate_ids = selection_report.get("selected_candidate_ids")
    candidate_summaries = selection_report.get("candidate_summaries")

    if not isinstance(selected_candidate_ids, Sequence) or isinstance(
        selected_candidate_ids,
        str,
    ):
        raise PortfolioConstructionInputContractError(
            "strategy selection result has invalid selected_candidate_ids"
        )

    if not selected_candidate_ids:
        raise PortfolioConstructionInputContractError(
            "strategy selection result has no selected candidates"
        )

    if not isinstance(candidate_summaries, Sequence) or isinstance(
        candidate_summaries,
        str,
    ):
        raise PortfolioConstructionInputContractError(
            "strategy selection result has invalid candidate_summaries"
        )

    candidate_rows_by_id = {
        str(row["candidate_id"]): row
        for row in candidate_rows
        if isinstance(row, Mapping) and "candidate_id" in row
    }

    selected_summaries_by_id = {
        str(summary["candidate_id"]): summary
        for summary in candidate_summaries
        if (
            isinstance(summary, Mapping)
            and summary.get("selected") is True
            and "candidate_id" in summary
        )
    }

    rows: list[dict[str, Any]] = []

    for candidate_id in selected_candidate_ids:
        candidate_id = str(candidate_id)

        candidate_row = candidate_rows_by_id.get(candidate_id)
        if candidate_row is None:
            raise PortfolioConstructionInputContractError(
                f"selected candidate missing candidate row: {candidate_id}"
            )

        summary = selected_summaries_by_id.get(candidate_id)
        if summary is None:
            raise PortfolioConstructionInputContractError(
                f"selected candidate missing selected summary: {candidate_id}"
            )

        rows.append(
            PortfolioConstructionInputRow(
                portfolio_input_id=f"portfolio_input_{candidate_id}",
                candidate_id=candidate_id,
                symbol=str(candidate_row["symbol"]),
                direction=str(candidate_row["direction"]),
                target_weight=float(candidate_row["target_weight"]),
                selection_rank=int(summary["rank"]),
                selection_score=float(summary["selection_score"]),
                diagnostics=dict(candidate_row["diagnostics"]),
                metadata=dict(candidate_row["metadata"]),
                performance_context=dict(candidate_row["performance_context"]),
            ).to_dict()
        )

    validation = validate_portfolio_construction_input_rows(rows)
    if not validation.passed:
        raise PortfolioConstructionInputContractError(
            "Portfolio construction input contract failed: "
            + "; ".join(validation.errors)
        )

    return rows


def validate_portfolio_construction_input_rows(
    rows: Sequence[Mapping[str, Any]],
) -> PortfolioConstructionInputValidationReport:
    errors: list[str] = []

    if not rows:
        errors.append("portfolio construction input rows are empty")

    for row_index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            errors.append(f"row {row_index} is not a mapping")
            continue

        for field in REQUIRED_PORTFOLIO_CONSTRUCTION_INPUT_FIELDS:
            if field not in row:
                errors.append(f"row {row_index} missing required field: {field}")

        if "portfolio_input_id" in row and not _non_empty_string(
            row["portfolio_input_id"]
        ):
            errors.append(f"row {row_index} has invalid portfolio_input_id")

        if "candidate_id" in row and not _non_empty_string(row["candidate_id"]):
            errors.append(f"row {row_index} has invalid candidate_id")

        if "symbol" in row and not _non_empty_string(row["symbol"]):
            errors.append(f"row {row_index} has invalid symbol")

        if "direction" in row and row["direction"] not in VALID_DIRECTIONS:
            errors.append(
                f"row {row_index} has invalid direction: {row['direction']!r}"
            )

        if "target_weight" in row and not _valid_number(row["target_weight"]):
            errors.append(f"row {row_index} has invalid target_weight")

        if "selection_rank" in row and not _positive_int(row["selection_rank"]):
            errors.append(f"row {row_index} has invalid selection_rank")

        if "selection_score" in row and not _valid_number(row["selection_score"]):
            errors.append(f"row {row_index} has invalid selection_score")

        for mapping_field in ("diagnostics", "metadata", "performance_context"):
            if mapping_field in row and not isinstance(row[mapping_field], Mapping):
                errors.append(f"row {row_index} has invalid {mapping_field}")

    return PortfolioConstructionInputValidationReport(
        passed=not errors,
        row_count=len(rows),
        errors=tuple(errors),
    )


def _block_invalid_strategy_selection_result(payload: Mapping[str, Any]) -> None:
    health = payload.get("health")
    if isinstance(health, Mapping) and health.get("passed") is False:
        raise PortfolioConstructionInputContractError(
            "strategy selection health did not pass"
        )

    selection_report = _selection_report(payload)

    if selection_report.get("passed") is not True:
        raise PortfolioConstructionInputContractError(
            "strategy selection report did not pass"
        )

    if selection_report.get("selection_status") != "selected":
        raise PortfolioConstructionInputContractError(
            "strategy selection result was not selected"
        )

    selected_count = selection_report.get("selected_count")
    if not isinstance(selected_count, int) or selected_count < 1:
        raise PortfolioConstructionInputContractError(
            "strategy selection result has no selected candidates"
        )


def _candidate_rows(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    candidate_rows = payload.get("candidate_rows")

    if not isinstance(candidate_rows, Sequence) or isinstance(candidate_rows, str):
        raise PortfolioConstructionInputContractError(
            "strategy selection result missing candidate_rows"
        )

    return list(candidate_rows)


def _selection_report(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    selection_report = payload.get("selection_report")

    if isinstance(selection_report, Mapping):
        return selection_report

    operation_record = payload.get("operation_record")
    if isinstance(operation_record, Mapping):
        nested_report = operation_record.get("selection_report")
        if isinstance(nested_report, Mapping):
            return nested_report

    raise PortfolioConstructionInputContractError(
        "strategy selection result missing selection_report"
    )


def _to_mapping(source: Any) -> Mapping[str, Any]:
    if hasattr(source, "to_dict"):
        source = source.to_dict()
    elif is_dataclass(source):
        source = asdict(source)

    if not isinstance(source, Mapping):
        raise PortfolioConstructionInputContractError(
            "strategy selection result must be a mapping or expose to_dict()"
        )

    return source


def _non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _valid_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and isfinite(float(value))
    )


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1
