from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import polars as pl

from signalforge.engines.strategy_selection.candidates import (
    REQUIRED_CANDIDATE_COLUMNS,
    add_candidate_id,
)


@dataclass(frozen=True)
class CandidateRuleConfig:
    max_candidates: int | None = None
    max_per_symbol: int | None = None
    max_per_strategy: int | None = None
    max_per_regime: int | None = None
    max_per_asset_class: int | None = None
    max_per_direction: int | None = None
    excluded_symbols: Sequence[str] | None = None
    excluded_strategies: Sequence[str] | None = None
    max_rank: int | None = None
    unique_candidates: bool = False
    single_direction_per_symbol: bool = False
    rank_column: str = "rank"
    candidate_id_column: str = "candidate_id"


def _validate_candidate_frame(df: pl.DataFrame) -> None:
    if not isinstance(df, pl.DataFrame):
        raise TypeError("Candidate data must be a Polars DataFrame.")

    missing = REQUIRED_CANDIDATE_COLUMNS - set(df.columns)

    if missing:
        raise ValueError(f"Missing required candidate columns: {sorted(missing)}")


def _validate_positive_int(value: int, name: str) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be greater than 0.")


def _require_column(df: pl.DataFrame, column: str, label: str) -> None:
    if column not in df.columns:
        raise ValueError(f"Missing {label} column: {column}")


def _normalize_label(value: str) -> str:
    return value.strip().replace("-", "_").replace(" ", "_").lower()


def _ordered_candidates(
    df: pl.DataFrame,
    rank_column: str = "rank",
) -> pl.DataFrame:
    """
    Keep candidates in selection order.

    If a rank column exists, lower rank is better.
    Otherwise, fallback to opportunity_score descending.
    """
    _validate_candidate_frame(df)

    if rank_column in df.columns:
        return df.sort(rank_column)

    return df.sort("opportunity_score", descending=True)


def enforce_max_candidates(
    df: pl.DataFrame,
    max_candidates: int,
    rank_column: str = "rank",
) -> pl.DataFrame:
    """
    Keep only the top N candidates.
    """
    _validate_candidate_frame(df)
    _validate_positive_int(max_candidates, "max_candidates")

    return _ordered_candidates(df, rank_column=rank_column).head(max_candidates)


def enforce_max_per_group(
    df: pl.DataFrame,
    group_column: str,
    max_per_group: int,
    rank_column: str = "rank",
) -> pl.DataFrame:
    """
    Limit selected candidates per group.

    Useful for:
    - symbol
    - strategy
    - regime
    - asset_class
    - direction
    """
    _validate_candidate_frame(df)
    _validate_positive_int(max_per_group, "max_per_group")
    _require_column(df, group_column, "group")

    ordered = _ordered_candidates(df, rank_column=rank_column)

    result = ordered.group_by(
        group_column,
        maintain_order=True,
    ).head(max_per_group)

    return _ordered_candidates(result, rank_column=rank_column)


def enforce_max_per_symbol(
    df: pl.DataFrame,
    max_per_symbol: int,
    symbol_column: str = "symbol",
    rank_column: str = "rank",
) -> pl.DataFrame:
    """
    Limit the number of selected candidates per symbol.
    """
    _validate_candidate_frame(df)
    _validate_positive_int(max_per_symbol, "max_per_symbol")
    _require_column(df, symbol_column, "symbol")

    return enforce_max_per_group(
        df,
        group_column=symbol_column,
        max_per_group=max_per_symbol,
        rank_column=rank_column,
    )


def enforce_max_per_strategy(
    df: pl.DataFrame,
    max_per_strategy: int,
    strategy_column: str = "strategy",
    rank_column: str = "rank",
) -> pl.DataFrame:
    """
    Limit the number of selected candidates per strategy.
    """
    _validate_candidate_frame(df)
    _validate_positive_int(max_per_strategy, "max_per_strategy")
    _require_column(df, strategy_column, "strategy")

    return enforce_max_per_group(
        df,
        group_column=strategy_column,
        max_per_group=max_per_strategy,
        rank_column=rank_column,
    )


def enforce_max_per_regime(
    df: pl.DataFrame,
    max_per_regime: int,
    regime_column: str = "regime",
    rank_column: str = "rank",
) -> pl.DataFrame:
    """
    Limit selected candidates per market regime.
    """
    _validate_candidate_frame(df)
    _validate_positive_int(max_per_regime, "max_per_regime")
    _require_column(df, regime_column, "regime")

    return enforce_max_per_group(
        df,
        group_column=regime_column,
        max_per_group=max_per_regime,
        rank_column=rank_column,
    )


