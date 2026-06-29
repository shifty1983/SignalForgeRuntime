from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class MinimalResearchHandoffBacktestResult:
    total_return: float
    max_drawdown: float
    sharpe_ratio: float
    trade_count: int
    equity_curve: list[dict[str, Any]]
    turnover: float
    rebalance_count: int
    diagnostics: dict[str, Any]

    def to_performance_summary(self) -> dict[str, Any]:
        return {
            "total_return": self.total_return,
            "max_drawdown": self.max_drawdown,
            "sharpe_ratio": self.sharpe_ratio,
            "trade_count": self.trade_count,
            "equity_curve": self.equity_curve,
            "turnover": self.turnover,
            "rebalance_count": self.rebalance_count,
            "diagnostics": self.diagnostics,
        }


def run_minimal_research_handoff_backtest(
    *,
    fixture: Any,
    returns: Any,
    initial_equity: float = 1.0,
) -> dict[str, Any]:
    """
    Run a deterministic minimal backtest from a research-to-backtest handoff fixture.

    This is intentionally small. It validates that the accepted handoff can be
    consumed by backtesting logic without mutating research signals or weights.
    """
    if initial_equity <= 0 or not isfinite(float(initial_equity)):
        raise ValueError("initial_equity must be positive and finite")

    weights_by_asset = _extract_weights_by_asset(fixture)
    if not weights_by_asset:
        raise ValueError("handoff fixture has no weights_by_asset")

    returns_rows = _to_records(returns)
    if not returns_rows:
        raise ValueError("returns input is empty")

    daily_returns = _compute_portfolio_returns(
        weights_by_asset=weights_by_asset,
        returns_rows=returns_rows,
    )

    if not daily_returns:
        raise ValueError("no compatible returns rows for handoff fixture weights")

    equity_curve = _build_equity_curve(
        daily_returns=daily_returns,
        initial_equity=initial_equity,
    )

    total_return = equity_curve[-1]["equity"] / initial_equity - 1.0
    max_drawdown = _calculate_max_drawdown(equity_curve)
    sharpe_ratio = _calculate_simple_sharpe(
        [row["portfolio_return"] for row in daily_returns]
    )

    trade_count = sum(
        1 for symbol, weight in weights_by_asset.items() if abs(weight) > 0
    )

    result = MinimalResearchHandoffBacktestResult(
        total_return=round(total_return, 10),
        max_drawdown=round(max_drawdown, 10),
        sharpe_ratio=round(sharpe_ratio, 10),
        trade_count=trade_count,
        equity_curve=equity_curve,
        turnover=round(sum(abs(weight) for weight in weights_by_asset.values()), 10),
        rebalance_count=len(daily_returns),
        diagnostics={
            "source": "minimal_research_handoff_backtest",
            "candidate_id": getattr(fixture, "candidate_id", None),
            "source_operation_id": getattr(fixture, "source_operation_id", None),
            "asset_count": len(weights_by_asset),
        },
    )

    return result.to_performance_summary()


def _extract_weights_by_asset(fixture: Any) -> dict[str, float]:
    raw_weights = getattr(fixture, "weights_by_asset", None)

    if raw_weights is None and isinstance(fixture, Mapping):
        raw_weights = fixture.get("weights_by_asset")

    if not isinstance(raw_weights, Mapping):
        raise ValueError("handoff fixture weights_by_asset must be a mapping")

    weights: dict[str, float] = {}

    for symbol, raw_weight in raw_weights.items():
        try:
            weight = float(raw_weight)
        except (TypeError, ValueError) as error:
            raise ValueError(f"invalid weight for {symbol}: {raw_weight}") from error

        if not isfinite(weight):
            raise ValueError(f"non-finite weight for {symbol}: {raw_weight}")

        weights[str(symbol)] = weight

    return weights


def _compute_portfolio_returns(
    *,
    weights_by_asset: Mapping[str, float],
    returns_rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[str, float] = {}

    for row in returns_rows:
        symbol = str(row.get("symbol"))
        if symbol not in weights_by_asset:
            continue

        date = str(row.get("date"))
        if date in {"None", ""}:
            raise ValueError("returns row missing date")

        raw_return = row.get("return")
        try:
            asset_return = float(raw_return)
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"invalid return for {symbol} {date}: {raw_return}"
            ) from error

        if not isfinite(asset_return):
            raise ValueError(f"non-finite return for {symbol} {date}: {raw_return}")

        grouped[date] = grouped.get(date, 0.0) + (
            weights_by_asset[symbol] * asset_return
        )

    return [
        {
            "date": date,
            "portfolio_return": round(portfolio_return, 10),
        }
        for date, portfolio_return in sorted(grouped.items())
    ]


def _build_equity_curve(
    *,
    daily_returns: list[dict[str, Any]],
    initial_equity: float,
) -> list[dict[str, Any]]:
    equity = float(initial_equity)
    curve: list[dict[str, Any]] = []

    for row in daily_returns:
        equity *= 1.0 + row["portfolio_return"]
        curve.append(
            {
                "date": row["date"],
                "portfolio_return": row["portfolio_return"],
                "equity": round(equity, 10),
            }
        )

    return curve


def _calculate_max_drawdown(equity_curve: list[dict[str, Any]]) -> float:
    peak = equity_curve[0]["equity"]
    max_drawdown = 0.0

    for row in equity_curve:
        equity = row["equity"]
        peak = max(peak, equity)
        drawdown = equity / peak - 1.0
        max_drawdown = min(max_drawdown, drawdown)

    return max_drawdown


def _calculate_simple_sharpe(returns: list[float]) -> float:
    if len(returns) < 2:
        return 0.0

    mean_return = sum(returns) / len(returns)
    variance = sum((value - mean_return) ** 2 for value in returns) / (
        len(returns) - 1
    )

    if variance <= 0:
        return 0.0

    return mean_return / (variance**0.5)


def _to_records(value: Any) -> list[dict[str, Any]]:
    if hasattr(value, "to_dicts"):
        return value.to_dicts()

    if hasattr(value, "to_dict"):
        try:
            records = value.to_dict(orient="records")
            if isinstance(records, list):
                return records
        except TypeError:
            pass

    if isinstance(value, list):
        return [dict(row) for row in value]

    if isinstance(value, tuple):
        return [dict(row) for row in value]

    raise TypeError(f"unsupported returns input type: {type(value)!r}")
