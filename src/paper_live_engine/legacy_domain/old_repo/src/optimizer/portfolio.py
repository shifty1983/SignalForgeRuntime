"""
Optimized portfolio output structures.

This module defines the standardized portfolio object returned by the
optimizer solver and rebalance logic.

It does not decide which trades to select. That belongs in solver.py.
It does not enforce hard limits. That belongs in constraints.py.

Its job is to normalize selected candidates into a clean portfolio result:
- positions
- weights
- expected return
- objective score
- capital at risk
- portfolio Greeks
- symbol / sector / strategy exposures
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class PortfolioGreeks:
    """
    Portfolio-level Greek exposure.
    """

    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0

    def total_abs_exposure(self) -> float:
        return abs(self.delta) + abs(self.gamma) + abs(self.theta) + abs(self.vega)

    def to_dict(self) -> dict[str, float]:
        return {
            "delta": round(self.delta, 6),
            "gamma": round(self.gamma, 6),
            "theta": round(self.theta, 6),
            "vega": round(self.vega, 6),
        }


@dataclass(frozen=True)
class OptimizedPosition:
    """
    A single optimized portfolio position.
    """

    symbol: str
    weight: float

    strategy_type: str | None = None
    sector: str | None = None

    objective_score: float = 0.0
    expected_return: float = 0.0
    probability_of_profit: float = 0.0
    confidence: float = 0.0
    liquidity_score: float = 0.0

    capital_at_risk: float = 0.0
    max_profit: float | None = None
    max_loss: float | None = None

    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0

    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_candidate(cls, candidate: Mapping[str, Any]) -> "OptimizedPosition":
        symbol = _first_string(candidate, ("symbol", "ticker", "underlying"))

        if symbol is None:
            raise ValueError("OptimizedPosition requires a symbol, ticker, or underlying field.")

        weight = _first_number(
            candidate,
            (
                "weight",
                "target_weight",
                "allocation",
                "allocation_pct",
                "position_weight",
            ),
            default=0.0,
        )

        weight = _percentage_to_decimal_if_needed(weight)

        expected_return = _first_number(
            candidate,
            (
                "expected_return",
                "expected_return_pct",
                "ev_return",
                "ev_return_pct",
                "return_on_risk",
            ),
            default=0.0,
        )

        probability_of_profit = _first_number(
            candidate,
            (
                "probability_of_profit",
                "probability",
                "pop",
                "win_probability",
                "success_probability",
            ),
            default=0.0,
        )

        confidence = _first_number(
            candidate,
            (
                "confidence",
                "model_confidence",
                "signal_confidence",
                "selection_confidence",
            ),
            default=0.0,
        )

        liquidity_score = _first_number(
            candidate,
            (
                "liquidity_score",
                "option_liquidity_score",
                "market_liquidity_score",
            ),
            default=0.0,
        )

        capital_at_risk = _first_number(
            candidate,
            (
                "capital_at_risk",
                "capital_required",
                "margin_required",
                "max_loss_pct",
                "risk_weight",
            ),
            default=0.0,
        )

        return cls(
            symbol=symbol,
            weight=weight,
            strategy_type=_first_string(candidate, ("strategy_type", "strategy", "structure")),
            sector=_first_string(candidate, ("sector", "sector_name")),
            objective_score=_first_number(candidate, ("objective_score", "score"), default=0.0),
            expected_return=_percentage_to_decimal_if_needed(expected_return),
            probability_of_profit=_clamp_probability(probability_of_profit),
            confidence=_clamp_probability(confidence),
            liquidity_score=_clamp_probability(liquidity_score),
            capital_at_risk=_percentage_to_decimal_if_needed(capital_at_risk),
            max_profit=_first_number(candidate, ("max_profit", "max_reward"), default=None),
            max_loss=_first_number(candidate, ("max_loss", "max_risk"), default=None),
            delta=_first_number(candidate, ("delta", "net_delta"), default=0.0),
            gamma=_first_number(candidate, ("gamma", "net_gamma"), default=0.0),
            theta=_first_number(candidate, ("theta", "net_theta"), default=0.0),
            vega=_first_number(candidate, ("vega", "net_vega"), default=0.0),
            metadata=_metadata_without_core_fields(candidate),
        )

    def weighted_expected_return(self) -> float:
        return self.weight * self.expected_return

    def weighted_objective_score(self) -> float:
        return self.weight * self.objective_score

    def weighted_capital_at_risk(self) -> float:
        return self.weight * self.capital_at_risk

    def weighted_greeks(self) -> PortfolioGreeks:
        return PortfolioGreeks(
            delta=self.delta * self.weight,
            gamma=self.gamma * self.weight,
            theta=self.theta * self.weight,
            vega=self.vega * self.weight,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "strategy_type": self.strategy_type,
            "sector": self.sector,
            "weight": round(self.weight, 6),
            "objective_score": round(self.objective_score, 6),
            "expected_return": round(self.expected_return, 6),
            "probability_of_profit": round(self.probability_of_profit, 6),
            "confidence": round(self.confidence, 6),
            "liquidity_score": round(self.liquidity_score, 6),
            "capital_at_risk": round(self.capital_at_risk, 6),
            "max_profit": self.max_profit,
            "max_loss": self.max_loss,
            "delta": round(self.delta, 6),
            "gamma": round(self.gamma, 6),
            "theta": round(self.theta, 6),
            "vega": round(self.vega, 6),
            "weighted_delta": round(self.weighted_greeks().delta, 6),
            "weighted_gamma": round(self.weighted_greeks().gamma, 6),
            "weighted_theta": round(self.weighted_greeks().theta, 6),
            "weighted_vega": round(self.weighted_greeks().vega, 6),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class PortfolioSummary:
    """
    Aggregated optimized portfolio statistics.
    """

    position_count: int
    total_weight: float
    cash_weight: float
    expected_return: float
    weighted_objective_score: float
    total_capital_at_risk: float
    greeks: PortfolioGreeks
    symbol_exposure: dict[str, float]
    sector_exposure: dict[str, float]
    strategy_exposure: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "position_count": self.position_count,
            "total_weight": round(self.total_weight, 6),
            "cash_weight": round(self.cash_weight, 6),
            "expected_return": round(self.expected_return, 6),
            "weighted_objective_score": round(self.weighted_objective_score, 6),
            "total_capital_at_risk": round(self.total_capital_at_risk, 6),
            "greeks": self.greeks.to_dict(),
            "symbol_exposure": _rounded_dict(self.symbol_exposure),
            "sector_exposure": _rounded_dict(self.sector_exposure),
            "strategy_exposure": _rounded_dict(self.strategy_exposure),
        }


@dataclass(frozen=True)
class OptimizedPortfolio:
    """
    Standardized optimizer result.
    """

    positions: tuple[OptimizedPosition, ...]
    name: str = "optimized_portfolio"
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_candidates(
        cls,
        candidates: Iterable[Mapping[str, Any]],
        name: str = "optimized_portfolio",
        metadata: Mapping[str, Any] | None = None,
    ) -> "OptimizedPortfolio":
        positions = tuple(
            OptimizedPosition.from_candidate(candidate)
            for candidate in candidates
        )

        return cls(
            positions=positions,
            name=name,
            metadata=dict(metadata or {}),
        )

    def total_weight(self) -> float:
        return sum(position.weight for position in self.positions)

    def cash_weight(self) -> float:
        return max(0.0, 1.0 - self.total_weight())

    def expected_return(self) -> float:
        return sum(position.weighted_expected_return() for position in self.positions)

    def weighted_objective_score(self) -> float:
        total_weight = self.total_weight()

        if total_weight <= 0:
            return 0.0

        weighted_score = sum(
            position.weighted_objective_score()
            for position in self.positions
        )

        return weighted_score / total_weight

    def total_capital_at_risk(self) -> float:
        return sum(position.weighted_capital_at_risk() for position in self.positions)

    def greeks(self) -> PortfolioGreeks:
        delta = 0.0
        gamma = 0.0
        theta = 0.0
        vega = 0.0

        for position in self.positions:
            weighted = position.weighted_greeks()
            delta += weighted.delta
            gamma += weighted.gamma
            theta += weighted.theta
            vega += weighted.vega

        return PortfolioGreeks(
            delta=delta,
            gamma=gamma,
            theta=theta,
            vega=vega,
        )

    def symbol_exposure(self) -> dict[str, float]:
        return self._exposure_by(lambda position: position.symbol)

    def sector_exposure(self) -> dict[str, float]:
        return self._exposure_by(lambda position: position.sector)

    def strategy_exposure(self) -> dict[str, float]:
        return self._exposure_by(lambda position: position.strategy_type)

    def summary(self) -> PortfolioSummary:
        return PortfolioSummary(
            position_count=len(self.positions),
            total_weight=self.total_weight(),
            cash_weight=self.cash_weight(),
            expected_return=self.expected_return(),
            weighted_objective_score=self.weighted_objective_score(),
            total_capital_at_risk=self.total_capital_at_risk(),
            greeks=self.greeks(),
            symbol_exposure=self.symbol_exposure(),
            sector_exposure=self.sector_exposure(),
            strategy_exposure=self.strategy_exposure(),
        )

    def sorted_by_objective(self, descending: bool = True) -> "OptimizedPortfolio":
        return OptimizedPortfolio(
            positions=tuple(
                sorted(
                    self.positions,
                    key=lambda position: position.objective_score,
                    reverse=descending,
                )
            ),
            name=self.name,
            metadata=dict(self.metadata),
        )

    def sorted_by_weight(self, descending: bool = True) -> "OptimizedPortfolio":
        return OptimizedPortfolio(
            positions=tuple(
                sorted(
                    self.positions,
                    key=lambda position: position.weight,
                    reverse=descending,
                )
            ),
            name=self.name,
            metadata=dict(self.metadata),
        )

    def to_rows(self) -> list[dict[str, Any]]:
        return [position.to_dict() for position in self.positions]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "summary": self.summary().to_dict(),
            "positions": self.to_rows(),
            "metadata": dict(self.metadata),
        }

    def _exposure_by(self, key_fn: Any) -> dict[str, float]:
        exposure: dict[str, float] = {}

        for position in self.positions:
            key = key_fn(position)

            if key is None:
                continue

            exposure[key] = exposure.get(key, 0.0) + position.weight

        return exposure


def build_optimized_portfolio(
    candidates: Iterable[Mapping[str, Any]],
    name: str = "optimized_portfolio",
    metadata: Mapping[str, Any] | None = None,
) -> OptimizedPortfolio:
    """
    Convenience function for building an OptimizedPortfolio.
    """

    return OptimizedPortfolio.from_candidates(
        candidates=candidates,
        name=name,
        metadata=metadata,
    )


def _first_number(
    values: Mapping[str, Any],
    names: tuple[str, ...],
    default: float | None,
) -> float | None:
    for name in names:
        value = values.get(name)

        if value is None:
            continue

        if isinstance(value, bool):
            continue

        if isinstance(value, (int, float)):
            return float(value)

        try:
            return float(value)
        except (TypeError, ValueError):
            continue

    return default


def _first_string(
    values: Mapping[str, Any],
    names: tuple[str, ...],
) -> str | None:
    for name in names:
        value = values.get(name)

        if value is None:
            continue

        text = str(value).strip()

        if text:
            return text

    return None


def _percentage_to_decimal_if_needed(value: float) -> float:
    if abs(value) > 1.0:
        return value / 100.0

    return value


def _clamp_probability(value: float) -> float:
    value = _percentage_to_decimal_if_needed(value)
    return max(0.0, min(1.0, value))


def _rounded_dict(values: Mapping[str, float]) -> dict[str, float]:
    return {
        key: round(value, 6)
        for key, value in values.items()
    }


def _metadata_without_core_fields(candidate: Mapping[str, Any]) -> dict[str, Any]:
    core_fields = {
        "symbol",
        "ticker",
        "underlying",
        "weight",
        "target_weight",
        "allocation",
        "allocation_pct",
        "position_weight",
        "strategy_type",
        "strategy",
        "structure",
        "sector",
        "sector_name",
        "objective_score",
        "score",
        "expected_return",
        "expected_return_pct",
        "ev_return",
        "ev_return_pct",
        "return_on_risk",
        "probability_of_profit",
        "probability",
        "pop",
        "win_probability",
        "success_probability",
        "confidence",
        "model_confidence",
        "signal_confidence",
        "selection_confidence",
        "liquidity_score",
        "option_liquidity_score",
        "market_liquidity_score",
        "capital_at_risk",
        "capital_required",
        "margin_required",
        "max_loss_pct",
        "risk_weight",
        "max_profit",
        "max_reward",
        "max_loss",
        "max_risk",
        "delta",
        "net_delta",
        "gamma",
        "net_gamma",
        "theta",
        "net_theta",
        "vega",
        "net_vega",
    }

    return {
        key: value
        for key, value in candidate.items()
        if key not in core_fields
    }
