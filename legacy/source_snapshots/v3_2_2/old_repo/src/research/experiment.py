from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import polars as pl


DataFrameTransform = Callable[[pl.DataFrame], pl.DataFrame]


class ResearchExperimentStatus(str, Enum):
    DRAFT = "draft"
    READY = "ready"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class ExperimentValidationIssue:
    field: str
    message: str


@dataclass(frozen=True)
class ExperimentValidationResult:
    passed: bool
    issues: tuple[ExperimentValidationIssue, ...] = field(default_factory=tuple)

    @property
    def failed(self) -> bool:
        return not self.passed


@dataclass(frozen=True)
class ResearchExperiment:
    name: str
    hypothesis_name: str
    input_columns: tuple[str, ...]
    signal_column: str = "signal"
    date_column: str = "date"
    symbol_column: str = "symbol"
    target_column: str | None = None
    universe: tuple[str, ...] = field(default_factory=tuple)
    start_date: str | None = None
    end_date: str | None = None
    status: ResearchExperimentStatus | str = ResearchExperimentStatus.DRAFT
    tags: tuple[str, ...] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", self.name.strip())
        object.__setattr__(self, "hypothesis_name", self.hypothesis_name.strip())
        object.__setattr__(
            self,
            "input_columns",
            _clean_string_tuple(self.input_columns, "input_columns"),
        )
        object.__setattr__(self, "signal_column", self.signal_column.strip())
        object.__setattr__(self, "date_column", self.date_column.strip())
        object.__setattr__(self, "symbol_column", self.symbol_column.strip())
        object.__setattr__(
            self,
            "target_column",
            self.target_column.strip() if self.target_column is not None else None,
        )
        object.__setattr__(
            self,
            "universe",
            _clean_string_tuple(self.universe, "universe"),
        )
        object.__setattr__(
            self,
            "status",
            _coerce_enum(self.status, ResearchExperimentStatus, "status"),
        )
        object.__setattr__(
            self,
            "tags",
            _clean_string_tuple(self.tags, "tags"),
        )
        object.__setattr__(self, "metadata", dict(self.metadata))

        validation = validate_experiment(self)
        if validation.failed:
            messages = "; ".join(issue.message for issue in validation.issues)
            raise ValueError(f"Invalid research experiment: {messages}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "hypothesis_name": self.hypothesis_name,
            "input_columns": list(self.input_columns),
            "signal_column": self.signal_column,
            "date_column": self.date_column,
            "symbol_column": self.symbol_column,
            "target_column": self.target_column,
            "universe": list(self.universe),
            "start_date": self.start_date,
            "end_date": self.end_date,
            "status": self.status.value,
            "tags": list(self.tags),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ResearchExperiment":
        return cls(
            name=payload["name"],
            hypothesis_name=payload["hypothesis_name"],
            input_columns=tuple(payload.get("input_columns", ())),
            signal_column=payload.get("signal_column", "signal"),
            date_column=payload.get("date_column", "date"),
            symbol_column=payload.get("symbol_column", "symbol"),
            target_column=payload.get("target_column"),
            universe=tuple(payload.get("universe", ())),
            start_date=payload.get("start_date"),
            end_date=payload.get("end_date"),
            status=payload.get("status", ResearchExperimentStatus.DRAFT),
            tags=tuple(payload.get("tags", ())),
            metadata=dict(payload.get("metadata", {})),
        )


@dataclass(frozen=True)
class ExperimentRunResult:
    experiment: ResearchExperiment
    output: pl.DataFrame
    input_rows: int
    output_rows: int
    active_signal_count: int
    long_signal_count: int
    short_signal_count: int
    neutral_signal_count: int
    status: ResearchExperimentStatus = ResearchExperimentStatus.COMPLETED
    metrics: Mapping[str, Any] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        return {
            "experiment_name": self.experiment.name,
            "hypothesis_name": self.experiment.hypothesis_name,
            "status": self.status.value,
            "input_rows": self.input_rows,
            "output_rows": self.output_rows,
            "active_signal_count": self.active_signal_count,
            "long_signal_count": self.long_signal_count,
            "short_signal_count": self.short_signal_count,
            "neutral_signal_count": self.neutral_signal_count,
            "metrics": dict(self.metrics),
        }


def validate_experiment(
    experiment: ResearchExperiment,
) -> ExperimentValidationResult:
    issues: list[ExperimentValidationIssue] = []

    if not experiment.name:
        issues.append(
            ExperimentValidationIssue(
                field="name",
                message="Experiment name cannot be empty.",
            )
        )

    if not experiment.hypothesis_name:
        issues.append(
            ExperimentValidationIssue(
                field="hypothesis_name",
                message="Hypothesis name cannot be empty.",
            )
        )

    if not experiment.input_columns:
        issues.append(
            ExperimentValidationIssue(
                field="input_columns",
                message="At least one input column must be provided.",
            )
        )

    if len(set(experiment.input_columns)) != len(experiment.input_columns):
        issues.append(
            ExperimentValidationIssue(
                field="input_columns",
                message="Input columns cannot contain duplicates.",
            )
        )

    if not experiment.signal_column:
        issues.append(
            ExperimentValidationIssue(
                field="signal_column",
                message="Signal column cannot be empty.",
            )
        )

    if not experiment.date_column:
        issues.append(
            ExperimentValidationIssue(
                field="date_column",
                message="Date column cannot be empty.",
            )
        )

    if not experiment.symbol_column:
        issues.append(
            ExperimentValidationIssue(
                field="symbol_column",
                message="Symbol column cannot be empty.",
            )
        )

    if len(set(experiment.universe)) != len(experiment.universe):
        issues.append(
            ExperimentValidationIssue(
                field="universe",
                message="Universe cannot contain duplicate symbols.",
            )
        )

    if len(set(experiment.tags)) != len(experiment.tags):
        issues.append(
            ExperimentValidationIssue(
                field="tags",
                message="Tags cannot contain duplicates.",
            )
        )

    if (
        experiment.start_date is not None
        and experiment.end_date is not None
        and experiment.start_date > experiment.end_date
    ):
        issues.append(
            ExperimentValidationIssue(
                field="date_range",
                message="Start date cannot be after end date.",
            )
        )

    return ExperimentValidationResult(
        passed=len(issues) == 0,
        issues=tuple(issues),
    )


def prepare_experiment_input(
    df: pl.DataFrame,
    experiment: ResearchExperiment,
) -> pl.DataFrame:
    required_columns = set(experiment.input_columns)
    required_columns.add(experiment.date_column)
    required_columns.add(experiment.symbol_column)

    if experiment.target_column is not None:
        required_columns.add(experiment.target_column)

    _require_columns(df, sorted(required_columns), context=experiment.name)

    result = df

    if experiment.universe:
        result = result.filter(
            pl.col(experiment.symbol_column).is_in(list(experiment.universe))
        )

    if experiment.start_date is not None:
        result = result.filter(pl.col(experiment.date_column) >= experiment.start_date)

    if experiment.end_date is not None:
        result = result.filter(pl.col(experiment.date_column) <= experiment.end_date)

    return result


def run_research_experiment(
    df: pl.DataFrame,
    experiment: ResearchExperiment,
    factor_steps: Iterable[DataFrameTransform] = (),
    signal_steps: Iterable[DataFrameTransform] = (),
) -> ExperimentRunResult:
    prepared = prepare_experiment_input(df, experiment)
    result = prepared

    for step in factor_steps:
        result = step(result)

    for step in signal_steps:
        result = step(result)

    _require_columns(
        result,
        [experiment.signal_column],
        context=f"{experiment.name} output",
    )

    return ExperimentRunResult(
        experiment=ResearchExperiment(
            **{
                **experiment.to_dict(),
                "status": ResearchExperimentStatus.COMPLETED,
            }
        ),
        output=result,
        input_rows=prepared.height,
        output_rows=result.height,
        active_signal_count=result.filter(pl.col(experiment.signal_column) != 0).height,
        long_signal_count=result.filter(pl.col(experiment.signal_column) > 0).height,
        short_signal_count=result.filter(pl.col(experiment.signal_column) < 0).height,
        neutral_signal_count=result.filter(pl.col(experiment.signal_column) == 0).height,
        metrics=_build_basic_metrics(result, experiment),
    )


def _build_basic_metrics(
    df: pl.DataFrame,
    experiment: ResearchExperiment,
) -> dict[str, Any]:
    metrics: dict[str, Any] = {}

    signal_column = experiment.signal_column
    target_column = experiment.target_column

    if target_column is None or target_column not in df.columns:
        return metrics

    active = df.filter(pl.col(signal_column) != 0)

    metrics["active_rows"] = active.height

    if active.height == 0:
        metrics["average_active_target"] = None
        metrics["average_signed_target"] = None
        return metrics

    metrics["average_active_target"] = active.select(
        pl.col(target_column).mean()
    ).item()

    metrics["average_signed_target"] = active.select(
        (pl.col(signal_column) * pl.col(target_column)).mean()
    ).item()

    return metrics


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


def _coerce_enum(value: Any, enum_type: type[Enum], field_name: str) -> Enum:
    if isinstance(value, enum_type):
        return value

    try:
        return enum_type(value)
    except ValueError as exc:
        allowed = ", ".join(member.value for member in enum_type)
        raise ValueError(
            f"Invalid {field_name}: {value!r}. Allowed values: {allowed}"
        ) from exc


def _clean_string_tuple(
    values: Iterable[str],
    field_name: str,
) -> tuple[str, ...]:
    cleaned = tuple(str(value).strip() for value in values)

    if any(not value for value in cleaned):
        raise ValueError(f"{field_name} cannot contain empty values.")

    return cleaned
