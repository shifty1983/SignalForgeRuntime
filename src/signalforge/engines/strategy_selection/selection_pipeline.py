from __future__ import annotations

"""Core strategy-selection pipeline facade.

Stage 19 uses this module as the stable core entry point for strategy-selection
pipeline behavior. It intentionally consolidates existing core helpers instead
of reimplementing selection logic.

The historical backtesting builder may continue to call the lower-level helpers
directly, but paper/live code should prefer this facade when it needs the full
selection pipeline namespace.
"""

from signalforge.engines.strategy_selection.selection_decision import *  # noqa: F401,F403
from signalforge.engines.strategy_selection.selection_report import *  # noqa: F401,F403
from signalforge.engines.strategy_selection.selector import *  # noqa: F401,F403
from signalforge.engines.strategy_selection.rules import *  # noqa: F401,F403
from signalforge.engines.strategy_selection.allocation import *  # noqa: F401,F403
from signalforge.engines.strategy_selection.portfolio_candidate_input import *  # noqa: F401,F403


__all__ = [
    "add_dollar_allocation",
    "add_risk_budget",
    "add_weighted_greek_exposures",
    "allocate_selected_candidates",
    "allocation_summary",
    "allocation_with_greek_exposures",
    "apply_selection_rules",
    "build_signalforge_portfolio_candidate_input",
    "build_strategy_selection_report",
    "cap_allocation_weights",
    "cap_group_allocation_weights",
    "enforce_max_candidates",
    "enforce_max_per_asset_class",
    "enforce_max_per_direction",
    "enforce_max_per_group",
    "enforce_max_per_regime",
    "enforce_max_per_strategy",
    "enforce_max_per_symbol",
    "enforce_rank_cutoff",
    "enforce_single_direction_per_symbol",
    "enforce_unique_candidates",
    "equal_weight_allocation",
    "exclude_strategies",
    "exclude_symbols",
    "greek_exposure_summary",
    "has_valid_selection",
    "inverse_risk_allocation",
    "normalize_allocation_weights",
    "rank_weighted_allocation",
    "risk_adjusted_score_allocation",
    "score_weighted_allocation",
    "select_candidates",
    "select_top_candidate",
    "selection_breakdown",
    "selection_diagnostics",
    "selection_summary",
]
