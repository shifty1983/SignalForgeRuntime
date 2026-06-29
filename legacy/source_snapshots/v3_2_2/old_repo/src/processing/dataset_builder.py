from pathlib import Path
from typing import Iterable

import polars as pl


class DatasetBuilder:
    """
    Builds multi-asset research datasets from feature parquet files.

    Expected input shape:
        date
        symbol
        feature columns...
    """

    def __init__(self, feature_dir: str | Path):
        self.feature_dir = Path(feature_dir)

    def load_feature_file(self, path: str | Path) -> pl.DataFrame:
        path = Path(path)

        if not path.exists():
            raise FileNotFoundError(f"Feature file not found: {path}")

        df = pl.read_parquet(path)

        required_columns = {"date", "symbol"}
        missing = required_columns - set(df.columns)

        if missing:
            raise ValueError(
                f"Feature file {path} missing required columns: {missing}"
            )

        return df

    def build_from_files(self, files: Iterable[str | Path]) -> pl.DataFrame:
        frames: list[pl.DataFrame] = []

        for file in files:
            frames.append(self.load_feature_file(file))

        if not frames:
            raise ValueError("No feature files provided.")

        return pl.concat(frames, how="diagonal").sort(["symbol", "date"])

    def build_from_directory(self, pattern: str = "*.parquet") -> pl.DataFrame:
        files = sorted(self.feature_dir.glob(pattern))

        if not files:
            raise FileNotFoundError(
                f"No feature files found in {self.feature_dir} using pattern {pattern}"
            )

        return self.build_from_files(files)

    def save_dataset(
        self,
        df: pl.DataFrame,
        output_path: str | Path,
    ) -> Path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        df.write_parquet(output_path)

        return output_path