def enforce_max_per_asset_class(
    df: pl.DataFrame,
    max_per_asset_class: int,
    asset_class_column: str = "asset_class",
    rank_column: str = "rank",
) -> pl.DataFrame:
    """
    Limit selected candidates per asset class.
    """
    _validate_candidate_frame(df)
    _validate_positive_int(max_per_asset_class, "max_per_asset_class")
    _require_column(df, asset_class_column, "asset_class")

    return enforce_max_per_group(
        df,
        group_column=asset_class_column,
        max_per_group=max_per_asset_class,
        rank_column=rank_column,
    )


def enforce_max_per_direction(
    df: pl.DataFrame,
    max_per_direction: int,
    direction_column: str = "direction",
    rank_column: str = "rank",
) -> pl.DataFrame:
    """
    Limit selected candidates per directional exposure.
    """
    _validate_candidate_frame(df)
    _validate_positive_int(max_per_direction, "max_per_direction")
    _require_column(df, direction_column, "direction")

    return enforce_max_per_group(
        df,
        group_column=direction_column,
        max_per_group=max_per_direction,
        rank_column=rank_column,
    )


def exclude_symbols(
    df: pl.DataFrame,
    symbols: Sequence[str],
    symbol_column: str = "symbol",
    rank_column: str = "rank",
) -> pl.DataFrame:
    """
    Exclude blocked symbols from selection.
    """
    _validate_candidate_frame(df)
    _require_column(df, symbol_column, "symbol")

    if not symbols:
        return _ordered_candidates(df, rank_column=rank_column)

    blocked = [symbol.strip().upper() for symbol in symbols]

    result = df.filter(
        ~pl.col(symbol_column)
        .cast(pl.Utf8)
        .str.strip_chars()
        .str.to_uppercase()
        .is_in(blocked)
    )

    return _ordered_candidates(result, rank_column=rank_column)


def exclude_strategies(
    df: pl.DataFrame,
    strategies: Sequence[str],
    strategy_column: str = "strategy",
    rank_column: str = "rank",
) -> pl.DataFrame:
    """
    Exclude blocked strategies from selection.
    """
    _validate_candidate_frame(df)
    _require_column(df, strategy_column, "strategy")

    if not strategies:
        return _ordered_candidates(df, rank_column=rank_column)

    blocked = [_normalize_label(strategy) for strategy in strategies]

    result = df.filter(
        ~pl.col(strategy_column)
        .cast(pl.Utf8)
        .str.strip_chars()
        .str.replace_all(r"[\s\-]+", "_")
        .str.to_lowercase()
        .is_in(blocked)
    )

    return _ordered_candidates(result, rank_column=rank_column)


def enforce_rank_cutoff(
    df: pl.DataFrame,
    max_rank: int,
    rank_column: str = "rank",
) -> pl.DataFrame:
    """
    Keep only candidates with rank less than or equal to max_rank.
    """
    _validate_candidate_frame(df)
    _validate_positive_int(max_rank, "max_rank")
    _require_column(df, rank_column, "rank")

    return df.filter(pl.col(rank_column) <= max_rank).sort(rank_column)


def enforce_unique_candidates(
    df: pl.DataFrame,
    candidate_id_column: str = "candidate_id",
    rank_column: str = "rank",
) -> pl.DataFrame:
    """
    Keep only one row per candidate_id.

    If candidate_id is missing, it is created from symbol + strategy.
    The best-ranked candidate is kept.
    """
    _validate_candidate_frame(df)

    if df.is_empty():
        return df

    working = df

    if candidate_id_column not in working.columns:
        working = add_candidate_id(
            working,
            candidate_id_column=candidate_id_column,
        )

    ordered = _ordered_candidates(working, rank_column=rank_column)

    return ordered.unique(
        subset=[candidate_id_column],
        keep="first",
        maintain_order=True,
    )


def enforce_single_direction_per_symbol(
    df: pl.DataFrame,
    symbol_column: str = "symbol",
    direction_column: str = "direction",
    rank_column: str = "rank",
) -> pl.DataFrame:
    """
    Prevent conflicting directional exposure within the same symbol.

    For each symbol, the highest-ranked direction is kept.
    Other directions for that same symbol are removed.
    """
    _validate_candidate_frame(df)
    _require_column(df, symbol_column, "symbol")
    _require_column(df, direction_column, "direction")

    if df.is_empty():
        return df

    ordered = _ordered_candidates(df, rank_column=rank_column).with_columns(
        pl.col(direction_column)
        .cast(pl.Utf8)
        .str.strip_chars()
        .str.replace_all(r"[\s\-]+", "_")
        .str.to_lowercase()
        .alias("_direction_normalized")
    )

    primary_direction = ordered.group_by(
        symbol_column,
        maintain_order=True,
    ).agg(
        pl.col("_direction_normalized").first().alias("_primary_direction")
    )

    result = (
        ordered.join(primary_direction, on=symbol_column, how="left")
        .filter(pl.col("_direction_normalized") == pl.col("_primary_direction"))
        .drop(["_direction_normalized", "_primary_direction"])
    )

    return _ordered_candidates(result, rank_column=rank_column)


