from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

import polars as pl

from src.research.experiment import (
    ExperimentRunResult,
    ResearchExperiment,
    run_research_experiment,
)
from src.research.research_score import (
    ResearchScoreReport,
    score_research,
)
from src.research.robustness import (
    RobustnessReport,
    RobustnessScenario,
    run_robustness_checks,
)
from src.research.validation import (
    ResearchValidationReport,
    validate_research_output,
)
from src.research.walk_forward import (
    WalkForwardMode,
    WalkForwardReport,
    WalkForwardWindow,
    run_walk_forward_validation,
    run_walk_forward_validation_from_frame,
)
from src.research.factor_library import (
    apply_factors,
    default_factor_library,
)
from src.research.signals import (
    apply_signal_rules,
    default_signal_rules,
)
from src.research.research_diagnostics import (
    ResearchDiagnosticsReport,
    run_research_diagnostics,
)

DataFrameTransform = Callable[[pl.DataFrame], pl.DataFrame]


@dataclass(frozen=True)
class ResearchEvaluationPipelineConfig:
    experiment: ResearchExperiment
    factor_steps: tuple[DataFrameTransform, ...] = field(default_factory=tuple)
    signal_steps: tuple[DataFrameTransform, ...] = field(default_factory=tuple)

    use_default_factors: bool = False
    use_default_signal_rules: bool = False
    run_diagnostics: bool = True

    validation_kwargs: Mapping[str, Any] = field(default_factory=dict)

    robustness_scenarios: tuple[RobustnessScenario, ...] = field(default_factory=tuple)
    robustness_validation_kwargs: Mapping[str, Any] | None = None

    run_walk_forward: bool = False
    walk_forward_windows: tuple[WalkForwardWindow, ...] = field(default_factory=tuple)
    walk_forward_validation_kwargs: Mapping[str, Any] | None = None
    walk_forward_train_size: int = 60
    walk_forward_test_size: int = 20
    walk_forward_step_size: int | None = None
    walk_forward_mode: WalkForwardMode | str = WalkForwardMode.ROLLING

    score_kwargs: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "factor_steps", tuple(self.factor_steps))
        object.__setattr__(self, "signal_steps", tuple(self.signal_steps))
        object.__setattr__(
            self,
            "robustness_scenarios",
            tuple(self.robustness_scenarios),
        )
        object.__setattr__(
            self,
            "walk_forward_windows",
            tuple(self.walk_forward_windows),
        )
        object.__setattr__(self, "validation_kwargs", dict(self.validation_kwargs))
        object.__setattr__(
            self,
            "robustness_validation_kwargs",
            (
                dict(self.robustness_validation_kwargs)
                if self.robustness_validation_kwargs is not None
                else None
            ),
        )
        object.__setattr__(
            self,
            "walk_forward_validation_kwargs",
            (
                dict(self.walk_forward_validation_kwargs)
                if self.walk_forward_validation_kwargs is not None
                else None
            ),
        )
        object.__setattr__(self, "score_kwargs", dict(self.score_kwargs))
        object.__setattr__(self, "metadata", dict(self.metadata))

        if not isinstance(self.experiment, ResearchExperiment):
            raise TypeError("experiment must be a ResearchExperiment.")

        for step in self.factor_steps:
            if not callable(step):
                raise TypeError("All factor_steps must be callable.")

        for step in self.signal_steps:
            if not callable(step):
                raise TypeError("All signal_steps must be callable.")

        if self.walk_forward_train_size <= 0:
            raise ValueError("walk_forward_train_size must be greater than zero.")

        if self.walk_forward_test_size <= 0:
            raise ValueError("walk_forward_test_size must be greater than zero.")

        if (
            self.walk_forward_step_size is not None
            and self.walk_forward_step_size <= 0
        ):
            raise ValueError(
                "walk_forward_step_size must be greater than zero when provided."
            )


