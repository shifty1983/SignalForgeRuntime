from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import sqrt
from typing import Any, Iterable, Mapping

import polars as pl


class ResearchValidationStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    INSUFFICIENT_DATA = "insufficient_data"


@dataclass(frozen=True)
class ResearchValidationMetric:
    name: str
    value: float | int | None
    threshold: float | int | None = None
    passed: bool | None = None
    description: str = ""


@dataclass(frozen=True)
class ResearchValidationReport:
    status: ResearchValidationStatus
    metrics: Mapping[str, ResearchValidationMetric]
    issues: tuple[str, ...] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status == ResearchValidationStatus.PASSED

    @property
    def failed(self) -> bool:
        return self.status == ResearchValidationStatus.FAILED

    @property
    def insufficient_data(self) -> bool:
        return self.status == ResearchValidationStatus.INSUFFICIENT_DATA

    def metric_value(self, name: str) -> float | int | None:
        return self.metrics[name].value

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "metrics": {
                name: {
                    "name": metric.name,
                    "value": metric.value,
                    "threshold": metric.threshold,
                    "passed": metric.passed,
                    "description": metric.description,
                }
                for name, metric in self.metrics.items()
            },
            "issues": list(self.issues),
            "metadata": dict(self.metadata),
        }


def validate_research_output(
    df: pl.DataFrame,
    signal_column: str = "signal",
    target_column: str = "forward_return",
    factor_column: str | None = None,
    date_column: str = "date",
    symbol_column: str = "symbol",
    min_rows: int = 1,
    min_active_signals: int = 1,
    min_coverage: float = 0.0,
    min_hit_rate: float | None = None,
    min_average_signed_return: float | None = None,
    min_abs_information_coefficient: float | None = None,
) -> ResearchValidationReport:
    """
    Validate research output using fast signal-quality diagnostics.

    Expected inputs:
    - signal_column: numeric long/short/flat signal, usually 1, -1, or 0
    - target_column: forward return or other realized outcome
    - factor_column: optional continuous factor score used for IC calculation
    """

    required_columns = [signal_column, target_column]

    if factor_column is not None:
        required_columns.append(factor_column)

    if date_column in df.columns:
        required_columns.append(date_column)

    if symbol_column in df.columns:
        required_columns.append(symbol_column)

    _require_columns(df, required_columns, context="Research validation input")

    metrics = build_research_validation_metrics(
        df=df,
        signal_column=signal_column,
        target_column=target_column,
        factor_column=factor_column,
        date_column=date_column,
        symbol_column=symbol_column,
    )

    issues: list[str] = []

    row_count = int(metrics["row_count"].value or 0)
    active_signal_count = int(metrics["active_signal_count"].value or 0)
    coverage = float(metrics["signal_coverage"].value or 0.0)

    if row_count < min_rows:
        issues.append(f"Row count below minimum: {row_count} < {min_rows}")

    if active_signal_count < min_active_signals:
        issues.append(
            f"Active signal count below minimum: "
            f"{active_signal_count} < {min_active_signals}"
        )

    if coverage < min_coverage:
        issues.append(f"Signal coverage below minimum: {coverage} < {min_coverage}")

    if min_hit_rate is not None:
        hit_rate = metrics["hit_rate"].value

        if hit_rate is None or hit_rate < min_hit_rate:
            issues.append(f"Hit rate below minimum: {hit_rate} < {min_hit_rate}")

        metrics = {
            **metrics,
            "hit_rate": ResearchValidationMetric(
                name="hit_rate",
                value=hit_rate,
                threshold=min_hit_rate,
                passed=hit_rate is not None and hit_rate >= min_hit_rate,
                description="Share of active signals where signed forward return is positive.",
            ),
        }

    if min_average_signed_return is not None:
        average_signed_return = metrics["average_signed_return"].value

        if (
            average_signed_return is None
            or average_signed_return < min_average_signed_return
        ):
            issues.append(
                f"Average signed return below minimum: "
                f"{average_signed_return} < {min_average_signed_return}"
            )

        metrics = {
            **metrics,
            "average_signed_return": ResearchValidationMetric(
                name="average_signed_return",
                value=average_signed_return,
                threshold=min_average_signed_return,
                passed=average_signed_return is not None
                and average_signed_return >= min_average_signed_return,
                description="Average of signal multiplied by target return for active signals.",
            ),
        }

    if min_abs_information_coefficient is not None:
        information_coefficient = metrics["information_coefficient"].value

        if (
            information_coefficient is None
            or abs(information_coefficient) < min_abs_information_coefficient
        ):
            issues.append(
                f"Absolute information coefficient below minimum: "
                f"{information_coefficient} < {min_abs_information_coefficient}"
            )

        metrics = {
            **metrics,
            "information_coefficient": ResearchValidationMetric(
                name="information_coefficient",
                value=information_coefficient,
                threshold=min_abs_information_coefficient,
                passed=information_coefficient is not None
                and abs(information_coefficient) >= min_abs_information_coefficient,
                description="Pearson correlation between factor values and target returns.",
            ),
        }

    if row_count < min_rows or active_signal_count < min_active_signals:
        status = ResearchValidationStatus.INSUFFICIENT_DATA
    elif issues:
        status = ResearchValidationStatus.FAILED
    else:
        status = ResearchValidationStatus.PASSED

    return ResearchValidationReport(
        status=status,
        metrics=metrics,
        issues=tuple(issues),
        metadata={
            "signal_column": signal_column,
            "target_column": target_column,
            "factor_column": factor_column,
            "date_column": date_column,
            "symbol_column": symbol_column,
        },
    )


