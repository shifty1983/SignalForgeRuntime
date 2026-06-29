from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd


REQUIRED_ROBUSTNESS_COLUMNS = {
    "date",
    "asset",
    "factor_value",
    "factor_rank",
    "signal",
    "forward_return",
}


@dataclass(frozen=True)
class FactorRobustnessPeriod:
    date: str
    observation_count: int
    top_bottom_spread: float
    passed: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FactorRobustnessReport:
    case_name: str
    row_count: int
    date_count: int
    asset_count: int
    missing_value_count: int
    missing_value_rate: float
    average_spread: float | None
    spread_std: float | None
    min_spread: float | None
    max_spread: float | None
    positive_period_rate: float
    stability_score: float
    robust: bool
    failure_reasons: tuple[str, ...]
    periods: tuple[FactorRobustnessPeriod, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["periods"] = [period.to_dict() for period in self.periods]
        return data


def build_factor_robustness_report(
    *,
    case_name: str,
    factor_data: pd.DataFrame,
    min_periods: int = 3,
    min_assets: int = 3,
    min_average_spread: float = 0.0,
    min_positive_period_rate: float = 0.67,
    max_missing_value_rate: float = 0.0,
) -> FactorRobustnessReport:
    failure_reasons: list[str] = []

    row_count = len(factor_data)
    date_count = _safe_nunique(factor_data, "date")
    asset_count = _safe_nunique(factor_data, "asset")

    missing_columns = REQUIRED_ROBUSTNESS_COLUMNS.difference(factor_data.columns)
    if missing_columns:
        failure_reasons.append("missing_factor_columns")

        return FactorRobustnessReport(
            case_name=case_name,
            row_count=row_count,
            date_count=date_count,
            asset_count=asset_count,
            missing_value_count=0,
            missing_value_rate=0.0,
            average_spread=None,
            spread_std=None,
            min_spread=None,
            max_spread=None,
            positive_period_rate=0.0,
            stability_score=0.0,
            robust=False,
            failure_reasons=tuple(failure_reasons),
            periods=(),
        )

    if factor_data.empty:
        failure_reasons.append("empty_factor_data")

        return FactorRobustnessReport(
            case_name=case_name,
            row_count=row_count,
            date_count=date_count,
            asset_count=asset_count,
            missing_value_count=0,
            missing_value_rate=0.0,
            average_spread=None,
            spread_std=None,
            min_spread=None,
            max_spread=None,
            positive_period_rate=0.0,
            stability_score=0.0,
            robust=False,
            failure_reasons=tuple(failure_reasons),
            periods=(),
        )

    required_frame = factor_data[list(REQUIRED_ROBUSTNESS_COLUMNS)]
    missing_value_count = int(required_frame.isna().sum().sum())
    total_required_values = int(required_frame.shape[0] * required_frame.shape[1])
    missing_value_rate = (
        missing_value_count / total_required_values if total_required_values else 0.0
    )

    if missing_value_rate > max_missing_value_rate:
        failure_reasons.append("missing_factor_data")

    if date_count < min_periods:
        failure_reasons.append("insufficient_factor_history")

    if asset_count < min_assets:
        failure_reasons.append("insufficient_factor_universe")

    periods = tuple(_build_period_results(factor_data))
    spreads = [period.top_bottom_spread for period in periods]

    average_spread = float(pd.Series(spreads).mean()) if spreads else None
    spread_std = float(pd.Series(spreads).std(ddof=0)) if spreads else None
    min_spread = min(spreads) if spreads else None
    max_spread = max(spreads) if spreads else None

    positive_period_count = sum(spread > 0 for spread in spreads)
    positive_period_rate = positive_period_count / len(spreads) if spreads else 0.0
    stability_score = _calculate_stability_score(spreads)

    if not periods:
        failure_reasons.append("missing_period_results")

    if average_spread is None or average_spread <= min_average_spread:
        failure_reasons.append("low_average_spread")

    if positive_period_rate < min_positive_period_rate:
        failure_reasons.append("low_positive_period_rate")

    if _has_spread_direction_reversal(spreads):
        failure_reasons.append("unstable_period_spreads")

    unique_failure_reasons = tuple(dict.fromkeys(failure_reasons))

    return FactorRobustnessReport(
        case_name=case_name,
        row_count=row_count,
        date_count=date_count,
        asset_count=asset_count,
        missing_value_count=missing_value_count,
        missing_value_rate=missing_value_rate,
        average_spread=average_spread,
        spread_std=spread_std,
        min_spread=min_spread,
        max_spread=max_spread,
        positive_period_rate=positive_period_rate,
        stability_score=stability_score,
        robust=not unique_failure_reasons,
        failure_reasons=unique_failure_reasons,
        periods=periods,
    )


def _build_period_results(
    factor_data: pd.DataFrame,
) -> list[FactorRobustnessPeriod]:
    periods: list[FactorRobustnessPeriod] = []

    clean_data = factor_data.dropna(subset=["date", "factor_rank", "forward_return"])

    for date, date_frame in clean_data.groupby("date"):
        midpoint = date_frame["factor_rank"].median()

        top = date_frame[date_frame["factor_rank"] > midpoint]
        bottom = date_frame[date_frame["factor_rank"] <= midpoint]

        if top.empty or bottom.empty:
            continue

        spread = float(top["forward_return"].mean() - bottom["forward_return"].mean())

        periods.append(
            FactorRobustnessPeriod(
                date=pd.Timestamp(date).date().isoformat(),
                observation_count=len(date_frame),
                top_bottom_spread=spread,
                passed=spread > 0,
            )
        )

    return periods


def _calculate_stability_score(spreads: list[float]) -> float:
    if not spreads:
        return 0.0

    spread_series = pd.Series(spreads, dtype="float64")
    average_abs_spread = abs(float(spread_series.mean()))
    spread_std = float(spread_series.std(ddof=0))

    denominator = average_abs_spread + spread_std

    if denominator == 0:
        return 1.0

    score = average_abs_spread / denominator

    return max(0.0, min(1.0, score))


def _has_spread_direction_reversal(spreads: list[float]) -> bool:
    if len(spreads) < 2:
        return False

    return min(spreads) < 0 < max(spreads)


def _safe_nunique(data: pd.DataFrame, column: str) -> int:
    if column not in data.columns:
        return 0

    return int(data[column].nunique())
