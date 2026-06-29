from __future__ import annotations

import numpy as np
import polars as pl


def _require_columns(df: pl.DataFrame, required: set[str]) -> None:
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")


def calculate_realized_volatility(
    returns: pl.Series,
    annualization_factor: int = 252,
) -> float:
    """
    Calculate annualized realized volatility from a return series.
    """

    if len(returns) == 0:
        raise ValueError("Returns series is empty")

    volatility = returns.std()

    if volatility is None:
        return 0.0

    return float(volatility * np.sqrt(annualization_factor))


def rolling_volatility(
    df: pl.DataFrame,
    return_col: str = "returns",
    window: int = 20,
    annualization_factor: int = 252,
) -> pl.DataFrame:
    """
    Calculate rolling annualized volatility.
    """

    _require_columns(df, {return_col})

    if window <= 1:
        raise ValueError("window must be greater than 1")

    return df.with_columns(
        (
            pl.col(return_col).rolling_std(window_size=window)
            * np.sqrt(annualization_factor)
        ).alias(f"volatility_{window}")
    )


def calculate_covariance_matrix(
    returns: pl.DataFrame,
    date_col: str = "date",
    symbol_col: str = "symbol",
    return_col: str = "returns",
    annualize: bool = True,
    annualization_factor: int = 252,
) -> tuple[list[str], np.ndarray]:
    """
    Calculate covariance matrix from long-form returns data.

    Expected columns:
    - date
    - symbol
    - returns
    """

    _require_columns(returns, {date_col, symbol_col, return_col})

    wide = (
        returns.pivot(
            index=date_col,
            on=symbol_col,
            values=return_col,
            aggregate_function="first",
        )
        .sort(date_col)
        .drop_nulls()
    )

    symbols = [col for col in wide.columns if col != date_col]

    if len(symbols) == 0:
        raise ValueError("No symbols available for covariance calculation")

    if wide.height < 2:
        raise ValueError("At least two observations are required")

    matrix = wide.select(symbols).to_numpy()

    covariance = np.cov(matrix, rowvar=False)

    covariance = np.atleast_2d(covariance)

    if annualize:
        covariance = covariance * annualization_factor

    return symbols, covariance


def calculate_correlation_matrix(
    covariance_matrix: np.ndarray,
) -> np.ndarray:
    """
    Convert covariance matrix into correlation matrix.
    """

    covariance_matrix = np.asarray(covariance_matrix, dtype=float)

    if covariance_matrix.ndim != 2:
        raise ValueError("covariance_matrix must be two-dimensional")

    std_dev = np.sqrt(np.diag(covariance_matrix))

    with np.errstate(divide="ignore", invalid="ignore"):
        correlation = covariance_matrix / np.outer(std_dev, std_dev)

    correlation = np.nan_to_num(correlation, nan=0.0)

    np.fill_diagonal(correlation, 1.0)

    return correlation


def calculate_portfolio_volatility(
    weights: np.ndarray,
    covariance_matrix: np.ndarray,
    annualization_factor: int = 252,
    covariance_is_annualized: bool = False,
) -> float:
    """
    Calculate annualized portfolio volatility.

    Formula:
    sqrt(w' Î£ w)
    """

    weights = np.asarray(weights, dtype=float)
    covariance_matrix = np.asarray(covariance_matrix, dtype=float)

    if covariance_matrix.ndim != 2:
        raise ValueError("covariance_matrix must be two-dimensional")

    if covariance_matrix.shape[0] != covariance_matrix.shape[1]:
        raise ValueError("covariance_matrix must be square")

    if covariance_matrix.shape[0] != weights.shape[0]:
        raise ValueError("weights length must match covariance matrix dimensions")

    portfolio_variance = float(weights.T @ covariance_matrix @ weights)

    if portfolio_variance < 0:
        portfolio_variance = 0.0

    portfolio_volatility = np.sqrt(portfolio_variance)

    if not covariance_is_annualized:
        portfolio_volatility *= np.sqrt(annualization_factor)

    return float(portfolio_volatility)


def calculate_risk_contribution(
    weights: np.ndarray,
    covariance_matrix: np.ndarray,
    symbols: list[str] | None = None,
) -> pl.DataFrame:
    """
    Calculate portfolio risk contribution by asset.

    Returns:
    - marginal_risk_contribution
    - component_risk_contribution
    - percent_risk_contribution
    """

    weights = np.asarray(weights, dtype=float)
    covariance_matrix = np.asarray(covariance_matrix, dtype=float)

    if covariance_matrix.shape[0] != weights.shape[0]:
        raise ValueError("weights length must match covariance matrix dimensions")

    if symbols is None:
        symbols = [f"asset_{i}" for i in range(len(weights))]

    if len(symbols) != len(weights):
        raise ValueError("symbols length must match weights length")

    portfolio_variance = float(weights.T @ covariance_matrix @ weights)

    if portfolio_variance <= 0:
        raise ValueError("Portfolio variance must be positive")

    marginal = covariance_matrix @ weights
    component = weights * marginal
    percent = component / portfolio_variance

    return pl.DataFrame(
        {
            "symbol": symbols,
            "weight": weights,
            "marginal_risk_contribution": marginal,
            "component_risk_contribution": component,
            "percent_risk_contribution": percent,
        }
    )


def volatility_target_scaler(
    current_volatility: float,
    target_volatility: float = 0.10,
    max_scaler: float | None = None,
) -> float:
    """
    Calculate scaling factor for volatility targeting.
    """

    if current_volatility <= 0:
        raise ValueError("Current volatility must be positive")

    if target_volatility <= 0:
        raise ValueError("Target volatility must be positive")

    scaler = target_volatility / current_volatility

    if max_scaler is not None:
        scaler = min(scaler, max_scaler)

    return float(scaler)
