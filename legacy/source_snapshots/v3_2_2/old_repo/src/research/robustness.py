from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import polars as pl

from src.research.validation import (
    ResearchValidationReport,
    ResearchValidationStatus,
    validate_research_output,
)


DataFrameTransform = Callable[[pl.DataFrame], pl.DataFrame]


class RobustnessScenarioStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    INSUFFICIENT_DATA = "insufficient_data"
    ERROR = "error"


class RobustnessReportStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    MIXED = "mixed"
    INSUFFICIENT_DATA = "insufficient_data"


@dataclass(frozen=True)
class RobustnessScenario:
    name: str
    transform: DataFrameTransform = field(compare=False)
    description: str = ""
    required_columns: tuple[str, ...] = field(default_factory=tuple)
    tags: tuple[str, ...] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", self.name.strip())
        object.__setattr__(self, "description", self.description.strip())
        object.__setattr__(
            self,
            "required_columns",
            _clean_string_tuple(self.required_columns, "required_columns"),
        )
        object.__setattr__(
            self,
            "tags",
            _clean_string_tuple(self.tags, "tags"),
        )
        object.__setattr__(self, "metadata", dict(self.metadata))

        if not self.name:
            raise ValueError("Robustness scenario name cannot be empty.")

        if not callable(self.transform):
            raise TypeError("transform must be callable.")

    def run(self, df: pl.DataFrame) -> pl.DataFrame:
        _require_columns(
            df,
            self.required_columns,
            context=f"Robustness scenario {self.name}",
        )

        result = self.transform(df)

        if not isinstance(result, pl.DataFrame):
            raise TypeError(
                f"Robustness scenario {self.name} must return a polars DataFrame."
            )

        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "required_columns": list(self.required_columns),
            "tags": list(self.tags),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class RobustnessScenarioResult:
    scenario: RobustnessScenario
    status: RobustnessScenarioStatus
    validation_report: ResearchValidationReport | None = None
    input_rows: int = 0
    output_rows: int = 0
    error: str | None = None

    @property
    def passed(self) -> bool:
        return self.status == RobustnessScenarioStatus.PASSED

    @property
    def failed(self) -> bool:
        return self.status == RobustnessScenarioStatus.FAILED

    @property
    def insufficient_data(self) -> bool:
        return self.status == RobustnessScenarioStatus.INSUFFICIENT_DATA

    @property
    def errored(self) -> bool:
        return self.status == RobustnessScenarioStatus.ERROR

    def metric_value(self, name: str) -> float | int | None:
        if self.validation_report is None:
            return None

        return self.validation_report.metric_value(name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario.to_dict(),
            "status": self.status.value,
            "input_rows": self.input_rows,
            "output_rows": self.output_rows,
            "error": self.error,
            "validation_report": (
                self.validation_report.to_dict()
                if self.validation_report is not None
                else None
            ),
        }


