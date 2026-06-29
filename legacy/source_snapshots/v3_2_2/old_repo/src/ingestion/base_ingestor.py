from abc import ABC, abstractmethod
from pathlib import Path

import polars as pl

from src.common.logger import get_logger


class BaseIngestor(ABC):
    def __init__(self, source: str, interval: str = "1d"):
        self.source = source
        self.interval = interval
        self.logger = get_logger(self.__class__.__name__)

    @abstractmethod
    def fetch(self, symbol: str) -> object:
        pass

    @abstractmethod
    def normalize(self, data: object, symbol: str) -> pl.DataFrame:
        pass

    @abstractmethod
    def validate(self, df: pl.DataFrame) -> None:
        pass

    @abstractmethod
    def save(self, df: pl.DataFrame, symbol: str) -> Path:
        pass

    def run(self, symbol: str) -> Path:
        symbol = symbol.upper()

        self.logger.info(f"Fetching {symbol} from {self.source}")
        raw_data = self.fetch(symbol)

        self.logger.info(f"Normalizing {symbol}")
        df = self.normalize(raw_data, symbol)

        self.logger.info(f"Validating {symbol}")
        self.validate(df)

        self.logger.info(f"Saving {symbol}")
        output_path = self.save(df, symbol)

        self.logger.info(f"Completed {symbol}: {output_path}")
        return output_path

    def run_many(self, symbols: list[str]) -> list[Path]:
        output_paths = []

        for symbol in symbols:
            try:
                output_paths.append(self.run(symbol))
            except Exception as error:
                self.logger.exception(f"Failed to ingest {symbol}: {error}")

        return output_paths
