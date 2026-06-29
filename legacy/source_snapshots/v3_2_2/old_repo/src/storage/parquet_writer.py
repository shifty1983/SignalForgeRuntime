from pathlib import Path

import polars as pl

from src.common.paths import (
    ensure_dir,
    raw_market_dir,
    raw_macro_dir,
    raw_fundamentals_dir,
    raw_sentiment_dir,
    raw_options_dir,
)


class ParquetWriter:
    def write_market_data(
        self,
        df: pl.DataFrame,
        source: str,
        symbol: str,
        interval: str = "1d",
    ) -> Path:
        output_dir = (
            raw_market_dir()
            / source
            / f"symbol={symbol.upper()}"
            / f"interval={interval}"
        )

        return self._write(
            df=df,
            output_dir=output_dir,
            filename=f"{symbol.upper()}.parquet",
        )

    def write_macro_data(
        self,
        df: pl.DataFrame,
        source: str,
        series: str,
    ) -> Path:
        output_dir = (
            raw_macro_dir()
            / source
            / f"series={series.upper()}"
        )

        return self._write(
            df=df,
            output_dir=output_dir,
            filename=f"{series.upper()}.parquet",
        )

    def write_fundamentals_data(
        self,
        df: pl.DataFrame,
        source: str,
        symbol: str,
        series: str = "overview",
    ) -> Path:
        output_dir = (
            raw_fundamentals_dir()
            / source
            / f"symbol={symbol.upper()}"
        )

        return self._write(
            df=df,
            output_dir=output_dir,
            filename=f"{symbol.upper()}_{series}.parquet",
        )

    def write_sentiment_data(
        self,
        df: pl.DataFrame,
        source: str,
        symbol: str,
    ) -> Path:
        output_dir = (
            raw_sentiment_dir()
            / source
            / f"symbol={symbol.upper()}"
        )

        return self._write(
            df=df,
            output_dir=output_dir,
            filename=f"{symbol.upper()}_news_sentiment.parquet",
        )

    def write_options_data(
        self,
        df: pl.DataFrame,
        source: str,
        symbol: str,
        expiration: str,
    ) -> Path:
        output_dir = (
            raw_options_dir()
            / source
            / f"symbol={symbol.upper()}"
            / f"expiration={expiration}"
        )

        return self._write(
            df=df,
            output_dir=output_dir,
            filename=f"{symbol.upper()}_{expiration}_options.parquet",
        )

    def _write(
        self,
        df: pl.DataFrame,
        output_dir: Path,
        filename: str,
    ) -> Path:
        ensure_dir(output_dir)

        output_path = output_dir / filename
        df.write_parquet(output_path)

        return output_path
