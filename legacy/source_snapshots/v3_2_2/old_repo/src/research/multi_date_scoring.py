from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd


REQUIRED_MULTI_DATE_SCORE_COLUMNS = {
    "date",
    "asset",
    "factor_value",
    "factor_rank",
    "signal",
    "forward_return",
}


@dataclass(frozen=True)
class MultiDateScorePeriod:
    date: str
    observation_count: int
    top_bottom_spread: float
    score: float
    passed: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MultiDateScoreResult:
    case_name: str
    row_count: int
    date_count: int
    asset_count: int
    aggregate_score: float | None
    stability_score: float
    positive_period_rate: float
    promotable_score: bool
    failure_reasons: tuple[str, ...]
    periods: tuple[MultiDateScorePeriod, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["periods"] = [period.to_dict() for period in self.periods]
        return data

    def to_diagnostics(self) -> dict[str, Any]:
        return {
            "case_name": self.case_name,
            "row_count": self.row_count,
            "date_count": self.date_count,
            "asset_count": self.asset_count,
            "score": self.aggregate_score,
            "stability_score": self.stability_score,
            "positive_period_rate": self.positive_period_rate,
            "promotable_score": self.promotable_score,
            "failure_reasons": self.failure_reasons,
            "per_date_scores": {
                period.date: period.score for period in self.periods
            },
        }


def build_multi_date_score_result(
    *,
    case_name: str,
    factor_data: pd.DataFrame,
    min_periods: int = 3,
    min_assets: int = 3,
    min_score: float = 0.50,
    min_stability_score: float = 0.50,
    min_positive_period_rate: float = 0.67,
    spread_scale: float = 0.05,
) -> MultiDateScoreResult:
    failure_reasons: list[str] = []

    row_count = len(factor_data)
    date_count = _safe_nunique(factor_data, "date")
    asset_count = _safe_nunique(factor_data, "asset")

    missing_columns = REQUIRED_MULTI_DATE_SCORE_COLUMNS.difference(factor_data.columns)
    if missing_columns:
        failure_reasons.append("missing_factor_columns")
        return _empty_result(
            case_name=case_name,
            row_count=row_count,
            date_count=date_count,
            asset_count=asset_count,
            failure_reasons=tuple(failure_reasons),
        )

    if factor_data.empty:
        failure_reasons.append("empty_factor_data")
        return _empty_result(
            case_name=case_name,
            row_count=row_count,
            date_count=date_count,
            asset_count=asset_count,
            failure_reasons=tuple(failure_reasons),
        )

    required_frame = factor_data[list(REQUIRED_MULTI_DATE_SCORE_COLUMNS)]
    if required_frame.isna().any().any():
        failure_reasons.append("missing_factor_data")

    if date_count < min_periods:
        failure_reasons.append("insufficient_factor_history")

    if asset_count < min_assets:
        failure_reasons.append("insufficient_factor_universe")

    periods = tuple(
        _build_score_periods(
            factor_data=factor_data,
            spread_scale=spread_scale,
        )
    )

    if not periods:
        failure_reasons.append("missing_score_periods")

    scores = [period.score for period in periods]
    spreads = [period.top_bottom_spread for period in periods]

    aggregate_score = (
        float(pd.Series(scores, dtype="float64").mean()) if scores else None
    )

    positive_period_count = sum(period.top_bottom_spread > 0 for period in periods)
    positive_period_rate = positive_period_count / len(periods) if periods else 0.0

    stability_score = _calculate_stability_score(spreads)

    if aggregate_score is None or aggregate_score < min_score:
        failure_reasons.append("low_aggregate_score")

    if stability_score < min_stability_score:
        failure_reasons.append("low_stability_score")

    if positive_period_rate < min_positive_period_rate:
        failure_reasons.append("low_positive_period_rate")

    if _has_direction_reversal(spreads):
        failure_reasons.append("multi_date_direction_reversal")

    unique_failure_reasons = tuple(dict.fromkeys(failure_reasons))

    return MultiDateScoreResult(
        case_name=case_name,
        row_count=row_count,
        date_count=date_count,
        asset_count=asset_count,
        aggregate_score=aggregate_score,
        stability_score=stability_score,
        positive_period_rate=positive_period_rate,
        promotable_score=not unique_failure_reasons,
        failure_reasons=unique_failure_reasons,
        periods=periods,
    )


def _build_score_periods(
    *,
    factor_data: pd.DataFrame,
    spread_scale: float,
) -> list[MultiDateScorePeriod]:
    clean_data = factor_data.dropna(subset=["date", "factor_rank", "forward_return"])

    periods: list[MultiDateScorePeriod] = []

    for date, date_frame in clean_data.groupby("date"):
        midpoint = date_frame["factor_rank"].median()

        top = date_frame[date_frame["factor_rank"] > midpoint]
        bottom = date_frame[date_frame["factor_rank"] <= midpoint]

        if top.empty or bottom.empty:
            continue

        spread = float(top["forward_return"].mean() - bottom["forward_return"].mean())
        score = _spread_to_score(spread=spread, spread_scale=spread_scale)

        periods.append(
            MultiDateScorePeriod(
                date=pd.Timestamp(date).date().isoformat(),
                observation_count=len(date_frame),
                top_bottom_spread=spread,
                score=score,
                passed=score >= 0.50 and spread > 0,
            )
        )

    return periods


def _spread_to_score(*, spread: float, spread_scale: float) -> float:
    if spread_scale <= 0:
        raise ValueError("spread_scale must be greater than zero")

    raw_score = 0.50 + (spread / spread_scale)

    return max(0.0, min(1.0, raw_score))


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


def _has_direction_reversal(spreads: list[float]) -> bool:
    if len(spreads) < 2:
        return False

    return min(spreads) < 0 < max(spreads)


def _empty_result(
    *,
    case_name: str,
    row_count: int,
    date_count: int,
    asset_count: int,
    failure_reasons: tuple[str, ...],
) -> MultiDateScoreResult:
    return MultiDateScoreResult(
        case_name=case_name,
        row_count=row_count,
        date_count=date_count,
        asset_count=asset_count,
        aggregate_score=None,
        stability_score=0.0,
        positive_period_rate=0.0,
        promotable_score=False,
        failure_reasons=failure_reasons,
        periods=(),
    )


def _safe_nunique(data: pd.DataFrame, column: str) -> int:
    if column not in data.columns:
        return 0

    return int(data[column].nunique())
