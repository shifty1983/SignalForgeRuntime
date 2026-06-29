from pathlib import Path

import duckdb
import polars as pl

from src.common.paths import data_dir, ensure_dir


class DuckDBManager:
    def __init__(self, db_path: Path | None = None):
        if db_path is None:
            db_dir = data_dir() / "duckdb"
            ensure_dir(db_dir)
            db_path = db_dir / "research.duckdb"

        self.db_path = db_path
        self.connection = duckdb.connect(str(self.db_path))

    def query(self, sql: str) -> pl.DataFrame:
        return self.connection.sql(sql).pl()

    def close(self) -> None:
        self.connection.close()
