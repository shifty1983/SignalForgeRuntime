from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd


_EPSILON = 1e-12


@dataclass(frozen=True)
class TradeSummary:
    number_of_trades: int
    winning_trades: int
    losing_trades: int
    breakeven_trades: int
    win_rate: float
    average_trade_return: float
    average_winner: float
    average_loser: float
    profit_factor: float
    largest_winner: float
    largest_loser: float
    average_holding_period_days: float
    total_fees: float
    total_slippage: float
    gross_pnl: float
    net_pnl: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _to_frame(
    trades: pd.DataFrame | Sequence[Mapping[str, Any]],
) -> pd.DataFrame:
    if isinstance(trades, pd.DataFrame):
        frame = trades.copy()
    else:
        frame = pd.DataFrame(list(trades))

    if frame.empty:
        return pd.DataFrame()

    return frame


def _side_to_direction(side: Any) -> float:
    if pd.isna(side):
        return np.nan

    if isinstance(side, (int, float, np.integer, np.floating)):
        if side > 0:
            return 1.0
        if side < 0:
            return -1.0
        return np.nan

    normalized = str(side).strip().lower()

    if normalized in {"long", "buy", "b", "bullish", "1"}:
        return 1.0

    if normalized in {"short", "sell", "s", "bearish", "-1"}:
        return -1.0

    return np.nan


def _safe_numeric(series: pd.Series, default: float = 0.0) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(default)


def normalize_trades(
    trades: pd.DataFrame | Sequence[Mapping[str, Any]],
    *,
    trade_id_col: str = "trade_id",
    symbol_col: str = "symbol",
    strategy_col: str = "strategy",
    side_col: str = "side",
    quantity_col: str = "quantity",
    entry_price_col: str = "entry_price",
    exit_price_col: str = "exit_price",
    entry_date_col: str = "entry_date",
    exit_date_col: str = "exit_date",
    pnl_col: str | None = None,
    return_col: str | None = None,
    fees_col: str = "fees",
    slippage_col: str = "slippage",
) -> pd.DataFrame:
    frame = _to_frame(trades)

    if frame.empty:
        return pd.DataFrame(
            columns=[
                "trade_id",
                "symbol",
                "strategy",
                "side",
                "direction",
                "quantity",
                "entry_price",
                "exit_price",
                "entry_date",
                "exit_date",
                "notional",
                "gross_pnl",
                "fees",
                "slippage",
                "net_pnl",
                "trade_return",
                "holding_period_days",
                "is_winner",
                "is_loser",
                "is_breakeven",
            ]
        )

    normalized = pd.DataFrame(index=frame.index)

    normalized["trade_id"] = (
        frame[trade_id_col]
        if trade_id_col in frame.columns
        else range(1, len(frame) + 1)
    )

    normalized["symbol"] = (
        frame[symbol_col].astype(str)
        if symbol_col in frame.columns
        else "UNKNOWN"
    )

    normalized["strategy"] = (
        frame[strategy_col].astype(str)
        if strategy_col in frame.columns
        else "UNKNOWN"
    )

    normalized["side"] = (
        frame[side_col].astype(str)
        if side_col in frame.columns
        else np.nan
    )

    normalized["direction"] = (
        frame[side_col].map(_side_to_direction)
        if side_col in frame.columns
        else np.nan
    )

    normalized["quantity"] = (
        _safe_numeric(frame[quantity_col]).abs()
        if quantity_col in frame.columns
        else np.nan
    )

    normalized["entry_price"] = (
        _safe_numeric(frame[entry_price_col], default=np.nan)
        if entry_price_col in frame.columns
        else np.nan
    )

    normalized["exit_price"] = (
        _safe_numeric(frame[exit_price_col], default=np.nan)
        if exit_price_col in frame.columns
        else np.nan
    )

    normalized["entry_date"] = (
        pd.to_datetime(frame[entry_date_col], errors="coerce")
        if entry_date_col in frame.columns
        else pd.NaT
    )

    normalized["exit_date"] = (
        pd.to_datetime(frame[exit_date_col], errors="coerce")
        if exit_date_col in frame.columns
        else pd.NaT
    )

    normalized["fees"] = (
        _safe_numeric(frame[fees_col])
        if fees_col in frame.columns
        else 0.0
    )

    normalized["slippage"] = (
        _safe_numeric(frame[slippage_col])
        if slippage_col in frame.columns
        else 0.0
    )

    normalized["notional"] = (
        normalized["quantity"] * normalized["entry_price"].abs()
    )

    can_derive_pnl = normalized[
        ["direction", "quantity", "entry_price", "exit_price"]
    ].notna().all(axis=1)

    derived_gross_pnl = (
        (normalized["exit_price"] - normalized["entry_price"])
        * normalized["quantity"]
        * normalized["direction"]
    )

    if pnl_col is not None and pnl_col in frame.columns:
        normalized["net_pnl"] = _safe_numeric(frame[pnl_col], default=np.nan)
        normalized["gross_pnl"] = (
            normalized["net_pnl"] + normalized["fees"] + normalized["slippage"]
        )
    else:
        normalized["gross_pnl"] = np.where(can_derive_pnl, derived_gross_pnl, np.nan)
        normalized["net_pnl"] = (
            normalized["gross_pnl"] - normalized["fees"] - normalized["slippage"]
        )

    if return_col is not None and return_col in frame.columns:
        normalized["trade_return"] = _safe_numeric(frame[return_col], default=np.nan)
    else:
        normalized["trade_return"] = np.where(
            normalized["notional"].abs() > _EPSILON,
            normalized["net_pnl"] / normalized["notional"].abs(),
            np.nan,
        )

    holding_period = normalized["exit_date"] - normalized["entry_date"]
    normalized["holding_period_days"] = holding_period.dt.days.astype(float)

    normalized["is_winner"] = normalized["net_pnl"] > 0.0
    normalized["is_loser"] = normalized["net_pnl"] < 0.0
    normalized["is_breakeven"] = normalized["net_pnl"].abs() <= _EPSILON

    return normalized.reset_index(drop=True)


