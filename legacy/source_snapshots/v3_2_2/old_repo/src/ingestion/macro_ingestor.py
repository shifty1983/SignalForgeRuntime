from pathlib import Path

import polars as pl
from fredapi import Fred

from src.ingestion.base_ingestor import BaseIngestor
from src.storage.metadata_manager import MetadataManager
from src.common.retry import RetryConfig, retry_call
from src.validation.macro_validators import validate_macro_series
from src.storage.parquet_writer import ParquetWriter
from src.common.config import get_fred_api_key


class MacroIngestor(BaseIngestor):
    def __init__(self, source: str = "fred"):
        super().__init__(source=source, interval="macro")
        self.writer = ParquetWriter()
        self.api_key = get_fred_api_key()
        self.fred = Fred(api_key=self.api_key)
        self.metadata_manager = MetadataManager()
        
        self.retry_config = RetryConfig(
        max_attempts=3,
        initial_delay_seconds=1.0,
        max_delay_seconds=30.0,
        backoff_factor=2.0,
        jitter=True,
        exceptions=(Exception,),
)

    def fetch(self, symbol: str) -> object:
        if self.source != "fred":
            raise ValueError(f"Unsupported macro data source: {self.source}")

        return retry_call(
            self.fred.get_series,
            symbol,
            config=self.retry_config,
            logger=self.logger,
        )

    def normalize(self, data: object, symbol: str) -> pl.DataFrame:
        if data is None or data.empty:
            raise ValueError(f"No macro data returned for series: {symbol}")

        pandas_df = data.reset_index()
        pandas_df.columns = ["date", "value"]

        df = pl.from_pandas(pandas_df)

        df = df.with_columns(
            [
                pl.col("date").cast(pl.Date),
                pl.col("value").cast(pl.Float64),
                pl.lit(symbol.upper()).alias("series_id"),
                pl.lit(symbol.upper()).alias("series"),
                pl.lit(self.source).alias("source"),
            ]
        )

        df = df.drop_nulls(subset=["value"])
        
        return df

    def validate(self, df: pl.DataFrame) -> None:
        validate_macro_series(df)

    def save(self, df: pl.DataFrame, series: str) -> Path:
        parquet_path = self.writer.write_macro_data(
            df=df,
            source=self.source,
            series=series,
        )

        date_col = "date" if "date" in df.columns else None

        metadata = self.metadata_manager.build_metadata(
            dataset="macro",
            source=self.source,
            symbol=None,
            series=series,
            rows=df.height,
            columns=df.width,
            start_date=str(df[date_col].min()) if date_col else None,
            end_date=str(df[date_col].max()) if date_col else None,
            parquet_path=parquet_path,
        )

        self.metadata_manager.append_metadata(
            metadata=metadata,
            dataset="macro",
        )

        return parquet_path
