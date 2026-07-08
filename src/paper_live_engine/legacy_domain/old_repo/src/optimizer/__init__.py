"""
Optimizer layer.

This package turns strategy-selection candidates into an optimized portfolio.

Main components:
- objective.py      -> scores candidates
- constraints.py   -> enforces hard portfolio rules
- portfolio.py     -> standardized optimized portfolio output
- solver.py        -> selects and weights candidates
- rebalance.py     -> compares current vs target portfolios
"""

from src.optimizer.constraints import (
    ConstraintCheckResult,
    ConstraintViolation,
    GreekLimits,
    LiquidityLimits,
    PortfolioConstraintChecker,
    PortfolioConstraints,
    check_candidate_constraints,
    check_portfolio_constraints,
    filter_candidates_by_constraints,
)
from src.optimizer.objective import (
    GreekPenaltyConfig,
    ObjectiveBreakdown,
    ObjectiveConfig,
    ObjectiveWeights,
    OptimizationObjective,
    calculate_objective_score,
    rank_by_objective,
)
from src.optimizer.portfolio import (
    OptimizedPortfolio,
    OptimizedPosition,
    PortfolioGreeks,
    PortfolioSummary,
    build_optimized_portfolio,
)
from src.optimizer.rebalance import (
    PortfolioRebalancer,
    RebalanceConfig,
    RebalanceInstruction,
    RebalancePlan,
    create_rebalance_plan,
)
from src.optimizer.solver import (
    OptimizationSolveResult,
    OptimizerSolver,
    RejectedCandidate,
    SolverConfig,
    solve_optimized_portfolio,
)


__all__ = [
    # Objective
    "ObjectiveWeights",
    "GreekPenaltyConfig",
    "ObjectiveConfig",
    "ObjectiveBreakdown",
    "OptimizationObjective",
    "calculate_objective_score",
    "rank_by_objective",

    # Constraints
    "GreekLimits",
    "LiquidityLimits",
    "PortfolioConstraints",
    "ConstraintViolation",
    "ConstraintCheckResult",
    "PortfolioConstraintChecker",
    "check_candidate_constraints",
    "check_portfolio_constraints",
    "filter_candidates_by_constraints",

    # Portfolio
    "PortfolioGreeks",
    "OptimizedPosition",
    "PortfolioSummary",
    "OptimizedPortfolio",
    "build_optimized_portfolio",

    # Solver
    "SolverConfig",
    "RejectedCandidate",
    "OptimizationSolveResult",
    "OptimizerSolver",
    "solve_optimized_portfolio",

    # Rebalance
    "RebalanceConfig",
    "RebalanceInstruction",
    "RebalancePlan",
    "PortfolioRebalancer",
    "create_rebalance_plan",
]
