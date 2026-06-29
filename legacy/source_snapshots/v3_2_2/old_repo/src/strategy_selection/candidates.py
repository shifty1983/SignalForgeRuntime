from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import polars as pl


REQUIRED_CANDIDATE_COLUMNS = {
    "symbol",
    "strategy",
    "opportunity_score",
}


OPTIONAL_NUMERIC_COLUMNS = {
    "expected_return",
    "expected_value",
    "max_loss",
    "probability_of_profit",
    "confidence",
    "risk_reward",
    "liquidity_score",
    "bid_ask_spread_pct",
    "volume",
    "open_interest",
    "days_to_expiration",
    "strike",

    # Greeks
    "delta",
    "gamma",
    "theta",
    "vega",
    "rho",

    # Optional position-adjusted Greeks
    "net_delta",
    "net_gamma",
    "net_theta",
    "net_vega",
    "net_rho",
}


OPTIONAL_TEXT_COLUMNS = {
    "regime",
    "asset_class",
    "direction",
    "option_type",
    "source",
}


OPTIONAL_NUMERIC_COLUMNS = {
    "expected_return",
    "expected_value",
    "max_loss",
    "probability_of_profit",
    "confidence",
    "risk_reward",
    "liquidity_score",
    "bid_ask_spread_pct",
    "volume",
    "open_interest",
    "days_to_expiration",
    "strike",

    # Greeks
    "delta",
    "gamma",
    "theta",
    "vega",
    "rho",

    # Optional position-adjusted Greeks
    "net_delta",
    "net_gamma",
    "net_theta",
    "net_vega",
    "net_rho",
}

@dataclass(frozen=True)
class CandidateSchema:
    symbol: str = "symbol"
    strategy: str = "strategy"
    candidate_id: str = "candidate_id"
    opportunity_score: str = "opportunity_score"
    expected_return: str = "expected_return"
    expected_value: str = "expected_value"
    max_loss: str = "max_loss"
    probability_of_profit: str = "probability_of_profit"
    confidence: str = "confidence"
    risk_reward: str = "risk_reward"
    liquidity_score: str = "liquidity_score"
    bid_ask_spread_pct: str = "bid_ask_spread_pct"
    volume: str = "volume"
    open_interest: str = "open_interest"
    regime: str = "regime"
    asset_class: str = "asset_class"
    direction: str = "direction"
    expiration: str = "expiration"
    strike: str = "strike"
    option_type: str = "option_type"
    days_to_expiration: str = "days_to_expiration"
    source: str = "source"

    # Greeks
    delta: str = "delta"
    gamma: str = "gamma"
    theta: str = "theta"
    vega: str = "vega"
    rho: str = "rho"

    # Position-adjusted Greeks
    net_delta: str = "net_delta"
    net_gamma: str = "net_gamma"
    net_theta: str = "net_theta"
    net_vega: str = "net_vega"
    net_rho: str = "net_rho"

@dataclass(frozen=True)
class CandidatePreparationConfig:
    """
    Configuration for normalizing and identifying strategy-selection candidates.
    """

    required_columns: set[str] = field(
        default_factory=lambda: set(REQUIRED_CANDIDATE_COLUMNS)
    )
    id_columns: tuple[str, ...] = ("symbol", "strategy")
    sort_column: str = "opportunity_score"
    candidate_id_column: str = "candidate_id"
    strict_quality_checks: bool = False


def validate_candidate_data(
    df: pl.DataFrame,
    required_columns: set[str] | None = None,
) -> None:
    """
    Validate that candidate input data contains the minimum fields required
    for strategy selection.
    """
    if not isinstance(df, pl.DataFrame):
        raise TypeError("Candidate data must be a Polars DataFrame.")

    required = required_columns or REQUIRED_CANDIDATE_COLUMNS
    missing = required - set(df.columns)

    if missing:
        raise ValueError(f"Missing required candidate columns: {sorted(missing)}")

    if df.is_empty():
        raise ValueError("Candidate data is empty.")


