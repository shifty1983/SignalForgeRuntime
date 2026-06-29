from src.backtesting.engine import BacktestEngine, BacktestResult
from src.backtesting.performance import (
    PerformanceSummary,
    calmar_ratio,
    cagr,
    compute_returns,
    cumulative_return,
    downside_deviation,
    drawdown_series,
    hit_rate,
    max_drawdown,
    mean_return,
    sharpe_ratio,
    sortino_ratio,
    summarize_performance,
    volatility,
)
from src.backtesting.portfolio import Portfolio, Position, TradeRecord
from src.backtesting.rebalance import (
    RebalanceDecision,
    RebalanceSchedule,
    compute_turnover,
    drift_exceeded,
    evaluate_rebalance,
    gross_exposure,
    max_weight_drift,
    normalize_to_gross_exposure,
    normalize_weights,
    validate_weights,
    weight_deltas,
)
from src.backtesting.transaction_costs import (
    TransactionCostModel,
    commission_cost,
    execution_price,
    infer_trade_side,
    slippage_cost,
    total_transaction_cost,
)
from .research_handoff import (
    MinimalResearchHandoffBacktestResult,
    run_minimal_research_handoff_backtest,
)
from src.backtesting.historical_option_behavior_summary_export import (
    export_historical_option_behavior_summary,
)
from src.backtesting.historical_option_behavior_readiness_review import (
    build_historical_option_behavior_readiness_review,
)
from src.backtesting.historical_option_behavior_dry_run import (
    run_historical_option_behavior_dry_run,
)

__all__ = [
    "BacktestEngine",
    "BacktestResult",
    "Portfolio",
    "Position",
    "TradeRecord",
    "RebalanceSchedule",
    "RebalanceDecision",
    "TransactionCostModel",
    "PerformanceSummary",
    "compute_returns",
    "cumulative_return",
    "mean_return",
    "volatility",
    "downside_deviation",
    "sharpe_ratio",
    "sortino_ratio",
    "drawdown_series",
    "max_drawdown",
    "cagr",
    "calmar_ratio",
    "hit_rate",
    "summarize_performance",
    "normalize_weights",
    "normalize_to_gross_exposure",
    "gross_exposure",
    "validate_weights",
    "weight_deltas",
    "compute_turnover",
    "max_weight_drift",
    "drift_exceeded",
    "evaluate_rebalance",
    "commission_cost",
    "slippage_cost",
    "total_transaction_cost",
    "execution_price",
    "infer_trade_side",
    "MinimalResearchHandoffBacktestResult",
    "run_minimal_research_handoff_backtest",
    "export_historical_option_behavior_summary",
    "build_historical_option_behavior_readiness_review",
    "run_historical_option_behavior_dry_run",
    ]