@dataclass(frozen=True)
class RobustnessReport:
    status: RobustnessReportStatus
    scenario_results: tuple[RobustnessScenarioResult, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status == RobustnessReportStatus.PASSED

    @property
    def failed(self) -> bool:
        return self.status == RobustnessReportStatus.FAILED

    @property
    def mixed(self) -> bool:
        return self.status == RobustnessReportStatus.MIXED

    @property
    def insufficient_data(self) -> bool:
        return self.status == RobustnessReportStatus.INSUFFICIENT_DATA

    def pass_rate(self) -> float:
        if not self.scenario_results:
            return 0.0

        passed = sum(result.passed for result in self.scenario_results)

        return passed / len(self.scenario_results)

    def failed_scenarios(self) -> tuple[RobustnessScenarioResult, ...]:
        return tuple(
            result
            for result in self.scenario_results
            if result.status in {
                RobustnessScenarioStatus.FAILED,
                RobustnessScenarioStatus.ERROR,
                RobustnessScenarioStatus.INSUFFICIENT_DATA,
            }
        )

    def metric_values(self, metric_name: str) -> tuple[float | int, ...]:
        values: list[float | int] = []

        for result in self.scenario_results:
            value = result.metric_value(metric_name)

            if value is not None:
                values.append(value)

        return tuple(values)

    def metric_summary(self, metric_name: str) -> dict[str, float | int | None]:
        values = self.metric_values(metric_name)

        if not values:
            return {
                "count": 0,
                "min": None,
                "max": None,
                "mean": None,
            }

        return {
            "count": len(values),
            "min": min(values),
            "max": max(values),
            "mean": sum(values) / len(values),
        }

    def summary(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "scenario_count": len(self.scenario_results),
            "passed_count": sum(result.passed for result in self.scenario_results),
            "failed_count": sum(result.failed for result in self.scenario_results),
            "insufficient_data_count": sum(
                result.insufficient_data for result in self.scenario_results
            ),
            "error_count": sum(result.errored for result in self.scenario_results),
            "pass_rate": self.pass_rate(),
            "metadata": dict(self.metadata),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "scenario_results": [
                result.to_dict() for result in self.scenario_results
            ],
            "metadata": dict(self.metadata),
        }


def run_robustness_checks(
    df: pl.DataFrame,
    scenarios: Iterable[RobustnessScenario],
    validation_kwargs: Mapping[str, Any] | None = None,
) -> RobustnessReport:
    scenario_tuple = tuple(scenarios)

    if not scenario_tuple:
        raise ValueError("At least one robustness scenario must be provided.")

    kwargs = dict(validation_kwargs or {})
    results: list[RobustnessScenarioResult] = []

    for scenario in scenario_tuple:
        results.append(
            run_robustness_scenario(
                df=df,
                scenario=scenario,
                validation_kwargs=kwargs,
            )
        )

    status = _derive_report_status(results)

    return RobustnessReport(
        status=status,
        scenario_results=tuple(results),
        metadata={
            "scenario_count": len(results),
            "validation_kwargs": kwargs,
        },
    )


def run_robustness_scenario(
    df: pl.DataFrame,
    scenario: RobustnessScenario,
    validation_kwargs: Mapping[str, Any] | None = None,
) -> RobustnessScenarioResult:
    kwargs = dict(validation_kwargs or {})

    try:
        output = scenario.run(df)
        report = validate_research_output(output, **kwargs)

        if report.status == ResearchValidationStatus.PASSED:
            status = RobustnessScenarioStatus.PASSED
        elif report.status == ResearchValidationStatus.INSUFFICIENT_DATA:
            status = RobustnessScenarioStatus.INSUFFICIENT_DATA
        else:
            status = RobustnessScenarioStatus.FAILED

        return RobustnessScenarioResult(
            scenario=scenario,
            status=status,
            validation_report=report,
            input_rows=df.height,
            output_rows=output.height,
        )

    except Exception as exc:
        return RobustnessScenarioResult(
            scenario=scenario,
            status=RobustnessScenarioStatus.ERROR,
            validation_report=None,
            input_rows=df.height,
            output_rows=0,
            error=str(exc),
        )


def identity_scenario(
    name: str = "base_sample",
) -> RobustnessScenario:
    return RobustnessScenario(
        name=name,
        transform=lambda df: df,
        description="Use the full input sample without modification.",
        tags=("base",),
    )


def date_range_scenario(
    name: str,
    start_date: str | None = None,
    end_date: str | None = None,
    date_column: str = "date",
) -> RobustnessScenario:
    if start_date is None and end_date is None:
        raise ValueError("At least one of start_date or end_date must be provided.")

    def transform(df: pl.DataFrame) -> pl.DataFrame:
        result = df

        if start_date is not None:
            result = result.filter(pl.col(date_column) >= start_date)

        if end_date is not None:
            result = result.filter(pl.col(date_column) <= end_date)

        return result

    return RobustnessScenario(
        name=name,
        transform=transform,
        description="Filter the research output to a specific date range.",
        required_columns=(date_column,),
        tags=("date_range",),
        metadata={
            "start_date": start_date,
            "end_date": end_date,
            "date_column": date_column,
        },
    )


def universe_scenario(
    name: str,
    symbols: Iterable[str],
    symbol_column: str = "symbol",
) -> RobustnessScenario:
    symbol_tuple = _clean_string_tuple(symbols, "symbols")

    if not symbol_tuple:
        raise ValueError("At least one symbol must be provided.")

    def transform(df: pl.DataFrame) -> pl.DataFrame:
        return df.filter(pl.col(symbol_column).is_in(list(symbol_tuple)))

    return RobustnessScenario(
        name=name,
        transform=transform,
        description="Filter the research output to a universe subset.",
        required_columns=(symbol_column,),
        tags=("universe",),
        metadata={
            "symbols": list(symbol_tuple),
            "symbol_column": symbol_column,
        },
    )


def numeric_perturbation_scenario(
    name: str,
    column: str,
    multiplier: float = 1.0,
    offset: float = 0.0,
    output_column: str | None = None,
) -> RobustnessScenario:
    if multiplier == 1.0 and offset == 0.0:
        raise ValueError("Perturbation must change the column.")

    input_column = column.strip()
    perturbed_column = output_column.strip() if output_column is not None else input_column

    def transform(df: pl.DataFrame) -> pl.DataFrame:
        return df.with_columns(
            ((pl.col(input_column) * multiplier) + offset).alias(perturbed_column)
        )

    return RobustnessScenario(
        name=name,
        transform=transform,
        description="Apply a deterministic numeric perturbation to a column.",
        required_columns=(input_column,),
        tags=("perturbation",),
        metadata={
            "column": input_column,
            "output_column": perturbed_column,
            "multiplier": multiplier,
            "offset": offset,
        },
    )


def _derive_report_status(
    results: Iterable[RobustnessScenarioResult],
) -> RobustnessReportStatus:
    result_tuple = tuple(results)

    if all(result.passed for result in result_tuple):
        return RobustnessReportStatus.PASSED

    if all(result.insufficient_data for result in result_tuple):
        return RobustnessReportStatus.INSUFFICIENT_DATA

    if all(result.failed or result.errored for result in result_tuple):
        return RobustnessReportStatus.FAILED

    return RobustnessReportStatus.MIXED


def _require_columns(
    df: pl.DataFrame,
    columns: Iterable[str],
    context: str,
) -> None:
    missing = [column for column in columns if column not in df.columns]

    if missing:
        raise ValueError(
            f"{context} missing required columns: {', '.join(missing)}"
        )


def _clean_string_tuple(
    values: Iterable[str],
    field_name: str,
) -> tuple[str, ...]:
    cleaned = tuple(str(value).strip() for value in values)

    if any(not value for value in cleaned):
        raise ValueError(f"{field_name} cannot contain empty values.")

    return cleaned