def build_research_validation_metrics(
    df: pl.DataFrame,
    signal_column: str = "signal",
    target_column: str = "forward_return",
    factor_column: str | None = None,
    date_column: str = "date",
    symbol_column: str = "symbol",
) -> dict[str, ResearchValidationMetric]:
    _require_columns(df, [signal_column, target_column], context="Research metrics input")

    active = df.filter(pl.col(signal_column) != 0)

    row_count = df.height
    active_signal_count = active.height
    long_signal_count = df.filter(pl.col(signal_column) > 0).height
    short_signal_count = df.filter(pl.col(signal_column) < 0).height
    neutral_signal_count = df.filter(pl.col(signal_column) == 0).height
    coverage = active_signal_count / row_count if row_count else 0.0

    average_target = _mean(active, target_column)
    average_signed_return = _mean_expression(
        active,
        pl.col(signal_column) * pl.col(target_column),
    )
    hit_rate = calculate_hit_rate(
        df,
        signal_column=signal_column,
        target_column=target_column,
    )
    long_short_spread = calculate_long_short_spread(
        df,
        signal_column=signal_column,
        target_column=target_column,
    )
    signal_volatility = calculate_signal_return_volatility(
        df,
        signal_column=signal_column,
        target_column=target_column,
    )
    signal_sharpe = calculate_signal_sharpe_like_score(
        df,
        signal_column=signal_column,
        target_column=target_column,
    )

    turnover = None
    if date_column in df.columns and symbol_column in df.columns:
        turnover = calculate_signal_turnover(
            df,
            signal_column=signal_column,
            date_column=date_column,
            symbol_column=symbol_column,
        )

    information_coefficient = None
    if factor_column is not None:
        _require_columns(
            df,
            [factor_column],
            context="Information coefficient input",
        )
        information_coefficient = calculate_information_coefficient(
            df,
            factor_column=factor_column,
            target_column=target_column,
        )

    return {
        "row_count": ResearchValidationMetric(
            name="row_count",
            value=row_count,
            description="Total number of rows evaluated.",
        ),
        "active_signal_count": ResearchValidationMetric(
            name="active_signal_count",
            value=active_signal_count,
            description="Rows where signal is non-zero.",
        ),
        "long_signal_count": ResearchValidationMetric(
            name="long_signal_count",
            value=long_signal_count,
            description="Rows where signal is positive.",
        ),
        "short_signal_count": ResearchValidationMetric(
            name="short_signal_count",
            value=short_signal_count,
            description="Rows where signal is negative.",
        ),
        "neutral_signal_count": ResearchValidationMetric(
            name="neutral_signal_count",
            value=neutral_signal_count,
            description="Rows where signal is zero.",
        ),
        "signal_coverage": ResearchValidationMetric(
            name="signal_coverage",
            value=coverage,
            description="Active signals divided by total rows.",
        ),
        "average_active_target": ResearchValidationMetric(
            name="average_active_target",
            value=average_target,
            description="Average target return on active signals.",
        ),
        "average_signed_return": ResearchValidationMetric(
            name="average_signed_return",
            value=average_signed_return,
            description="Average of signal multiplied by target return for active signals.",
        ),
        "hit_rate": ResearchValidationMetric(
            name="hit_rate",
            value=hit_rate,
            description="Share of active signals where signed forward return is positive.",
        ),
        "long_short_spread": ResearchValidationMetric(
            name="long_short_spread",
            value=long_short_spread,
            description="Average long target return minus average short target return.",
        ),
        "signal_return_volatility": ResearchValidationMetric(
            name="signal_return_volatility",
            value=signal_volatility,
            description="Sample volatility of signed active signal returns.",
        ),
        "signal_sharpe_like_score": ResearchValidationMetric(
            name="signal_sharpe_like_score",
            value=signal_sharpe,
            description="Average signed return divided by signed return volatility.",
        ),
        "signal_turnover": ResearchValidationMetric(
            name="signal_turnover",
            value=turnover,
            description="Average absolute signal change by symbol through time.",
        ),
        "information_coefficient": ResearchValidationMetric(
            name="information_coefficient",
            value=information_coefficient,
            description="Pearson correlation between factor values and target returns.",
        ),
    }


