from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

import polars as pl

from src.research.evaluation_operation import (
    ResearchEvaluationOperationConfig,
    ResearchEvaluationOperationResult,
    run_research_evaluation_operation,
)
from src.research.operation_log import (
    ResearchOperationLogConfig,
    ResearchOperationLogWriteResult,
    append_research_operation_record,
)
from src.research.operation_record import (
    ResearchOperationRecord,
    ResearchOperationRecordConfig,
    ResearchOperationRecordValidationResult,
    build_research_operation_record,
    enforce_research_operation_record,
    validate_research_operation_record,
)
from src.research.operation_health import (
    ResearchOperationHealthConfig,
    ResearchOperationHealthResult,
    enforce_research_operation_health,
    evaluate_research_operation_log_health,
    evaluate_research_operation_records_health,
)
from src.research.backtest_attachment import (
    MinimalBacktestFixture,
    ResearchBacktestAttachment,
    ResearchBacktestHandoffResult,
    build_research_backtest_attachment,
    run_research_to_backtest_validation,
)
from src.research.model_readiness import (
    ModelReadinessConfig,
    ModelReadinessReport,
    evaluate_model_readiness,
)
from src.research.model_comparison import build_model_comparison_summary
from src.research.experiment_regression import compare_experiment_runs

@dataclass(frozen=True)
class ResearchOperationRunnerConfig:
    operation_config: ResearchEvaluationOperationConfig
    record_config: ResearchOperationRecordConfig = field(
        default_factory=ResearchOperationRecordConfig
    )
    log_config: ResearchOperationLogConfig | None = None
    health_config: ResearchOperationHealthConfig | None = None
    enforce_record: bool = True
    require_passed_record: bool = False
    enforce_health: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)
    attach_backtest_report: bool = False
    attach_backtest_handoff: bool = False
    backtest_handoff_runner: Callable[[MinimalBacktestFixture], Any] | None = None
    backtest_prices: pl.DataFrame | None = None
    backtest_initial_cash: float = 100_000.0
    backtest_rebalance_frequency: str = "daily"
    backtest_price_column: str = "close"
    backtest_date_column: str = "date"
    backtest_symbol_column: str = "symbol"
    backtest_drift_threshold: float | None = None
    backtest_metadata: Mapping[str, Any] = field(default_factory=dict)
    attach_model_readiness_report: bool = False
    model_readiness_config: ModelReadinessConfig = field(
        default_factory=ModelReadinessConfig
    )
    attach_model_quality_report: bool = False
    attach_model_testing_summary: bool = False
    model_testing_summary: Mapping[str, Any] | None = None
    attach_experiment_regression_report: bool = False
    baseline_experiment_summary: Mapping[str, Any] | None = None
    current_experiment_summary: Mapping[str, Any] | None = None
    experiment_regression_report: Mapping[str, Any] | None = None
    max_allowed_quality_score_degradation: float = 0.05
    fail_on_experiment_rank_change: bool = False
    
    def __post_init__(self) -> None:
        if not isinstance(self.operation_config, ResearchEvaluationOperationConfig):
            raise TypeError(
                "operation_config must be a ResearchEvaluationOperationConfig."
            )

        if not isinstance(self.record_config, ResearchOperationRecordConfig):
            raise TypeError("record_config must be a ResearchOperationRecordConfig.")

        if self.log_config is not None and not isinstance(
            self.log_config,
            ResearchOperationLogConfig,
        ):
            raise TypeError("log_config must be a ResearchOperationLogConfig.")

        if self.health_config is not None and not isinstance(
            self.health_config,
            ResearchOperationHealthConfig,
        ):
            raise TypeError("health_config must be a ResearchOperationHealthConfig.")

        object.__setattr__(self, "metadata", dict(self.metadata))

        if self.attach_backtest_report and self.backtest_prices is None:
            raise ValueError(
                "backtest_prices is required when attach_backtest_report=True."
            )

        if (
            self.attach_backtest_handoff
            and self.backtest_handoff_runner is None
            and self.backtest_prices is None
        ):
            raise ValueError(
                "backtest_prices or backtest_handoff_runner is required when "
                "attach_backtest_handoff=True."
            )

        if (
            self.backtest_handoff_runner is not None
            and not callable(self.backtest_handoff_runner)
        ):
            raise TypeError("backtest_handoff_runner must be callable.")

        if self.backtest_prices is not None and not isinstance(
            self.backtest_prices,
            pl.DataFrame,
        ):
            raise TypeError("backtest_prices must be a polars DataFrame.")

        object.__setattr__(
            self,
            "backtest_metadata",
            dict(self.backtest_metadata),
        )
        
        if not isinstance(self.model_readiness_config, ModelReadinessConfig):
            raise TypeError(
                "model_readiness_config must be a ModelReadinessConfig."
            )

        if self.model_testing_summary is not None and not isinstance(
            self.model_testing_summary,
            Mapping,
        ):
            raise TypeError("model_testing_summary must be a mapping.")

        if self.model_testing_summary is not None:
            object.__setattr__(
                self,
                "model_testing_summary",
                dict(self.model_testing_summary),
            )

        if self.baseline_experiment_summary is not None and not isinstance(
            self.baseline_experiment_summary,
            Mapping,
        ):
            raise TypeError("baseline_experiment_summary must be a mapping.")

        if self.current_experiment_summary is not None and not isinstance(
            self.current_experiment_summary,
            Mapping,
        ):
            raise TypeError("current_experiment_summary must be a mapping.")

        if self.experiment_regression_report is not None and not isinstance(
            self.experiment_regression_report,
            Mapping,
        ):
            raise TypeError("experiment_regression_report must be a mapping.")

        if self.max_allowed_quality_score_degradation < 0:
            raise ValueError(
                "max_allowed_quality_score_degradation cannot be negative."
            )

        if self.baseline_experiment_summary is not None:
            object.__setattr__(
                self,
                "baseline_experiment_summary",
                dict(self.baseline_experiment_summary),
            )

        if self.current_experiment_summary is not None:
            object.__setattr__(
                self,
                "current_experiment_summary",
                dict(self.current_experiment_summary),
            )

        if self.experiment_regression_report is not None:
            object.__setattr__(
                self,
                "experiment_regression_report",
                dict(self.experiment_regression_report),
            )

