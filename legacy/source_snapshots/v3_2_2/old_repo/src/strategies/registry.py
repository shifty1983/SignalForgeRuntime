from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.strategies.base import Strategy
from src.strategies.long_short import LongShortStrategy
from src.strategies.mean_reversion import MeanReversionStrategy
from src.strategies.momentum import MomentumStrategy
from src.strategies.trend_following import TrendFollowingStrategy


StrategyFactory = Callable[..., Strategy]


STRATEGY_REGISTRY: dict[str, StrategyFactory] = {
    "long_short": LongShortStrategy,
    "momentum": MomentumStrategy,
    "mean_reversion": MeanReversionStrategy,
    "trend_following": TrendFollowingStrategy,
}


def list_strategies() -> list[str]:
    """
    List available registered strategy names.
    """

    return sorted(STRATEGY_REGISTRY.keys())


def get_strategy_factory(name: str) -> StrategyFactory:
    """
    Retrieve a strategy factory by name.
    """

    if name not in STRATEGY_REGISTRY:
        available = ", ".join(list_strategies())
        raise KeyError(
            f"Unknown strategy '{name}'. Available strategies: {available}"
        )

    return STRATEGY_REGISTRY[name]


def create_strategy(name: str, **kwargs: Any) -> Strategy:
    """
    Create a strategy instance by name.
    """

    factory = get_strategy_factory(name)
    return factory(**kwargs)


def register_strategy(
    name: str,
    factory: StrategyFactory,
    overwrite: bool = False,
) -> None:
    """
    Register a new strategy factory.

    Useful for custom strategies or experimental research strategies.
    """

    if name in STRATEGY_REGISTRY and not overwrite:
        raise ValueError(
            f"Strategy '{name}' is already registered. "
            "Use overwrite=True to replace it."
        )

    STRATEGY_REGISTRY[name] = factory
