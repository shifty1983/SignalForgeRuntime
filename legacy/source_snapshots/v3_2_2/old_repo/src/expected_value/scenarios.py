from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Scenario:
    name: str
    price: float
    probability: float
    return_pct: float | None = None


@dataclass(frozen=True)
class ScenarioSet:
    name: str
    scenarios: list[Scenario]


def _validate_spot(spot: float) -> None:
    if spot <= 0:
        raise ValueError("spot must be greater than zero.")


def _validate_probability(probability: float) -> None:
    if probability < 0 or probability > 1:
        raise ValueError("probability must be between 0 and 1.")


def validate_scenarios(
    scenarios: list[Scenario],
    tolerance: float = 1e-6,
) -> None:
    """
    Validate scenario probabilities and prices.
    """
    if not scenarios:
        raise ValueError("scenarios cannot be empty.")

    for scenario in scenarios:
        if scenario.price <= 0:
            raise ValueError("scenario price must be greater than zero.")
        _validate_probability(scenario.probability)

    total_probability = sum(s.probability for s in scenarios)

    if abs(total_probability - 1.0) > tolerance:
        raise ValueError("scenario probabilities must sum to 1.0.")


def normalize_scenarios(
    scenarios: list[Scenario],
) -> list[Scenario]:
    """
    Normalize scenario probabilities so they sum to 1.
    """
    if not scenarios:
        raise ValueError("scenarios cannot be empty.")

    total_probability = sum(s.probability for s in scenarios)

    if total_probability <= 0:
        raise ValueError("total probability must be greater than zero.")

    return [
        Scenario(
            name=scenario.name,
            price=scenario.price,
            probability=scenario.probability / total_probability,
            return_pct=scenario.return_pct,
        )
        for scenario in scenarios
    ]


def scenario_from_return(
    name: str,
    spot: float,
    return_pct: float,
    probability: float,
) -> Scenario:
    """
    Create a price scenario from a return assumption.
    """
    _validate_spot(spot)
    _validate_probability(probability)

    return Scenario(
        name=name,
        price=max(spot * (1.0 + return_pct), 0.01),
        probability=probability,
        return_pct=return_pct,
    )


def generate_price_scenarios(
    spot: float,
    volatility: float,
    time_to_expiry: float,
    moves: tuple[float, ...] = (-2.0, -1.0, 0.0, 1.0, 2.0),
    probabilities: tuple[float, ...] | None = None,
) -> list[Scenario]:
    """
    Generate volatility-based price scenarios.

    moves are expressed as standard-deviation units.
    """
    _validate_spot(spot)

    if not moves:
        raise ValueError("moves cannot be empty.")

    if probabilities is not None and len(probabilities) != len(moves):
        raise ValueError("probabilities must have the same length as moves.")

    if volatility <= 0 or time_to_expiry <= 0:
        sigma_move = 0.0
    else:
        sigma_move = volatility * math.sqrt(time_to_expiry)

    if probabilities is None:
        probability_values = tuple(1.0 / len(moves) for _ in moves)
    else:
        probability_values = probabilities

    scenarios = []

    for move, probability in zip(moves, probability_values, strict=True):
        _validate_probability(probability)

        return_pct = move * sigma_move

        scenarios.append(
            scenario_from_return(
                name=f"{move:+.0f}Ïƒ",
                spot=spot,
                return_pct=return_pct,
                probability=probability,
            )
        )

    return normalize_scenarios(scenarios)


def bull_base_bear_scenarios(
    spot: float,
    bull_return: float = 0.15,
    base_return: float = 0.00,
    bear_return: float = -0.15,
    bear_probability: float = 0.25,
    base_probability: float = 0.50,
    bull_probability: float = 0.25,
) -> list[Scenario]:
    """
    Generate bull/base/bear scenarios.
    """
    scenarios = [
        scenario_from_return(
            name="bear",
            spot=spot,
            return_pct=bear_return,
            probability=bear_probability,
        ),
        scenario_from_return(
            name="base",
            spot=spot,
            return_pct=base_return,
            probability=base_probability,
        ),
        scenario_from_return(
            name="bull",
            spot=spot,
            return_pct=bull_return,
            probability=bull_probability,
        ),
    ]

    return normalize_scenarios(scenarios)


def custom_return_scenarios(
    spot: float,
    return_assumptions: dict[str, float],
    probabilities: dict[str, float] | None = None,
) -> list[Scenario]:
    """
    Build scenarios from named return assumptions.

    If probabilities are not supplied, equal weights are used.
    """
    _validate_spot(spot)

    if not return_assumptions:
        raise ValueError("return_assumptions cannot be empty.")

    if probabilities is None:
        equal_probability = 1.0 / len(return_assumptions)
        probabilities = {
            name: equal_probability
            for name in return_assumptions
        }

    scenarios = [
        scenario_from_return(
            name=name,
            spot=spot,
            return_pct=return_pct,
            probability=probabilities[name],
        )
        for name, return_pct in return_assumptions.items()
    ]

    return normalize_scenarios(scenarios)


def downside_stress_scenarios(
    spot: float,
    drawdowns: tuple[float, ...] = (-0.05, -0.10, -0.20, -0.30),
) -> list[Scenario]:
    """
    Generate downside stress scenarios.
    """
    if not drawdowns:
        raise ValueError("drawdowns cannot be empty.")

    probability = 1.0 / len(drawdowns)

    scenarios = [
        scenario_from_return(
            name=f"stress_{abs(drawdown):.0%}",
            spot=spot,
            return_pct=drawdown,
            probability=probability,
        )
        for drawdown in drawdowns
    ]

    return normalize_scenarios(scenarios)


def weighted_average_price(
    scenarios: list[Scenario],
) -> float:
    """
    Calculate probability-weighted scenario price.
    """
    validate_scenarios(scenarios)

    return sum(s.price * s.probability for s in scenarios)


def expected_scenario_return(
    spot: float,
    scenarios: list[Scenario],
) -> float:
    """
    Calculate probability-weighted expected return from scenarios.
    """
    _validate_spot(spot)
    validate_scenarios(scenarios)

    return sum(((s.price / spot) - 1.0) * s.probability for s in scenarios)


def scenario_prices(
    scenarios: list[Scenario],
) -> list[float]:
    """
    Extract scenario prices.
    """
    return [scenario.price for scenario in scenarios]