@dataclass(frozen=True)
class ResearchEvaluationPipelineResult:
    config: ResearchEvaluationPipelineConfig
    experiment_result: ExperimentRunResult
    validation_report: ResearchValidationReport
    score_report: ResearchScoreReport
    robustness_report: RobustnessReport | None = None
    walk_forward_report: WalkForwardReport | None = None
    diagnostics_report: ResearchDiagnosticsReport | None = None
    research_output: Mapping[str, Any] = field(default_factory=dict)

    @property
    def output(self) -> pl.DataFrame:
        return self.experiment_result.output

    @property
    def promoted(self) -> bool:
        return self.score_report.promoted

    @property
    def decision(self) -> str:
        return self.score_report.decision.value

    def summary(self) -> dict[str, Any]:
        return {
            "experiment": self.experiment_result.summary(),
            "validation_status": self.validation_report.status.value,
            "score": self.score_report.score,
            "decision": self.score_report.decision.value,
            "promoted": self.score_report.promoted,
            "robustness": (
                self.robustness_report.summary()
                if self.robustness_report is not None
                else None
            ),
            "walk_forward": (
                self.walk_forward_report.summary()
                if self.walk_forward_report is not None
                else None
            ),
            "diagnostics": (
                self.diagnostics_report.to_dict()
                if self.diagnostics_report is not None
                else None
            ),
            "metadata": dict(self.config.metadata),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary(),
            "validation_report": self.validation_report.to_dict(),
            "score_report": self.score_report.to_dict(),
            "robustness_report": (
                self.robustness_report.to_dict()
                if self.robustness_report is not None
                else None
            ),
            "walk_forward_report": (
                self.walk_forward_report.to_dict()
                if self.walk_forward_report is not None
                else None
            ),
            "research_output": dict(self.research_output),
            "diagnostics_report": (
                self.diagnostics_report.to_dict()
                if self.diagnostics_report is not None
                else None
            ),
        }


def run_research_evaluation_pipeline(
    df: pl.DataFrame,
    config: ResearchEvaluationPipelineConfig,
) -> ResearchEvaluationPipelineResult:
    factor_steps = _build_factor_steps(config)
    signal_steps = _build_signal_steps(config)
    experiment_result = run_research_experiment(
        df=df,
        experiment=config.experiment,
        factor_steps=factor_steps,
        signal_steps=signal_steps,
    )

    output = experiment_result.output

    validation_kwargs = _build_validation_kwargs(
        experiment=config.experiment,
        override_kwargs=config.validation_kwargs,
    )

    validation_report = validate_research_output(
        output,
        **validation_kwargs,
    )

    robustness_report = None
    if config.robustness_scenarios:
        robustness_kwargs = _build_validation_kwargs(
            experiment=config.experiment,
            override_kwargs=(
                config.robustness_validation_kwargs
                if config.robustness_validation_kwargs is not None
                else config.validation_kwargs
            ),
        )

        robustness_report = run_robustness_checks(
            df=output,
            scenarios=config.robustness_scenarios,
            validation_kwargs=robustness_kwargs,
        )

    walk_forward_report = None
    if config.walk_forward_windows:
        walk_forward_kwargs = _build_validation_kwargs(
            experiment=config.experiment,
            override_kwargs=(
                config.walk_forward_validation_kwargs
                if config.walk_forward_validation_kwargs is not None
                else config.validation_kwargs
            ),
        )

        walk_forward_report = run_walk_forward_validation(
            df=output,
            windows=config.walk_forward_windows,
            validation_kwargs=walk_forward_kwargs,
            date_column=config.experiment.date_column,
        )

    elif config.run_walk_forward:
        walk_forward_kwargs = _build_validation_kwargs(
            experiment=config.experiment,
            override_kwargs=(
                config.walk_forward_validation_kwargs
                if config.walk_forward_validation_kwargs is not None
                else config.validation_kwargs
            ),
        )

        walk_forward_report = run_walk_forward_validation_from_frame(
            df=output,
            date_column=config.experiment.date_column,
            train_size=config.walk_forward_train_size,
            test_size=config.walk_forward_test_size,
            step_size=config.walk_forward_step_size,
            mode=config.walk_forward_mode,
            validation_kwargs=walk_forward_kwargs,
        )

    score_report = score_research(
        validation_report=validation_report,
        robustness_report=robustness_report,
        walk_forward_report=walk_forward_report,
        **dict(config.score_kwargs),
    )

    research_output = build_research_evaluation_output(
        output=output,
        validation_report=validation_report,
        score_report=score_report,
        experiment=config.experiment,
        robustness_report=robustness_report,
        walk_forward_report=walk_forward_report,
        metadata=config.metadata,
    )
    
    diagnostics_report = (
        run_research_diagnostics(research_output)
        if config.run_diagnostics
        else None
    )

    return ResearchEvaluationPipelineResult(
        config=config,
        experiment_result=experiment_result,
        validation_report=validation_report,
        robustness_report=robustness_report,
        walk_forward_report=walk_forward_report,
        diagnostics_report=diagnostics_report,
        score_report=score_report,
        research_output=research_output,
    )