@dataclass(frozen=True)
class ResearchOperationRunnerResult:
    operation_result: ResearchEvaluationOperationResult
    record: ResearchOperationRecord
    record_validation: ResearchOperationRecordValidationResult
    log_write_result: ResearchOperationLogWriteResult | None = None
    health_result: ResearchOperationHealthResult | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    backtest_attachment: ResearchBacktestAttachment | None = None
    backtest_handoff_result: ResearchBacktestHandoffResult | None = None
    model_readiness_report: ModelReadinessReport | None = None
    model_quality_report: Any | None = None
    model_testing_summary: Mapping[str, Any] | None = None
    experiment_regression_report: Mapping[str, Any] | None = None
        
    @property
    def passed(self) -> bool:
        health_passed = (
            self.health_result.passed
            if self.health_result is not None
            else True
        )
        backtest_handoff_passed = (
            self.backtest_handoff_result.passed
            if self.backtest_handoff_result is not None
            else True
        )

        return (
            self.operation_result.passed
            and self.record_validation.passed
            and health_passed
            and backtest_handoff_passed
        )

    @property
    def logged(self) -> bool:
        return self.log_write_result is not None

    @property
    def health_checked(self) -> bool:
        return self.health_result is not None

    def summary(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "logged": self.logged,
            "health_checked": self.health_checked,
            "operation": self.operation_result.summary(),
            "record": self.record.to_dict(),
            "record_validation": self.record_validation.to_dict(),
            "log_write": (
                self.log_write_result.to_dict()
                if self.log_write_result is not None
                else None
            ),
            "health": (
                self.health_result.to_dict()
                if self.health_result is not None
                else None
            ),
            "metadata": dict(self.metadata),
            "backtest_attachment": (
                self.backtest_attachment.to_dict()
                if self.backtest_attachment is not None
                else None
            ),
            "backtest_handoff_result": (
                self.backtest_handoff_result.to_dict()
                if self.backtest_handoff_result is not None
                else None
            ),
            "model_readiness_report": (
                self.model_readiness_report.to_dict()
                if self.model_readiness_report is not None
                else None
            ),
            "model_quality_report": _report_to_dict(self.model_quality_report),
            "model_testing_summary": (
                dict(self.model_testing_summary)
                if self.model_testing_summary is not None
                else None
            ),
            "experiment_regression_report": (
                dict(self.experiment_regression_report)
                if self.experiment_regression_report is not None
                else None
            ),
        }

    def to_dict(self) -> dict[str, Any]:
        return self.summary()


