from pathlib import Path

import polars as pl
import yfinance as yf

from src.ingestion.base_ingestor import BaseIngestor
from src.storage.parquet_writer import ParquetWriter
from src.validation.market_validators import validate_market_ohlcv
from src.storage.metadata_manager import MetadataManager
from src.ingestion.providers.alpha_vantage_client import AlphaVantageClient

class MarketIngestor(BaseIngestor):
    def __init__(self, source: str = "yfinance", interval: str = "1d", period: str = "max"):
        super().__init__(source=source, interval=interval)
        self.period = period
        self.writer = ParquetWriter()
        self.metadata_manager = MetadataManager()
        self.alpha_vantage_client = AlphaVantageClient() if source == "alpha_vantage" else None

    def fetch(self, symbol: str) -> object:
        if self.source == "yfinance":
            ticker = yf.Ticker(symbol)
            return ticker.history(
                period=self.period,
                interval=self.interval,
                auto_adjust=False,
            )

        if self.source == "alpha_vantage":
            if self.interval != "1d":
                raise ValueError("Alpha Vantage market ingestion currently supports only interval='1d'")

            return self.alpha_vantage_client.get_daily(symbol)

        raise ValueError(f"Unsupported market data source: {self.source}")

    def normalize(self, data: object, symbol: str) -> pl.DataFrame:
        if self.source == "yfinance":
            return self._normalize_yfinance(data, symbol)

        if self.source == "alpha_vantage":
            return self._normalize_alpha_vantage(data, symbol)

        raise ValueError(f"Unsupported market data source: {self.source}")

    def _normalize_yfinance(self, data: object, symbol: str) -> pl.DataFrame:
        if data is None or data.empty:
            raise ValueError(f"No data returned for symbol: {symbol}")

        pandas_df = data.reset_index()

        column_map = {
            "Date": "date",
            "Datetime": "date",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Adj Close": "adj_close",
            "Volume": "volume",
        }

        pandas_df = pandas_df.rename(columns=column_map)

        keep_columns = [
            "date",
            "open",
            "high",
            "low",
            "close",
            "adj_close",
            "volume",
        ]

        pandas_df = pandas_df[keep_columns]

        df = pl.from_pandas(pandas_df)

        df = df.with_columns(
            [
                pl.col("date").cast(pl.Date),
                pl.col("open").cast(pl.Float64),
                pl.col("high").cast(pl.Float64),
                pl.col("low").cast(pl.Float64),
                pl.col("close").cast(pl.Float64),
                pl.col("adj_close").cast(pl.Float64),
                pl.col("volume").cast(pl.Int64),
                pl.lit(symbol.upper()).alias("symbol"),
                pl.lit(self.source).alias("source"),
                pl.lit(self.interval).alias("interval"),
            ]
        )
       
        return df
    
    def _normalize_alpha_vantage(self, data: dict, symbol: str) -> pl.DataFrame:
        time_series_key = "Time Series (Daily)"

        if time_series_key not in data:
            raise ValueError(f"Missing Alpha Vantage time series data for {symbol}")

        rows = []

        for date, values in data[time_series_key].items():
            rows.append(
                {
                    "date": date,
                    "open": values.get("1. open"),
                    "high": values.get("2. high"),
                    "low": values.get("3. low"),
                    "close": values.get("4. close"),
                    "adj_close": values.get("4. close"),
                    "volume": values.get("5. volume"),
                    "symbol": symbol.upper(),
                    "source": self.source,
                    "interval": self.interval,
                }
            )

        df = pl.DataFrame(rows)

        df = df.with_columns(
            [
                pl.col("date").str.strptime(pl.Date, "%Y-%m-%d"),
                pl.col("open").cast(pl.Float64),
                pl.col("high").cast(pl.Float64),
                pl.col("low").cast(pl.Float64),
                pl.col("close").cast(pl.Float64),
                pl.col("adj_close").cast(pl.Float64),
                pl.col("volume").cast(pl.Int64),
            ]
        ).sort("date")

        return df

    def validate(self, df: pl.DataFrame) -> None:
        validate_market_ohlcv(df)

    def save(self, df: pl.DataFrame, symbol: str) -> Path:
        parquet_path = self.writer.write_market_data(
            df=df,
            source=self.source,
            symbol=symbol,
            interval=self.interval,
        )

        metadata = self.metadata_manager.build_metadata(
            dataset="market",
            source=self.source,
            symbol=symbol.upper(),
            series=None,
            rows=df.height,
            columns=df.width,
            start_date=str(df["date"].min()),
            end_date=str(df["date"].max()),
            parquet_path=parquet_path,
        )

        self.metadata_manager.append_metadata(
            metadata=metadata,
            dataset="market",
        )

        return parquet_path
