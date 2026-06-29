from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Sequence

import polars as pl


@dataclass(frozen=True)
class FactorConfig:
    name: str
    input_columns: Sequence[str]
    output_column: str


class Factor(ABC):
    def __init__(self, config: FactorConfig) -> None:
        self.config = config

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def output_column(self) -> str:
        return self.config.output_column

    def validate_inputs(self, df: pl.DataFrame) -> None:
        missing = [
            col for col in self.config.input_columns
            if col not in df.columns
        ]

        if missing:
            raise ValueError(
                f"Missing required columns for factor '{self.name}': {missing}"
            )

    def run(self, df: pl.DataFrame) -> pl.DataFrame:
        self.validate_inputs(df)
        return self.compute(df)

    @abstractmethod
    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        raise NotImplementedError


class ColumnFactor(Factor):
    """
    Simple reusable factor that renames or copies an existing column
    into a standardized factor output column.
    """

    def __init__(
        self,
        name: str,
        input_column: str,
        output_column: str | None = None,
    ) -> None:
        super().__init__(
            FactorConfig(
                name=name,
                input_columns=[input_column],
                output_column=output_column or name,
            )
        )
        self.input_column = input_column

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        return df.with_columns(
            pl.col(self.input_column).alias(self.output_column)
        )


class ExpressionFactor(Factor):
    """
    Generic factor powered by a Polars expression.
    """

    def __init__(
        self,
        name: str,
        input_columns: Sequence[str],
        expression: pl.Expr,
        output_column: str | None = None,
    ) -> None:
        super().__init__(
            FactorConfig(
                name=name,
                input_columns=input_columns,
                output_column=output_column or name,
            )
        )
        self.expression = expression

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        return df.with_columns(
            self.expression.alias(self.output_column)
        )