def apply_selection_rules(
    df: pl.DataFrame,
    max_candidates: int | None = None,
    max_per_symbol: int | None = None,
    max_per_strategy: int | None = None,
    excluded_symbols: Sequence[str] | None = None,
    max_rank: int | None = None,
    rank_column: str = "rank",
    *,
    config: CandidateRuleConfig | None = None,
    max_per_regime: int | None = None,
    max_per_asset_class: int | None = None,
    max_per_direction: int | None = None,
    excluded_strategies: Sequence[str] | None = None,
    unique_candidates: bool | None = None,
    single_direction_per_symbol: bool | None = None,
) -> pl.DataFrame:
    """
    Apply hard selection rules to already-ranked candidates.

    Rule order:
    1. order candidates
    2. exclude blocked symbols/strategies
    3. optionally deduplicate candidates
    4. apply rank cutoff
    5. optionally prevent conflicting symbol directions
    6. apply per-group limits
    7. apply total candidate limit
    """
    _validate_candidate_frame(df)

    cfg = config or CandidateRuleConfig()

    active_rank_column = cfg.rank_column if rank_column == "rank" else rank_column

    max_candidates = (
        cfg.max_candidates if max_candidates is None else max_candidates
    )
    max_per_symbol = (
        cfg.max_per_symbol if max_per_symbol is None else max_per_symbol
    )
    max_per_strategy = (
        cfg.max_per_strategy if max_per_strategy is None else max_per_strategy
    )
    max_per_regime = (
        cfg.max_per_regime if max_per_regime is None else max_per_regime
    )
    max_per_asset_class = (
        cfg.max_per_asset_class
        if max_per_asset_class is None
        else max_per_asset_class
    )
    max_per_direction = (
        cfg.max_per_direction
        if max_per_direction is None
        else max_per_direction
    )
    excluded_symbols = (
        cfg.excluded_symbols if excluded_symbols is None else excluded_symbols
    )
    excluded_strategies = (
        cfg.excluded_strategies
        if excluded_strategies is None
        else excluded_strategies
    )
    max_rank = cfg.max_rank if max_rank is None else max_rank
    unique_candidates = (
        cfg.unique_candidates
        if unique_candidates is None
        else unique_candidates
    )
    single_direction_per_symbol = (
        cfg.single_direction_per_symbol
        if single_direction_per_symbol is None
        else single_direction_per_symbol
    )

    result = _ordered_candidates(df, rank_column=active_rank_column)

    if excluded_symbols is not None:
        result = exclude_symbols(
            result,
            symbols=excluded_symbols,
            rank_column=active_rank_column,
        )

    if excluded_strategies is not None:
        result = exclude_strategies(
            result,
            strategies=excluded_strategies,
            rank_column=active_rank_column,
        )

    if unique_candidates:
        result = enforce_unique_candidates(
            result,
            candidate_id_column=cfg.candidate_id_column,
            rank_column=active_rank_column,
        )

    if max_rank is not None:
        result = enforce_rank_cutoff(
            result,
            max_rank=max_rank,
            rank_column=active_rank_column,
        )

    if single_direction_per_symbol:
        result = enforce_single_direction_per_symbol(
            result,
            rank_column=active_rank_column,
        )

    if max_per_symbol is not None:
        result = enforce_max_per_symbol(
            result,
            max_per_symbol=max_per_symbol,
            rank_column=active_rank_column,
        )

    if max_per_strategy is not None:
        result = enforce_max_per_strategy(
            result,
            max_per_strategy=max_per_strategy,
            rank_column=active_rank_column,
        )

    if max_per_regime is not None:
        result = enforce_max_per_regime(
            result,
            max_per_regime=max_per_regime,
            rank_column=active_rank_column,
        )

    if max_per_asset_class is not None:
        result = enforce_max_per_asset_class(
            result,
            max_per_asset_class=max_per_asset_class,
            rank_column=active_rank_column,
        )

    if max_per_direction is not None:
        result = enforce_max_per_direction(
            result,
            max_per_direction=max_per_direction,
            rank_column=active_rank_column,
        )

    if max_candidates is not None:
        result = enforce_max_candidates(
            result,
            max_candidates=max_candidates,
            rank_column=active_rank_column,
        )

    return result
