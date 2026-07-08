from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


OptionType = Literal["call", "put"]
PositionSide = Literal["long", "short"]


@dataclass(frozen=True)
class OptionLeg:
    option_type: OptionType
    side: PositionSide
    strike: float
    premium: float
    quantity: float = 1.0
    multiplier: float = 1.0


@dataclass(frozen=True)
class PayoffPoint:
    price: float
    payoff: float


def _validate_price(name: str, value: float) -> None:
    if value < 0:
        raise ValueError(f"{name} cannot be negative.")


def intrinsic_value(
    spot_at_expiry: float,
    strike: float,
    option_type: OptionType,
) -> float:
    """
    Calculate option intrinsic value at expiry.
    """
    _validate_price("spot_at_expiry", spot_at_expiry)
    _validate_price("strike", strike)

    if option_type == "call":
        return max(spot_at_expiry - strike, 0.0)

    if option_type == "put":
        return max(strike - spot_at_expiry, 0.0)

    raise ValueError("option_type must be 'call' or 'put'.")


def option_leg_payoff(
    spot_at_expiry: float,
    leg: OptionLeg,
) -> float:
    """
    Calculate payoff for one option leg.
    """
    intrinsic = intrinsic_value(
        spot_at_expiry=spot_at_expiry,
        strike=leg.strike,
        option_type=leg.option_type,
    )

    if leg.side == "long":
        payoff = intrinsic - leg.premium
    elif leg.side == "short":
        payoff = leg.premium - intrinsic
    else:
        raise ValueError("side must be 'long' or 'short'.")

    return payoff * leg.quantity * leg.multiplier


def strategy_payoff(
    spot_at_expiry: float,
    legs: list[OptionLeg],
) -> float:
    """
    Calculate total payoff for a multi-leg option strategy.
    """
    return sum(option_leg_payoff(spot_at_expiry, leg) for leg in legs)


def payoff_curve(
    price_range: list[float],
    legs: list[OptionLeg],
) -> list[PayoffPoint]:
    """
    Generate payoff values across a list of expiry prices.
    """
    return [
        PayoffPoint(
            price=price,
            payoff=strategy_payoff(price, legs),
        )
        for price in price_range
    ]


def long_call_payoff(spot_at_expiry: float, strike: float, premium: float) -> float:
    return option_leg_payoff(
        spot_at_expiry,
        OptionLeg(
            option_type="call",
            side="long",
            strike=strike,
            premium=premium,
        ),
    )


def short_call_payoff(spot_at_expiry: float, strike: float, premium: float) -> float:
    return option_leg_payoff(
        spot_at_expiry,
        OptionLeg(
            option_type="call",
            side="short",
            strike=strike,
            premium=premium,
        ),
    )


def long_put_payoff(spot_at_expiry: float, strike: float, premium: float) -> float:
    return option_leg_payoff(
        spot_at_expiry,
        OptionLeg(
            option_type="put",
            side="long",
            strike=strike,
            premium=premium,
        ),
    )


def short_put_payoff(spot_at_expiry: float, strike: float, premium: float) -> float:
    return option_leg_payoff(
        spot_at_expiry,
        OptionLeg(
            option_type="put",
            side="short",
            strike=strike,
            premium=premium,
        ),
    )


def stock_payoff(
    spot_at_expiry: float,
    entry_price: float,
    shares: float = 1.0,
) -> float:
    return (spot_at_expiry - entry_price) * shares


def vertical_call_spread_payoff(
    spot_at_expiry: float,
    long_strike: float,
    short_strike: float,
    net_debit: float,
) -> float:
    legs = [
        OptionLeg(
            option_type="call",
            side="long",
            strike=long_strike,
            premium=net_debit,
        ),
        OptionLeg(
            option_type="call",
            side="short",
            strike=short_strike,
            premium=0.0,
        ),
    ]

    return strategy_payoff(spot_at_expiry, legs)


def vertical_put_spread_payoff(
    spot_at_expiry: float,
    long_strike: float,
    short_strike: float,
    net_debit: float,
) -> float:
    legs = [
        OptionLeg(
            option_type="put",
            side="long",
            strike=long_strike,
            premium=net_debit,
        ),
        OptionLeg(
            option_type="put",
            side="short",
            strike=short_strike,
            premium=0.0,
        ),
    ]

    return strategy_payoff(spot_at_expiry, legs)


def covered_call_payoff(
    spot_at_expiry: float,
    stock_entry_price: float,
    call_strike: float,
    call_premium: float,
    shares: float = 1.0,
) -> float:
    """
    Payoff for long stock plus short call.
    """
    stock = stock_payoff(
        spot_at_expiry=spot_at_expiry,
        entry_price=stock_entry_price,
        shares=shares,
    )

    call = short_call_payoff(
        spot_at_expiry=spot_at_expiry,
        strike=call_strike,
        premium=call_premium,
    ) * shares

    return stock + call


def protective_put_payoff(
    spot_at_expiry: float,
    stock_entry_price: float,
    put_strike: float,
    put_premium: float,
    shares: float = 1.0,
) -> float:
    """
    Payoff for long stock plus long put.
    """
    stock = stock_payoff(
        spot_at_expiry=spot_at_expiry,
        entry_price=stock_entry_price,
        shares=shares,
    )

    put = long_put_payoff(
        spot_at_expiry=spot_at_expiry,
        strike=put_strike,
        premium=put_premium,
    ) * shares

    return stock + put
