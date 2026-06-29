from pathlib import Path

import polars as pl


class FeatureStore:
    """
    Saves and loads processed research datasets.
    """

    def __init__(self, root_dir: str | Path):
        self.root_dir = Path(root_dir)

    def save(
        self,
        df: pl.DataFrame,
        dataset_name: str,
    ) -> Path:
        output_path = self.root_dir / f"{dataset_name}.parquet"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        df.write_parquet(output_path)

        return output_path

    def load(self, dataset_name: str) -> pl.DataFrame:
        path = self.root_dir / f"{dataset_name}.parquet"

        if not path.exists():
            raise FileNotFoundError(f"Dataset not found: {path}")

        return pl.read_parquet(path)

    def exists(self, dataset_name: str) -> bool:
        return (self.root_dir / f"{dataset_name}.parquet").exists()

    def list_datasets(self) -> list[str]:
        if not self.root_dir.exists():
            return []

        return sorted(path.stem for path in self.root_dir.glob("*.parquet"))

    def delete(self, dataset_name: str) -> None:
        path = self.root_dir / f"{dataset_name}.parquet"

        if path.exists():
            path.unlink()
