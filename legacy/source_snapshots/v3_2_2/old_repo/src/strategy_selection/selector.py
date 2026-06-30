from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

import polars as pl

from src.signalforge.engines.strategy_selection.candidates import (
    CandidatePreparationConfig,
    prepare_candidates,
    validate_candidate_data,
)
from src.signalforge.engines.strategy_selection.filters import (
    CandidateFilterConfig,
    apply_candidate_filters,
)
from src.signalforge.engines.strategy_selection.ranking import (
    CandidateRankingConfig,
    add_group_rank,
    add_score_bucket,
    rank_selection_pipeline,
)
from src.signalforge.engines.strategy_selection.rules import (
    CandidateRuleConfig,
    apply_selection_rules,
)


@dataclass(frozen=True)
class StrategySelectionConfig:
    preparation: CandidatePreparationConfig = field(
        default_factory=CandidatePreparationConfig
    )
    filters: CandidateFilterConfig = field(default_factory=CandidateFilterConfig)
    ranking: CandidateRankingConfig = field(default_factory=CandidateRankingConfig)
    rules: CandidateRuleConfig = field(default_factory=CandidateRuleConfig)
    prepare_input: bool = True
    deduplicate_candidates: bool = False
    add_candidate_flags: bool = False
    add_score_buckets: bool = False
    group_rank_column: str | None = None


def select_candidates(
    df: pl.DataFrame,
    *,
    prepare_input: bool = True,
    min_score: float | None = None,
    min_probability: float | None = None,
    max_loss: float | None = None,
    allowed_strategies: Sequence[str] | None = None,
    allowed_regimes: Sequence[str] | None = None,
    weights: Mapping[str, float] | None = None,
    top_n: int | None = None,
    max_candidates: int | None = None,
    max_per_symbol: int | None = None,
    max_per_strategy: int | None = None,
    excluded_symbols: Sequence[str] | None = None,
    max_rank: int | None = None,
    config: StrategySelectionConfig | None = None,
    max_score: float | None = None,
    max_probability: float | None = None,
    min_expected_return: float | None = None,
    min_expected_value: float | None = None,
    min_confidence: float | None = None,
    min_risk_reward: float | None = None,
    min_liquidity_score: float | None = None,
    max_bid_ask_spread_pct: float | None = None,
    min_volume: float | None = None,
    min_open_interest: float | None = None,
    min_days_to_expiration: int | None = None,
    max_days_to_expiration: int | None = None,
    allowed_asset_classes: Sequence[str] | None = None,
    allowed_directions: Sequence[str] | None = None,
    require_selection_eligible: bool | None = None,
    normalized_weights: bool = False,
    max_per_regime: int | None = None,
    max_per_asset_class: int | None = None,
    max_per_direction: int | None = None,
    excluded_strategies: Sequence[str] | None = None,
    unique_candidates: bool | None = None,
    single_direction_per_symbol: bool | None = None,
    min_delta: float | None = None,
    max_delta: float | None = None,
    min_gamma: float | None = None,
    max_gamma: float | None = None,
    min_theta: float | None = None,
    max_theta: float | None = None,
    min_vega: float | None = None,
    max_vega: float | None = None,
    min_rho: float | None = None,
    max_rho: float | None = None,
    min_net_delta: float | None = None,
    max_net_delta: float | None = None,
    min_net_gamma: float | None = None,
    max_net_gamma: float | None = None,
    min_net_theta: float | None = None,
    max_net_theta: float | None = None,
    min_net_vega: float | None = None,
    max_net_vega: float | None = None,
    min_net_rho: float | None = None,
    max_net_rho: float | None = None,
    max_abs_delta: float | None = None,
    max_abs_gamma: float | None = None,
    max_abs_theta: float | None = None,
    max_abs_vega: float | None = None,
    max_abs_rho: float | None = None,
    max_abs_net_delta: float | None = None,
    max_abs_net_gamma: float | None = None,
    max_abs_net_theta: float | None = None,
    max_abs_net_vega: float | None = None,
    max_abs_net_rho: float | None = None,
) -> pl.DataFrame:
    """
    Full strategy-selection pipeline.

    Pipeline:
    1. prepare candidates
    2. apply filters
    3. rank candidates
    4. optionally add score buckets / group ranks
    5. apply hard selection rules
    """
    validate_candidate_data(df)

    cfg = config or StrategySelectionConfig()

    active_prepare_input = cfg.prepare_input if prepare_input is True else prepare_input

    candidates = (
        prepare_candidates(
            df,
            config=cfg.preparation,
            deduplicate=cfg.deduplicate_candidates,
            add_flags=cfg.add_candidate_flags,
        )
        if active_prepare_input
        else df
    )

    filtered = apply_candidate_filters(
        candidates,
        min_score=min_score,
        min_probability=min_probability,
        max_loss=max_loss,
        allowed_strategies=allowed_strategies,
        allowed_regimes=allowed_regimes,
        config=cfg.filters,
        max_score=max_score,
        max_probability=max_probability,
        min_expected_return=min_expected_return,
        min_expected_value=min_expected_value,
        min_confidence=min_confidence,
        min_risk_reward=min_risk_reward,
        min_liquidity_score=min_liquidity_score,
        max_bid_ask_spread_pct=max_bid_ask_spread_pct,
        min_volume=min_volume,
        min_open_interest=min_open_interest,
        min_days_to_expiration=min_days_to_expiration,
        max_days_to_expiration=max_days_to_expiration,
        allowed_asset_classes=allowed_asset_classes,
        allowed_directions=allowed_directions,
        require_selection_eligible=require_selection_eligible,
        min_delta=min_delta,
        max_delta=max_delta,
        min_gamma=min_gamma,
        max_gamma=max_gamma,
        min_theta=min_theta,
        max_theta=max_theta,
        min_vega=min_vega,
        max_vega=max_vega,
        min_rho=min_rho,
        max_rho=max_rho,
        min_net_delta=min_net_delta,
        max_net_delta=max_net_delta,
        min_net_gamma=min_net_gamma,
        max_net_gamma=max_net_gamma,
        min_net_theta=min_net_theta,
        max_net_theta=max_net_theta,
        min_net_vega=min_net_vega,
        max_net_vega=max_net_vega,
        min_net_rho=min_net_rho,
        max_net_rho=max_net_rho,
        max_abs_delta=max_abs_delta,
        max_abs_gamma=max_abs_gamma,
        max_abs_theta=max_abs_theta,
        max_abs_vega=max_abs_vega,
        max_abs_rho=max_abs_rho,
        max_abs_net_delta=max_abs_net_delta,
        max_abs_net_gamma=max_abs_net_gamma,
        max_abs_net_theta=max_abs_net_theta,
        max_abs_net_vega=max_abs_net_vega,
        max_abs_net_rho=max_abs_net_rho,
    )

    if filtered.is_empty():
        return filtered

    ranked = rank_selection_pipeline(
        filtered,
        weights=weights,
        top_n=top_n,
        config=cfg.ranking,
        normalized_weights=normalized_weights,
    )

    if cfg.add_score_buckets:
        score_column = (
            cfg.ranking.weighted_score_column
            if weights is not None or cfg.ranking.weights is not None
            else list(cfg.ranking.sort_columns)[0]
        )
        ranked = add_score_bucket(ranked, score_column=score_column)

    if cfg.group_rank_column is not None:
        ranked = add_group_rank(
            ranked,
            group_column=cfg.group_rank_column,
            score_column=(
                cfg.ranking.weighted_score_column
                if weights is not None or cfg.ranking.weights is not None
                else list(cfg.ranking.sort_columns)[0]
            ),
        )

    selected = apply_selection_rules(
        ranked,
        max_candidates=max_candidates,
        max_per_symbol=max_per_symbol,
        max_per_strategy=max_per_strategy,
        excluded_symbols=excluded_symbols,
        max_rank=max_rank,
        config=cfg.rules,
        max_per_regime=max_per_regime,
        max_per_asset_class=max_per_asset_class,
        max_per_direction=max_per_direction,
        excluded_strategies=excluded_strategies,
        unique_candidates=unique_candidates,
        single_direction_per_symbol=single_direction_per_symbol,
    )

    return selected


