from pathlib import Path
from typing import Iterable

import polars as pl

from src.processing.align import DatasetAligner
from src.processing.catalog import DatasetCatalog
from src.processing.dataset_builder import DatasetBuilder
from src.processing.feature_store import FeatureStore
from src.processing.filters import DatasetFilter
from src.processing.labels import DatasetLabeler
from src.processing.normalize import DatasetNormalizer
from src.processing.schema import ProcessingSchema
from src.processing.winsorize import DatasetWinsorizer


class ProcessedDatasetPipeline:
    """
    End-to-end processed dataset pipeline.

    Connects:
    - dataset building
    - schema validation
    - filtering
    - date alignment
    - winsorization
    - normalization
    - forward-return labeling
    - parquet storage
    - catalog registration
    """

    def __init__(
        self,
        feature_dir: str | Path,
        output_dir: str | Path,
        catalog_path: str | Path | None = None,
    ):
        self.feature_dir = Path(feature_dir)
        self.output_dir = Path(output_dir)

        self.builder = DatasetBuilder(self.feature_dir)
        self.aligner = DatasetAligner()
        self.filters = DatasetFilter()
        self.winsorizer = DatasetWinsorizer()
        self.normalizer = DatasetNormalizer()
        self.labeler = DatasetLabeler()
        self.schema = ProcessingSchema()
        self.store = FeatureStore(self.output_dir)

        if catalog_path is None:
            catalog_path = self.output_dir / "catalog.json"

        self.catalog = DatasetCatalog(catalog_path)

    def build_dataset(
        self,
        dataset_name: str,
        files: Iterable[str | Path] | None = None,
        pattern: str = "*.parquet",
        feature_columns: list[str] | None = None,
        symbols: list[str] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        align_common_dates: bool = False,
        drop_null_features: bool = True,
        min_observations_per_symbol: int | None = None,
        winsorize_columns: list[str] | None = None,
        winsorize_by_date: bool = True,
        lower_quantile: float = 0.01,
        upper_quantile: float = 0.99,
        zscore_columns: list[str] | None = None,
        rank_columns: list[str] | None = None,
        percentile_rank_columns: list[str] | None = None,
        minmax_columns: list[str] | None = None,
        price_column: str | None = None,
        forward_return_horizons: list[int] | None = None,
        save: bool = True,
        register_catalog: bool = True,
        description: str | None = None,
        tags: list[str] | None = None,
    ) -> pl.DataFrame:
        self._validate_dataset_name(dataset_name)

        if files is None:
            df = self.builder.build_from_directory(pattern=pattern)
        else:
            df = self.builder.build_from_files(files)

        processed = self.process_dataset(
            df=df,
            feature_columns=feature_columns,
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            align_common_dates=align_common_dates,
            drop_null_features=drop_null_features,
            min_observations_per_symbol=min_observations_per_symbol,
            winsorize_columns=winsorize_columns,
            winsorize_by_date=winsorize_by_date,
            lower_quantile=lower_quantile,
            upper_quantile=upper_quantile,
            zscore_columns=zscore_columns,
            rank_columns=rank_columns,
            percentile_rank_columns=percentile_rank_columns,
            minmax_columns=minmax_columns,
            price_column=price_column,
            forward_return_horizons=forward_return_horizons,
        )

        if save:
            dataset_path = self.store.save(processed, dataset_name)

            if register_catalog:
                self.catalog.register_dataset(
                    name=dataset_name,
                    df=processed,
                    dataset_path=dataset_path,
                    description=description,
                    tags=tags,
                )

        return processed

    def process_dataset(
        self,
        df: pl.DataFrame,
        feature_columns: list[str] | None = None,
        symbols: list[str] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        align_common_dates: bool = False,
        drop_null_features: bool = True,
        min_observations_per_symbol: int | None = None,
        winsorize_columns: list[str] | None = None,
        winsorize_by_date: bool = True,
        lower_quantile: float = 0.01,
        upper_quantile: float = 0.99,
        zscore_columns: list[str] | None = None,
        rank_columns: list[str] | None = None,
        percentile_rank_columns: list[str] | None = None,
        minmax_columns: list[str] | None = None,
        price_column: str | None = None,
        forward_return_horizons: list[int] | None = None,
    ) -> pl.DataFrame:
        self.schema.validate(
            df=df,
            feature_columns=feature_columns,
            require_features=True,
            require_numeric_features=True,
        )

        processed = df.sort(["date", "symbol"])

        if symbols is not None:
            processed = self.filters.filter_symbols(processed, symbols)

        if start_date is not None or end_date is not None:
            processed = self.filters.filter_date_range(
                df=processed,
                start_date=start_date,
                end_date=end_date,
            )

        if min_observations_per_symbol is not None:
            processed = self.filters.filter_min_observations_per_symbol(
                df=processed,
                min_observations=min_observations_per_symbol,
            )

        if align_common_dates:
            processed = self.aligner.align_to_common_dates(processed)

        if drop_null_features:
            processed = self.filters.drop_null_features(
                df=processed,
                feature_columns=feature_columns,
            )

        if winsorize_columns is not None:
            if winsorize_by_date:
                processed = self.winsorizer.winsorize_by_date(
                    df=processed,
                    columns=winsorize_columns,
                    lower_quantile=lower_quantile,
                    upper_quantile=upper_quantile,
                )
            else:
                processed = self.winsorizer.winsorize_columns(
                    df=processed,
                    columns=winsorize_columns,
                    lower_quantile=lower_quantile,
                    upper_quantile=upper_quantile,
                )

        if zscore_columns is not None:
            processed = self.normalizer.zscore_by_date(
                df=processed,
                columns=zscore_columns,
            )

        if rank_columns is not None:
            processed = self.normalizer.rank_by_date(
                df=processed,
                columns=rank_columns,
            )

        if percentile_rank_columns is not None:
            processed = self.normalizer.percentile_rank_by_date(
                df=processed,
                columns=percentile_rank_columns,
            )

        if minmax_columns is not None:
            processed = self.normalizer.min_max_scale_by_date(
                df=processed,
                columns=minmax_columns,
            )

        if price_column is not None:
            processed = self.labeler.add_forward_returns(
                df=processed,
                price_column=price_column,
                horizons=forward_return_horizons,
            )

        self.schema.validate(
            df=processed,
            require_features=True,
            require_numeric_features=True,
        )

        return processed.sort(["date", "symbol"])

    def _validate_dataset_name(self, dataset_name: str) -> None:
        if not dataset_name or not dataset_name.strip():
            raise ValueError("dataset_name cannot be empty.")
