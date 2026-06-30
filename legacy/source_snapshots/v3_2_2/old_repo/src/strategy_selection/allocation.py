from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import polars as pl

from src.signalforge.engines.strategy_selection.candidates import validate_candidate_data


@dataclass(frozen=True)
class CandidateAllocationConfig:
    method: str = "score"
    total_capital: float | None = None
    total_risk_budget: float | None = None
    max_weight: float | None = None
    max_symbol_weight: float | None = None
    max_strategy_weight: float | None = None
    max_regime_weight: float | None = None
    max_asset_class_weight: float | None = None
    target_gross_exposure: float = 1.0
    score_column: str = "opportunity_score"
    rank_column: str = "rank"
    risk_column: str = "max_loss"
    weight_column: str = "target_weight"
    allocation_column: str = "target_allocation"
    risk_budget_column: str = "target_risk_budget"


def _validate_weight_column(
    df: pl.DataFrame,
    weight_column: str,
) -> None:
    if weight_column not in df.columns:
        raise ValueError(f"Missing weight column: {weight_column}")


def _require_column(
    df: pl.DataFrame,
    column: str,
    label: str,
) -> None:
    if column not in df.columns:
        raise ValueError(f"Missing {label} column: {column}")


def _validate_positive(value: float, name: str) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be greater than 0.")


def _weight_values(df: pl.DataFrame, weight_column: str) -> list[float]:
    _validate_weight_column(df, weight_column)

    weights = [
        0.0 if value is None else float(value)
        for value in df[weight_column].to_list()
    ]

    if any(weight < 0 for weight in weights):
        raise ValueError("Weights cannot be negative.")

    return weights


def normalize_allocation_weights(
    df: pl.DataFrame,
    source_column: str = "target_weight",
    weight_column: str = "target_weight",
    target_gross_exposure: float = 1.0,
) -> pl.DataFrame:
    """
    Normalize an existing weight column so weights sum to target_gross_exposure.
    """
    validate_candidate_data(df)
    _validate_positive(target_gross_exposure, "target_gross_exposure")

    weights = _weight_values(df, source_column)
    total_weight = sum(weights)

    if total_weight <= 0:
        raise ValueError("Total weight must be greater than 0.")

    normalized = [
        weight / total_weight * target_gross_exposure
        for weight in weights
    ]

    return df.with_columns(pl.Series(weight_column, normalized))


def equal_weight_allocation(
    df: pl.DataFrame,
    weight_column: str = "target_weight",
    target_gross_exposure: float = 1.0,
) -> pl.DataFrame:
    """
    Assign equal portfolio weight to each selected candidate.
    """
    validate_candidate_data(df)
    _validate_positive(target_gross_exposure, "target_gross_exposure")

    weight = target_gross_exposure / df.height

    return df.with_columns(
        pl.lit(weight).alias(weight_column)
    )


def score_weighted_allocation(
    df: pl.DataFrame,
    score_column: str = "opportunity_score",
    weight_column: str = "target_weight",
    target_gross_exposure: float = 1.0,
) -> pl.DataFrame:
    """
    Allocate weights proportional to a score column.

    Negative or null scores are treated as zero.
    """
    validate_candidate_data(df)
    _validate_positive(target_gross_exposure, "target_gross_exposure")

    if score_column not in df.columns:
        raise ValueError(f"Missing score column: {score_column}")

    score_expr = pl.col(score_column).cast(pl.Float64, strict=False).fill_null(0.0)

    scored = df.with_columns(
        pl.when(score_expr < 0.0)
        .then(0.0)
        .otherwise(score_expr)
        .alias("_allocation_score")
    )

    total_score = scored.select(pl.col("_allocation_score").sum()).item()

    if total_score <= 0:
        raise ValueError("Total allocation score must be greater than 0.")

    return (
        scored.with_columns(
            (
                pl.col("_allocation_score")
                / total_score
                * target_gross_exposure
            ).alias(weight_column)
        )
        .drop("_allocation_score")
    )


def rank_weighted_allocation(
    df: pl.DataFrame,
    rank_column: str = "rank",
    weight_column: str = "target_weight",
    target_gross_exposure: float = 1.0,
) -> pl.DataFrame:
    """
    Allocate more weight to higher-ranked candidates.

    Rank 1 receives the highest weight.
    """
    validate_candidate_data(df)
    _validate_positive(target_gross_exposure, "target_gross_exposure")

    if rank_column not in df.columns:
        raise ValueError(f"Missing rank column: {rank_column}")

    min_rank = df.select(pl.col(rank_column).min()).item()

    if min_rank <= 0:
        raise ValueError("Ranks must be greater than 0.")

    ranked = df.with_columns(
        (1.0 / pl.col(rank_column).cast(pl.Float64)).alias("_allocation_score")
    )

    total_score = ranked.select(pl.col("_allocation_score").sum()).item()

    return (
        ranked.with_columns(
            (
                pl.col("_allocation_score")
                / total_score
                * target_gross_exposure
            ).alias(weight_column)
        )
        .drop("_allocation_score")
    )