def select_top_candidate(
    df: pl.DataFrame,
    *,
    prepare_input: bool = True,
    min_score: float | None = None,
    min_probability: float | None = None,
    max_loss: float | None = None,
    allowed_strategies: Sequence[str] | None = None,
    allowed_regimes: Sequence[str] | None = None,
    weights: Mapping[str, float] | None = None,
) -> pl.DataFrame:
    """
    Select the single highest-ranked candidate.
    """
    return select_candidates(
        df,
        prepare_input=prepare_input,
        min_score=min_score,
        min_probability=min_probability,
        max_loss=max_loss,
        allowed_strategies=allowed_strategies,
        allowed_regimes=allowed_regimes,
        weights=weights,
        max_candidates=1,
    )


def has_valid_selection(df: pl.DataFrame) -> bool:
    """
    Return True when the selection output contains at least one candidate.
    """
    return not df.is_empty()


def selection_summary(
    df: pl.DataFrame,
    symbol_column: str = "symbol",
    strategy_column: str = "strategy",
) -> dict[str, int]:
    """
    Summarize the number of selected candidates.
    """
    if df.is_empty():
        return {
            "total_selected": 0,
            "unique_symbols": 0,
            "unique_strategies": 0,
        }

    if symbol_column not in df.columns:
        raise ValueError(f"Missing symbol column: {symbol_column}")

    if strategy_column not in df.columns:
        raise ValueError(f"Missing strategy column: {strategy_column}")

    return {
        "total_selected": df.height,
        "unique_symbols": df.select(pl.col(symbol_column).n_unique()).item(),
        "unique_strategies": df.select(pl.col(strategy_column).n_unique()).item(),
    }


def selection_breakdown(
    df: pl.DataFrame,
    group_columns: Sequence[str],
) -> pl.DataFrame:
    """
    Return counts by one or more grouping columns.
    """
    if df.is_empty():
        return pl.DataFrame(
            {
                "selected_count": [],
            }
        )

    missing = [column for column in group_columns if column not in df.columns]

    if missing:
        raise ValueError(f"Missing breakdown columns: {missing}")

    return (
        df.group_by(list(group_columns))
        .agg(pl.len().alias("selected_count"))
        .sort("selected_count", descending=True)
    )


def selection_diagnostics(
    df: pl.DataFrame,
    score_column: str = "opportunity_score",
    weight_column: str = "target_weight",
) -> dict[str, float | int]:
    """
    Return lightweight diagnostics for selected candidates.
    """
    if df.is_empty():
        return {
            "total_selected": 0,
            "average_score": 0.0,
            "max_score": 0.0,
            "min_score": 0.0,
            "total_weight": 0.0,
        }

    if score_column not in df.columns:
        raise ValueError(f"Missing score column: {score_column}")

    total_weight = (
        float(df.select(pl.col(weight_column).sum()).item())
        if weight_column in df.columns
        else 0.0
    )

    return {
        "total_selected": df.height,
        "average_score": float(df.select(pl.col(score_column).mean()).item()),
        "max_score": float(df.select(pl.col(score_column).max()).item()),
        "min_score": float(df.select(pl.col(score_column).min()).item()),
        "total_weight": total_weight,
    }
