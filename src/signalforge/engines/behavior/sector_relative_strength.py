from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def infer_sector_benchmark_symbol(symbol: Any, asset_class: Any | None = None) -> str:
    """Resolve a simple sector/asset-class benchmark for relative strength.

    This intentionally stays deterministic and dependency-free. Callers can
    override by passing a specific sector benchmark into the profile builder.
    """

    text = _clean(symbol)
    asset_class_text = _clean(asset_class)

    sector_map = {
        "xlk": "QQQ",
        "smh": "QQQ",
        "soxx": "QQQ",
        "xlf": "SPY",
        "xle": "DBC",
        "xlv": "SPY",
        "xli": "SPY",
        "xly": "SPY",
        "xlp": "SPY",
        "xlu": "SPY",
        "xlb": "DBC",
        "xlre": "VNQ",
        "xlc": "QQQ",
        "iwm": "SPY",
        "ijr": "IWM",
        "ijh": "SPY",
        "agg": "BND",
        "bnd": "AGG",
        "tlt": "AGG",
        "ief": "AGG",
        "hyg": "LQD",
        "lqd": "AGG",
        "gld": "DBC",
        "slv": "DBC",
        "uso": "DBC",
        "uup": "CEW",
        "vixy": "SPY",
        "vxx": "SPY",
    }

    if text in sector_map:
        return sector_map[text]

    if asset_class_text in {"bonds", "bond", "credit", "fixed_income"}:
        return "AGG"
    if asset_class_text in {"commodities", "commodity", "energy", "metals"}:
        return "DBC"
    if asset_class_text in {"currencies", "currency", "fx"}:
        return "UUP"
    if asset_class_text in {"volatility", "vol"}:
        return "SPY"

    return "SPY"


def build_sector_relative_strength_profile(
    *,
    asset_returns: Sequence[float] | None = None,
    sector_returns: Sequence[float] | None = None,
    symbol: Any | None = None,
    sector_benchmark_symbol: Any | None = None,
    asset_class: Any | None = None,
) -> dict[str, Any]:
    """Classify asset performance relative to its sector/asset benchmark.

    The function accepts return series so it can be used by any caller that has
    already calculated prices/returns. If the benchmark symbol is not supplied,
    a deterministic resolver is used.
    """

    benchmark = _string(sector_benchmark_symbol) or infer_sector_benchmark_symbol(
        symbol, asset_class
    )
    asset_total_return = _compound_return(asset_returns)
    sector_total_return = _compound_return(sector_returns)
    relative_return = asset_total_return - sector_total_return

    asset_series = _float_list(asset_returns)
    sector_series = _float_list(sector_returns)
    relative_series = [a - b for a, b in zip(asset_series, sector_series)]
    relative_trend = _relative_trend(relative_series)

    state = _sector_relative_state(relative_return)
    leadership = _sector_leadership_state(state, relative_trend)

    return {
        "sector_benchmark_symbol": benchmark,
        "sector_relative_return": round(relative_return, 6),
        "sector_relative_state": state,
        "sector_relative_trend": relative_trend,
        "sector_leadership_state": leadership,
    }


def _sector_relative_state(relative_return: float) -> str:
    if relative_return >= 0.10:
        return "sector_leader"
    if relative_return >= 0.03:
        return "sector_outperformer"
    if relative_return <= -0.10:
        return "sector_laggard"
    if relative_return <= -0.03:
        return "sector_underperformer"
    return "sector_performer"


def _relative_trend(relative_series: Sequence[float]) -> str:
    values = list(relative_series)
    if len(values) < 4:
        return "stable_sector_relative_strength"

    midpoint = max(len(values) // 2, 1)
    early = sum(values[:midpoint]) / len(values[:midpoint])
    late = sum(values[midpoint:]) / len(values[midpoint:])
    change = late - early

    if change >= 0.0025:
        return "improving_sector_relative_strength"
    if change <= -0.0025:
        return "deteriorating_sector_relative_strength"
    return "stable_sector_relative_strength"


def _sector_leadership_state(state: str, trend: str) -> str:
    if state == "sector_leader" and trend != "deteriorating_sector_relative_strength":
        return "leading_sector"
    if state in {"sector_leader", "sector_outperformer"} and trend == "deteriorating_sector_relative_strength":
        return "weakening_sector_leader"
    if state in {"sector_underperformer", "sector_laggard"} and trend == "improving_sector_relative_strength":
        return "improving_sector_laggard"
    if state == "sector_laggard":
        return "lagging_sector"
    if state == "sector_outperformer":
        return "outperforming_sector"
    if state == "sector_underperformer":
        return "underperforming_sector"
    return "sector_performer"


def _compound_return(values: Sequence[float] | None) -> float:
    result = 1.0
    for value in _float_list(values):
        result *= 1.0 + value
    return result - 1.0


def _float_list(values: Sequence[float] | None) -> list[float]:
    if values is None or isinstance(values, (str, bytes)):
        return []
    output: list[float] = []
    for value in values:
        try:
            output.append(float(value))
        except (TypeError, ValueError):
            continue
    return output


def _string(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().upper()


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()