def validate_candidate_quality(
    df: pl.DataFrame,
    probability_column: str = "probability_of_profit",
    confidence_column: str = "confidence",
    max_loss_column: str = "max_loss",
    score_column: str = "opportunity_score",
) -> None:
    """
    Validate common numeric candidate quality constraints.

    Rules:
    - opportunity_score must be numeric when present.
    - probability_of_profit must be between 0 and 1 when present.
    - confidence must be between 0 and 1 when present.
    - max_loss must be non-negative when present.
    """
    validate_candidate_data(df)

    _validate_numeric_column(df, score_column)

    if probability_column in df.columns:
        _validate_numeric_column(df, probability_column)
        _validate_range(df, probability_column, minimum=0.0, maximum=1.0)

    if confidence_column in df.columns:
        _validate_numeric_column(df, confidence_column)
        _validate_range(df, confidence_column, minimum=0.0, maximum=1.0)

    if max_loss_column in df.columns:
        _validate_numeric_column(df, max_loss_column)
        _validate_minimum(df, max_loss_column, minimum=0.0)


def _validate_numeric_column(df: pl.DataFrame, column: str) -> None:
    if column not in df.columns:
        return

    checked = df.with_columns(
        pl.col(column).cast(pl.Float64, strict=False).alias("_numeric_check")
    )

    invalid = checked.filter(
        pl.col(column).is_not_null() & pl.col("_numeric_check").is_null()
    )

    if invalid.height > 0:
        raise ValueError(f"{column} must be numeric.")


def _validate_range(
    df: pl.DataFrame,
    column: str,
    minimum: float,
    maximum: float,
) -> None:
    checked = df.with_columns(
        pl.col(column).cast(pl.Float64, strict=False).alias("_range_check")
    )

    invalid = checked.filter(
        pl.col("_range_check").is_not_null()
        & (
            (pl.col("_range_check") < minimum)
            | (pl.col("_range_check") > maximum)
        )
    )

    if invalid.height > 0:
        raise ValueError(f"{column} must be between {minimum} and {maximum}.")


def _validate_minimum(
    df: pl.DataFrame,
    column: str,
    minimum: float,
) -> None:
    checked = df.with_columns(
        pl.col(column).cast(pl.Float64, strict=False).alias("_minimum_check")
    )

    invalid = checked.filter(
        pl.col("_minimum_check").is_not_null()
        & (pl.col("_minimum_check") < minimum)
    )

    if invalid.height > 0:
        raise ValueError(f"{column} must be greater than or equal to {minimum}.")


def _clean_symbol_expr(column: str) -> pl.Expr:
    return (
        pl.col(column)
        .cast(pl.Utf8)
        .str.strip_chars()
        .str.to_uppercase()
        .alias(column)
    )


def _clean_label_expr(column: str) -> pl.Expr:
    return (
        pl.col(column)
        .cast(pl.Utf8)
        .str.strip_chars()
        .str.replace_all(r"[\s\-]+", "_")
        .str.to_lowercase()
        .alias(column)
    )


def _numeric_expr(column: str) -> pl.Expr:
    return pl.col(column).cast(pl.Float64, strict=False).alias(column)


def normalize_candidates(
    df: pl.DataFrame,
    config: CandidatePreparationConfig | None = None,
) -> pl.DataFrame:
    """
    Clean and normalize raw opportunity data into selection-ready candidates.

    Required minimum columns:
    - symbol
    - strategy
    - opportunity_score

    Optional columns are normalized when present.
    """
    cfg = config or CandidatePreparationConfig()

    validate_candidate_data(df, required_columns=cfg.required_columns)

    expressions: list[pl.Expr] = []

    if "symbol" in df.columns:
        expressions.append(_clean_symbol_expr("symbol"))

    if "strategy" in df.columns:
        expressions.append(_clean_label_expr("strategy"))

    for column in sorted(OPTIONAL_TEXT_COLUMNS):
        if column in df.columns:
            expressions.append(_clean_label_expr(column))

    numeric_columns = set(OPTIONAL_NUMERIC_COLUMNS)
    numeric_columns.add("opportunity_score")

    for column in sorted(numeric_columns):
        if column in df.columns:
            expressions.append(_numeric_expr(column))

    normalized = df.with_columns(expressions)

    if cfg.strict_quality_checks:
        validate_candidate_quality(normalized)

    if cfg.sort_column not in normalized.columns:
        raise ValueError(f"Missing sort column: {cfg.sort_column}")

    return (
        normalized.filter(pl.col(cfg.sort_column).is_not_null())
        .sort(cfg.sort_column, descending=True)
    )


