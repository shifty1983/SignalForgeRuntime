from __future__ import annotations

import polars as pl


def _require_columns(df: pl.DataFrame, required: set[str]) -> None:
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")


def equal_weight_positions(
    symbols: list[str],
    gross_exposure: float = 1.0,
) -> pl.DataFrame:
    """
    Create equal-weight long-only positions.
    """

    if len(symbols) == 0:
        raise ValueError("Symbol list is empty")

    if gross_exposure <= 0:
        raise ValueError("gross_exposure must be positive")

    weight = gross_exposure / len(symbols)

    return pl.DataFrame(
        {
            "symbol": symbols,
            "weight": [weight] * len(symbols),
        }
    )


def long_short_equal_weights(
    long_symbols: list[str],
    short_symbols: list[str],
    long_exposure: float = 1.0,
    short_exposure: float = -1.0,
) -> pl.DataFrame:
    """
    Create equal-weight long/short portfolio.
    """

    if len(long_symbols) == 0:
        raise ValueError("long_symbols cannot be empty")

    if len(short_symbols) == 0:
        raise ValueError("short_symbols cannot be empty")

    if long_exposure <= 0:
        raise ValueError("long_exposure must be positive")

    if short_exposure >= 0:
        raise ValueError("short_exposure must be negative")

    long_weight = long_exposure / len(long_symbols)
    short_weight = short_exposure / len(short_symbols)

    return pl.DataFrame(
        {
            "symbol": long_symbols + short_symbols,
            "weight": [long_weight] * len(long_symbols)
            + [short_weight] * len(short_symbols),
        }
    )


def inverse_volatility_weights(
    volatility: pl.DataFrame,
    symbol_col: str = "symbol",
    volatility_col: str = "volatility",
    gross_exposure: float = 1.0,
) -> pl.DataFrame:
    """
    Create inverse-volatility portfolio weights.

    Lower-volatility assets receive larger weights.
    """

    _require_columns(volatility, {symbol_col, volatility_col})

    if gross_exposure <= 0:
        raise ValueError("gross_exposure must be positive")

    invalid = volatility.filter(pl.col(volatility_col) <= 0)

    if invalid.height > 0:
        raise ValueError("Volatility values must be positive")

    df = volatility.with_columns(
        (1.0 / pl.col(volatility_col)).alias("_inv_vol")
    )

    total_inv_vol = df.select(pl.col("_inv_vol").sum()).item()

    if total_inv_vol <= 0:
        raise ValueError("Total inverse volatility must be positive")

    return (
        df.with_columns(
            (
                pl.col("_inv_vol") / total_inv_vol * gross_exposure
            ).alias("weight")
        )
        .select(symbol_col, "weight")
        .sort(symbol_col)
    )


def score_weighted_positions(
    scores: pl.DataFrame,
    score_col: str = "score",
    symbol_col: str = "symbol",
    gross_exposure: float = 1.0,
    long_only: bool = True,
) -> pl.DataFrame:
    """
    Convert opportunity scores into portfolio weights.

    If long_only=True, negative scores are clipped to zero.
    If long_only=False, signed scores are normalized by absolute score.
    """

    _require_columns(scores, {symbol_col, score_col})

    if gross_exposure <= 0:
        raise ValueError("gross_exposure must be positive")

    if long_only:
        df = scores.with_columns(
            pl.when(pl.col(score_col) > 0)
            .then(pl.col(score_col))
            .otherwise(0.0)
            .alias("_sizing_score")
        )
        denominator = df.select(pl.col("_sizing_score").sum()).item()
    else:
        df = scores.with_columns(
            pl.col(score_col).alias("_sizing_score")
        )
        denominator = df.select(pl.col("_sizing_score").abs().sum()).item()

    if denominator <= 0:
        raise ValueError("Sizing score denominator must be positive")

    return (
        df.with_columns(
            (
                pl.col("_sizing_score") / denominator * gross_exposure
            ).alias("weight")
        )
        .select(symbol_col, "weight")
        .sort(symbol_col)
    )


def volatility_target_weights(
    weights: pl.DataFrame,
    current_volatility: float,
    target_volatility: float = 0.10,
    max_scaler: float | None = None,
    weight_col: str = "weight",
) -> pl.DataFrame:
    """
    Scale portfolio weights to target volatility.
    """

    _require_columns(weights, {weight_col})

    if current_volatility <= 0:
        raise ValueError("Current volatility must be positive")

    if target_volatility <= 0:
        raise ValueError("Target volatility must be positive")

    scaler = target_volatility / current_volatility

    if max_scaler is not None:
        scaler = min(scaler, max_scaler)

    return weights.with_columns(
        (pl.col(weight_col) * scaler).alias(weight_col)
    )


def normalize_weights(
    weights: pl.DataFrame,
    target_gross_exposure: float = 1.0,
    weight_col: str = "weight",
) -> pl.DataFrame:
    """
    Normalize weights so absolute weights sum to target_gross_exposure.
    """

    _require_columns(weights, {weight_col})

    if target_gross_exposure <= 0:
        raise ValueError("target_gross_exposure must be positive")

    total_weight = weights.select(pl.col(weight_col).abs().sum()).item()

    if total_weight == 0:
        raise ValueError("Total weight is zero")

    return weights.with_columns(
        (
            pl.col(weight_col) / total_weight * target_gross_exposure
        ).alias(weight_col)
    )


def capped_weights(
    weights: pl.DataFrame,
    max_weight: float = 0.10,
    weight_col: str = "weight",
) -> pl.DataFrame:
    """
    Cap individual position weights by absolute size.

    This caps weights but does not redistribute leftover exposure.
    """

    _require_columns(weights, {weight_col})

    if max_weight <= 0:
        raise ValueError("max_weight must be positive")

    return weights.with_columns(
        (
            pl.when(pl.col(weight_col) > max_weight)
            .then(max_weight)
            .when(pl.col(weight_col) < -max_weight)
            .then(-max_weight)
            .otherwise(pl.col(weight_col))
        ).alias(weight_col)
    )


def dollar_position_sizes(
    weights: pl.DataFrame,
    portfolio_value: float,
    weight_col: str = "weight",
) -> pl.DataFrame:
    """
    Convert portfolio weights into dollar position sizes.
    """

    _require_columns(weights, {weight_col})

    if portfolio_value <= 0:
        raise ValueError("portfolio_value must be positive")

    return weights.with_columns(
        (pl.col(weight_col) * portfolio_value).alias("dollar_position")
    )


def shares_from_weights(
    weights: pl.DataFrame,
    prices: pl.DataFrame,
    portfolio_value: float,
    symbol_col: str = "symbol",
    weight_col: str = "weight",
    price_col: str = "price",
) -> pl.DataFrame:
    """
    Convert target weights into share quantities using current prices.
    """

    _require_columns(weights, {symbol_col, weight_col})
    _require_columns(prices, {symbol_col, price_col})

    if portfolio_value <= 0:
        raise ValueError("portfolio_value must be positive")

    joined = weights.join(prices, on=symbol_col, how="inner")

    if joined.height != weights.height:
        raise ValueError("Missing prices for one or more symbols")

    invalid_prices = joined.filter(pl.col(price_col) <= 0)

    if invalid_prices.height > 0:
        raise ValueError("Prices must be positive")

    return joined.with_columns(
        (pl.col(weight_col) * portfolio_value).alias("dollar_position"),
        (
            (pl.col(weight_col) * portfolio_value) / pl.col(price_col)
        ).alias("shares"),
    )
