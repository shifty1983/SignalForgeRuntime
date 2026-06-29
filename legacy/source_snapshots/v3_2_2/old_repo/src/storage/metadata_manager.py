from datetime import datetime, timezone
from pathlib import Path

import polars as pl

from src.common.paths import catalog_dir, ensure_dir


class MetadataManager:
    def __init__(self):
        self.metadata_dir = catalog_dir()
        ensure_dir(self.metadata_dir)

    def build_metadata(
        self,
        dataset: str,
        source: str,
        parquet_path: Path,
        rows: int,
        columns: int,
        symbol: str | None = None,
        series: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict:
        return {
            "dataset": dataset,
            "source": source,
            "symbol": symbol,
            "series": series,
            "rows": rows,
            "columns": columns,
            "start_date": start_date,
            "end_date": end_date,
            "ingested_at": datetime.now(timezone.utc).isoformat(),
            "parquet_path": str(parquet_path),
        }

    def append_metadata(self, metadata: dict, dataset: str) -> Path:
        output_path = self.metadata_dir / f"{dataset}_ingestions.parquet"
        new_df = pl.DataFrame([metadata])

        if output_path.exists():
            existing_df = pl.read_parquet(output_path)
            combined_df = pl.concat([existing_df, new_df], how="diagonal")
        else:
            combined_df = new_df

        combined_df.write_parquet(output_path)

        return output_path
