from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from src.expected_value.scenarios import Scenario, validate_scenarios


@dataclass(frozen=True)
class ScenarioPayoff:
    scenario_name: str
    price: float
    probability: float
    payoff: float
    weighted_payoff: float


@dataclass(frozen=True)
class ExpectedValueResult:
    expected_payoff: float
    expected_return: float
    annualized_return: float
    probability_profit: float
    probability_loss: float
    average_win: float
    average_loss: float


def expected_value(
    scenarios: list[Scenario],
    payoff_function: Callable[[float], float],
) -> float:
    """
    Calculate expected payoff across scenarios.
    """
    validate_scenarios(scenarios)

    return sum(
        payoff_function(scenario.price) * scenario.probability
        for scenario in scenarios
    )


def scenario_payoff_breakdown(
    scenarios: list[Scenario],
    payoff_function: Callable[[float], float],
) -> list[ScenarioPayoff]:
    """
    Return payoff details for each scenario.
    """
    validate_scenarios(scenarios)

    return [
        ScenarioPayoff(
            scenario_name=scenario.name,
            price=scenario.price,
            probability=scenario.probability,
            payoff=payoff_function(scenario.price),
            weighted_payoff=payoff_function(scenario.price) * scenario.probability,
        )
        for scenario in scenarios
    ]


def expected_value_from_payoffs(
    payoffs: list[float],
    probabilities: list[float],
) -> float:
    """
    Calculate expected value from direct payoff and probability arrays.
    """
    if not payoffs:
        raise ValueError("payoffs cannot be empty.")

    if len(payoffs) != len(probabilities):
        raise ValueError("payoffs and probabilities must have the same length.")

    if any(probability < 0 or probability > 1 for probability in probabilities):
        raise ValueError("probabilities must be between 0 and 1.")

    total_probability = sum(probabilities)

    if abs(total_probability - 1.0) > 1e-6:
        raise ValueError("probabilities must sum to 1.0.")

    return sum(payoff * probability for payoff, probability in zip(payoffs, probabilities, strict=True))


def expected_return(
    expected_payoff: float,
    capital_at_risk: float,
) -> float:
    """
    Convert expected payoff into expected return.
    """
    if capital_at_risk <= 0:
        return 0.0

    return expected_payoff / capital_at_risk


def annualized_expected_return(
    expected_return_value: float,
    time_to_expiry: float,
) -> float:
    """
    Annualize expected return using simple annualization.
    """
    if time_to_expiry <= 0:
        return 0.0

    return expected_return_value / time_to_expiry


def compounded_annualized_return(
    expected_return_value: float,
    time_to_expiry: float,
) -> float:
    """
    Annualize expected return using compounding.
    """
    if time_to_expiry <= 0:
        return 0.0

    if expected_return_value <= -1.0:
        return -1.0

    return (1.0 + expected_return_value) ** (1.0 / time_to_expiry) - 1.0


def probability_of_positive_payoff(
    scenarios: list[Scenario],
    payoff_function: Callable[[float], float],
) -> float:
    """
    Probability-weighted chance of payoff greater than zero.
    """
    validate_scenarios(scenarios)

    return sum(
        scenario.probability
        for scenario in scenarios
        if payoff_function(scenario.price) > 0
    )


def probability_of_negative_payoff(
    scenarios: list[Scenario],
    payoff_function: Callable[[float], float],
) -> float:
    """
    Probability-weighted chance of payoff less than zero.
    """
    validate_scenarios(scenarios)

    return sum(
        scenario.probability
        for scenario in scenarios
        if payoff_function(scenario.price) < 0
    )


def average_positive_payoff(
    scenarios: list[Scenario],
    payoff_function: Callable[[float], float],
) -> float:
    """
    Probability-weighted average payoff across winning scenarios.
    """
    validate_scenarios(scenarios)

    winning_scenarios = [
        scenario
        for scenario in scenarios
        if payoff_function(scenario.price) > 0
    ]

    win_probability = sum(scenario.probability for scenario in winning_scenarios)

    if win_probability <= 0:
        return 0.0

    return sum(
        payoff_function(scenario.price) * scenario.probability
        for scenario in winning_scenarios
    ) / win_probability


def average_negative_payoff(
    scenarios: list[Scenario],
    payoff_function: Callable[[float], float],
) -> float:
    """
    Probability-weighted average payoff across losing scenarios.
    """
    validate_scenarios(scenarios)

    losing_scenarios = [
        scenario
        for scenario in scenarios
        if payoff_function(scenario.price) < 0
    ]

    loss_probability = sum(scenario.probability for scenario in losing_scenarios)

    if loss_probability <= 0:
        return 0.0

    return sum(
        payoff_function(scenario.price) * scenario.probability
        for scenario in losing_scenarios
    ) / loss_probability


def expected_return_from_scenarios(
    scenarios: list[Scenario],
    payoff_function: Callable[[float], float],
    capital_at_risk: float,
) -> float:
    """
    Calculate expected return directly from scenarios and payoff function.
    """
    expected_payoff = expected_value(
        scenarios=scenarios,
        payoff_function=payoff_function,
    )

    return expected_return(
        expected_payoff=expected_payoff,
        capital_at_risk=capital_at_risk,
    )


def evaluate_expected_value(
    scenarios: list[Scenario],
    payoff_function: Callable[[float], float],
    capital_at_risk: float,
    time_to_expiry: float,
) -> ExpectedValueResult:
    """
    Full expected value evaluation bundle.
    """
    ev = expected_value(
        scenarios=scenarios,
        payoff_function=payoff_function,
    )

    er = expected_return(
        expected_payoff=ev,
        capital_at_risk=capital_at_risk,
    )

    annualized = annualized_expected_return(
        expected_return_value=er,
        time_to_expiry=time_to_expiry,
    )

    return ExpectedValueResult(
        expected_payoff=ev,
        expected_return=er,
        annualized_return=annualized,
        probability_profit=probability_of_positive_payoff(scenarios, payoff_function),
        probability_loss=probability_of_negative_payoff(scenarios, payoff_function),
        average_win=average_positive_payoff(scenarios, payoff_function),
        average_loss=average_negative_payoff(scenarios, payoff_function),
    )
