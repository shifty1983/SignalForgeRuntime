from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping
from typing import Any
from enum import Enum

from datetime import date as Date
from datetime import datetime, time

from src.backtesting.engine import BacktestEngine, BacktestResult
from src.backtesting.portfolio import Portfolio
from src.backtesting.rebalance import RebalanceSchedule

import polars as pl
import math


@dataclass(frozen=True)
class BacktestBridgeConfig:
    date_column: str = "date"
    symbol_column: str = "symbol"
    signal_column: str = "signal"
    target_weight_column: str = "target_weight"
    max_abs_weight: float = 0.10
    allow_short: bool = True

    def __post_init__(self) -> None:
        if self.max_abs_weight <= 0:
            raise ValueError("max_abs_weight must be greater than zero.")

class BacktestHandoffStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    
@dataclass(frozen=True)
class BacktestBridgeResult:
    portfolio_targets: pl.DataFrame
    metadata: Mapping[str, Any]

    @property
    def rows(self) -> int:
        return self.portfolio_targets.height

    @property
    def columns(self) -> list[str]:
        return self.portfolio_targets.columns

    def to_dict(self) -> dict[str, Any]:
        return {
            "rows": self.rows,
            "columns": self.columns,
            "metadata": dict(self.metadata),
        }

@dataclass(frozen=True)
class BacktestHandoffCheck:
    name: str
    passed: bool
    status: BacktestHandoffStatus
    message: str
    details: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class BacktestHandoffContractResult:
    checks: tuple[BacktestHandoffCheck, ...]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def failures(self) -> tuple[BacktestHandoffCheck, ...]:
        return tuple(check for check in self.checks if not check.passed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "checks": [
                {
                    "name": check.name,
                    "passed": check.passed,
                    "status": check.status.value,
                    "message": check.message,
                    "details": dict(check.details or {}),
                }
                for check in self.checks
            ],
        }


class BacktestHandoffContractError(ValueError):
    """Raised when portfolio targets are not safe to hand off to backtesting."""

def build_portfolio_targets_from_signals(
    df: pl.DataFrame,
    config: BacktestBridgeConfig | None = None,
) -> BacktestBridgeResult:
    config = config or BacktestBridgeConfig()

    _validate_required_columns(
        df=df,
        columns=(
            config.date_column,
            config.symbol_column,
            config.signal_column,
        ),
    )

    working = df.select(
        [
            pl.col(config.date_column).alias("date"),
            pl.col(config.symbol_column).alias("symbol"),
            pl.col(config.signal_column).alias("signal"),
        ]
    )

    working = working.with_columns(
        pl.col("signal").cast(pl.Float64, strict=False).alias("signal")
    )

    if not config.allow_short:
        working = working.with_columns(
            pl.when(pl.col("signal") < 0)
            .then(0.0)
            .otherwise(pl.col("signal"))
            .alias("signal")
        )

    working = working.with_columns(
        pl.col("signal").abs().sum().over("date").alias("_gross_signal")
    )

    targets = working.with_columns(
        pl.when(pl.col("_gross_signal") > 0)
        .then(pl.col("signal") / pl.col("_gross_signal"))
        .otherwise(0.0)
        .alias("target_weight")
    )

    targets = targets.with_columns(
        pl.when(pl.col("target_weight") > config.max_abs_weight)
        .then(config.max_abs_weight)
        .when(pl.col("target_weight") < -config.max_abs_weight)
        .then(-config.max_abs_weight)
        .otherwise(pl.col("target_weight"))
        .alias("target_weight")
    )

    portfolio_targets = targets.select(
        [
            "date",
            "symbol",
            "target_weight",
        ]
    ).sort(["date", "symbol"])
    
    portfolio_targets = enforce_backtest_portfolio_targets(
        portfolio_targets,
        max_abs_weight=config.max_abs_weight,   
    )

    metadata = {
        "source": "research_signals",
        "date_column": config.date_column,
        "symbol_column": config.symbol_column,
        "signal_column": config.signal_column,
        "target_weight_column": config.target_weight_column,
        "max_abs_weight": config.max_abs_weight,
        "allow_short": config.allow_short,
        "rows": portfolio_targets.height,
    }

    return BacktestBridgeResult(
        portfolio_targets=portfolio_targets,
        metadata=metadata,
    )


