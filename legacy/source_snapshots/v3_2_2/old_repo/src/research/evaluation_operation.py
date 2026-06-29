from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

import polars as pl

from src.research.evaluation_pipeline import (
    ResearchEvaluationPipelineConfig,
    ResearchEvaluationPipelineResult,
    run_research_evaluation_pipeline,
)
from src.research.model_operation import (
    ResearchModelOperationConfig,
    ResearchModelOperationResult,
    ResearchModelOperationStatus,
    run_research_model_operation,
)


class ResearchEvaluationOperationStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"


@dataclass(frozen=True)
class ResearchEvaluationOperationConfig:
    evaluation_config: ResearchEvaluationPipelineConfig
    model_operation_config: ResearchModelOperationConfig = field(
        default_factory=ResearchModelOperationConfig
    )
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.evaluation_config, ResearchEvaluationPipelineConfig):
            raise TypeError(
                "evaluation_config must be a ResearchEvaluationPipelineConfig."
            )

        if not isinstance(self.model_operation_config, ResearchModelOperationConfig):
            raise TypeError(
                "model_operation_config must be a ResearchModelOperationConfig."
            )

        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class ResearchEvaluationOperationResult:
    evaluation_result: ResearchEvaluationPipelineResult
    model_operation_result: ResearchModelOperationResult
    status: ResearchEvaluationOperationStatus
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status == ResearchEvaluationOperationStatus.PASS

    @property
    def failed(self) -> bool:
        return self.status == ResearchEvaluationOperationStatus.FAIL

    def summary(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "passed": self.passed,
            "evaluation": self.evaluation_result.summary(),
            "model_operation": self.model_operation_result.summary(),
            "metadata": dict(self.metadata),
        }

    def to_dict(self) -> dict[str, Any]:
        return self.summary()


def run_research_evaluation_operation(
    df: pl.DataFrame,
    returns: pl.DataFrame,
    config: ResearchEvaluationOperationConfig,
) -> ResearchEvaluationOperationResult:
    if not isinstance(df, pl.DataFrame):
        raise TypeError("df must be a polars DataFrame.")

    if not isinstance(returns, pl.DataFrame):
        raise TypeError("returns must be a polars DataFrame.")

    evaluation_result = run_research_evaluation_pipeline(
        df=df,
        config=config.evaluation_config,
    )

    model_operation_result = run_research_model_operation(
        evaluation_result=evaluation_result,
        returns=returns,
        config=config.model_operation_config,
    )

    status = (
        ResearchEvaluationOperationStatus.PASS
        if model_operation_result.status == ResearchModelOperationStatus.PASS
        else ResearchEvaluationOperationStatus.FAIL
    )

    metadata = {
        "source": "research_evaluation_operation",
        "evaluation_decision": evaluation_result.decision,
        "evaluation_promoted": evaluation_result.promoted,
        "model_operation_status": model_operation_result.status.value,
        "operation_status": status.value,
        **dict(config.metadata),
    }

    return ResearchEvaluationOperationResult(
        evaluation_result=evaluation_result,
        model_operation_result=model_operation_result,
        status=status,
        metadata=metadata,
    )
