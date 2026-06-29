from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping
from src.research.robustness_report import FactorRobustnessReport
from src.research.walk_forward_report import FactorWalkForwardReport

import pandas as pd


DEFAULT_MIN_MODEL_SCORE = 0.50
DEFAULT_MIN_STABILITY_SCORE = 0.50


@dataclass(frozen=True)
class ModelPromotionResult:
    model_name: str
    promotable: bool
    score: float | None
    stability_score: float | None
    backtest_attached: bool
    failure_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_model_promotion(
    *,
    model_name: str,
    diagnostics: Mapping[str, Any] | None,
    backtest_attachment: Mapping[str, Any] | None,
    factor_data: pd.DataFrame | None = None,
    robustness_report: FactorRobustnessReport | None = None,
    walk_forward_report: FactorWalkForwardReport | None = None,
    require_robustness_report: bool = False,
    require_walk_forward_report: bool = False,
    min_model_score: float = DEFAULT_MIN_MODEL_SCORE,
    min_stability_score: float = DEFAULT_MIN_STABILITY_SCORE,
) -> ModelPromotionResult:
    failure_reasons: list[str] = []

    if not diagnostics:
        failure_reasons.append("missing_diagnostics")
        score = None
        stability_score = None
    else:
        score = _get_float(diagnostics, "score")
        stability_score = _get_float(diagnostics, "stability_score")

        if score is None:
            failure_reasons.append("missing_model_score")
        elif score < min_model_score:
            failure_reasons.append("low_model_score")

        if stability_score is None:
            failure_reasons.append("missing_stability_score")
        elif stability_score < min_stability_score:
            failure_reasons.append("low_stability_score")
            
        if diagnostics.get("promotable_score") is False:
            failure_reasons.append("multi_date_score_failed")

        diagnostic_failure_reasons = diagnostics.get("failure_reasons", ())
        if isinstance(diagnostic_failure_reasons, (list, tuple, set)):
            failure_reasons.extend(str(reason) for reason in diagnostic_failure_reasons)    

    backtest_attached = _has_valid_backtest_attachment(backtest_attachment)
    if not backtest_attached:
        failure_reasons.append("missing_backtest_attachment")

    if factor_data is not None:
        failure_reasons.extend(_evaluate_factor_data_quality(factor_data))

    if robustness_report is None:
        if require_robustness_report:
            failure_reasons.append("missing_robustness_report")
    elif not robustness_report.robust:
        failure_reasons.append("robustness_report_failed")
        failure_reasons.extend(robustness_report.failure_reasons)

    if walk_forward_report is None:
        if require_walk_forward_report:
            failure_reasons.append("missing_walk_forward_report")
    elif not walk_forward_report.walk_forward_passed:
        failure_reasons.append("walk_forward_report_failed")
        failure_reasons.extend(walk_forward_report.failure_reasons)

    unique_failure_reasons = tuple(dict.fromkeys(failure_reasons))

    return ModelPromotionResult(
        model_name=model_name,
        promotable=not unique_failure_reasons,
        score=score,
        stability_score=stability_score,
        backtest_attached=backtest_attached,
        failure_reasons=unique_failure_reasons,
    )


def _get_float(values: Mapping[str, Any], key: str) -> float | None:
    value = values.get(key)

    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _has_valid_backtest_attachment(
    backtest_attachment: Mapping[str, Any] | None,
) -> bool:
    if not backtest_attachment:
        return False

    if backtest_attachment.get("attached") is not True:
        return False

    required_fields = {
        "engine",
        "period_count",
        "trade_count",
        "total_return",
        "sharpe",
        "max_drawdown",
    }

    return required_fields.issubset(backtest_attachment.keys())


def _evaluate_factor_data_quality(factor_data: pd.DataFrame) -> list[str]:
    failure_reasons: list[str] = []

    required_columns = {
        "date",
        "asset",
        "factor_value",
        "factor_rank",
        "signal",
        "forward_return",
    }

    missing_columns = required_columns.difference(factor_data.columns)
    if missing_columns:
        failure_reasons.append("missing_factor_columns")
        return failure_reasons

    if factor_data.empty:
        failure_reasons.append("empty_factor_data")
        return failure_reasons

    if factor_data[list(required_columns)].isna().any().any():
        failure_reasons.append("missing_factor_data")

    if factor_data["date"].nunique() < 2:
        failure_reasons.append("insufficient_factor_history")

    if factor_data["asset"].nunique() < 2:
        failure_reasons.append("insufficient_factor_universe")

    if _has_directional_reversal(factor_data):
        failure_reasons.append("regime_shift_detected")

    return failure_reasons


def _has_directional_reversal(factor_data: pd.DataFrame) -> bool:
    spreads = []

    for _, date_frame in factor_data.groupby("date"):
        ranks = date_frame["factor_rank"].dropna()

        if ranks.empty:
            continue

        midpoint = ranks.median()

        top = date_frame[date_frame["factor_rank"] > midpoint]
        bottom = date_frame[date_frame["factor_rank"] <= midpoint]

        if top.empty or bottom.empty:
            continue

        spread = top["forward_return"].mean() - bottom["forward_return"].mean()

        if pd.notna(spread):
            spreads.append(float(spread))

    if len(spreads) < 2:
        return False

    return min(spreads) < 0 < max(spreads)