def inverse_risk_allocation(
    df: pl.DataFrame,
    risk_column: str = "max_loss",
    weight_column: str = "target_weight",
    target_gross_exposure: float = 1.0,
) -> pl.DataFrame:
    """
    Allocate more weight to candidates with lower defined risk.

    Example:
    lower max_loss receives a higher allocation weight.
    """
    validate_candidate_data(df)
    _validate_positive(target_gross_exposure, "target_gross_exposure")
    _require_column(df, risk_column, "risk")

    risk_values = df.with_columns(
        pl.col(risk_column).cast(pl.Float64, strict=False).alias("_risk")
    )

    invalid = risk_values.filter(
        pl.col("_risk").is_null() | (pl.col("_risk") <= 0)
    )

    if invalid.height > 0:
        raise ValueError(f"{risk_column} must be greater than 0.")

    scored = risk_values.with_columns(
        (1.0 / pl.col("_risk")).alias("_allocation_score")
    )

    total_score = scored.select(pl.col("_allocation_score").sum()).item()

    return (
        scored.with_columns(
            (
                pl.col("_allocation_score")
                / total_score
                * target_gross_exposure
            ).alias(weight_column)
        )
        .drop(["_risk", "_allocation_score"])
    )


def risk_adjusted_score_allocation(
    df: pl.DataFrame,
    score_column: str = "opportunity_score",
    risk_column: str = "max_loss",
    weight_column: str = "target_weight",
    target_gross_exposure: float = 1.0,
) -> pl.DataFrame:
    """
    Allocate by score per unit of defined risk.

    Formula:
    allocation_score = positive_score / max_loss
    """
    validate_candidate_data(df)
    _validate_positive(target_gross_exposure, "target_gross_exposure")
    _require_column(df, score_column, "score")
    _require_column(df, risk_column, "risk")

    scored = df.with_columns(
        pl.col(score_column)
        .cast(pl.Float64, strict=False)
        .fill_null(0.0)
        .alias("_score"),
        pl.col(risk_column)
        .cast(pl.Float64, strict=False)
        .alias("_risk"),
    ).with_columns(
        pl.when((pl.col("_score") > 0) & (pl.col("_risk") > 0))
        .then(pl.col("_score") / pl.col("_risk"))
        .otherwise(0.0)
        .alias("_allocation_score")
    )

    total_score = scored.select(pl.col("_allocation_score").sum()).item()

    if total_score <= 0:
        raise ValueError("Total risk-adjusted allocation score must be greater than 0.")

    return (
        scored.with_columns(
            (
                pl.col("_allocation_score")
                / total_score
                * target_gross_exposure
            ).alias(weight_column)
        )
        .drop(["_score", "_risk", "_allocation_score"])
    )


def cap_allocation_weights(
    df: pl.DataFrame,
    max_weight: float,
    weight_column: str = "target_weight",
) -> pl.DataFrame:
    """
    Cap individual allocation weights and redistribute excess to uncapped rows.

    The final weights preserve the original total portfolio weight.
    """
    validate_candidate_data(df)
    _validate_weight_column(df, weight_column)

    if max_weight <= 0:
        raise ValueError("max_weight must be greater than 0.")

    weights = _weight_values(df, weight_column)
    total_weight = sum(weights)

    if total_weight <= 0:
        raise ValueError("Total weight must be greater than 0.")

    if max_weight * df.height < total_weight:
        raise ValueError("max_weight is too low for the number of candidates.")

    normalized = [weight / total_weight * total_weight for weight in weights]
    final_weights = [0.0 for _ in normalized]
    remaining = set(range(len(normalized)))

    while remaining:
        fixed_weight = sum(
            final_weights[index]
            for index in range(len(final_weights))
            if index not in remaining
        )

        available_weight = total_weight - fixed_weight
        remaining_original_weight = sum(normalized[index] for index in remaining)

        proposed = {
            index: normalized[index] / remaining_original_weight * available_weight
            for index in remaining
        }

        capped = [
            index
            for index, proposed_weight in proposed.items()
            if proposed_weight > max_weight
        ]

        if not capped:
            for index, proposed_weight in proposed.items():
                final_weights[index] = proposed_weight
            break

        for index in capped:
            final_weights[index] = max_weight
            remaining.remove(index)

    return df.with_columns(
        pl.Series(weight_column, final_weights)
    )