def run_research_evaluation_pipeline_from_parts(
    df: pl.DataFrame,
    experiment: ResearchExperiment,
    factor_steps: Iterable[DataFrameTransform] = (),
    signal_steps: Iterable[DataFrameTransform] = (),
    validation_kwargs: Mapping[str, Any] | None = None,
    robustness_scenarios: Iterable[RobustnessScenario] = (),
    robustness_validation_kwargs: Mapping[str, Any] | None = None,
    run_walk_forward: bool = False,
    walk_forward_windows: Iterable[WalkForwardWindow] = (),
    walk_forward_validation_kwargs: Mapping[str, Any] | None = None,
    walk_forward_train_size: int = 60,
    walk_forward_test_size: int = 20,
    walk_forward_step_size: int | None = None,
    walk_forward_mode: WalkForwardMode | str = WalkForwardMode.ROLLING,
    score_kwargs: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
    use_default_factors: bool = False,
    use_default_signal_rules: bool = False,
    run_diagnostics: bool = True,
) -> ResearchEvaluationPipelineResult:
    config = ResearchEvaluationPipelineConfig(
        experiment=experiment,
        factor_steps=tuple(factor_steps),
        signal_steps=tuple(signal_steps),
        validation_kwargs=dict(validation_kwargs or {}),
        robustness_scenarios=tuple(robustness_scenarios),
        robustness_validation_kwargs=robustness_validation_kwargs,
        run_walk_forward=run_walk_forward,
        walk_forward_windows=tuple(walk_forward_windows),
        walk_forward_validation_kwargs=walk_forward_validation_kwargs,
        walk_forward_train_size=walk_forward_train_size,
        walk_forward_test_size=walk_forward_test_size,
        walk_forward_step_size=walk_forward_step_size,
        walk_forward_mode=walk_forward_mode,
        score_kwargs=dict(score_kwargs or {}),
        metadata=dict(metadata or {}),
        use_default_factors=use_default_factors,
        use_default_signal_rules=use_default_signal_rules,
        run_diagnostics=run_diagnostics,
    )

    return run_research_evaluation_pipeline(df=df, config=config)

def _build_factor_steps(
    config: ResearchEvaluationPipelineConfig,
) -> tuple[DataFrameTransform, ...]:
    steps: list[DataFrameTransform] = []

    if config.use_default_factors:
        steps.append(
            lambda frame: apply_factors(
                frame,
                default_factor_library(),
            )
        )

    steps.extend(config.factor_steps)

    return tuple(steps)


def _build_signal_steps(
    config: ResearchEvaluationPipelineConfig,
) -> tuple[DataFrameTransform, ...]:
    steps: list[DataFrameTransform] = []

    if config.use_default_signal_rules:
        steps.append(
            lambda frame: apply_signal_rules(
                frame,
                default_signal_rules(),
            )
        )

    steps.extend(config.signal_steps)

    return tuple(steps)

def _existing_columns(
    df: pl.DataFrame,
    columns: Iterable[str],
) -> list[str]:
    return [column for column in columns if column in df.columns]


