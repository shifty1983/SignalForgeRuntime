from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

import polars as pl

from src.research.model_gate import (
    ResearchModelGateConfig,
    ResearchModelGateError,
    ResearchModelGateResult,
    evaluate_research_model_gate,
)
from src.research.model_test import (
    ResearchModelTestConfig,
    ResearchModelTestResult,
    run_research_model_test,
)


class ResearchModelOperationStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"


@dataclass(frozen=True)
class ResearchModelOperationConfig:
    model_test_config: ResearchModelTestConfig = field(
        default_factory=ResearchModelTestConfig
    )
    model_gate_config: ResearchModelGateConfig = field(
        default_factory=ResearchModelGateConfig
    )
    fail_on_gate_failure: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.model_test_config, ResearchModelTestConfig):
            raise TypeError("model_test_config must be a ResearchModelTestConfig.")

        if not isinstance(self.model_gate_config, ResearchModelGateConfig):
            raise TypeError("model_gate_config must be a ResearchModelGateConfig.")

        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class ResearchModelOperationResult:
    model_test_result: ResearchModelTestResult
    model_gate_result: ResearchModelGateResult
    status: ResearchModelOperationStatus
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status == ResearchModelOperationStatus.PASS

    @property
    def failed(self) -> bool:
        return self.status == ResearchModelOperationStatus.FAIL

    def summary(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "passed": self.passed,
            "model_test": self.model_test_result.summary(),
            "model_gate": self.model_gate_result.to_dict(),
            "metadata": dict(self.metadata),
        }

    def to_dict(self) -> dict[str, Any]:
        return self.summary()


def run_research_model_operation(
    evaluation_result: Any,
    returns: pl.DataFrame,
    config: ResearchModelOperationConfig | None = None,
) -> ResearchModelOperationResult:
    config = config or ResearchModelOperationConfig()

    model_test_result = run_research_model_test(
        evaluation_result=evaluation_result,
        returns=returns,
        config=config.model_test_config,
    )

    model_gate_result = evaluate_research_model_gate(
        model_test_result=model_test_result,
        config=config.model_gate_config,
    )

    status = (
        ResearchModelOperationStatus.PASS
        if model_gate_result.passed
        else ResearchModelOperationStatus.FAIL
    )

    if config.fail_on_gate_failure and status == ResearchModelOperationStatus.FAIL:
        messages = "; ".join(
            check.message for check in model_gate_result.failures
        )
        raise ResearchModelGateError(
            f"Research model operation failed gate: {messages}"
        )

    metadata = {
        "source": "research_model_operation",
        "evaluation_result_type": type(evaluation_result).__name__,
        "evaluation_decision": getattr(evaluation_result, "decision", None),
        "evaluation_promoted": getattr(evaluation_result, "promoted", None),
        "operation_status": status.value,
        **dict(config.metadata),
    }

    return ResearchModelOperationResult(
        model_test_result=model_test_result,
        model_gate_result=model_gate_result,
        status=status,
        metadata=metadata,
    )