def build_portfolio_targets_from_existing_weights(
    df: pl.DataFrame,
    config: BacktestBridgeConfig | None = None,
) -> BacktestBridgeResult:
    config = config or BacktestBridgeConfig()

    _validate_required_columns(
        df=df,
        columns=(
            config.date_column,
            config.symbol_column,
            config.target_weight_column,
        ),
    )

    portfolio_targets = df.select(
        [
            pl.col(config.date_column).alias("date"),
            pl.col(config.symbol_column).alias("symbol"),
            pl.col(config.target_weight_column)
            .cast(pl.Float64, strict=False)
            .alias("target_weight"),
        ]
    ).sort(["date", "symbol"])

    portfolio_targets = portfolio_targets.with_columns(
        pl.when(pl.col("target_weight") > config.max_abs_weight)
        .then(config.max_abs_weight)
        .when(pl.col("target_weight") < -config.max_abs_weight)
        .then(-config.max_abs_weight)
        .otherwise(pl.col("target_weight"))
        .alias("target_weight")
    )
    
    portfolio_targets = enforce_backtest_portfolio_targets(
        portfolio_targets,
        max_abs_weight=config.max_abs_weight,
    )
    metadata = {
        "source": "existing_target_weights",
        "date_column": config.date_column,
        "symbol_column": config.symbol_column,
        "target_weight_column": config.target_weight_column,
        "max_abs_weight": config.max_abs_weight,
        "rows": portfolio_targets.height,
    }

    return BacktestBridgeResult(
        portfolio_targets=portfolio_targets,
        metadata=metadata,
    )


def build_backtest_ready_portfolio_targets(
    df: pl.DataFrame,
    config: BacktestBridgeConfig | None = None,
) -> BacktestBridgeResult:
    config = config or BacktestBridgeConfig()

    if config.target_weight_column in df.columns:
        return build_portfolio_targets_from_existing_weights(df=df, config=config)

    return build_portfolio_targets_from_signals(df=df, config=config)

def build_portfolio_targets_from_evaluation_result(
    result: Any,
    config: BacktestBridgeConfig | None = None,
) -> BacktestBridgeResult:
    if not hasattr(result, "output"):
        raise TypeError("result must expose an output dataframe.")

    output = result.output

    if not isinstance(output, pl.DataFrame):
        raise TypeError("result.output must be a polars DataFrame.")

    bridge_result = build_backtest_ready_portfolio_targets(
        df=output,
        config=config,
    )

    metadata = {
        **dict(bridge_result.metadata),
        "source_result_type": type(result).__name__,
        "evaluation_decision": getattr(result, "decision", None),
        "evaluation_promoted": getattr(result, "promoted", None),
    }

    return BacktestBridgeResult(
        portfolio_targets=bridge_result.portfolio_targets,
        metadata=metadata,
    )

