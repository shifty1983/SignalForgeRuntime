from pathlib import Path

import polars as pl

from src.ingestion.base_ingestor import BaseIngestor
from src.ingestion.providers.alpha_vantage_client import AlphaVantageClient
from src.storage.metadata_manager import MetadataManager
from src.validation.sentiment_validators  import validate_sentiment
from src.storage.parquet_writer import ParquetWriter

class SentimentIngestor(BaseIngestor):
    def __init__(self, source: str = "alpha_vantage"):
        super().__init__(source=source, interval="sentiment")
        self.writer = ParquetWriter()

        self.client = AlphaVantageClient()
        
        self.metadata_manager = MetadataManager()

    def fetch(self, symbol: str) -> object:
        return self.client.get_news_sentiment(symbol)

    def normalize(self, data: object, symbol: str) -> pl.DataFrame:
        if not data or "feed" not in data:
            raise ValueError(f"No sentiment data returned for symbol: {symbol}")

        rows = []

        for item in data["feed"]:
            rows.append(
                {
                    "symbol": symbol.upper(),
                    "source": self.source,
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "time_published": item.get("time_published"),
                    "authors": ", ".join(item.get("authors", [])),
                    "summary": item.get("summary"),
                    "banner_image": item.get("banner_image"),
                    "source_name": item.get("source"),
                    "category_within_source": item.get("category_within_source"),
                    "source_domain": item.get("source_domain"),
                    "overall_sentiment_score": item.get("overall_sentiment_score"),
                    "overall_sentiment_label": item.get("overall_sentiment_label"),
                    "ticker_sentiment": str(item.get("ticker_sentiment")),
                    "topics": str(item.get("topics")),
                }
            )

        df = pl.DataFrame(rows)

        df = df.with_columns(
            [
                pl.col("overall_sentiment_score").cast(pl.Float64),
                pl.lit(symbol.upper()).alias("query_symbol"),
            ]
        )

        return df

    def validate(self, df: pl.DataFrame) -> None:
        validate_sentiment(df)

    def save(self, df: pl.DataFrame, symbol: str) -> Path:
        parquet_path = self.writer.write_sentiment_data(
            df=df,
            source=self.source,
            symbol=symbol,
        )

        date_col = "date" if "date" in df.columns else None

        metadata = self.metadata_manager.build_metadata(
            dataset="sentiment",
            source=self.source,
            symbol=symbol.upper(),
            series=None,
            rows=df.height,
            columns=df.width,
            start_date=str(df[date_col].min()) if date_col else None,
            end_date=str(df[date_col].max()) if date_col else None,
            parquet_path=parquet_path,
        )

        self.metadata_manager.append_metadata(
            metadata=metadata,
            dataset="sentiment",
        )

        return parquet_path
