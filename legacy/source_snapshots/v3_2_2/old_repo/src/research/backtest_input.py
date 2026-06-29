from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

import polars as pl

from src.research.backtest_bridge import (
    BacktestBridgeResult,
    enforce_backtest_portfolio_targets,
)


@dataclass(frozen=True)
class BacktestInputConfig:
    date_column: str = "date"
    symbol_column: str = "symbol"
    return_column: str = "return"
    target_weight_column: str = "target_weight"
    max_abs_weight: float | None = None
    fill_missing_returns: bool = False
    missing_return_fill_value: float = 0.0

    def __post_init__(self) -> None:
        if self.max_abs_weight is not None and self.max_abs_weight <= 0:
            raise ValueError("max_abs_weight must be greater than zero when provided.")


@dataclass(frozen=True)
class BacktestInputPackage:
    frame: pl.DataFrame
    portfolio_targets: pl.DataFrame
    returns: pl.DataFrame
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def rows(self) -> int:
        return self.frame.height

    @property
    def columns(self) -> list[str]:
        return self.frame.columns

    def to_dict(self) -> dict[str, Any]:
        return {
            "rows": self.rows,
            "columns": self.columns,
            "metadata": dict(self.metadata),
        }


def build_backtest_input_package(
    bridge_result: BacktestBridgeResult,
    returns: pl.DataFrame,
    config: BacktestInputConfig | None = None,
) -> BacktestInputPackage:
    config = config or BacktestInputConfig()

    portfolio_targets = enforce_backtest_portfolio_targets(
        bridge_result.portfolio_targets,
        max_abs_weight=config.max_abs_weight,
    )

    _validate_required_columns(
        returns,
        required_columns=(
            config.date_column,
            config.symbol_column,
            config.return_column,
        ),
        frame_name="returns",
    )

    standardized_returns = returns.select(
        [
            pl.col(config.date_column).alias("date"),
            pl.col(config.symbol_column).alias("symbol"),
            pl.col(config.return_column).cast(pl.Float64, strict=False).alias("return"),
        ]
    )

    frame = portfolio_targets.join(
        standardized_returns,
        on=["date", "symbol"],
        how="left",
    )

    missing_return_count = frame.filter(pl.col("return").is_null()).height

    if missing_return_count and not config.fill_missing_returns:
        raise ValueError(
            f"Backtest input contains {missing_return_count} missing return rows."
        )

    if config.fill_missing_returns:
        frame = frame.with_columns(
            pl.col("return")
            .fill_null(config.missing_return_fill_value)
            .alias("return")
        )

    frame = frame.select(
        [
            "date",
            "symbol",
            "target_weight",
            "return",
        ]
    ).sort(["date", "symbol"])

    metadata = {
        "source": "research_to_backtest_input",
        "bridge_metadata": dict(bridge_result.metadata),
        "rows": frame.height,
        "columns": frame.columns,
        "missing_return_count": missing_return_count,
        "fill_missing_returns": config.fill_missing_returns,
        "missing_return_fill_value": config.missing_return_fill_value,
        "max_abs_weight": config.max_abs_weight,
    }

    return BacktestInputPackage(
        frame=frame,
        portfolio_targets=portfolio_targets,
        returns=standardized_returns,
        metadata=metadata,
    )


def build_backtest_input_from_targets(
    portfolio_targets: pl.DataFrame,
    returns: pl.DataFrame,
    config: BacktestInputConfig | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> BacktestInputPackage:
    bridge_result = BacktestBridgeResult(
        portfolio_targets=portfolio_targets,
        metadata=dict(metadata or {"source": "direct_portfolio_targets"}),
    )

    return build_backtest_input_package(
        bridge_result=bridge_result,
        returns=returns,
        config=config,
    )


def _validate_required_columns(
    df: pl.DataFrame,
    required_columns: tuple[str, ...],
    frame_name: str,
) -> None:
    missing = [column for column in required_columns if column not in df.columns]

    if missing:
        raise ValueError(
            f"{frame_name} is missing required columns: {missing}"
        )