def summarize_trades(
    trades: pd.DataFrame | Sequence[Mapping[str, Any]],
    **normalize_kwargs: Any,
) -> TradeSummary:
    normalized = normalize_trades(trades, **normalize_kwargs)

    if normalized.empty:
        return TradeSummary(
            number_of_trades=0,
            winning_trades=0,
            losing_trades=0,
            breakeven_trades=0,
            win_rate=0.0,
            average_trade_return=0.0,
            average_winner=0.0,
            average_loser=0.0,
            profit_factor=0.0,
            largest_winner=0.0,
            largest_loser=0.0,
            average_holding_period_days=0.0,
            total_fees=0.0,
            total_slippage=0.0,
            gross_pnl=0.0,
            net_pnl=0.0,
        )

    pnl = normalized["net_pnl"].dropna()
    trade_returns = normalized["trade_return"].dropna()
    holding_periods = normalized["holding_period_days"].dropna()

    winners = pnl[pnl > 0.0]
    losers = pnl[pnl < 0.0]
    breakeven = pnl[pnl.abs() <= _EPSILON]

    gross_profit = float(winners.sum()) if not winners.empty else 0.0
    gross_loss = float(abs(losers.sum())) if not losers.empty else 0.0

    if gross_loss > _EPSILON:
        profit_factor = gross_profit / gross_loss
    elif gross_profit > _EPSILON:
        profit_factor = float("inf")
    else:
        profit_factor = 0.0

    number_of_trades = int(len(normalized))

    return TradeSummary(
        number_of_trades=number_of_trades,
        winning_trades=int(len(winners)),
        losing_trades=int(len(losers)),
        breakeven_trades=int(len(breakeven)),
        win_rate=float(len(winners) / number_of_trades) if number_of_trades else 0.0,
        average_trade_return=float(trade_returns.mean()) if not trade_returns.empty else 0.0,
        average_winner=float(winners.mean()) if not winners.empty else 0.0,
        average_loser=float(losers.mean()) if not losers.empty else 0.0,
        profit_factor=float(profit_factor),
        largest_winner=float(winners.max()) if not winners.empty else 0.0,
        largest_loser=float(losers.min()) if not losers.empty else 0.0,
        average_holding_period_days=(
            float(holding_periods.mean()) if not holding_periods.empty else 0.0
        ),
        total_fees=float(normalized["fees"].sum()),
        total_slippage=float(normalized["slippage"].sum()),
        gross_pnl=float(normalized["gross_pnl"].sum()),
        net_pnl=float(normalized["net_pnl"].sum()),
    )


def trade_summary_by_symbol(
    trades: pd.DataFrame | Sequence[Mapping[str, Any]],
    **normalize_kwargs: Any,
) -> pd.DataFrame:
    normalized = normalize_trades(trades, **normalize_kwargs)

    if normalized.empty:
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []

    for symbol, group in normalized.groupby("symbol"):
        summary = summarize_trades(group).to_dict()
        summary["symbol"] = symbol
        rows.append(summary)

    return pd.DataFrame(rows).set_index("symbol").sort_index()


def trade_summary_by_strategy(
    trades: pd.DataFrame | Sequence[Mapping[str, Any]],
    **normalize_kwargs: Any,
) -> pd.DataFrame:
    normalized = normalize_trades(trades, **normalize_kwargs)

    if normalized.empty:
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []

    for strategy, group in normalized.groupby("strategy"):
        summary = summarize_trades(group).to_dict()
        summary["strategy"] = strategy
        rows.append(summary)

    return pd.DataFrame(rows).set_index("strategy").sort_index()


def trade_blotter(
    trades: pd.DataFrame | Sequence[Mapping[str, Any]],
    *,
    sort_by: str | None = "exit_date",
    ascending: bool = True,
    **normalize_kwargs: Any,
) -> pd.DataFrame:
    normalized = normalize_trades(trades, **normalize_kwargs)

    if normalized.empty:
        return normalized

    if sort_by is not None:
        if sort_by not in normalized.columns:
            raise ValueError(f"sort_by column '{sort_by}' not found in trade blotter.")

        normalized = normalized.sort_values(sort_by, ascending=ascending)

    return normalized.reset_index(drop=True)