def run_logged_research_operation(
    df: pl.DataFrame,
    returns: pl.DataFrame,
    config: ResearchOperationRunnerConfig,
) -> ResearchOperationRunnerResult:
    if not isinstance(df, pl.DataFrame):
        raise TypeError("df must be a polars DataFrame.")

    if not isinstance(returns, pl.DataFrame):
        raise TypeError("returns must be a polars DataFrame.")

    operation_result = run_research_evaluation_operation(
        df=df,
        returns=returns,
        config=config.operation_config,
    )
    
    backtest_attachment = None
    backtest_handoff_result = None

    if config.attach_backtest_report:
        evaluation_result = getattr(operation_result, "evaluation_result", None)
        research_output = getattr(evaluation_result, "research_output", None)

        if research_output is None:
            raise ValueError(
                "Cannot attach backtest report because operation_result.evaluation_result.research_output is missing."
            )

        backtest_attachment = build_research_backtest_attachment(
            research_output=research_output,
            prices=config.backtest_prices,
            initial_cash=config.backtest_initial_cash,
            rebalance_frequency=config.backtest_rebalance_frequency,
            price_column=config.backtest_price_column,
            date_column=config.backtest_date_column,
            symbol_column=config.backtest_symbol_column,
            drift_threshold=config.backtest_drift_threshold,
            metadata={
                "source": "research_operation_runner",
                **dict(config.backtest_metadata),
            },
        )
        
    model_readiness_report = None

    if config.attach_model_readiness_report:
        evaluation_result = getattr(operation_result, "evaluation_result", None)
        research_output = getattr(evaluation_result, "research_output", None)

        if research_output is None:
            raise ValueError(
                "Cannot attach model readiness report because "
                "operation_result.evaluation_result.research_output is missing."
            )

        diagnostics_report = getattr(evaluation_result, "diagnostics_report", None)

        model_readiness_report = evaluate_model_readiness(
            evaluation_output=research_output,
            diagnostics_report=diagnostics_report,
            backtest_attachment=backtest_attachment,
            config=config.model_readiness_config,
        )

    model_quality_report = None

    if config.attach_model_quality_report:
        model_quality_report = _extract_model_quality_report(operation_result)

        if model_quality_report is None:
            raise ValueError(
                "Cannot attach model quality report because no model_quality_report "
                "was found on operation_result or operation_result.evaluation_result."
            )

    model_testing_summary = (
        dict(config.model_testing_summary)
        if config.model_testing_summary is not None
        else None
    )

    if config.attach_model_testing_summary and model_testing_summary is None:
        model_testing_summary = _extract_model_testing_summary(operation_result)

        if model_testing_summary is None:
            raise ValueError(
                "Cannot attach model testing summary because no model_testing_summary "
                "or model_comparison_report was found on operation_result or "
                "operation_result.evaluation_result."
            )

    if getattr(config, "attach_backtest_handoff", False):
        evaluation_result = getattr(operation_result, "evaluation_result", None)
        research_output = getattr(evaluation_result, "research_output", None)

        if research_output is None:
            raise ValueError(
                "Cannot attach backtest handoff because "
                "operation_result.evaluation_result.research_output is missing."
            )

        logged_operation_output = _build_backtest_handoff_operation_output(
            operation_result=operation_result,
            research_output=research_output,
            model_testing_summary=model_testing_summary,
            config=config,
        )
        handoff_runner = getattr(config, "backtest_handoff_runner", None) or (
            _build_default_backtest_handoff_runner(config)
        )
        backtest_handoff_result = run_research_to_backtest_validation(
            logged_operation_output=logged_operation_output,
            backtest_runner=handoff_runner,
        )

    experiment_regression_report = None

    if config.attach_experiment_regression_report:
        experiment_regression_report = _build_experiment_regression_report(
            operation_result=operation_result,
            model_testing_summary=model_testing_summary,
            config=config,
        )

    record = build_research_operation_record(
        operation_result=operation_result,
        config=config.record_config,
        backtest_attachment=backtest_attachment,
        backtest_handoff_result=backtest_handoff_result,
        model_readiness_report=model_readiness_report,
        model_quality_report=model_quality_report,
        model_testing_summary=model_testing_summary,
        experiment_regression_report=experiment_regression_report,
    )

    if config.enforce_record:
        record = enforce_research_operation_record(
            record=record,
            require_passed=config.require_passed_record,
        )

    record_validation = validate_research_operation_record(
        record=record,
        require_passed=config.require_passed_record,
    )

    log_write_result = None

    if config.log_config is not None:
        log_write_result = append_research_operation_record(
            record=record,
            config=config.log_config,
        )

    health_result = None

    if config.health_config is not None:
        if config.log_config is not None:
            health_result = evaluate_research_operation_log_health(
                path=str(config.log_config.path),
                config=config.health_config,
            )
        else:
            health_result = evaluate_research_operation_records_health(
                records=(
                    {
                        "record": record.to_dict(),
                    },
                ),
                config=config.health_config,
            )

        if config.enforce_health:
            health_result = enforce_research_operation_health(health_result)

    metadata = {
        "source": "logged_research_operation",
        "operation_status": operation_result.status.value,
        "record_status": record.status.value,
        "record_passed": record.passed,
        "record_validation_passed": record_validation.passed,
        "logged": log_write_result is not None,
        "health_checked": health_result is not None,
        "health_passed": (
            health_result.passed
            if health_result is not None
            else None
        ),
        "backtest_report_attached": backtest_attachment is not None,
        "backtest_attachment_passed": (
            backtest_attachment.passed
            if backtest_attachment is not None
            else None
        ),
        "backtest_handoff_attached": backtest_handoff_result is not None,
        "backtest_handoff_passed": (
            backtest_handoff_result.passed
            if backtest_handoff_result is not None
            else None
        ),
        "backtest_handoff_fixture_id": (
            backtest_handoff_result.fixture_id
            if backtest_handoff_result is not None
            else None
        ),
        "backtest_handoff_candidate_id": (
            backtest_handoff_result.candidate_id
            if backtest_handoff_result is not None
            else None
        ),
        "backtest_handoff_failure_count": _backtest_handoff_failure_count(
            backtest_handoff_result
        ),
        "backtest_handoff_failures": _backtest_handoff_failures(
            backtest_handoff_result
        ),
        "model_readiness_attached": model_readiness_report is not None,
        "model_readiness_passed": (
            model_readiness_report.passed
            if model_readiness_report is not None
            else None
        ),
        "model_readiness_failure_count": (
            len(model_readiness_report.failures)
            if model_readiness_report is not None
            else 0
        ),
        "model_readiness_warning_count": (
            len(model_readiness_report.warnings)
            if model_readiness_report is not None
            else 0
        ),
        "model_quality_attached": model_quality_report is not None,
        "model_quality_passed": (
            record.model_quality_summary.get("passed")
            if record.model_quality_summary is not None
            else None
        ),
        "model_quality_failure_count": len(record.model_quality_failures or []),
        "model_quality_failures": list(record.model_quality_failures or []),
        "model_testing_attached": model_testing_summary is not None,
        "model_testing_passed": _model_testing_summary_passed(model_testing_summary),
        "model_testing_candidate_count": _model_testing_summary_value(
            model_testing_summary,
            "candidate_count",
            default=0,
        ),
        "model_testing_promoted_candidate_count": _model_testing_summary_value(
            model_testing_summary,
            "promoted_candidate_count",
            default=0,
        ),
        "model_testing_rejected_candidate_count": _model_testing_summary_value(
            model_testing_summary,
            "rejected_candidate_count",
            default=0,
        ),
        "model_testing_best_candidate_id": _model_testing_summary_value(
            model_testing_summary,
            "best_candidate_id",
        ),
        "experiment_regression_attached": experiment_regression_report is not None,
        "experiment_regression_passed": _experiment_regression_report_passed(
            experiment_regression_report
        ),
        "experiment_regression_has_regression": (
            experiment_regression_report.get("has_regression")
            if experiment_regression_report is not None
            else None
        ),
        "experiment_regression_failure_count": _experiment_regression_failure_count(
            experiment_regression_report
        ),
        "experiment_regression_failures": _experiment_regression_failures(
            experiment_regression_report
        ),
        **dict(config.metadata),
    }

    return ResearchOperationRunnerResult(
        operation_result=operation_result,
        record=record,
        record_validation=record_validation,
        log_write_result=log_write_result,
        health_result=health_result,
        metadata=metadata,
        backtest_attachment=backtest_attachment,
        backtest_handoff_result=backtest_handoff_result,
        model_readiness_report=model_readiness_report,
        model_quality_report=model_quality_report,
        model_testing_summary=model_testing_summary,
        experiment_regression_report=experiment_regression_report,
    )