def validate_backtest_portfolio_targets(
    portfolio_targets: pl.DataFrame,
    max_abs_weight: float | None = None,
) -> BacktestHandoffContractResult:
    checks: list[BacktestHandoffCheck] = []

    required_columns = ("date", "symbol", "target_weight")
    missing_columns = [
        column for column in required_columns if column not in portfolio_targets.columns
    ]

    checks.append(
        BacktestHandoffCheck(
            name="required_columns",
            passed=not missing_columns,
            status=(
                BacktestHandoffStatus.PASS
                if not missing_columns
                else BacktestHandoffStatus.FAIL
            ),
            message=(
                "Portfolio targets contain required columns."
                if not missing_columns
                else "Portfolio targets are missing required columns."
            ),
            details={"missing_columns": missing_columns},
        )
    )

    if missing_columns:
        return BacktestHandoffContractResult(checks=tuple(checks))

    checks.append(
        BacktestHandoffCheck(
            name="non_empty",
            passed=portfolio_targets.height > 0,
            status=(
                BacktestHandoffStatus.PASS
                if portfolio_targets.height > 0
                else BacktestHandoffStatus.FAIL
            ),
            message=(
                "Portfolio targets are non-empty."
                if portfolio_targets.height > 0
                else "Portfolio targets are empty."
            ),
            details={"rows": portfolio_targets.height},
        )
    )

    duplicate_count = (
        portfolio_targets
        .group_by(["date", "symbol"])
        .len()
        .filter(pl.col("len") > 1)
        .height
    )

    checks.append(
        BacktestHandoffCheck(
            name="unique_date_symbol",
            passed=duplicate_count == 0,
            status=(
                BacktestHandoffStatus.PASS
                if duplicate_count == 0
                else BacktestHandoffStatus.FAIL
            ),
            message=(
                "Portfolio targets have unique date-symbol rows."
                if duplicate_count == 0
                else "Portfolio targets contain duplicate date-symbol rows."
            ),
            details={"duplicate_count": duplicate_count},
        )
    )

    records = portfolio_targets.select(["date", "symbol", "target_weight"]).to_dicts()

    null_weight_count = sum(
        1 for row in records if row["target_weight"] is None
    )

    non_finite_weight_count = sum(
        1
        for row in records
        if row["target_weight"] is not None
        and not math.isfinite(float(row["target_weight"]))
    )

    checks.append(
        BacktestHandoffCheck(
            name="target_weight_not_null",
            passed=null_weight_count == 0,
            status=(
                BacktestHandoffStatus.PASS
                if null_weight_count == 0
                else BacktestHandoffStatus.FAIL
            ),
            message=(
                "Target weights contain no null values."
                if null_weight_count == 0
                else "Target weights contain null values."
            ),
            details={"null_weight_count": null_weight_count},
        )
    )

    checks.append(
        BacktestHandoffCheck(
            name="target_weight_finite",
            passed=non_finite_weight_count == 0,
            status=(
                BacktestHandoffStatus.PASS
                if non_finite_weight_count == 0
                else BacktestHandoffStatus.FAIL
            ),
            message=(
                "Target weights are finite."
                if non_finite_weight_count == 0
                else "Target weights contain non-finite values."
            ),
            details={"non_finite_weight_count": non_finite_weight_count},
        )
    )

    if max_abs_weight is not None:
        breach_count = sum(
            1
            for row in records
            if row["target_weight"] is not None
            and math.isfinite(float(row["target_weight"]))
            and abs(float(row["target_weight"])) > max_abs_weight
        )

        checks.append(
            BacktestHandoffCheck(
                name="max_abs_weight",
                passed=breach_count == 0,
                status=(
                    BacktestHandoffStatus.PASS
                    if breach_count == 0
                    else BacktestHandoffStatus.FAIL
                ),
                message=(
                    "Target weights are within max absolute weight."
                    if breach_count == 0
                    else "Target weights exceed max absolute weight."
                ),
                details={
                    "max_abs_weight": max_abs_weight,
                    "breach_count": breach_count,
                },
            )
        )

    return BacktestHandoffContractResult(checks=tuple(checks))


def enforce_backtest_portfolio_targets(
    portfolio_targets: pl.DataFrame,
    max_abs_weight: float | None = None,
) -> pl.DataFrame:
    result = validate_backtest_portfolio_targets(
        portfolio_targets=portfolio_targets,
        max_abs_weight=max_abs_weight,
    )

    if not result.passed:
        messages = "; ".join(check.message for check in result.failures)
        raise BacktestHandoffContractError(
            f"Backtest portfolio target handoff failed: {messages}"
        )

    return portfolio_targets

def _validate_required_columns(
    df: pl.DataFrame,
    columns: tuple[str, ...],
) -> None:
    missing = [column for column in columns if column not in df.columns]

    if missing:
        raise ValueError(
            f"Missing required columns for research-to-backtesting bridge: {missing}"
        )
        
REQUIRED_PORTFOLIO_TARGET_COLUMNS = {
    "date",
    "symbol",
    "target_weight",
}


def research_output_has_portfolio_targets(
    research_output: Mapping[str, Any],
) -> bool:
    """
    Return True when research evaluation output contains portfolio targets.
    """

    portfolio_targets = research_output.get("portfolio_targets")

    return isinstance(portfolio_targets, list) and len(portfolio_targets) > 0


def portfolio_targets_from_research_output(
    research_output: Mapping[str, Any],
) -> pl.DataFrame:
    """
    Extract portfolio targets from research evaluation output.

    This produces the bridge object expected by downstream backtesting layers:
    date, symbol, target_weight.
    """

    if not research_output_has_portfolio_targets(research_output):
        raise ValueError("Research output does not contain portfolio_targets.")

    portfolio_targets = research_output["portfolio_targets"]

    frame = pl.DataFrame(portfolio_targets)

    missing = REQUIRED_PORTFOLIO_TARGET_COLUMNS.difference(frame.columns)

    if missing:
        raise ValueError(
            f"Portfolio targets are missing required columns: {sorted(missing)}"
        )

    return frame.select(
        [
            "date",
            "symbol",
            "target_weight",
        ]
    )


