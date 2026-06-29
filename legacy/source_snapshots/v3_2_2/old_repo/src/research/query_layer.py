import polars as pl
from pathlib import Path

from src.common.paths import (
    raw_market_dir,
    raw_macro_dir,
    raw_fundamentals_dir,
    raw_sentiment_dir,
    raw_options_dir,
)
from src.storage.duckdb_manager import DuckDBManager


def duckdb_glob(path: Path) -> str:
    return path.as_posix()


class QueryLayer:
    def __init__(self):
        self.db = DuckDBManager()

    def load_market_data(
        self,
        source: str = "yfinance",
        symbol: str | None = None,
    ) -> pl.DataFrame:
        where_clause = ""

        if symbol:
            where_clause = f"WHERE symbol = '{symbol.upper()}'"

        pattern = duckdb_glob(
            raw_market_dir()
            / source
            / "symbol=*"
            / "interval=*"
            / "[A-Z]*.parquet"
        )

        query = f"""
        SELECT *
        FROM parquet_scan('{pattern}')
        {where_clause}
        ORDER BY symbol, date
        """

        return self.db.query(query)

    def load_macro_data(
        self,
        source: str = "fred",
        series: str | None = None,
    ) -> pl.DataFrame:
        where_clause = ""

        if series:
            where_clause = f"WHERE series = '{series.upper()}'"

        pattern = duckdb_glob(
            raw_macro_dir()
            / source
            / "series=*"
            / "[A-Z]*.parquet"
        )

        query = f"""
        SELECT *
        FROM parquet_scan('{pattern}')
        {where_clause}
        ORDER BY series, date
        """

        return self.db.query(query)

    def load_fundamentals(
        self,
        source: str = "alpha_vantage",
        symbol: str | None = None,
    ) -> pl.DataFrame:
        where_clause = ""

        if symbol:
            where_clause = f"WHERE symbol = '{symbol.upper()}'"

        pattern = duckdb_glob(
            raw_fundamentals_dir()
            / source
            / "symbol=*"
            / "*_overview.parquet"
        )

        query = f"""
        SELECT *
        FROM parquet_scan('{pattern}', union_by_name=True)
        {where_clause}
        """

        return self.db.query(query)

    def load_sentiment(
        self,
        source: str = "alpha_vantage",
        symbol: str | None = None,
    ) -> pl.DataFrame:
        where_clause = ""

        if symbol:
            where_clause = f"WHERE symbol = '{symbol.upper()}'"

        pattern = duckdb_glob(
            raw_sentiment_dir()
            / source
            / "symbol=*"
            / "*_news_sentiment.parquet"
        )

        query = f"""
        SELECT *
        FROM parquet_scan('{pattern}', union_by_name=True)
        {where_clause}
        """

        return self.db.query(query)

    def load_options_data(
        self,
        source: str = "yfinance",
        symbol: str | None = None,
        expiration: str | None = None,
    ) -> pl.DataFrame:
        filters = []

        if symbol:
            filters.append(f"underlying_symbol = '{symbol.upper()}'")

        if expiration:
            filters.append(f"expiration = DATE '{expiration}'")

        where_clause = ""

        if filters:
            where_clause = "WHERE " + " AND ".join(filters)

        pattern = duckdb_glob(
            raw_options_dir()
            / source
            / "symbol=*"
            / "expiration=*"
            / "*_options.parquet"
        )

        query = f"""
        SELECT *
        FROM parquet_scan('{pattern}', union_by_name=True)
        {where_clause}
        ORDER BY underlying_symbol, expiration, option_type, strike
        """

        return self.db.query(query)

    def close(self) -> None:
        self.db.close()
