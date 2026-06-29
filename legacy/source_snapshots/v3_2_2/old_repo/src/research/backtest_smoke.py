from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping

import polars as pl

from src.research.backtest_input import BacktestInputPackage


@dataclass(frozen=True)
class ResearchBacktestSmokeConfig:
    initial_equity: float = 1.0
    date_column: str = "date"
    symbol_column: str = "symbol"
    target_weight_column: str = "target_weight"
    return_column: str = "return"

    def __post_init__(self) -> None:
        if self.initial_equity <= 0:
            raise ValueError("initial_equity must be greater than zero.")


@dataclass(frozen=True)
class ResearchBacktestSmokeResult:
    daily_returns: pl.DataFrame
    equity_curve: pl.DataFrame
    summary: Mapping[str, Any] = field(default_factory=dict)

    @property
    def rows(self) -> int:
        return self.daily_returns.height

    @property
    def passed(self) -> bool:
        return bool(self.summary.get("passed", False))

    def to_dict(self) -> dict[str, Any]:
        return {
            "rows": self.rows,
            "summary": dict(self.summary),
            "daily_return_columns": self.daily_returns.columns,
            "equity_curve_columns": self.equity_curve.columns,
        }


def run_research_backtest_smoke(
    package: BacktestInputPackage,
    config: ResearchBacktestSmokeConfig | None = None,
) -> ResearchBacktestSmokeResult:
    config = config or ResearchBacktestSmokeConfig()

    frame = package.frame

    _validate_required_columns(
        frame=frame,
        required_columns=(
            config.date_column,
            config.symbol_column,
            config.target_weight_column,
            config.return_column,
        ),
    )

    working = frame.select(
        [
            pl.col(config.date_column).alias("date"),
            pl.col(config.symbol_column).alias("symbol"),
            pl.col(config.target_weight_column)
            .cast(pl.Float64, strict=False)
            .alias("target_weight"),
            pl.col(config.return_column)
            .cast(pl.Float64, strict=False)
            .alias("return"),
        ]
    )

    if working.height == 0:
        raise ValueError("Backtest smoke input frame cannot be empty.")

    invalid_count = working.filter(
        pl.col("target_weight").is_null()
        | pl.col("return").is_null()
        | pl.col("target_weight").is_nan()
        | pl.col("return").is_nan()
    ).height

    if invalid_count:
        raise ValueError(
            f"Backtest smoke input contains {invalid_count} invalid rows."
        )

    contribution_frame = working.with_columns(
        (pl.col("target_weight") * pl.col("return")).alias("weighted_return")
    )

    daily_returns = (
        contribution_frame
        .group_by("date")
        .agg(
            [
                pl.col("weighted_return").sum().alias("portfolio_return"),
                pl.col("target_weight").abs().sum().alias("gross_exposure"),
                pl.col("target_weight").sum().alias("net_exposure"),
                pl.len().alias("position_count"),
            ]
        )
        .sort("date")
    )

    daily_returns = daily_returns.with_columns(
        (1.0 + pl.col("portfolio_return")).cum_prod().alias("_growth")
    )

    equity_curve = daily_returns.select(
        [
            "date",
            (pl.lit(config.initial_equity) * pl.col("_growth")).alias("equity"),
            "portfolio_return",
            "gross_exposure",
            "net_exposure",
            "position_count",
        ]
    )

    returns = daily_returns["portfolio_return"].to_list()
    final_equity = equity_curve["equity"][-1]
    total_return = (final_equity / config.initial_equity) - 1.0
    max_drawdown = _calculate_max_drawdown(equity_curve["equity"].to_list())

    summary = {
        "passed": True,
        "source": "research_backtest_smoke",
        "rows": daily_returns.height,
        "initial_equity": config.initial_equity,
        "final_equity": final_equity,
        "total_return": total_return,
        "mean_daily_return": sum(returns) / len(returns),
        "max_drawdown": max_drawdown,
        "package_metadata": dict(package.metadata),
    }

    return ResearchBacktestSmokeResult(
        daily_returns=daily_returns.select(
            [
                "date",
                "portfolio_return",
                "gross_exposure",
                "net_exposure",
                "position_count",
            ]
        ),
        equity_curve=equity_curve,
        summary=summary,
    )


def _calculate_max_drawdown(equity_values: list[float]) -> float:
    if not equity_values:
        return 0.0

    peak = equity_values[0]
    max_drawdown = 0.0

    for value in equity_values:
        if not math.isfinite(float(value)):
            raise ValueError("Equity curve contains non-finite values.")

        peak = max(peak, value)

        if peak == 0:
            continue

        drawdown = (value / peak) - 1.0
        max_drawdown = min(max_drawdown, drawdown)

    return max_drawdown


def _validate_required_columns(
    frame: pl.DataFrame,
    required_columns: tuple[str, ...],
) -> None:
    missing = [column for column in required_columns if column not in frame.columns]

    if missing:
        raise ValueError(
            f"Backtest smoke input is missing required columns: {missing}"
        )
