from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


SUPPORTED_FREQUENCIES = {
    "daily",
    "weekly",
    "monthly",
    "quarterly",
}


@dataclass(frozen=True)
class RebalanceDecision:
    should_rebalance: bool
    reason: str
    turnover: float = 0.0
    max_drift: float = 0.0


@dataclass
class RebalanceSchedule:
    frequency: str

    def __post_init__(self) -> None:
        self.frequency = self.frequency.lower()

        if self.frequency not in SUPPORTED_FREQUENCIES:
            raise ValueError(f"Unsupported frequency: {self.frequency}")

    def should_rebalance(
        self,
        current_date: datetime,
        previous_date: datetime | None,
    ) -> bool:
        if previous_date is None:
            return True

        if self.frequency == "daily":
            return current_date.date() != previous_date.date()

        if self.frequency == "weekly":
            current_calendar = current_date.isocalendar()
            previous_calendar = previous_date.isocalendar()

            return (
                current_calendar.year != previous_calendar.year
                or current_calendar.week != previous_calendar.week
            )

        if self.frequency == "monthly":
            return (
                current_date.month != previous_date.month
                or current_date.year != previous_date.year
            )

        if self.frequency == "quarterly":
            current_quarter = (current_date.month - 1) // 3
            previous_quarter = (previous_date.month - 1) // 3

            return (
                current_quarter != previous_quarter
                or current_date.year != previous_date.year
            )

        return False


def validate_weights(
    weights: dict[str, float],
    allow_short: bool = True,
) -> None:
    if not weights:
        raise ValueError("Weights cannot be empty.")

    for symbol, weight in weights.items():
        if not symbol:
            raise ValueError("Symbol cannot be empty.")

        if not allow_short and weight < 0:
            raise ValueError("Negative weights are not allowed.")


def normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    validate_weights(weights)

    total = sum(weights.values())

    if total == 0:
        raise ValueError("Weight sum cannot be zero.")

    return {
        symbol.upper(): weight / total
        for symbol, weight in weights.items()
    }


def gross_exposure(weights: dict[str, float]) -> float:
    validate_weights(weights)

    return sum(abs(weight) for weight in weights.values())


def normalize_to_gross_exposure(
    weights: dict[str, float],
    target_gross_exposure: float = 1.0,
) -> dict[str, float]:
    validate_weights(weights)

    if target_gross_exposure <= 0:
        raise ValueError("Target gross exposure must be greater than zero.")

    gross = gross_exposure(weights)

    if gross == 0:
        raise ValueError("Gross exposure cannot be zero.")

    return {
        symbol.upper(): (weight / gross) * target_gross_exposure
        for symbol, weight in weights.items()
    }


def weight_deltas(
    current_weights: dict[str, float],
    target_weights: dict[str, float],
) -> dict[str, float]:
    symbols = set(current_weights) | set(target_weights)

    return {
        symbol.upper(): target_weights.get(symbol, 0.0) - current_weights.get(symbol, 0.0)
        for symbol in symbols
    }


def compute_turnover(
    current_weights: dict[str, float],
    target_weights: dict[str, float],
) -> float:
    deltas = weight_deltas(
        current_weights=current_weights,
        target_weights=target_weights,
    )

    return sum(abs(delta) for delta in deltas.values()) / 2.0


def max_weight_drift(
    current_weights: dict[str, float],
    target_weights: dict[str, float],
) -> float:
    deltas = weight_deltas(
        current_weights=current_weights,
        target_weights=target_weights,
    )

    if not deltas:
        return 0.0

    return max(abs(delta) for delta in deltas.values())


def drift_exceeded(
    current_weights: dict[str, float],
    target_weights: dict[str, float],
    threshold: float,
) -> bool:
    if threshold < 0:
        raise ValueError("Threshold cannot be negative.")

    return max_weight_drift(
        current_weights=current_weights,
        target_weights=target_weights,
    ) > threshold


def evaluate_rebalance(
    current_date: datetime,
    previous_date: datetime | None,
    schedule: RebalanceSchedule,
    current_weights: dict[str, float],
    target_weights: dict[str, float],
    drift_threshold: float | None = None,
) -> RebalanceDecision:
    turnover = compute_turnover(
        current_weights=current_weights,
        target_weights=target_weights,
    )

    max_drift = max_weight_drift(
        current_weights=current_weights,
        target_weights=target_weights,
    )

    if schedule.should_rebalance(
        current_date=current_date,
        previous_date=previous_date,
    ):
        return RebalanceDecision(
            should_rebalance=True,
            reason="schedule",
            turnover=turnover,
            max_drift=max_drift,
        )

    if drift_threshold is not None:
        if drift_threshold < 0:
            raise ValueError("Drift threshold cannot be negative.")

        if max_drift > drift_threshold:
            return RebalanceDecision(
                should_rebalance=True,
                reason="drift",
                turnover=turnover,
                max_drift=max_drift,
            )

    return RebalanceDecision(
        should_rebalance=False,
        reason="none",
        turnover=turnover,
        max_drift=max_drift,
    )