def _build_backtest_handoff_operation_output(
    *,
    operation_result: ResearchEvaluationOperationResult,
    research_output: Any,
    model_testing_summary: Mapping[str, Any] | None,
    config: ResearchOperationRunnerConfig,
) -> dict[str, Any]:
    payload = _mapping_from_object(research_output)
    operation_metadata = dict(getattr(operation_result, "metadata", {}) or {})

    payload.setdefault(
        "operation_id",
        config.record_config.run_id
        or operation_metadata.get("run_id")
        or config.record_config.operation_name,
    )
    payload.setdefault("run_id", config.record_config.run_id)
    payload.setdefault("status", getattr(operation_result.status, "value", None))
    payload.setdefault("passed", operation_result.passed)
    payload.setdefault(
        "evaluation_decision",
        operation_metadata.get("evaluation_decision"),
    )
    payload.setdefault(
        "evaluation_promoted",
        operation_metadata.get("evaluation_promoted"),
    )

    if model_testing_summary is not None:
        payload.setdefault("model_testing_summary", dict(model_testing_summary))
        candidate_id = (
            model_testing_summary.get("promotion_candidate_id")
            or model_testing_summary.get("selected_candidate_id")
            or model_testing_summary.get("best_candidate_id")
            or model_testing_summary.get("candidate_id")
        )
        if candidate_id is not None:
            payload.setdefault("accepted_candidate_id", str(candidate_id))

    return payload


