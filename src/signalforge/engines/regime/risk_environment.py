from __future__ import annotations

import polars as pl


def risk_spread(
    df: pl.DataFrame,
    risk_asset: str,
    safe_asset: str,
    output_column: str = "risk_spread",
) -> pl.DataFrame:
    missing = [c for c in [risk_asset, safe_asset] if c not in df.columns]

    if missing:
        raise ValueError(f"Missing columns: {missing}")

    return df.with_columns(
        (pl.col(risk_asset) - pl.col(safe_asset)).alias(output_column)
    )


def risk_trend(
    df: pl.DataFrame,
    column: str,
    window: int = 3,
    output_column: str | None = None,
) -> pl.DataFrame:
    if column not in df.columns:
        raise ValueError(f"Missing column: {column}")

    if window <= 0:
        raise ValueError("window must be positive")

    output_column = output_column or f"{column}_risk_trend"

    return df.with_columns(
        pl.col(column).rolling_mean(window).alias(output_column)
    )


def classify_risk_environment(
    df: pl.DataFrame,
    column: str,
    output_column: str = "risk_environment",
) -> pl.DataFrame:
    if column not in df.columns:
        raise ValueError(f"Missing column: {column}")

    return df.with_columns(
        pl.when(pl.col(column) > 0)
        .then(pl.lit("risk_on"))
        .when(pl.col(column) < 0)
        .then(pl.lit("risk_off"))
        .otherwise(pl.lit("risk_neutral"))
        .alias(output_column)
    )


def add_relative_risk_signal(
    df: pl.DataFrame,
    risk_column: str,
    defensive_column: str,
    output_column: str,
) -> pl.DataFrame:
    """Add a +1/0/-1 signal from one risk proxy versus one defensive proxy.

    The input columns are expected to be comparable return, momentum, or spread
    values. A higher risk proxy versus defensive proxy is treated as risk-on.
    """

    missing = [c for c in [risk_column, defensive_column] if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {missing}")

    return df.with_columns(
        pl.when(pl.col(risk_column) > pl.col(defensive_column))
        .then(pl.lit(1.0))
        .when(pl.col(risk_column) < pl.col(defensive_column))
        .then(pl.lit(-1.0))
        .otherwise(pl.lit(0.0))
        .alias(output_column)
    )


def _polarity_signal(column: str, risk_on_when_positive: bool = True) -> pl.Expr:
    positive_value = 1.0 if risk_on_when_positive else -1.0
    negative_value = -1.0 if risk_on_when_positive else 1.0

    return (
        pl.when(pl.col(column) > 0)
        .then(pl.lit(positive_value))
        .when(pl.col(column) < 0)
        .then(pl.lit(negative_value))
        .otherwise(pl.lit(0.0))
    )


def add_enhanced_risk_score(
    df: pl.DataFrame,
    signal_columns: list[str] | None = None,
    risk_pairs: list[tuple[str, str, str]] | None = None,
    vix_trend_column: str | None = None,
    breadth_score_column: str | None = None,
    breadth_trend_column: str | None = None,
    credit_trend_column: str | None = None,
    output_column: str = "risk_score",
) -> pl.DataFrame:
    """Build a multi-signal risk score from market, breadth, vol, and credit inputs.

    The score is the average of available +1/0/-1 component signals. It is
    intentionally vendor-neutral so QuantConnect market proxies, FRED credit
    data, and previously calculated breadth outputs can feed the same model.
    """

    result = df
    component_columns: list[str] = []

    for column in signal_columns or []:
        if column not in result.columns:
            raise ValueError(f"Missing column: {column}")
        component_columns.append(column)

    for risk_column, defensive_column, signal_name in risk_pairs or []:
        result = add_relative_risk_signal(
            result,
            risk_column=risk_column,
            defensive_column=defensive_column,
            output_column=signal_name,
        )
        component_columns.append(signal_name)

    if vix_trend_column is not None:
        if vix_trend_column not in result.columns:
            raise ValueError(f"Missing column: {vix_trend_column}")
        signal_name = f"{vix_trend_column}_risk_signal"
        result = result.with_columns(
            _polarity_signal(vix_trend_column, risk_on_when_positive=False).alias(signal_name)
        )
        component_columns.append(signal_name)

    if breadth_score_column is not None:
        if breadth_score_column not in result.columns:
            raise ValueError(f"Missing column: {breadth_score_column}")
        signal_name = f"{breadth_score_column}_risk_signal"
        result = result.with_columns(
            pl.when(pl.col(breadth_score_column) >= 0.60)
            .then(pl.lit(1.0))
            .when(pl.col(breadth_score_column) <= 0.40)
            .then(pl.lit(-1.0))
            .otherwise(pl.lit(0.0))
            .alias(signal_name)
        )
        component_columns.append(signal_name)

    if breadth_trend_column is not None:
        if breadth_trend_column not in result.columns:
            raise ValueError(f"Missing column: {breadth_trend_column}")
        signal_name = f"{breadth_trend_column}_risk_signal"
        result = result.with_columns(
            _polarity_signal(breadth_trend_column, risk_on_when_positive=True).alias(signal_name)
        )
        component_columns.append(signal_name)

    if credit_trend_column is not None:
        if credit_trend_column not in result.columns:
            raise ValueError(f"Missing column: {credit_trend_column}")
        signal_name = f"{credit_trend_column}_risk_signal"
        result = result.with_columns(
            _polarity_signal(credit_trend_column, risk_on_when_positive=False).alias(signal_name)
        )
        component_columns.append(signal_name)

    if not component_columns:
        raise ValueError("At least one risk signal input is required")

    return result.with_columns(
        pl.mean_horizontal([pl.col(column) for column in component_columns]).alias(output_column)
    )


def add_risk_confidence(
    df: pl.DataFrame,
    score_column: str = "risk_score",
    output_column: str = "risk_confidence",
) -> pl.DataFrame:
    if score_column not in df.columns:
        raise ValueError(f"Missing column: {score_column}")

    return df.with_columns(pl.col(score_column).abs().alias(output_column))


def classify_enhanced_risk_environment(
    df: pl.DataFrame,
    score_column: str = "risk_score",
    output_column: str = "risk_environment",
) -> pl.DataFrame:
    if score_column not in df.columns:
        raise ValueError(f"Missing column: {score_column}")

    return df.with_columns(
        pl.when(pl.col(score_column) >= 0.60)
        .then(pl.lit("strong_risk_on"))
        .when(pl.col(score_column) >= 0.20)
        .then(pl.lit("risk_on"))
        .when(pl.col(score_column) <= -0.60)
        .then(pl.lit("strong_risk_off"))
        .when(pl.col(score_column) <= -0.20)
        .then(pl.lit("risk_off"))
        .otherwise(pl.lit("risk_neutral"))
        .alias(output_column)
    )


def add_enhanced_risk_trend(
    df: pl.DataFrame,
    score_column: str = "risk_score",
    output_column: str = "risk_trend",
) -> pl.DataFrame:
    if score_column not in df.columns:
        raise ValueError(f"Missing column: {score_column}")

    return df.with_columns(pl.col(score_column).diff().alias(output_column))


