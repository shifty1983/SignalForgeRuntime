from pathlib import Path

import polars as pl


class DataLakeAuditor:
    def __init__(
        self,
        data_root: Path | None = None,
        datasets: list[str] | None = None,
    ) -> None:
        self.data_root = data_root or Path(__file__).resolve().parents[2] / "data"
        self.raw_root = self.data_root / "raw"
        self.metadata_dir = self.data_root / "metadata" / "catalog"

        self.datasets = datasets or [
            "market",
            "macro",
            "fundamentals",
            "sentiment",
            "options",
        ]

    def _read_parquet_safe(self, path: Path) -> pl.DataFrame | None:
        try:
            return pl.read_parquet(path)
        except Exception as error:
            print(f"[ERROR] Failed reading {path}: {error}")
            return None

    def audit_dataset(self, dataset: str) -> dict:
        dataset_path = self.raw_root / dataset

        result = {
            "dataset": dataset,
            "exists": dataset_path.exists(),
            "files": 0,
            "rows": 0,
            "latest_date": None,
            "status": "OK",
        }

        if not dataset_path.exists():
            result["status"] = "MISSING_FOLDER"
            return result

        parquet_files = list(dataset_path.rglob("*.parquet"))
        result["files"] = len(parquet_files)

        if not parquet_files:
            result["status"] = "NO_FILES"
            return result

        latest_dates = []

        for file in parquet_files:
            df = self._read_parquet_safe(file)

            if df is None:
                result["status"] = "READ_ERROR"
                continue

            result["rows"] += df.height

            for date_col in ["date", "timestamp", "as_of_date", "expiration"]:
                if date_col in df.columns:
                    try:
                        latest_dates.append(df.select(pl.col(date_col).max()).item())
                    except Exception:
                        pass
                    break

        if latest_dates:
            result["latest_date"] = max(latest_dates)

        if result["rows"] == 0:
            result["status"] = "ZERO_ROWS"

        return result

    def audit_datasets(self) -> pl.DataFrame:
        results = [self.audit_dataset(dataset) for dataset in self.datasets]
        return pl.DataFrame(results)

    def audit_metadata(self) -> pl.DataFrame | None:
        if not self.metadata_dir.exists():
            print(f"[MISSING] Metadata directory not found: {self.metadata_dir}")
            return None

        metadata_files = list(self.metadata_dir.glob("*_ingestions.parquet"))

        if not metadata_files:
            print(f"[MISSING] No ingestion metadata files found in: {self.metadata_dir}")
            return None

        frames = []

        for file in metadata_files:
            df = self._read_parquet_safe(file)

            if df is None:
                continue

            df = df.with_columns(
                pl.lit(file.name).alias("metadata_file")
            )

            frames.append(df)

        if not frames:
            return None

        return pl.concat(frames, how="diagonal_relaxed")

    def audit_metadata_file_paths(self) -> pl.DataFrame | None:
        catalog = self.audit_metadata()

        if catalog is None:
            return None

        if "parquet_path" not in catalog.columns:
            print("[WARNING] Metadata catalog has no parquet_path column.")
            return None

        return catalog.with_columns(
            pl.col("parquet_path")
            .map_elements(lambda path: Path(path).exists(), return_dtype=pl.Boolean)
            .alias("file_exists")
        )

    def run(self) -> dict[str, pl.DataFrame | None]:
        dataset_audit = self.audit_datasets()
        metadata_audit = self.audit_metadata()
        metadata_file_audit = self.audit_metadata_file_paths()

        return {
            "datasets": dataset_audit,
            "metadata": metadata_audit,
            "metadata_files": metadata_file_audit,
        }