def _build_default_backtest_handoff_runner(
    config: ResearchOperationRunnerConfig,
) -> Callable[[MinimalBacktestFixture], Any]:
    def _runner(fixture: MinimalBacktestFixture) -> Mapping[str, Any]:
        if config.backtest_prices is None:
            raise ValueError(
                "backtest_prices is required for the default backtest handoff runner"
            )

        attachment = build_research_backtest_attachment(
            research_output=_fixture_to_research_output(fixture),
            prices=config.backtest_prices,
            initial_cash=config.backtest_initial_cash,
            rebalance_frequency=config.backtest_rebalance_frequency,
            price_column=config.backtest_price_column,
            date_column=config.backtest_date_column,
            symbol_column=config.backtest_symbol_column,
            drift_threshold=config.backtest_drift_threshold,
            metadata={
                "source": "research_to_backtest_handoff",
                **dict(config.backtest_metadata),
            },
        )

        return attachment.to_dict()

    return _runner


def _fixture_to_research_output(
    fixture: MinimalBacktestFixture,
) -> dict[str, Any]:
    return {
        "operation_id": fixture.source_operation_id,
        "accepted_candidate_id": fixture.candidate_id,
        "weights_by_asset": dict(fixture.weights_by_asset),
        "target_weights": dict(fixture.weights_by_asset),
        "signals_by_asset": dict(fixture.signals_by_asset),
        "metadata": {
            **dict(fixture.metadata),
            "fixture_id": fixture.fixture_id,
        },
    }


def _mapping_from_object(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)

    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        data = to_dict()
        if isinstance(data, Mapping):
            return dict(data)
        raise TypeError("research_output.to_dict() must return a mapping.")

    return dict(getattr(value, "__dict__", {}) or {})


def _backtest_handoff_failure_count(
    result: ResearchBacktestHandoffResult | None,
) -> int:
    return len(_backtest_handoff_failures(result))


def _backtest_handoff_failures(
    result: ResearchBacktestHandoffResult | None,
) -> list[str]:
    if result is None:
        return []

    if result.failure_reason:
        return [result.failure_reason]

    if not result.passed:
        return ["backtest_handoff_failed"]

    return []


