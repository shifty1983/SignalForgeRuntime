from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class ProbabilityInputs:
    spot: float
    strike: float
    volatility: float
    time_to_expiry: float
    risk_free_rate: float = 0.0
    dividend_yield: float = 0.0


def clamp_probability(value: float) -> float:
    """
    Clamp a numeric value into a valid probability range.
    """
    return max(0.0, min(1.0, value))


def normal_pdf(x: float) -> float:
    """
    Standard normal probability density function.
    """
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def normal_cdf(x: float) -> float:
    """
    Standard normal cumulative distribution function.
    """
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _validate_positive(name: str, value: float) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero.")


def _forward_price(
    spot: float,
    time_to_expiry: float,
    risk_free_rate: float = 0.0,
    dividend_yield: float = 0.0,
) -> float:
    """
    Risk-neutral forward price approximation.
    """
    if time_to_expiry <= 0:
        return spot

    return spot * math.exp((risk_free_rate - dividend_yield) * time_to_expiry)


def expected_move_pct(
    volatility: float,
    time_to_expiry: float,
    sigma: float = 1.0,
) -> float:
    """
    Expected percentage move using annualized volatility.

    Example:
    volatility=0.20, time_to_expiry=0.25, sigma=1
    means a one-standard-deviation move over 3 months.
    """
    if volatility <= 0 or time_to_expiry <= 0:
        return 0.0

    return abs(sigma) * volatility * math.sqrt(time_to_expiry)


def expected_move_price(
    spot: float,
    volatility: float,
    time_to_expiry: float,
    sigma: float = 1.0,
) -> float:
    """
    Expected dollar move from current spot price.
    """
    _validate_positive("spot", spot)

    return spot * expected_move_pct(
        volatility=volatility,
        time_to_expiry=time_to_expiry,
        sigma=sigma,
    )


def probability_above_price(
    spot: float,
    target_price: float,
    volatility: float,
    time_to_expiry: float,
    risk_free_rate: float = 0.0,
    dividend_yield: float = 0.0,
) -> float:
    """
    Approximate probability that terminal price finishes above target_price.
    """
    _validate_positive("spot", spot)
    _validate_positive("target_price", target_price)

    forward = _forward_price(
        spot=spot,
        time_to_expiry=time_to_expiry,
        risk_free_rate=risk_free_rate,
        dividend_yield=dividend_yield,
    )

    if volatility <= 0 or time_to_expiry <= 0:
        return float(forward > target_price)

    denominator = volatility * math.sqrt(time_to_expiry)

    z_score = (
        math.log(spot / target_price)
        + (risk_free_rate - dividend_yield - 0.5 * volatility**2) * time_to_expiry
    ) / denominator

    return clamp_probability(normal_cdf(z_score))


def probability_below_price(
    spot: float,
    target_price: float,
    volatility: float,
    time_to_expiry: float,
    risk_free_rate: float = 0.0,
    dividend_yield: float = 0.0,
) -> float:
    """
    Approximate probability that terminal price finishes below target_price.
    """
    return clamp_probability(
        1.0
        - probability_above_price(
            spot=spot,
            target_price=target_price,
            volatility=volatility,
            time_to_expiry=time_to_expiry,
            risk_free_rate=risk_free_rate,
            dividend_yield=dividend_yield,
        )
    )


def probability_between_prices(
    spot: float,
    lower_price: float,
    upper_price: float,
    volatility: float,
    time_to_expiry: float,
    risk_free_rate: float = 0.0,
    dividend_yield: float = 0.0,
) -> float:
    """
    Approximate probability that terminal price finishes between two prices.
    """
    _validate_positive("lower_price", lower_price)
    _validate_positive("upper_price", upper_price)

    if lower_price >= upper_price:
        raise ValueError("lower_price must be less than upper_price.")

    probability_above_lower = probability_above_price(
        spot=spot,
        target_price=lower_price,
        volatility=volatility,
        time_to_expiry=time_to_expiry,
        risk_free_rate=risk_free_rate,
        dividend_yield=dividend_yield,
    )

    probability_above_upper = probability_above_price(
        spot=spot,
        target_price=upper_price,
        volatility=volatility,
        time_to_expiry=time_to_expiry,
        risk_free_rate=risk_free_rate,
        dividend_yield=dividend_yield,
    )

    return clamp_probability(probability_above_lower - probability_above_upper)


