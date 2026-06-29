from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import polars as pl


@dataclass(frozen=True)
class StrategyConfig:
    """
    Shared strategy configuration.

    This keeps strategy parameters explicit and portable.
    """

    name: str
    date_col: str = "date"
    symbol_col: str = "symbol"
    signal_col: str = "signal"
    weight_col: str = "target_weight"
    required_columns: tuple[str, ...] = field(default_factory=tuple)


class Strategy(ABC):
    """
    Base class for all strategy modules.

    Strategies convert research data into target portfolio weights.
    """

    def __init__(self, config: StrategyConfig):
        self.config = config
        self.name = config.name

    def validate_input(self, data: pl.DataFrame) -> None:
        """
        Validate required input columns.
        """

        missing = [
            col for col in self.config.required_columns
            if col not in data.columns
        ]

        if missing:
            raise ValueError(
                f"{self.name} missing required columns: {missing}"
            )

    @abstractmethod
    def generate_signals(self, data: pl.DataFrame) -> pl.DataFrame:
        """
        Generate strategy signals from input data.
        """
        raise NotImplementedError

    @abstractmethod
    def generate_target_weights(self, signals: pl.DataFrame) -> pl.DataFrame:
        """
        Convert strategy signals into target weights.
        """
        raise NotImplementedError

    def run(self, data: pl.DataFrame) -> pl.DataFrame:
        """
        Full strategy pipeline.
        """

        self.validate_input(data)

        signals = self.generate_signals(data)
        weights = self.generate_target_weights(signals)

        return weights.with_columns(
            pl.lit(self.name).alias("strategy_name")
        )
