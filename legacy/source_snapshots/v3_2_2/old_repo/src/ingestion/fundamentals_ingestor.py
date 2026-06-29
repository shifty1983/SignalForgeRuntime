from pathlib import Path

import polars as pl

from src.ingestion.base_ingestor import BaseIngestor
from src.ingestion.providers.alpha_vantage_client import AlphaVantageClient
from src.storage.metadata_manager import MetadataManager
from src.validation.fundamentals_validators import validate_fundamentals
from src.storage.parquet_writer import ParquetWriter


class FundamentalsIngestor(BaseIngestor):
    def __init__(self, source: str = "alpha_vantage"):
        super().__init__(source=source, interval="fundamentals")

        self.writer = ParquetWriter()
        self.metadata_manager = MetadataManager()

        self.client = AlphaVantageClient()

    def fetch(self, symbol: str) -> object:
        return self.client.get_company_overview(symbol)

    def normalize(self, data: object, symbol: str) -> pl.DataFrame:
        if not data:
            raise ValueError(f"No fundamentals returned for symbol: {symbol}")

        if "Symbol" not in data:
            raise ValueError(f"Invalid fundamentals response for symbol: {symbol}")

        row = dict(data)
        row["symbol"] = symbol.upper()
        row["source"] = self.source

        return pl.DataFrame([row])

    def validate(self, df: pl.DataFrame) -> None:
        validate_fundamentals(df)

    def save(self, df: pl.DataFrame, symbol: str) -> Path:
        parquet_path = self.writer.write_fundamentals_data(
            df=df,
            source=self.source,
            symbol=symbol,
            series="overview",
        )

        metadata = self.metadata_manager.build_metadata(
            dataset="fundamentals",
            source=self.source,
            symbol=symbol.upper(),
            series="overview",
            rows=df.height,
            columns=df.width,
            start_date=None,
            end_date=None,
            parquet_path=parquet_path,
        )

        self.metadata_manager.append_metadata(
            metadata=metadata,
            dataset="fundamentals",
        )

        return parquet_path
