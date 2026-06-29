from __future__ import annotations

import math
import numbers
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence


class ContractSeverity(str, Enum):
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"


class ResearchEvaluationContractError(ValueError):
    """Raised when research evaluation output violates required contracts."""


@dataclass(frozen=True)
class ContractCheck:
    name: str
    passed: bool
    severity: ContractSeverity
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ResearchTableContract:
    name: str
    required_columns: tuple[str, ...] = ()
    one_of_columns: tuple[tuple[str, ...], ...] = ()
    key_sets: tuple[tuple[str, ...], ...] = ()
    numeric_columns: tuple[str, ...] = ()
    allow_empty: bool = False


@dataclass(frozen=True)
class ResearchEvaluationContractResult:
    checks: tuple[ContractCheck, ...]

    @property
    def passed(self) -> bool:
        return not any(
            check.severity == ContractSeverity.FAIL and not check.passed
            for check in self.checks
        )

    @property
    def failures(self) -> tuple[ContractCheck, ...]:
        return tuple(
            check
            for check in self.checks
            if check.severity == ContractSeverity.FAIL and not check.passed
        )

    @property
    def warnings(self) -> tuple[ContractCheck, ...]:
        return tuple(
            check
            for check in self.checks
            if check.severity == ContractSeverity.WARNING and not check.passed
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "checks": [
                {
                    "name": check.name,
                    "passed": check.passed,
                    "severity": check.severity.value,
                    "message": check.message,
                    "details": dict(check.details),
                }
                for check in self.checks
            ],
        }


DEFAULT_RESEARCH_EVALUATION_CONTRACTS: tuple[ResearchTableContract, ...] = (
    ResearchTableContract(
        name="factors",
        required_columns=("date", "symbol"),
        one_of_columns=(
            ("factor", "factor_name"),
            ("value", "factor_value", "score"),
        ),
        key_sets=(
            ("date", "symbol", "factor"),
            ("date", "symbol", "factor_name"),
        ),
        numeric_columns=("value", "factor_value", "score"),
        allow_empty=False,
    ),
    ResearchTableContract(
        name="signals",
        required_columns=("date", "symbol"),
        one_of_columns=(
            ("signal", "signal_name"),
            ("signal_value", "direction", "score"),
        ),
        key_sets=(
            ("date", "symbol", "signal"),
            ("date", "symbol", "signal_name"),
        ),
        numeric_columns=("signal_value", "direction", "score"),
        allow_empty=False,
    ),
    ResearchTableContract(
        name="portfolio_targets",
        required_columns=("date", "symbol", "target_weight"),
        key_sets=(("date", "symbol"),),
        numeric_columns=("target_weight",),
        allow_empty=False,
    ),
)


def table_columns(table: Any) -> tuple[str, ...]:
    if table is None:
        return ()

    if hasattr(table, "columns"):
        return tuple(str(column) for column in table.columns)

    if isinstance(table, Sequence) and not isinstance(table, (str, bytes)):
        columns: set[str] = set()
        for row in table:
            if isinstance(row, Mapping):
                columns.update(str(key) for key in row.keys())
        return tuple(sorted(columns))

    if isinstance(table, Mapping):
        return tuple(str(key) for key in table.keys())

    return ()


def table_records(table: Any) -> list[dict[str, Any]]:
    if table is None:
        return []

    if hasattr(table, "to_dicts"):
        return [dict(row) for row in table.to_dicts()]

    if hasattr(table, "to_dict"):
        try:
            records = table.to_dict(orient="records")
            return [dict(row) for row in records]
        except TypeError:
            pass

    if isinstance(table, Sequence) and not isinstance(table, (str, bytes)):
        return [dict(row) for row in table if isinstance(row, Mapping)]

    if isinstance(table, Mapping):
        keys = list(table.keys())
        values = list(table.values())

        if not values:
            return []

        if all(isinstance(value, Sequence) and not isinstance(value, (str, bytes)) for value in values):
            row_count = min(len(value) for value in values)
            return [
                {str(key): table[key][index] for key in keys}
                for index in range(row_count)
            ]

    return []


