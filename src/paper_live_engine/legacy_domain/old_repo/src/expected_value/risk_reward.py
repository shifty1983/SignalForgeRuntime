from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class RiskRewardMetrics:
    max_profit: float
    max_loss: float
    reward_risk: float
    risk_reward: float
    breakeven: float | None = None
    breakeven_distance_pct: float | None = None
    return_on_risk_value: float | None = None


def _absolute_risk(max_loss: float) -> float:
    """
    Convert max loss into positive capital-at-risk value.
    """
    return abs(max_loss)


def reward_risk_ratio(
    max_profit: float,
    max_loss: float,
) -> float:
    """
    Calculate reward-to-risk ratio.

    max_loss can be supplied as either positive risk or negative PnL.
    """
    risk = _absolute_risk(max_loss)

    if risk == 0:
        return 0.0

    if math.isinf(max_profit):
        return float("inf")

    return max_profit / risk


def risk_reward_ratio(
    max_loss: float,
    max_profit: float,
) -> float:
    """
    Calculate risk-to-reward ratio.
    """
    if max_profit <= 0:
        return 0.0

    return _absolute_risk(max_loss) / max_profit


def breakeven_long_call(
    strike: float,
    premium: float,
) -> float:
    """
    Breakeven price for a long call.
    """
    return strike + premium


def breakeven_short_call(
    strike: float,
    premium: float,
) -> float:
    """
    Breakeven price for a short call.
    """
    return strike + premium


def breakeven_long_put(
    strike: float,
    premium: float,
) -> float:
    """
    Breakeven price for a long put.
    """
    return strike - premium


def breakeven_short_put(
    strike: float,
    premium: float,
) -> float:
    """
    Breakeven price for a short put.
    """
    return strike - premium


def breakeven_distance_pct(
    spot: float,
    breakeven: float,
) -> float:
    """
    Distance from current spot to breakeven as a percentage of spot.
    """
    if spot <= 0:
        return 0.0

    return (breakeven - spot) / spot


def max_profit_long_call() -> float:
    """
    Long call has theoretically unlimited upside.
    """
    return float("inf")


def max_loss_long_call(
    premium: float,
) -> float:
    """
    Max loss for long call equals premium paid.
    """
    return -abs(premium)


def max_profit_short_call(
    premium: float,
) -> float:
    """
    Max profit for short call equals premium received.
    """
    return premium


def max_loss_short_call() -> float:
    """
    Short call has theoretically unlimited loss.
    """
    return float("-inf")


def max_profit_long_put(
    strike: float,
    premium: float,
) -> float:
    """
    Max profit for long put occurs if underlying goes to zero.
    """
    return strike - premium


def max_loss_long_put(
    premium: float,
) -> float:
    """
    Max loss for long put equals premium paid.
    """
    return -abs(premium)


def max_profit_short_put(
    premium: float,
) -> float:
    """
    Max profit for short put equals premium received.
    """
    return premium


def max_loss_short_put(
    strike: float,
    premium: float,
) -> float:
    """
    Max loss for short put occurs if underlying goes to zero.
    """
    return -(strike - premium)


def max_profit_debit_spread(
    long_strike: float,
    short_strike: float,
    net_debit: float,
) -> float:
    """
    Max profit for a debit vertical spread.
    """
    width = abs(short_strike - long_strike)

    return width - net_debit


def max_loss_debit_spread(
    net_debit: float,
) -> float:
    """
    Max loss for a debit spread equals net debit paid.
    """
    return -abs(net_debit)


def max_profit_credit_spread(
    net_credit: float,
) -> float:
    """
    Max profit for a credit spread equals credit received.
    """
    return net_credit


def max_loss_credit_spread(
    long_strike: float,
    short_strike: float,
    net_credit: float,
) -> float:
    """
    Max loss for a credit vertical spread.
    """
    width = abs(short_strike - long_strike)

    return -(width - net_credit)


def return_on_risk(
    profit: float,
    max_risk: float,
) -> float:
    """
    Profit relative to capital at risk.
    """
    risk = _absolute_risk(max_risk)

    if risk == 0:
        return 0.0

    return profit / risk


def profit_factor(
    gross_profit: float,
    gross_loss: float,
) -> float:
    """
    Gross profit divided by gross loss.
    """
    loss = abs(gross_loss)

    if loss == 0:
        return float("inf") if gross_profit > 0 else 0.0

    return gross_profit / loss


def expectancy(
    win_probability: float,
    average_win: float,
    loss_probability: float,
    average_loss: float,
) -> float:
    """
    Trading expectancy from win/loss probability and average win/loss.
    """
    if win_probability < 0 or loss_probability < 0:
        raise ValueError("Probabilities cannot be negative.")

    if win_probability > 1 or loss_probability > 1:
        raise ValueError("Probabilities cannot be greater than 1.")

    return (win_probability * average_win) + (loss_probability * average_loss)


def evaluate_risk_reward(
    max_profit: float,
    max_loss: float,
    spot: float | None = None,
    breakeven: float | None = None,
) -> RiskRewardMetrics:
    """
    Bundle core risk/reward metrics.
    """
    rr = reward_risk_ratio(
        max_profit=max_profit,
        max_loss=max_loss,
    )

    risk_reward = risk_reward_ratio(
        max_loss=max_loss,
        max_profit=max_profit,
    )

    distance = None

    if spot is not None and breakeven is not None:
        distance = breakeven_distance_pct(
            spot=spot,
            breakeven=breakeven,
        )

    return RiskRewardMetrics(
        max_profit=max_profit,
        max_loss=max_loss,
        reward_risk=rr,
        risk_reward=risk_reward,
        breakeven=breakeven,
        breakeven_distance_pct=distance,
        return_on_risk_value=return_on_risk(
            profit=max_profit,
            max_risk=max_loss,
        )
        if not math.isinf(max_profit)
        else float("inf"),
    )