def validate_backtest_target_frame(
    targets: pl.DataFrame,
) -> bool:
    """
    Validate the minimal portfolio target contract needed for backtesting.
    """

    missing = REQUIRED_PORTFOLIO_TARGET_COLUMNS.difference(targets.columns)

    if missing:
        raise ValueError(
            f"Backtest target frame is missing required columns: {sorted(missing)}"
        )

    if targets.is_empty():
        raise ValueError("Backtest target frame is empty.")

    invalid_weights = targets.filter(
        pl.col("target_weight").is_null()
        | pl.col("target_weight").is_nan()
    )

    if invalid_weights.height > 0:
        raise ValueError("Backtest target frame contains invalid target weights.")

    return True


def build_backtest_targets_from_research_output(
    research_output: Mapping[str, Any],
) -> pl.DataFrame:
    """
    Build a validated backtesting target frame from research evaluation output.
    """

    targets = portfolio_targets_from_research_output(research_output)
    validate_backtest_target_frame(targets)

    return targets

def _coerce_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value

    if isinstance(value, Date):
        return datetime.combine(value, time.min)

    if isinstance(value, str):
        return datetime.fromisoformat(value)

    raise TypeError(f"Unsupported date value type: {type(value).__name__}")


def target_weight_dict_from_frame(
    targets: pl.DataFrame,
    date_column: str = "date",
    symbol_column: str = "symbol",
    weight_column: str = "target_weight",
) -> dict[datetime, dict[str, float]]:
    """
    Convert a validated target frame into BacktestEngine target_weights input.
    """

    missing = {date_column, symbol_column, weight_column}.difference(targets.columns)

    if missing:
        raise ValueError(
            f"Target frame is missing required columns: {sorted(missing)}"
        )

    target_weights: dict[datetime, dict[str, float]] = {}

    for row in targets.to_dicts():
        date = _coerce_datetime(row[date_column])
        symbol = str(row[symbol_column]).upper()
        weight = row[weight_column]

        if weight is None:
            raise ValueError("Target weight cannot be null.")

        target_weights.setdefault(date, {})[symbol] = float(weight)

    return target_weights


def price_dict_from_frame(
    prices: pl.DataFrame,
    date_column: str = "date",
    symbol_column: str = "symbol",
    price_column: str = "close",
) -> dict[datetime, dict[str, float]]:
    """
    Convert market prices into BacktestEngine prices input.
    """

    missing = {date_column, symbol_column, price_column}.difference(prices.columns)

    if missing:
        raise ValueError(
            f"Price frame is missing required columns: {sorted(missing)}"
        )

    price_dict: dict[datetime, dict[str, float]] = {}

    for row in prices.to_dicts():
        date = _coerce_datetime(row[date_column])
        symbol = str(row[symbol_column]).upper()
        price = row[price_column]

        if price is None:
            raise ValueError("Price cannot be null.")

        price_float = float(price)

        if price_float <= 0:
            raise ValueError("Price must be greater than zero.")

        price_dict.setdefault(date, {})[symbol] = price_float

    return price_dict


def dates_from_price_frame(
    prices: pl.DataFrame,
    date_column: str = "date",
) -> list[datetime]:
    """
    Build sorted backtest dates from a price frame.
    """

    if date_column not in prices.columns:
        raise ValueError(f"Price frame is missing date column: {date_column}")

    dates = {
        _coerce_datetime(value)
        for value in prices[date_column].to_list()
    }

    return sorted(dates)


def run_backtest_from_research_output(
    research_output: Mapping[str, Any],
    prices: pl.DataFrame,
    initial_cash: float = 100_000.0,
    rebalance_frequency: str = "daily",
    price_column: str = "close",
    date_column: str = "date",
    symbol_column: str = "symbol",
    drift_threshold: float | None = None,
) -> BacktestResult:
    """
    Run the backtest engine directly from research evaluation output.

    Research output supplies portfolio targets.
    Price frame supplies market prices.
    """

    targets = build_backtest_targets_from_research_output(research_output)

    dates = dates_from_price_frame(
        prices=prices,
        date_column=date_column,
    )

    price_dict = price_dict_from_frame(
        prices=prices,
        date_column=date_column,
        symbol_column=symbol_column,
        price_column=price_column,
    )

    target_weights = target_weight_dict_from_frame(
        targets=targets,
        date_column=date_column,
        symbol_column=symbol_column,
        weight_column="target_weight",
    )

    engine = BacktestEngine(
        portfolio=Portfolio(cash=initial_cash),
        schedule=RebalanceSchedule(frequency=rebalance_frequency),
        drift_threshold=drift_threshold,
    )

    return engine.run(
        dates=dates,
        prices=price_dict,
        target_weights=target_weights,
    )