def table_row_count(table: Any) -> int:
    try:
        return len(table)
    except TypeError:
        return len(table_records(table))


def is_null(value: Any) -> bool:
    if value is None:
        return True

    try:
        return bool(math.isnan(value))
    except TypeError:
        return False


def is_finite_number(value: Any) -> bool:
    if is_null(value):
        return False

    if isinstance(value, bool):
        return False

    if isinstance(value, numbers.Number):
        return math.isfinite(float(value))

    return False


def _check_required_section(
    output: Mapping[str, Any],
    contract: ResearchTableContract,
) -> list[ContractCheck]:
    if contract.name not in output:
        return [
            ContractCheck(
                name=f"{contract.name}.exists",
                passed=False,
                severity=ContractSeverity.FAIL,
                message=f"Missing required research output section: {contract.name}",
            )
        ]

    return [
        ContractCheck(
            name=f"{contract.name}.exists",
            passed=True,
            severity=ContractSeverity.PASS,
            message=f"Found required research output section: {contract.name}",
        )
    ]


def _check_required_columns(
    table: Any,
    contract: ResearchTableContract,
) -> list[ContractCheck]:
    columns = set(table_columns(table))
    missing = [column for column in contract.required_columns if column not in columns]

    if missing:
        return [
            ContractCheck(
                name=f"{contract.name}.required_columns",
                passed=False,
                severity=ContractSeverity.FAIL,
                message=f"{contract.name} is missing required columns.",
                details={"missing_columns": missing, "available_columns": sorted(columns)},
            )
        ]

    return [
        ContractCheck(
            name=f"{contract.name}.required_columns",
            passed=True,
            severity=ContractSeverity.PASS,
            message=f"{contract.name} contains required columns.",
            details={"required_columns": list(contract.required_columns)},
        )
    ]


def _check_one_of_columns(
    table: Any,
    contract: ResearchTableContract,
) -> list[ContractCheck]:
    columns = set(table_columns(table))
    checks: list[ContractCheck] = []

    for group in contract.one_of_columns:
        found = [column for column in group if column in columns]

        if not found:
            checks.append(
                ContractCheck(
                    name=f"{contract.name}.one_of_columns",
                    passed=False,
                    severity=ContractSeverity.FAIL,
                    message=f"{contract.name} must include at least one of: {group}",
                    details={"accepted_columns": list(group), "available_columns": sorted(columns)},
                )
            )
        else:
            checks.append(
                ContractCheck(
                    name=f"{contract.name}.one_of_columns",
                    passed=True,
                    severity=ContractSeverity.PASS,
                    message=f"{contract.name} satisfies one-of column requirement.",
                    details={"accepted_columns": list(group), "found_columns": found},
                )
            )

    return checks


def _check_non_empty(
    table: Any,
    contract: ResearchTableContract,
) -> list[ContractCheck]:
    row_count = table_row_count(table)

    if row_count == 0 and not contract.allow_empty:
        return [
            ContractCheck(
                name=f"{contract.name}.non_empty",
                passed=False,
                severity=ContractSeverity.FAIL,
                message=f"{contract.name} cannot be empty.",
                details={"row_count": row_count},
            )
        ]

    return [
        ContractCheck(
            name=f"{contract.name}.non_empty",
            passed=True,
            severity=ContractSeverity.PASS,
            message=f"{contract.name} row count is valid.",
            details={"row_count": row_count},
        )
    ]


def _select_key_set(
    columns: set[str],
    key_sets: Iterable[tuple[str, ...]],
) -> tuple[str, ...] | None:
    for key_set in key_sets:
        if all(column in columns for column in key_set):
            return key_set

    return None


