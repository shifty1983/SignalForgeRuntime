from pathlib import Path

import polars as pl
import yfinance as yf

from src.ingestion.base_ingestor import BaseIngestor
from src.storage.metadata_manager import MetadataManager
from src.validation.options_validators import validate_options_chain
from src.storage.parquet_writer import ParquetWriter
class OptionsIngestor(BaseIngestor):
    def __init__(self, source: str = "yfinance", expiration: str | None = None):
        super().__init__(source=source, interval="options")
        self.expiration = expiration
        self.metadata_manager = MetadataManager()
        self.writer = ParquetWriter()

    def fetch(self, symbol: str) -> object:
        if self.source != "yfinance":
            raise ValueError(f"Unsupported options source: {self.source}")

        ticker = yf.Ticker(symbol)
        expirations = ticker.options

        if not expirations:
            raise ValueError(f"No option expirations found for {symbol}")

        expiration = self.expiration or expirations[0]

        if expiration not in expirations:
            raise ValueError(
                f"Expiration {expiration} not available for {symbol}. "
                f"Available expirations: {expirations}"
            )

        chain = ticker.option_chain(expiration)

        return {
            "expiration": expiration,
            "calls": chain.calls,
            "puts": chain.puts,
        }

    def normalize(self, data: object, symbol: str) -> pl.DataFrame:
        expiration = data["expiration"]

        calls = data["calls"].copy()
        puts = data["puts"].copy()

        calls["option_type"] = "call"
        puts["option_type"] = "put"

        pandas_df = pl.concat(
            [
                pl.from_pandas(calls),
                pl.from_pandas(puts),
            ],
            how="diagonal",
        ).to_pandas()

        column_map = {
            "contractSymbol": "contract_symbol",
            "lastPrice": "last_price",
            "openInterest": "open_interest",
            "impliedVolatility": "implied_volatility",
            "inTheMoney": "in_the_money",
        }

        pandas_df = pandas_df.rename(columns=column_map)

        df = pl.from_pandas(pandas_df)

        df = df.with_columns(
            [
                pl.lit(symbol.upper()).alias("underlying_symbol"),
                pl.lit(expiration).str.strptime(pl.Date, "%Y-%m-%d").alias("expiration"),
                pl.col("contract_symbol").cast(pl.Utf8),
                pl.col("strike").cast(pl.Float64),
                pl.col("option_type").cast(pl.Utf8),
                pl.col("bid").cast(pl.Float64),
                pl.col("ask").cast(pl.Float64),
                pl.col("last_price").cast(pl.Float64),
                pl.col("volume").cast(pl.Int64, strict=False),
                pl.col("open_interest").cast(pl.Int64, strict=False),
                pl.col("implied_volatility").cast(pl.Float64),
                pl.col("in_the_money").cast(pl.Boolean),
                pl.lit(self.source).alias("source"),
            ]
        )

        keep_columns = [
            "underlying_symbol",
            "contract_symbol",
            "expiration",
            "strike",
            "option_type",
            "bid",
            "ask",
            "last_price",
            "volume",
            "open_interest",
            "implied_volatility",
            "in_the_money",
            "source",
        ]

        return df.select(keep_columns)

    def validate(self, df: pl.DataFrame) -> None:
        validate_options_chain(df)

    def save(self, df: pl.DataFrame, symbol: str) -> Path:
        expiration = None

        if "expiration" in df.columns and df.height > 0:
            expiration = str(df["expiration"][0])

        parquet_path = self.writer.write_options_data(
            df=df,
            source=self.source,
            symbol=symbol,
            expiration=expiration,
        )

        metadata = self.metadata_manager.build_metadata(
            dataset="options",
            source=self.source,
            symbol=symbol.upper(),
            series=expiration,
            rows=df.height,
            columns=df.width,
            start_date=expiration,
            end_date=expiration,
            parquet_path=parquet_path,
        )

        self.metadata_manager.append_metadata(
            metadata=metadata,
            dataset="options",
        )

        return parquet_path