def _build_experiment_regression_report(
    *,
    operation_result: ResearchEvaluationOperationResult,
    model_testing_summary: Mapping[str, Any] | None,
    config: ResearchOperationRunnerConfig,
) -> dict[str, Any]:
    if config.experiment_regression_report is not None:
        return dict(config.experiment_regression_report)

    baseline_summary = config.baseline_experiment_summary
    current_summary = config.current_experiment_summary

    if current_summary is None:
        current_summary = model_testing_summary or _extract_model_testing_summary(
            operation_result
        )

    if baseline_summary is None or current_summary is None:
        raise ValueError(
            "Cannot attach experiment regression report because baseline_experiment_summary "
            "and current_experiment_summary/model_testing_summary are required."
        )

    report = compare_experiment_runs(
        baseline_summary=baseline_summary,
        current_summary=current_summary,
        max_allowed_quality_score_degradation=(
            config.max_allowed_quality_score_degradation
        ),
        fail_on_rank_change=config.fail_on_experiment_rank_change,
    )

    return report.to_json_dict()


def _extract_model_quality_report(
    operation_result: ResearchEvaluationOperationResult,
) -> Any | None:
    """Return a ModelQualityReport attached by the evaluation operation, if present."""
    direct_report = getattr(operation_result, "model_quality_report", None)
    if direct_report is not None:
        return direct_report

    evaluation_result = getattr(operation_result, "evaluation_result", None)
    if evaluation_result is None:
        return None

    for attribute in (
        "model_quality_report",
        "quality_report",
        "promotion_quality_report",
    ):
        report = getattr(evaluation_result, attribute, None)
        if report is not None:
            return report

    return None


def _extract_model_testing_summary(
    operation_result: ResearchEvaluationOperationResult,
) -> dict[str, Any] | None:
    """Return a model-testing comparison summary attached to the operation, if present."""

    for container in (
        operation_result,
        getattr(operation_result, "evaluation_result", None),
    ):
        if container is None:
            continue

        summary = getattr(container, "model_testing_summary", None)
        if isinstance(summary, Mapping):
            return dict(summary)

        comparison_report = getattr(container, "model_comparison_report", None)
        if comparison_report is not None:
            if isinstance(comparison_report, Mapping):
                return dict(comparison_report)

            to_dict = getattr(comparison_report, "to_dict", None)
            if callable(to_dict):
                data = to_dict()
                if isinstance(data, Mapping):
                    return dict(data)

            summary_method = getattr(comparison_report, "summary", None)
            if callable(summary_method):
                data = summary_method()
                if isinstance(data, Mapping):
                    return dict(data)

            try:
                return build_model_comparison_summary(comparison_report)
            except AttributeError:
                pass

    return None


def _model_testing_summary_passed(
    summary: Mapping[str, Any] | None,
) -> bool | None:
    if summary is None:
        return None

    if summary.get("candidate_count") == 0:
        return False

    if summary.get("promoted_candidate_count") == 0:
        return False

    if summary.get("has_promoted_candidate") is False:
        return False

    if not summary.get("best_candidate_id"):
        return False

    return True


def _model_testing_summary_value(
    summary: Mapping[str, Any] | None,
    key: str,
    default: Any | None = None,
) -> Any | None:
    if summary is None:
        return default

    return summary.get(key, default)


def _experiment_regression_report_passed(
    report: Mapping[str, Any] | None,
) -> bool | None:
    if report is None:
        return None

    return report.get("has_regression") is False


def _experiment_regression_failure_count(
    report: Mapping[str, Any] | None,
) -> int:
    return len(_experiment_regression_failures(report))


def _experiment_regression_failures(
    report: Mapping[str, Any] | None,
) -> list[str]:
    if report is None:
        return []

    failures = report.get("failed_checks", [])

    if isinstance(failures, str):
        return [failures]

    if isinstance(failures, Sequence):
        return [str(failure) for failure in failures]

    return []


def _report_to_dict(report: Any | None) -> dict[str, Any] | None:
    if report is None:
        return None

    to_dict = getattr(report, "to_dict", None)
    if callable(to_dict):
        data = to_dict()
        if isinstance(data, Mapping):
            return dict(data)
        raise TypeError("report.to_dict() must return a mapping.")

    if isinstance(report, Mapping):
        return dict(report)

    return dict(getattr(report, "__dict__", {}) or {})