def _check_duplicates(
    table: Any,
    contract: ResearchTableContract,
) -> list[ContractCheck]:
    records = table_records(table)
    columns = set(table_columns(table))

    key_set = _select_key_set(columns, contract.key_sets)

    if not key_set:
        return [
            ContractCheck(
                name=f"{contract.name}.duplicates",
                passed=True,
                severity=ContractSeverity.WARNING,
                message=f"{contract.name} duplicate check skipped because no configured key set is fully present.",
                details={"available_columns": sorted(columns)},
            )
        ]

    seen: set[tuple[Any, ...]] = set()
    duplicates: list[tuple[Any, ...]] = []

    for row in records:
        key = tuple(row.get(column) for column in key_set)
        if key in seen:
            duplicates.append(key)
        seen.add(key)

    if duplicates:
        return [
            ContractCheck(
                name=f"{contract.name}.duplicates",
                passed=False,
                severity=ContractSeverity.FAIL,
                message=f"{contract.name} contains duplicate contract keys.",
                details={"key_columns": list(key_set), "duplicate_count": len(duplicates)},
            )
        ]

    return [
        ContractCheck(
            name=f"{contract.name}.duplicates",
            passed=True,
            severity=ContractSeverity.PASS,
            message=f"{contract.name} contains no duplicate contract keys.",
            details={"key_columns": list(key_set)},
        )
    ]


def _check_numeric_columns(
    table: Any,
    contract: ResearchTableContract,
) -> list[ContractCheck]:
    records = table_records(table)
    columns = set(table_columns(table))
    checks: list[ContractCheck] = []

    for column in contract.numeric_columns:
        if column not in columns:
            continue

        invalid_count = 0

        for row in records:
            value = row.get(column)
            if not is_null(value) and not is_finite_number(value):
                invalid_count += 1

        if invalid_count:
            checks.append(
                ContractCheck(
                    name=f"{contract.name}.{column}.finite",
                    passed=False,
                    severity=ContractSeverity.FAIL,
                    message=f"{contract.name}.{column} contains non-finite numeric values.",
                    details={"invalid_count": invalid_count},
                )
            )
        else:
            checks.append(
                ContractCheck(
                    name=f"{contract.name}.{column}.finite",
                    passed=True,
                    severity=ContractSeverity.PASS,
                    message=f"{contract.name}.{column} contains only finite numeric values.",
                )
            )

    return checks


def validate_research_evaluation_output(
    output: Mapping[str, Any],
    contracts: Sequence[ResearchTableContract] = DEFAULT_RESEARCH_EVALUATION_CONTRACTS,
) -> ResearchEvaluationContractResult:
    checks: list[ContractCheck] = []

    if not isinstance(output, Mapping):
        return ResearchEvaluationContractResult(
            checks=(
                ContractCheck(
                    name="research_output.mapping",
                    passed=False,
                    severity=ContractSeverity.FAIL,
                    message="Research evaluation output must be a mapping/dictionary.",
                ),
            )
        )

    for contract in contracts:
        checks.extend(_check_required_section(output, contract))

        if contract.name not in output:
            continue

        table = output[contract.name]

        checks.extend(_check_non_empty(table, contract))
        checks.extend(_check_required_columns(table, contract))
        checks.extend(_check_one_of_columns(table, contract))
        checks.extend(_check_duplicates(table, contract))
        checks.extend(_check_numeric_columns(table, contract))

    if "diagnostics" not in output:
        checks.append(
            ContractCheck(
                name="diagnostics.exists",
                passed=False,
                severity=ContractSeverity.WARNING,
                message="Research output does not include diagnostics yet.",
            )
        )

    if "metadata" not in output:
        checks.append(
            ContractCheck(
                name="metadata.exists",
                passed=False,
                severity=ContractSeverity.WARNING,
                message="Research output does not include metadata yet.",
            )
        )

    return ResearchEvaluationContractResult(checks=tuple(checks))


def enforce_research_evaluation_output(
    output: Mapping[str, Any],
    contracts: Sequence[ResearchTableContract] = DEFAULT_RESEARCH_EVALUATION_CONTRACTS,
) -> Mapping[str, Any]:
    result = validate_research_evaluation_output(output=output, contracts=contracts)

    if not result.passed:
        failure_messages = "; ".join(check.message for check in result.failures)
        raise ResearchEvaluationContractError(
            f"Research evaluation output failed contract validation: {failure_messages}"
        )

    return output