def cap_group_allocation_weights(
    df: pl.DataFrame,
    group_column: str,
    max_group_weight: float,
    weight_column: str = "target_weight",
) -> pl.DataFrame:
    """
    Cap total allocation weight for a group and redistribute excess.

    Useful group columns:
    - symbol
    - strategy
    - regime
    - asset_class
    """
    validate_candidate_data(df)
    _validate_weight_column(df, weight_column)
    _require_column(df, group_column, "group")

    if max_group_weight <= 0:
        raise ValueError("max_group_weight must be greater than 0.")

    weights = _weight_values(df, weight_column)
    total_weight = sum(weights)

    if total_weight <= 0:
        raise ValueError("Total weight must be greater than 0.")

    groups = df[group_column].to_list()
    unique_groups = list(dict.fromkeys(groups))

    if max_group_weight * len(unique_groups) < total_weight:
        raise ValueError("max_group_weight is too low for the number of groups.")

    group_original_weights: dict[object, float] = {
        group: 0.0 for group in unique_groups
    }

    for group, weight in zip(groups, weights):
        group_original_weights[group] += weight

    final_group_weights: dict[object, float] = {}
    remaining_groups = set(unique_groups)

    while remaining_groups:
        fixed_weight = sum(
            final_group_weights[group]
            for group in unique_groups
            if group not in remaining_groups
        )

        available_weight = total_weight - fixed_weight
        remaining_original_weight = sum(
            group_original_weights[group]
            for group in remaining_groups
        )

        proposed = {
            group: (
                group_original_weights[group]
                / remaining_original_weight
                * available_weight
            )
            for group in remaining_groups
        }

        capped = [
            group
            for group, proposed_weight in proposed.items()
            if proposed_weight > max_group_weight
        ]

        if not capped:
            final_group_weights.update(proposed)
            break

        for group in capped:
            final_group_weights[group] = max_group_weight
            remaining_groups.remove(group)

    final_weights: list[float] = []

    for group, weight in zip(groups, weights):
        original_group_weight = group_original_weights[group]

        if original_group_weight <= 0:
            final_weights.append(0.0)
        else:
            final_weights.append(
                weight / original_group_weight * final_group_weights[group]
            )

    return df.with_columns(
        pl.Series(weight_column, final_weights)
    )


def add_dollar_allocation(
    df: pl.DataFrame,
    total_capital: float,
    weight_column: str = "target_weight",
    allocation_column: str = "target_allocation",
) -> pl.DataFrame:
    """
    Convert target weights into dollar allocations.
    """
    validate_candidate_data(df)
    _validate_weight_column(df, weight_column)
    _validate_positive(total_capital, "total_capital")

    return df.with_columns(
        (pl.col(weight_column) * total_capital).alias(allocation_column)
    )


def add_risk_budget(
    df: pl.DataFrame,
    total_risk_budget: float,
    weight_column: str = "target_weight",
    risk_budget_column: str = "target_risk_budget",
) -> pl.DataFrame:
    """
    Convert target weights into risk-budget allocations.
    """
    validate_candidate_data(df)
    _validate_weight_column(df, weight_column)
    _validate_positive(total_risk_budget, "total_risk_budget")

    return df.with_columns(
        (pl.col(weight_column) * total_risk_budget).alias(risk_budget_column)
    )


def allocation_summary(
    df: pl.DataFrame,
    weight_column: str = "target_weight",
    allocation_column: str = "target_allocation",
) -> dict[str, float | int]:
    """
    Return lightweight allocation diagnostics.
    """
    if df.is_empty():
        return {
            "total_candidates": 0,
            "total_weight": 0.0,
            "max_weight": 0.0,
            "min_weight": 0.0,
            "total_allocation": 0.0,
        }

    _validate_weight_column(df, weight_column)

    total_allocation = (
        float(df.select(pl.col(allocation_column).sum()).item())
        if allocation_column in df.columns
        else 0.0
    )

    return {
        "total_candidates": df.height,
        "total_weight": float(df.select(pl.col(weight_column).sum()).item()),
        "max_weight": float(df.select(pl.col(weight_column).max()).item()),
        "min_weight": float(df.select(pl.col(weight_column).min()).item()),
        "total_allocation": total_allocation,
    }

