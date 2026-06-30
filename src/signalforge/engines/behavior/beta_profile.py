from __future__ import annotations

from collections.abc import Sequence
from typing import Any


BETA_STATES = {
    "high_beta",
    "market_beta",
    "low_beta",
    "inverse_beta",
    "unstable_beta",
}

MARKET_SENSITIVITY_STATES = {
    "high_market_sensitivity",
    "normal_market_sensitivity",
    "defensive_market_sensitivity",
    "inverse_market_sensitivity",
    "unstable_market_sensitivity",
}

CORRELATION_BREAKDOWN_STATES = {
    "correlation_intact",
    "correlation_weakening",
    "correlation_breakdown",
}


def build_beta_profile(
    prices: Sequence[float],
    benchmark_prices: Sequence[float],
    *,
    window: int = 60,
    min_periods: int = 20,
) -> dict[str, Any]:
    """Build beta / market-sensitivity behavior from asset and benchmark prices.

    This is an asset-behavior classification helper. It uses local price series
    only and does not fetch data, route orders, select contracts, model fills,
    or trigger any automatic action.
    """

    asset_returns = _returns_from_prices(prices)
    benchmark_returns = _returns_from_prices(benchmark_prices)
    paired = _aligned_pairs(asset_returns, benchmark_returns, window=window)

    if len(paired) < min_periods:
        return {
            "beta_status": "blocked",
            "beta_estimate": None,
            "beta_state": None,
            "market_sensitivity": None,
            "beta_correlation": None,
            "correlation_breakdown": None,
            "beta_observation_count": len(paired),
            "beta_warning": f"requires at least {min_periods} aligned return observations",
        }

    asset = [item[0] for item in paired]
    benchmark = [item[1] for item in paired]
    beta = estimate_beta(asset, benchmark)
    corr = estimate_correlation(asset, benchmark)

    beta_state = classify_beta_state(beta_estimate=beta, correlation=corr)
    market_sensitivity = classify_market_sensitivity(beta_state=beta_state)
    breakdown = classify_correlation_breakdown(correlation=corr)

    return {
        "beta_status": "ready",
        "beta_estimate": beta,
        "beta_state": beta_state,
        "market_sensitivity": market_sensitivity,
        "beta_correlation": corr,
        "correlation_breakdown": breakdown,
        "beta_observation_count": len(paired),
        "beta_warning": None,
    }


def estimate_beta(asset_returns: Sequence[float], benchmark_returns: Sequence[float]) -> float | None:
    paired = list(zip(asset_returns, benchmark_returns))
    if len(paired) < 2:
        return None

    asset = [float(item[0]) for item in paired]
    benchmark = [float(item[1]) for item in paired]
    benchmark_mean = sum(benchmark) / len(benchmark)
    asset_mean = sum(asset) / len(asset)

    variance = sum((value - benchmark_mean) ** 2 for value in benchmark)
    if variance == 0:
        return None

    covariance = sum(
        (asset_value - asset_mean) * (benchmark_value - benchmark_mean)
        for asset_value, benchmark_value in zip(asset, benchmark)
    )
    return round(covariance / variance, 4)


def estimate_correlation(asset_returns: Sequence[float], benchmark_returns: Sequence[float]) -> float | None:
    paired = list(zip(asset_returns, benchmark_returns))
    if len(paired) < 2:
        return None

    asset = [float(item[0]) for item in paired]
    benchmark = [float(item[1]) for item in paired]
    asset_mean = sum(asset) / len(asset)
    benchmark_mean = sum(benchmark) / len(benchmark)

    asset_variance = sum((value - asset_mean) ** 2 for value in asset)
    benchmark_variance = sum((value - benchmark_mean) ** 2 for value in benchmark)
    denominator = (asset_variance * benchmark_variance) ** 0.5
    if denominator == 0:
        return None

    covariance = sum(
        (asset_value - asset_mean) * (benchmark_value - benchmark_mean)
        for asset_value, benchmark_value in zip(asset, benchmark)
    )
    return round(covariance / denominator, 4)


def classify_beta_state(*, beta_estimate: float | None, correlation: float | None) -> str:
    if beta_estimate is None or correlation is None:
        return "unstable_beta"

    if abs(correlation) < 0.30:
        return "unstable_beta"

    if beta_estimate < -0.20:
        return "inverse_beta"

    if beta_estimate >= 1.30:
        return "high_beta"

    if beta_estimate >= 0.75:
        return "market_beta"

    return "low_beta"


def classify_market_sensitivity(*, beta_state: str | None) -> str:
    state = _clean(beta_state)

    if state == "high_beta":
        return "high_market_sensitivity"

    if state == "market_beta":
        return "normal_market_sensitivity"

    if state == "low_beta":
        return "defensive_market_sensitivity"

    if state == "inverse_beta":
        return "inverse_market_sensitivity"

    return "unstable_market_sensitivity"


def classify_correlation_breakdown(*, correlation: float | None) -> str:
    if correlation is None:
        return "correlation_breakdown"

    abs_corr = abs(correlation)
    if abs_corr < 0.30:
        return "correlation_breakdown"

    if abs_corr < 0.50:
        return "correlation_weakening"

    return "correlation_intact"


def _returns_from_prices(prices: Sequence[float]) -> list[float]:
    output: list[float] = []
    numeric = [float(value) for value in prices if value is not None]
    for previous, current in zip(numeric, numeric[1:]):
        if previous <= 0:
            continue
        output.append((current / previous) - 1.0)
    return output


def _aligned_pairs(
    asset_returns: Sequence[float],
    benchmark_returns: Sequence[float],
    *,
    window: int,
) -> list[tuple[float, float]]:
    length = min(len(asset_returns), len(benchmark_returns))
    if length <= 0:
        return []

    paired = list(zip(asset_returns[-length:], benchmark_returns[-length:]))
    if window > 0:
        paired = paired[-window:]
    return [(float(asset), float(benchmark)) for asset, benchmark in paired]


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    return text or None


