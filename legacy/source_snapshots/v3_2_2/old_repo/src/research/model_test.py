from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

import polars as pl

from src.research.backtest_bridge import (
    BacktestBridgeConfig,
    BacktestBridgeResult,
    build_portfolio_targets_from_evaluation_result,
)
from src.research.backtest_input import (
    BacktestInputConfig,
    BacktestInputPackage,
    build_backtest_input_package,
)
from src.research.backtest_smoke import (
    ResearchBacktestSmokeConfig,
    ResearchBacktestSmokeResult,
    run_research_backtest_smoke,
)


@dataclass(frozen=True)
class ResearchModelTestConfig:
    bridge_config: BacktestBridgeConfig = field(default_factory=BacktestBridgeConfig)
    input_config: BacktestInputConfig = field(default_factory=BacktestInputConfig)
    smoke_config: ResearchBacktestSmokeConfig = field(
        default_factory=ResearchBacktestSmokeConfig
    )
    require_promoted: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.bridge_config, BacktestBridgeConfig):
            raise TypeError("bridge_config must be a BacktestBridgeConfig.")

        if not isinstance(self.input_config, BacktestInputConfig):
            raise TypeError("input_config must be a BacktestInputConfig.")

        if not isinstance(self.smoke_config, ResearchBacktestSmokeConfig):
            raise TypeError("smoke_config must be a ResearchBacktestSmokeConfig.")


@dataclass(frozen=True)
class ResearchModelTestResult:
    bridge_result: BacktestBridgeResult
    input_package: BacktestInputPackage
    smoke_result: ResearchBacktestSmokeResult
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.smoke_result.passed

    @property
    def portfolio_targets(self) -> pl.DataFrame:
        return self.bridge_result.portfolio_targets

    @property
    def backtest_input(self) -> pl.DataFrame:
        return self.input_package.frame

    @property
    def daily_returns(self) -> pl.DataFrame:
        return self.smoke_result.daily_returns

    @property
    def equity_curve(self) -> pl.DataFrame:
        return self.smoke_result.equity_curve

    def summary(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "bridge": self.bridge_result.to_dict(),
            "input": self.input_package.to_dict(),
            "smoke": self.smoke_result.to_dict(),
            "metadata": dict(self.metadata),
        }

    def to_dict(self) -> dict[str, Any]:
        return self.summary()


def run_research_model_test(
    evaluation_result: Any,
    returns: pl.DataFrame,
    config: ResearchModelTestConfig | None = None,
) -> ResearchModelTestResult:
    config = config or ResearchModelTestConfig()

    if not isinstance(returns, pl.DataFrame):
        raise TypeError("returns must be a polars DataFrame.")

    promoted = getattr(evaluation_result, "promoted", None)

    if config.require_promoted and promoted is False:
        raise ValueError("Research model test requires a promoted evaluation result.")

    bridge_result = build_portfolio_targets_from_evaluation_result(
        result=evaluation_result,
        config=config.bridge_config,
    )

    input_package = build_backtest_input_package(
        bridge_result=bridge_result,
        returns=returns,
        config=config.input_config,
    )

    smoke_result = run_research_backtest_smoke(
        package=input_package,
        config=config.smoke_config,
    )

    metadata = {
        "source": "research_model_test",
        "evaluation_result_type": type(evaluation_result).__name__,
        "evaluation_decision": getattr(evaluation_result, "decision", None),
        "evaluation_promoted": promoted,
        "portfolio_target_rows": bridge_result.rows,
        "backtest_input_rows": input_package.rows,
        "daily_return_rows": smoke_result.rows,
    }

    return ResearchModelTestResult(
        bridge_result=bridge_result,
        input_package=input_package,
        smoke_result=smoke_result,
        metadata=metadata,
    )
