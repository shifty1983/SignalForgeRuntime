from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Mapping

import pandas as pd

from src.research.model_promotion import (
    ModelPromotionResult,
    evaluate_model_promotion,
)
from src.research.multi_date_scoring import (
    MultiDateScoreResult,
    build_multi_date_score_result,
)
from src.research.robustness_report import (
    FactorRobustnessReport,
    build_factor_robustness_report,
)
from src.research.walk_forward_report import (
    FactorWalkForwardReport,
    build_factor_walk_forward_report,
)


@dataclass(frozen=True)
class ModelQualityReport:
    model_name: str
    score_result: MultiDateScoreResult
    robustness_report: FactorRobustnessReport
    walk_forward_report: FactorWalkForwardReport
    promotion_result: ModelPromotionResult

    @property
    def promotable(self) -> bool:
        return self.promotion_result.promotable

    @property
    def failure_reasons(self) -> tuple[str, ...]:
        return self.promotion_result.failure_reasons

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_name": self.model_name,
            "promotable": self.promotable,
            "failure_reasons": self.failure_reasons,
            "score_result": self.score_result.to_dict(),
            "robustness_report": self.robustness_report.to_dict(),
            "walk_forward_report": self.walk_forward_report.to_dict(),
            "promotion_result": self.promotion_result.to_dict(),
        }


def build_model_quality_report(
    *,
    model_name: str,
    factor_data: pd.DataFrame,
    backtest_attachment: Mapping[str, Any] | None,
    require_robustness_report: bool = True,
    require_walk_forward_report: bool = True,
) -> ModelQualityReport:
    score_result = build_multi_date_score_result(
        case_name=model_name,
        factor_data=factor_data,
    )

    robustness_report = build_factor_robustness_report(
        case_name=model_name,
        factor_data=factor_data,
    )

    walk_forward_report = build_factor_walk_forward_report(
        case_name=model_name,
        factor_data=factor_data,
    )

    diagnostics = score_result.to_diagnostics()

    promotion_result = evaluate_model_promotion(
        model_name=model_name,
        diagnostics=diagnostics,
        backtest_attachment=backtest_attachment,
        factor_data=factor_data,
        robustness_report=robustness_report,
        walk_forward_report=walk_forward_report,
        require_robustness_report=require_robustness_report,
        require_walk_forward_report=require_walk_forward_report,
    )

    return ModelQualityReport(
        model_name=model_name,
        score_result=score_result,
        robustness_report=robustness_report,
        walk_forward_report=walk_forward_report,
        promotion_result=promotion_result,
    )
