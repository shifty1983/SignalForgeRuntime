from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

from src.research.model_candidate import ModelCandidate
from src.research.model_comparison import (
    ModelComparisonReport,
    build_model_comparison_summary,
)
from src.research.model_testing_harness import (
    CandidateEvaluationInputs,
    ModelQualityReportBuilder,
    run_model_testing_harness,
)


class CandidateExperimentOperationStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"


@dataclass(frozen=True)
class CandidateExperimentOperationConfig:
    experiment_id: str
    require_promoted_candidate: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.experiment_id:
            raise ValueError("experiment_id cannot be empty.")

        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class CandidateExperimentOperationResult:
    experiment_id: str
    status: CandidateExperimentOperationStatus
    passed: bool
    comparison_report: ModelComparisonReport
    comparison_summary: Mapping[str, Any]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def best_candidate_id(self) -> str | None:
        return self.comparison_report.best_candidate_id

    def summary(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "status": self.status.value,
            "passed": self.passed,
            "best_candidate_id": self.best_candidate_id,
            "comparison_summary": dict(self.comparison_summary),
            "metadata": dict(self.metadata),
        }

    def to_dict(self) -> dict[str, Any]:
        return self.summary()


def run_candidate_experiment_operation(
    *,
    candidates: Sequence[ModelCandidate],
    evaluation_inputs_by_candidate_id: Mapping[str, CandidateEvaluationInputs],
    build_quality_report: ModelQualityReportBuilder,
    config: CandidateExperimentOperationConfig,
) -> CandidateExperimentOperationResult:
    comparison_report = run_model_testing_harness(
        candidates=candidates,
        evaluation_inputs_by_candidate_id=evaluation_inputs_by_candidate_id,
        build_quality_report=build_quality_report,
    )

    comparison_summary = build_model_comparison_summary(comparison_report)

    passed = _comparison_summary_passed(
        comparison_summary=comparison_summary,
        config=config,
    )

    status = (
        CandidateExperimentOperationStatus.PASS
        if passed
        else CandidateExperimentOperationStatus.FAIL
    )

    metadata = {
        "source": "candidate_experiment_operation",
        "experiment_id": config.experiment_id,
        **dict(config.metadata),
    }

    return CandidateExperimentOperationResult(
        experiment_id=config.experiment_id,
        status=status,
        passed=passed,
        comparison_report=comparison_report,
        comparison_summary=comparison_summary,
        metadata=metadata,
    )


def _comparison_summary_passed(
    *,
    comparison_summary: Mapping[str, Any],
    config: CandidateExperimentOperationConfig,
) -> bool:
    candidate_count = int(comparison_summary.get("candidate_count", 0) or 0)

    if candidate_count <= 0:
        return False

    if not config.require_promoted_candidate:
        return True

    return (
        comparison_summary.get("has_promoted_candidate") is True
        and bool(comparison_summary.get("best_candidate_id"))
    )