GREEK_COLUMNS = ("delta", "gamma", "theta", "vega", "rho")
NET_GREEK_COLUMNS = ("net_delta", "net_gamma", "net_theta", "net_vega", "net_rho")


def add_weighted_greek_exposures(
    df: pl.DataFrame,
    weight_column: str = "target_weight",
    greek_columns: Sequence[str] = GREEK_COLUMNS,
    prefix: str = "weighted",
) -> pl.DataFrame:
    """
    Add weighted Greek exposure columns.

    Example:
    weighted_delta = target_weight * delta
    """
    validate_candidate_data(df)
    _validate_weight_column(df, weight_column)

    expressions: list[pl.Expr] = []

    for greek_column in greek_columns:
        if greek_column in df.columns:
            expressions.append(
                (
                    pl.col(weight_column).cast(pl.Float64, strict=False)
                    * pl.col(greek_column).cast(pl.Float64, strict=False)
                ).alias(f"{prefix}_{greek_column}")
            )

    if not expressions:
        raise ValueError("No Greek columns found for weighted exposure calculation.")

    return df.with_columns(expressions)


def greek_exposure_summary(
    df: pl.DataFrame,
    greek_columns: Sequence[str] = GREEK_COLUMNS,
    weight_column: str = "target_weight",
) -> dict[str, float]:
    """
    Summarize gross, net, and weighted Greek exposures.
    """
    validate_candidate_data(df)

    summary: dict[str, float] = {}

    for greek_column in greek_columns:
        if greek_column not in df.columns:
            continue

        values = df.select(
            pl.col(greek_column).cast(pl.Float64, strict=False)
        ).to_series()

        summary[f"net_{greek_column}"] = float(values.sum())
        summary[f"gross_{greek_column}"] = float(values.abs().sum())

        if weight_column in df.columns:
            weighted = df.select(
                (
                    pl.col(weight_column).cast(pl.Float64, strict=False)
                    * pl.col(greek_column).cast(pl.Float64, strict=False)
                ).sum()
            ).item()

            summary[f"weighted_{greek_column}"] = float(weighted)

    if not summary:
        raise ValueError("No Greek columns found for exposure summary.")

    return summary


def allocation_with_greek_exposures(
    df: pl.DataFrame,
    method: str = "score",
    total_capital: float | None = None,
    max_weight: float | None = None,
    score_column: str = "opportunity_score",
    rank_column: str = "rank",
    weight_column: str = "target_weight",
    allocation_column: str = "target_allocation",
    greek_columns: Sequence[str] = GREEK_COLUMNS,
    *,
    config: CandidateAllocationConfig | None = None,
    total_risk_budget: float | None = None,
    risk_column: str = "max_loss",
    risk_budget_column: str = "target_risk_budget",
    target_gross_exposure: float | None = None,
    max_symbol_weight: float | None = None,
    max_strategy_weight: float | None = None,
    max_regime_weight: float | None = None,
    max_asset_class_weight: float | None = None,
) -> pl.DataFrame:
    """
    Allocate selected candidates and append weighted Greek exposure columns.
    """
    allocated = allocate_selected_candidates(
        df,
        method=method,
        total_capital=total_capital,
        max_weight=max_weight,
        score_column=score_column,
        rank_column=rank_column,
        weight_column=weight_column,
        allocation_column=allocation_column,
        config=config,
        total_risk_budget=total_risk_budget,
        risk_column=risk_column,
        risk_budget_column=risk_budget_column,
        target_gross_exposure=target_gross_exposure,
        max_symbol_weight=max_symbol_weight,
        max_strategy_weight=max_strategy_weight,
        max_regime_weight=max_regime_weight,
        max_asset_class_weight=max_asset_class_weight,
    )

    return add_weighted_greek_exposures(
        allocated,
        weight_column=weight_column,
        greek_columns=greek_columns,
    )

