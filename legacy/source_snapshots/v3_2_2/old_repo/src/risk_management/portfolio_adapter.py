from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, is_dataclass
from math import isfinite
from typing import Any


REQUIRED_RISK_MANAGEMENT_INPUT_FIELDS = (
    "risk_input_id",
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
    "construction_context",
)

VALID_DIRECTIONS = {"LONG", "SHORT", "FLAT"}


class RiskManagementInputContractError(ValueError):
    """Raised when portfolio construction output cannot enter risk management."""


@dataclass(frozen=True)
class RiskManagementInputRow:
    risk_input_id: str
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
    construction_context: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "risk_input_id": self.risk_input_id,
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
            "construction_context": dict(self.construction_context),
        }


@dataclass(frozen=True)
class RiskManagementInputValidationReport:
    passed: bool
    row_count: int
    errors: tuple[str, ...]


def adapt_portfolio_construction_to_risk_inputs(
    portfolio_construction_result: Any,
) -> list[dict[str, Any]]:
    """
    Convert a passed portfolio-construction runner result into risk-management
    input rows.

    This adapter does not apply risk limits, reject concentration, resize
    positions, optimize exposure, generate orders, or execute trades.
    """
    payload = _to_mapping(portfolio_construction_result)

    _block_invalid_portfolio_construction_result(payload)

    portfolio_input_rows = _portfolio_input_rows(payload)
    construction_report = _construction_report(payload)

    accepted_candidate_ids = construction_report.get("accepted_candidate_ids")
    candidate_summaries = construction_report.get("candidate_summaries")

    if not isinstance(accepted_candidate_ids, Sequence) or isinstance(
        accepted_candidate_ids,
        str,
    ):
        raise RiskManagementInputContractError(
            "portfolio construction result has invalid accepted_candidate_ids"
        )

    if not accepted_candidate_ids:
        raise RiskManagementInputContractError(
            "portfolio construction result has no accepted candidates"
        )

    if not isinstance(candidate_summaries, Sequence) or isinstance(
        candidate_summaries,
        str,
    ):
        raise RiskManagementInputContractError(
            "portfolio construction result has invalid candidate_summaries"
        )

    portfolio_rows_by_candidate_id = {
        str(row["candidate_id"]): row
        for row in portfolio_input_rows
        if isinstance(row, Mapping) and "candidate_id" in row
    }

    accepted_summaries_by_candidate_id = {
        str(summary["candidate_id"]): summary
        for summary in candidate_summaries
        if (
            isinstance(summary, Mapping)
            and summary.get("accepted") is True
            and "candidate_id" in summary
        )
    }

    construction_context = _construction_context(construction_report)

    rows: list[dict[str, Any]] = []

    for candidate_id in accepted_candidate_ids:
        candidate_id = str(candidate_id)

        portfolio_row = portfolio_rows_by_candidate_id.get(candidate_id)
        if portfolio_row is None:
            raise RiskManagementInputContractError(
                f"accepted candidate missing portfolio input row: {candidate_id}"
            )

        summary = accepted_summaries_by_candidate_id.get(candidate_id)
        if summary is None:
            raise RiskManagementInputContractError(
                f"accepted candidate missing accepted summary: {candidate_id}"
            )

        rows.append(
            RiskManagementInputRow(
                risk_input_id=f"risk_input_{candidate_id}",
                portfolio_input_id=str(portfolio_row["portfolio_input_id"]),
                candidate_id=candidate_id,
                symbol=str(portfolio_row["symbol"]),
                direction=str(portfolio_row["direction"]),
                target_weight=float(portfolio_row["target_weight"]),
                selection_rank=int(portfolio_row["selection_rank"]),
                selection_score=float(portfolio_row["selection_score"]),
                diagnostics=dict(portfolio_row["diagnostics"]),
                metadata=dict(portfolio_row["metadata"]),
                performance_context=dict(portfolio_row["performance_context"]),
                construction_context=construction_context,
            ).to_dict()
        )

    validation = validate_risk_management_input_rows(rows)
    if not validation.passed:
        raise RiskManagementInputContractError(
            "Risk management input contract failed: "
            + "; ".join(validation.errors)
        )

    return rows


def validate_risk_management_input_rows(
    rows: Sequence[Mapping[str, Any]],
) -> RiskManagementInputValidationReport:
    errors: list[str] = []

    if not rows:
        errors.append("risk management input rows are empty")

    for row_index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            errors.append(f"row {row_index} is not a mapping")
            continue

        for field in REQUIRED_RISK_MANAGEMENT_INPUT_FIELDS:
            if field not in row:
                errors.append(f"row {row_index} missing required field: {field}")

        for string_field in (
            "risk_input_id",
            "portfolio_input_id",
            "candidate_id",
            "symbol",
        ):
            if string_field in row and not _non_empty_string(row[string_field]):
                errors.append(f"row {row_index} has invalid {string_field}")

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

        for mapping_field in (
            "diagnostics",
            "metadata",
            "performance_context",
            "construction_context",
        ):
            if mapping_field in row and not isinstance(row[mapping_field], Mapping):
                errors.append(f"row {row_index} has invalid {mapping_field}")

    return RiskManagementInputValidationReport(
        passed=not errors,
        row_count=len(rows),
        errors=tuple(errors),
    )


def _block_invalid_portfolio_construction_result(payload: Mapping[str, Any]) -> None:
    health = payload.get("health")
    if isinstance(health, Mapping) and health.get("passed") is False:
        raise RiskManagementInputContractError(
            "portfolio construction health did not pass"
        )

    construction_report = _construction_report(payload)

    if construction_report.get("passed") is not True:
        raise RiskManagementInputContractError(
            "portfolio construction report did not pass"
        )

    if construction_report.get("construction_status") != "constructed":
        raise RiskManagementInputContractError(
            "portfolio construction result was not constructed"
        )

    accepted_count = construction_report.get("accepted_count")
    if not isinstance(accepted_count, int) or accepted_count < 1:
        raise RiskManagementInputContractError(
            "portfolio construction result has no accepted candidates"
        )


def _portfolio_input_rows(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    portfolio_input_rows = payload.get("portfolio_input_rows")

    if not isinstance(portfolio_input_rows, Sequence) or isinstance(
        portfolio_input_rows,
        str,
    ):
        raise RiskManagementInputContractError(
            "portfolio construction result missing portfolio_input_rows"
        )

    return list(portfolio_input_rows)


def _construction_report(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    construction_report = payload.get("construction_report")

    if isinstance(construction_report, Mapping):
        return construction_report

    operation_record = payload.get("operation_record")
    if isinstance(operation_record, Mapping):
        nested_report = operation_record.get("construction_report")
        if isinstance(nested_report, Mapping):
            return nested_report

    raise RiskManagementInputContractError(
        "portfolio construction result missing construction_report"
    )


def _construction_context(
    construction_report: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "construction_status": construction_report.get("construction_status"),
        "accepted_count": construction_report.get("accepted_count"),
        "rejected_count": construction_report.get("rejected_count"),
        "total_target_exposure": construction_report.get("total_target_exposure"),
        "long_exposure": construction_report.get("long_exposure"),
        "short_exposure": construction_report.get("short_exposure"),
        "net_exposure": construction_report.get("net_exposure"),
    }


def _to_mapping(source: Any) -> Mapping[str, Any]:
    if hasattr(source, "to_dict"):
        source = source.to_dict()
    elif is_dataclass(source):
        source = asdict(source)

    if not isinstance(source, Mapping):
        raise RiskManagementInputContractError(
            "portfolio construction result must be a mapping or expose to_dict()"
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