def probability_itm_call(
    spot: float,
    strike: float,
    volatility: float,
    time_to_expiry: float,
    risk_free_rate: float = 0.0,
    dividend_yield: float = 0.0,
) -> float:
    """
    Approximate probability that a call expires in the money.
    """
    return probability_above_price(
        spot=spot,
        target_price=strike,
        volatility=volatility,
        time_to_expiry=time_to_expiry,
        risk_free_rate=risk_free_rate,
        dividend_yield=dividend_yield,
    )


def probability_itm_put(
    spot: float,
    strike: float,
    volatility: float,
    time_to_expiry: float,
    risk_free_rate: float = 0.0,
    dividend_yield: float = 0.0,
) -> float:
    """
    Approximate probability that a put expires in the money.
    """
    return probability_below_price(
        spot=spot,
        target_price=strike,
        volatility=volatility,
        time_to_expiry=time_to_expiry,
        risk_free_rate=risk_free_rate,
        dividend_yield=dividend_yield,
    )


def probability_otm_call(
    spot: float,
    strike: float,
    volatility: float,
    time_to_expiry: float,
    risk_free_rate: float = 0.0,
    dividend_yield: float = 0.0,
) -> float:
    """
    Approximate probability that a call expires out of the money.
    """
    return clamp_probability(
        1.0
        - probability_itm_call(
            spot=spot,
            strike=strike,
            volatility=volatility,
            time_to_expiry=time_to_expiry,
            risk_free_rate=risk_free_rate,
            dividend_yield=dividend_yield,
        )
    )


def probability_otm_put(
    spot: float,
    strike: float,
    volatility: float,
    time_to_expiry: float,
    risk_free_rate: float = 0.0,
    dividend_yield: float = 0.0,
) -> float:
    """
    Approximate probability that a put expires out of the money.
    """
    return clamp_probability(
        1.0
        - probability_itm_put(
            spot=spot,
            strike=strike,
            volatility=volatility,
            time_to_expiry=time_to_expiry,
            risk_free_rate=risk_free_rate,
            dividend_yield=dividend_yield,
        )
    )


def probability_profit_long_call(
    spot: float,
    strike: float,
    premium: float,
    volatility: float,
    time_to_expiry: float,
    risk_free_rate: float = 0.0,
    dividend_yield: float = 0.0,
) -> float:
    """
    Approximate probability that a long call expires profitable.
    """
    breakeven = strike + premium

    return probability_above_price(
        spot=spot,
        target_price=breakeven,
        volatility=volatility,
        time_to_expiry=time_to_expiry,
        risk_free_rate=risk_free_rate,
        dividend_yield=dividend_yield,
    )


def probability_profit_long_put(
    spot: float,
    strike: float,
    premium: float,
    volatility: float,
    time_to_expiry: float,
    risk_free_rate: float = 0.0,
    dividend_yield: float = 0.0,
) -> float:
    """
    Approximate probability that a long put expires profitable.
    """
    breakeven = strike - premium

    if breakeven <= 0:
        return 0.0

    return probability_below_price(
        spot=spot,
        target_price=breakeven,
        volatility=volatility,
        time_to_expiry=time_to_expiry,
        risk_free_rate=risk_free_rate,
        dividend_yield=dividend_yield,
    )


def probability_touch(
    spot: float,
    target_price: float,
    volatility: float,
    time_to_expiry: float,
    risk_free_rate: float = 0.0,
    dividend_yield: float = 0.0,
) -> float:
    """
    Rough approximation of probability that price touches target before expiry.

    Common rule of thumb:
    probability of touch is approximately 2x probability of finishing beyond target.
    """
    _validate_positive("spot", spot)
    _validate_positive("target_price", target_price)

    if target_price == spot:
        return 1.0

    if target_price > spot:
        finish_probability = probability_above_price(
            spot=spot,
            target_price=target_price,
            volatility=volatility,
            time_to_expiry=time_to_expiry,
            risk_free_rate=risk_free_rate,
            dividend_yield=dividend_yield,
        )
    else:
        finish_probability = probability_below_price(
            spot=spot,
            target_price=target_price,
            volatility=volatility,
            time_to_expiry=time_to_expiry,
            risk_free_rate=risk_free_rate,
            dividend_yield=dividend_yield,
        )

    return clamp_probability(2.0 * finish_probability)


def probability_of_profit(
    expected_return: float,
    volatility: float,
    time_horizon: float,
) -> float:
    """
    Approximate probability of positive return assuming normally distributed returns.
    """
    if volatility <= 0 or time_horizon <= 0:
        return float(expected_return > 0)

    sigma_t = volatility * math.sqrt(time_horizon)

    z_score = expected_return / sigma_t

    return clamp_probability(normal_cdf(z_score))