def allocate_selected_candidates(
    df: pl.DataFrame,
    method: str = "score",
    total_capital: float | None = None,
    max_weight: float | None = None,
    score_column: str = "opportunity_score",
    rank_column: str = "rank",
    weight_column: str = "target_weight",
    allocation_column: str = "target_allocation",
    *,
    config: CandidateAllocationConfig | None = None,
    total_risk_budget: float | None = None,
    risk_column: str = "max_loss",
    risk_budget_column: str = "target_risk_budget",
    target_gross_exposure: float | None = None,
    max_symbol_weight: float | None = None,
    max_strategy_weight: float | None = None,
    max_regime_weight: float | None = None,
    max_asset_class_weight: float | None = None,
) -> pl.DataFrame:
    """
    Full allocation pipeline for selected candidates.

    Supported methods:
    - equal
    - score
    - rank
    - inverse_risk
    - risk_adjusted_score
    """
    validate_candidate_data(df)

    cfg = config or CandidateAllocationConfig()

    active_method = cfg.method if config is not None and method == "score" else method
    active_total_capital = (
        cfg.total_capital if total_capital is None else total_capital
    )
    active_total_risk_budget = (
        cfg.total_risk_budget
        if total_risk_budget is None
        else total_risk_budget
    )
    active_max_weight = cfg.max_weight if max_weight is None else max_weight
    active_score_column = (
        cfg.score_column if score_column == "opportunity_score" else score_column
    )
    active_rank_column = cfg.rank_column if rank_column == "rank" else rank_column
    active_weight_column = (
        cfg.weight_column if weight_column == "target_weight" else weight_column
    )
    active_allocation_column = (
        cfg.allocation_column
        if allocation_column == "target_allocation"
        else allocation_column
    )
    active_risk_column = cfg.risk_column if risk_column == "max_loss" else risk_column
    active_risk_budget_column = (
        cfg.risk_budget_column
        if risk_budget_column == "target_risk_budget"
        else risk_budget_column
    )
    active_target_gross_exposure = (
        cfg.target_gross_exposure
        if target_gross_exposure is None
        else target_gross_exposure
    )
    active_max_symbol_weight = (
        cfg.max_symbol_weight
        if max_symbol_weight is None
        else max_symbol_weight
    )
    active_max_strategy_weight = (
        cfg.max_strategy_weight
        if max_strategy_weight is None
        else max_strategy_weight
    )
    active_max_regime_weight = (
        cfg.max_regime_weight
        if max_regime_weight is None
        else max_regime_weight
    )
    active_max_asset_class_weight = (
        cfg.max_asset_class_weight
        if max_asset_class_weight is None
        else max_asset_class_weight
    )

    method_normalized = active_method.lower()

    if method_normalized == "equal":
        allocated = equal_weight_allocation(
            df,
            weight_column=active_weight_column,
            target_gross_exposure=active_target_gross_exposure,
        )
    elif method_normalized == "score":
        allocated = score_weighted_allocation(
            df,
            score_column=active_score_column,
            weight_column=active_weight_column,
            target_gross_exposure=active_target_gross_exposure,
        )
    elif method_normalized == "rank":
        allocated = rank_weighted_allocation(
            df,
            rank_column=active_rank_column,
            weight_column=active_weight_column,
            target_gross_exposure=active_target_gross_exposure,
        )
    elif method_normalized == "inverse_risk":
        allocated = inverse_risk_allocation(
            df,
            risk_column=active_risk_column,
            weight_column=active_weight_column,
            target_gross_exposure=active_target_gross_exposure,
        )
    elif method_normalized == "risk_adjusted_score":
        allocated = risk_adjusted_score_allocation(
            df,
            score_column=active_score_column,
            risk_column=active_risk_column,
            weight_column=active_weight_column,
            target_gross_exposure=active_target_gross_exposure,
        )
    else:
        raise ValueError(f"Unsupported allocation method: {active_method}")

    if active_max_weight is not None:
        allocated = cap_allocation_weights(
            allocated,
            max_weight=active_max_weight,
            weight_column=active_weight_column,
        )

    if active_max_symbol_weight is not None:
        allocated = cap_group_allocation_weights(
            allocated,
            group_column="symbol",
            max_group_weight=active_max_symbol_weight,
            weight_column=active_weight_column,
        )

    if active_max_strategy_weight is not None:
        allocated = cap_group_allocation_weights(
            allocated,
            group_column="strategy",
            max_group_weight=active_max_strategy_weight,
            weight_column=active_weight_column,
        )

    if active_max_regime_weight is not None:
        allocated = cap_group_allocation_weights(
            allocated,
            group_column="regime",
            max_group_weight=active_max_regime_weight,
            weight_column=active_weight_column,
        )

    if active_max_asset_class_weight is not None:
        allocated = cap_group_allocation_weights(
            allocated,
            group_column="asset_class",
            max_group_weight=active_max_asset_class_weight,
            weight_column=active_weight_column,
        )

    if active_total_risk_budget is not None:
        allocated = add_risk_budget(
            allocated,
            total_risk_budget=active_total_risk_budget,
            weight_column=active_weight_column,
            risk_budget_column=active_risk_budget_column,
        )

    if active_total_capital is not None:
        allocated = add_dollar_allocation(
            allocated,
            total_capital=active_total_capital,
            weight_column=active_weight_column,
            allocation_column=active_allocation_column,
        )

    return allocated