def _columns_matching_suffix(
    df: pl.DataFrame,
    suffixes: tuple[str, ...],
) -> list[str]:
    return [
        column
        for column in df.columns
        if column.endswith(suffixes)
    ]


def _columns_containing(
    df: pl.DataFrame,
    terms: tuple[str, ...],
) -> list[str]:
    return [
        column
        for column in df.columns
        if any(term in column for term in terms)
    ]


def _records_for_columns(
    df: pl.DataFrame,
    columns: Iterable[str],
) -> list[dict[str, Any]]:
    selected_columns = _existing_columns(df, columns)

    if not selected_columns:
        return []

    return df.select(selected_columns).to_dicts()


def _factor_output_columns(
    output: pl.DataFrame,
    date_column: str,
    symbol_column: str,
) -> list[str]:
    identifier_columns = _existing_columns(output, [date_column, symbol_column])

    factor_columns = _columns_matching_suffix(
        output,
        ("_factor",),
    )

    optional_research_columns = _existing_columns(
        output,
        [
            "forward_return",
            "forward_return_1d",
            "forward_return_5d",
            "forward_return_21d",
        ],
    )

    return list(dict.fromkeys(identifier_columns + factor_columns + optional_research_columns))


def _signal_output_columns(
    output: pl.DataFrame,
    date_column: str,
    symbol_column: str,
    signal_column: str,
) -> list[str]:
    identifier_columns = _existing_columns(output, [date_column, symbol_column])

    signal_columns = _columns_containing(
        output,
        ("signal",),
    )

    signal_columns.extend(_existing_columns(output, [signal_column]))

    return list(dict.fromkeys(identifier_columns + signal_columns))


def _portfolio_target_output_columns(
    output: pl.DataFrame,
    date_column: str,
    symbol_column: str,
) -> list[str]:
    identifier_columns = _existing_columns(output, [date_column, symbol_column])

    target_columns = _existing_columns(
        output,
        [
            "target_weight",
            "weight",
            "position",
            "side",
            "quantity",
        ],
    )

    return list(dict.fromkeys(identifier_columns + target_columns))

def build_research_evaluation_output(
    output: pl.DataFrame,
    validation_report: ResearchValidationReport,
    score_report: ResearchScoreReport,
    experiment: ResearchExperiment,
    robustness_report: RobustnessReport | None = None,
    walk_forward_report: WalkForwardReport | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    factor_columns = _factor_output_columns(
        output=output,
        date_column=experiment.date_column,
        symbol_column=experiment.symbol_column,
    )

    signal_columns = _signal_output_columns(
        output=output,
        date_column=experiment.date_column,
        symbol_column=experiment.symbol_column,
        signal_column=experiment.signal_column,
    )

    portfolio_target_columns = _portfolio_target_output_columns(
        output=output,
        date_column=experiment.date_column,
        symbol_column=experiment.symbol_column,
    )

    research_output: dict[str, Any] = {
        "output_rows": output.height,
        "output_columns": output.columns,
        "validation_status": validation_report.status.value,
        "score": score_report.score,
        "decision": score_report.decision.value,
        "promoted": score_report.promoted,
        "has_robustness_report": robustness_report is not None,
        "has_walk_forward_report": walk_forward_report is not None,
        "metadata": dict(metadata or {}),
        "factors": _records_for_columns(output, factor_columns),
        "signals": _records_for_columns(output, signal_columns),
    }

    portfolio_targets = _records_for_columns(output, portfolio_target_columns)

    if portfolio_targets:
        research_output["portfolio_targets"] = portfolio_targets

    return research_output

def _build_validation_kwargs(
    experiment: ResearchExperiment,
    override_kwargs: Mapping[str, Any],
) -> dict[str, Any]:
    kwargs = dict(override_kwargs)

    kwargs.setdefault("signal_column", experiment.signal_column)

    if experiment.target_column is not None:
        kwargs.setdefault("target_column", experiment.target_column)

    kwargs.setdefault("date_column", experiment.date_column)
    kwargs.setdefault("symbol_column", experiment.symbol_column)

    return kwargs