def calculate_hit_rate(
    df: pl.DataFrame,
    signal_column: str = "signal",
    target_column: str = "forward_return",
) -> float | None:
    _require_columns(df, [signal_column, target_column], context="Hit rate input")

    active = df.filter(pl.col(signal_column) != 0)

    if active.height == 0:
        return None

    return active.select(
        ((pl.col(signal_column) * pl.col(target_column)) > 0)
        .cast(pl.Float64)
        .mean()
    ).item()


def calculate_long_short_spread(
    df: pl.DataFrame,
    signal_column: str = "signal",
    target_column: str = "forward_return",
) -> float | None:
    _require_columns(
        df,
        [signal_column, target_column],
        context="Long/short spread input",
    )

    longs = df.filter(pl.col(signal_column) > 0)
    shorts = df.filter(pl.col(signal_column) < 0)

    if longs.height == 0 or shorts.height == 0:
        return None

    long_average = _mean(longs, target_column)
    short_average = _mean(shorts, target_column)

    if long_average is None or short_average is None:
        return None

    return long_average - short_average


def calculate_information_coefficient(
    df: pl.DataFrame,
    factor_column: str,
    target_column: str,
) -> float | None:
    _require_columns(
        df,
        [factor_column, target_column],
        context="Information coefficient input",
    )

    values = (
        df.select([factor_column, target_column])
        .drop_nulls()
        .rows()
    )

    if len(values) < 2:
        return None

    x = [float(row[0]) for row in values]
    y = [float(row[1]) for row in values]

    return _pearson_correlation(x, y)


def calculate_signal_turnover(
    df: pl.DataFrame,
    signal_column: str = "signal",
    date_column: str = "date",
    symbol_column: str = "symbol",
) -> float | None:
    _require_columns(
        df,
        [signal_column, date_column, symbol_column],
        context="Signal turnover input",
    )

    sorted_df = df.sort([symbol_column, date_column])

    changes = (
        sorted_df.with_columns(
            pl.col(signal_column)
            .diff()
            .abs()
            .over(symbol_column)
            .alias("_signal_abs_change")
        )
        .select("_signal_abs_change")
        .drop_nulls()
    )

    if changes.height == 0:
        return None

    return changes.select(pl.col("_signal_abs_change").mean()).item()


def calculate_signal_return_volatility(
    df: pl.DataFrame,
    signal_column: str = "signal",
    target_column: str = "forward_return",
) -> float | None:
    _require_columns(
        df,
        [signal_column, target_column],
        context="Signal return volatility input",
    )

    active = df.filter(pl.col(signal_column) != 0)

    if active.height < 2:
        return None

    signed_returns = (
        active.select((pl.col(signal_column) * pl.col(target_column)).alias("_r"))
        .drop_nulls()
        .get_column("_r")
        .to_list()
    )

    if len(signed_returns) < 2:
        return None

    return _sample_std([float(value) for value in signed_returns])


def calculate_signal_sharpe_like_score(
    df: pl.DataFrame,
    signal_column: str = "signal",
    target_column: str = "forward_return",
) -> float | None:
    average_signed_return = _mean_expression(
        df.filter(pl.col(signal_column) != 0),
        pl.col(signal_column) * pl.col(target_column),
    )

    volatility = calculate_signal_return_volatility(
        df,
        signal_column=signal_column,
        target_column=target_column,
    )

    if average_signed_return is None or volatility is None or volatility == 0:
        return None

    return average_signed_return / volatility


def _mean(df: pl.DataFrame, column: str) -> float | None:
    if df.height == 0:
        return None

    value = df.select(pl.col(column).mean()).item()

    return None if value is None else float(value)


def _mean_expression(df: pl.DataFrame, expression: pl.Expr) -> float | None:
    if df.height == 0:
        return None

    value = df.select(expression.mean()).item()

    return None if value is None else float(value)


def _pearson_correlation(x: list[float], y: list[float]) -> float | None:
    if len(x) != len(y) or len(x) < 2:
        return None

    x_mean = sum(x) / len(x)
    y_mean = sum(y) / len(y)

    numerator = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, y))
    x_denominator = sqrt(sum((xi - x_mean) ** 2 for xi in x))
    y_denominator = sqrt(sum((yi - y_mean) ** 2 for yi in y))

    denominator = x_denominator * y_denominator

    if denominator == 0:
        return None

    return numerator / denominator


def _sample_std(values: list[float]) -> float | None:
    if len(values) < 2:
        return None

    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)

    return sqrt(variance)


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
