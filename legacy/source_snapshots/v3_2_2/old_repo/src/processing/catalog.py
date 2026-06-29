import json
from datetime import datetime, timezone
from pathlib import Path

import polars as pl


class DatasetCatalog:
    """
    Maintains metadata for processed research datasets.

    The catalog tracks:
    - dataset name
    - parquet path
    - row count
    - column count
    - columns
    - schema
    - date range
    - symbol count
    - creation timestamp
    """

    def __init__(self, catalog_path: str | Path):
        self.catalog_path = Path(catalog_path)

    def register_dataset(
        self,
        name: str,
        df: pl.DataFrame,
        dataset_path: str | Path,
        description: str | None = None,
        tags: list[str] | None = None,
        overwrite: bool = True,
    ) -> dict:
        self._validate_name(name)

        catalog = self.load_catalog()

        if name in catalog and not overwrite:
            raise ValueError(f"Dataset already exists in catalog: {name}")

        entry = self.create_entry(
            name=name,
            df=df,
            dataset_path=dataset_path,
            description=description,
            tags=tags,
        )

        catalog[name] = entry
        self.save_catalog(catalog)

        return entry

    def create_entry(
        self,
        name: str,
        df: pl.DataFrame,
        dataset_path: str | Path,
        description: str | None = None,
        tags: list[str] | None = None,
    ) -> dict:
        self._validate_name(name)

        date_bounds = self._get_date_bounds(df)
        symbol_count = self._get_symbol_count(df)

        return {
            "name": name,
            "path": str(Path(dataset_path)),
            "description": description or "",
            "tags": tags or [],
            "row_count": df.height,
            "column_count": df.width,
            "columns": df.columns,
            "schema": {col: str(dtype) for col, dtype in df.schema.items()},
            "start_date": date_bounds[0],
            "end_date": date_bounds[1],
            "symbol_count": symbol_count,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
        }

    def load_catalog(self) -> dict:
        if not self.catalog_path.exists():
            return {}

        with self.catalog_path.open("r", encoding="utf-8") as file:
            return json.load(file)

    def save_catalog(self, catalog: dict) -> Path:
        self.catalog_path.parent.mkdir(parents=True, exist_ok=True)

        with self.catalog_path.open("w", encoding="utf-8") as file:
            json.dump(catalog, file, indent=2, sort_keys=True)

        return self.catalog_path

    def get_dataset(self, name: str) -> dict:
        catalog = self.load_catalog()

        if name not in catalog:
            raise KeyError(f"Dataset not found in catalog: {name}")

        return catalog[name]

    def list_datasets(self) -> list[str]:
        return sorted(self.load_catalog().keys())

    def remove_dataset(self, name: str) -> None:
        catalog = self.load_catalog()

        if name in catalog:
            del catalog[name]
            self.save_catalog(catalog)

    def exists(self, name: str) -> bool:
        return name in self.load_catalog()

    def clear(self) -> None:
        self.save_catalog({})

    def _get_date_bounds(
        self,
        df: pl.DataFrame,
    ) -> tuple[str | None, str | None]:
        if "date" not in df.columns or df.is_empty():
            return None, None

        dates = df.select("date").drop_nulls().sort("date")

        if dates.is_empty():
            return None, None

        date_series = dates.to_series()

        return str(date_series[0]), str(date_series[-1])

    def _get_symbol_count(self, df: pl.DataFrame) -> int | None:
        if "symbol" not in df.columns or df.is_empty():
            return None

        return df.select(pl.col("symbol").n_unique()).item()

    def _validate_name(self, name: str) -> None:
        if not name or not name.strip():
            raise ValueError("Dataset name cannot be empty.")
        