def add_candidate_id(
    df: pl.DataFrame,
    id_columns: Sequence[str] | None = None,
    candidate_id_column: str = "candidate_id",
) -> pl.DataFrame:
    """
    Add a stable candidate_id based on selected identity columns.

    Default:
    - symbol
    - strategy

    Example:
    SPY_long_call
    """
    validate_candidate_data(df)

    columns = tuple(id_columns or ("symbol", "strategy"))

    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise ValueError(f"Missing candidate id columns: {missing}")

    id_expressions: list[pl.Expr] = []

    for column in columns:
        if column == "symbol":
            id_expressions.append(
                pl.col(column).cast(pl.Utf8).str.strip_chars().str.to_uppercase()
            )
        elif column in {"strategy", "regime", "asset_class", "direction", "option_type"}:
            id_expressions.append(
                pl.col(column)
                .cast(pl.Utf8)
                .str.strip_chars()
                .str.replace_all(r"[\s\-]+", "_")
                .str.to_lowercase()
            )
        else:
            id_expressions.append(pl.col(column).cast(pl.Utf8).str.strip_chars())

    return df.with_columns(
        pl.concat_str(id_expressions, separator="_").alias(candidate_id_column)
    )


def deduplicate_candidates(
    df: pl.DataFrame,
    candidate_id_column: str = "candidate_id",
    sort_column: str = "opportunity_score",
) -> pl.DataFrame:
    """
    Deduplicate candidates by candidate_id.

    The highest-scoring version of each candidate is kept.
    """
    validate_candidate_data(df)

    if candidate_id_column not in df.columns:
        df = add_candidate_id(df, candidate_id_column=candidate_id_column)

    if sort_column not in df.columns:
        raise ValueError(f"Missing sort column: {sort_column}")

    return (
        df.sort(sort_column, descending=True)
        .unique(subset=[candidate_id_column], keep="first", maintain_order=True)
    )


def add_candidate_flags(
    df: pl.DataFrame,
    score_column: str = "opportunity_score",
    expected_return_column: str = "expected_return",
    expected_value_column: str = "expected_value",
    max_loss_column: str = "max_loss",
    probability_column: str = "probability_of_profit",
) -> pl.DataFrame:
    """
    Add useful diagnostic flags for strategy-selection review.
    """
    validate_candidate_data(df)

    if score_column not in df.columns:
        raise ValueError(f"Missing score column: {score_column}")

    expressions: list[pl.Expr] = [
        (pl.col(score_column).cast(pl.Float64) > 0).alias("has_positive_score")
    ]

    eligibility_checks: list[pl.Expr] = [
        pl.col(score_column).cast(pl.Float64).is_not_null(),
        pl.col(score_column).cast(pl.Float64) > 0,
    ]

    if expected_return_column in df.columns:
        expr = pl.col(expected_return_column).cast(pl.Float64, strict=False) > 0
        expressions.append(expr.alias("has_positive_expected_return"))
        eligibility_checks.append(expr)

    if expected_value_column in df.columns:
        expr = pl.col(expected_value_column).cast(pl.Float64, strict=False) > 0
        expressions.append(expr.alias("has_positive_expected_value"))
        eligibility_checks.append(expr)

    if max_loss_column in df.columns:
        expr = (
            pl.col(max_loss_column).cast(pl.Float64, strict=False).is_not_null()
            & (pl.col(max_loss_column).cast(pl.Float64, strict=False) >= 0)
        )
        expressions.append(expr.alias("has_defined_risk"))
        eligibility_checks.append(expr)

    if probability_column in df.columns:
        expr = pl.col(probability_column).cast(pl.Float64, strict=False).is_between(
            0.0,
            1.0,
            closed="both",
        )
        expressions.append(expr.alias("has_valid_probability"))
        eligibility_checks.append(expr)

    expressions.append(
        pl.all_horizontal(eligibility_checks).alias("selection_eligible")
    )

    return df.with_columns(expressions)


def prepare_candidates(
    df: pl.DataFrame,
    config: CandidatePreparationConfig | None = None,
    *,
    deduplicate: bool = False,
    add_flags: bool = False,
) -> pl.DataFrame:
    """
    Full candidate preparation pipeline.

    Pipeline:
    1. validate input
    2. normalize symbols, strategies, text labels, and numeric fields
    3. add candidate_id
    4. optionally deduplicate
    5. optionally add diagnostic flags
    """
    cfg = config or CandidatePreparationConfig()

    normalized = normalize_candidates(df, config=cfg)

    identified = add_candidate_id(
        normalized,
        id_columns=cfg.id_columns,
        candidate_id_column=cfg.candidate_id_column,
    )

    result = identified

    if deduplicate:
        result = deduplicate_candidates(
            result,
            candidate_id_column=cfg.candidate_id_column,
            sort_column=cfg.sort_column,
        )

    if add_flags:
        result = add_candidate_flags(result)

    return result
