from __future__ import annotations

import json
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd


PathLike = str | Path


@dataclass(frozen=True)
class ExportResult:
    path: str
    format: str
    rows: int | None = None
    columns: int | None = None
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def ensure_parent_directory(path: PathLike) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return output_path


def _json_safe(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _json_safe(asdict(value))

    if isinstance(value, ExportResult):
        return _json_safe(value.to_dict())

    if isinstance(value, pd.DataFrame):
        return _json_safe(value.to_dict(orient="records"))

    if isinstance(value, pd.Series):
        return _json_safe(value.to_dict())

    if isinstance(value, Mapping):
        return {
            str(_json_safe(key)): _json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]

    if isinstance(value, list):
        return [_json_safe(item) for item in value]

    if isinstance(value, np.ndarray):
        return _json_safe(value.tolist())

    if isinstance(value, pd.Timestamp):
        return value.isoformat()

    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, date):
        return value.isoformat()

    if isinstance(value, np.integer):
        return int(value)

    if isinstance(value, np.floating):
        result = float(value)

        if np.isnan(result):
            return None

        if np.isposinf(result):
            return "Infinity"

        if np.isneginf(result):
            return "-Infinity"

        return result

    if isinstance(value, float):
        if np.isnan(value):
            return None

        if np.isposinf(value):
            return "Infinity"

        if np.isneginf(value):
            return "-Infinity"

        return value

    if isinstance(value, np.bool_):
        return bool(value)

    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    return value


def _to_frame(data: pd.DataFrame | Sequence[Mapping[str, Any]]) -> pd.DataFrame:
    if isinstance(data, pd.DataFrame):
        return data.copy()

    return pd.DataFrame(list(data))


def export_json(
    data: Any,
    path: PathLike,
    *,
    indent: int = 2,
    sort_keys: bool = False,
) -> ExportResult:
    output_path = ensure_parent_directory(path)

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(
            _json_safe(data),
            file,
            indent=indent,
            sort_keys=sort_keys,
        )

    return ExportResult(
        path=str(output_path),
        format="json",
        metadata={"indent": indent, "sort_keys": sort_keys},
    )


def export_dataframe_csv(
    frame: pd.DataFrame,
    path: PathLike,
    *,
    index: bool = False,
) -> ExportResult:
    output_path = ensure_parent_directory(path)

    frame.to_csv(output_path, index=index)

    return ExportResult(
        path=str(output_path),
        format="csv",
        rows=int(len(frame)),
        columns=int(len(frame.columns)),
        metadata={"index": index},
    )


def export_records_csv(
    records: Sequence[Mapping[str, Any]],
    path: PathLike,
    *,
    index: bool = False,
) -> ExportResult:
    frame = pd.DataFrame(list(records))

    return export_dataframe_csv(
        frame,
        path,
        index=index,
    )


def export_dataframe_json(
    frame: pd.DataFrame,
    path: PathLike,
    *,
    orient: str = "records",
    indent: int = 2,
) -> ExportResult:
    output_path = ensure_parent_directory(path)

    json_payload = json.loads(
        frame.to_json(
            orient=orient,
            date_format="iso",
        )
    )

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(
            _json_safe(json_payload),
            file,
            indent=indent,
        )

    return ExportResult(
        path=str(output_path),
        format="json",
        rows=int(len(frame)),
        columns=int(len(frame.columns)),
        metadata={"orient": orient, "indent": indent},
    )


def export_dataframe_parquet(
    frame: pd.DataFrame,
    path: PathLike,
    *,
    index: bool = False,
) -> ExportResult:
    output_path = ensure_parent_directory(path)

    frame.to_parquet(output_path, index=index)

    return ExportResult(
        path=str(output_path),
        format="parquet",
        rows=int(len(frame)),
        columns=int(len(frame.columns)),
        metadata={"index": index},
    )


def export_text(
    text: str,
    path: PathLike,
) -> ExportResult:
    output_path = ensure_parent_directory(path)

    with output_path.open("w", encoding="utf-8") as file:
        file.write(text)

    return ExportResult(
        path=str(output_path),
        format="txt",
        rows=None,
        columns=None,
        metadata={"characters": len(text)},
    )


def export_table(
    table: pd.DataFrame | Sequence[Mapping[str, Any]],
    path: PathLike,
    *,
    file_format: str | None = None,
    index: bool = False,
) -> ExportResult:
    output_path = Path(path)
    frame = _to_frame(table)

    resolved_format = (
        file_format.lower().strip()
        if file_format is not None
        else output_path.suffix.lower().lstrip(".")
    )

    if resolved_format == "csv":
        return export_dataframe_csv(
            frame,
            output_path,
            index=index,
        )

    if resolved_format == "json":
        return export_dataframe_json(
            frame,
            output_path,
        )

    if resolved_format in {"parquet", "pq"}:
        return export_dataframe_parquet(
            frame,
            output_path,
            index=index,
        )

    raise ValueError(
        "Unsupported table export format. Expected one of: csv, json, parquet."
    )


def export_dashboard_json(
    dashboard_payload: Mapping[str, Any],
    output_dir: PathLike,
    *,
    filename: str = "dashboard.json",
) -> ExportResult:
    output_path = Path(output_dir) / filename

    return export_json(
        dashboard_payload,
        output_path,
    )


def export_dashboard_tables(
    dashboard_payload: Mapping[str, Any],
    output_dir: PathLike,
    *,
    file_format: str = "csv",
) -> list[ExportResult]:
    output_directory = Path(output_dir)
    output_directory.mkdir(parents=True, exist_ok=True)

    resolved_format = file_format.lower().strip()

    if resolved_format not in {"csv", "json", "parquet", "pq"}:
        raise ValueError("file_format must be one of: csv, json, parquet.")

    results: list[ExportResult] = []

    table_sections = {
        "top_positions": dashboard_payload.get("exposures", {}).get("top_positions", []),
        "asset_class_exposure": dashboard_payload.get("exposures", {}).get("asset_class", []),
        "sector_exposure": dashboard_payload.get("exposures", {}).get("sector", []),
        "strategy_exposure": dashboard_payload.get("exposures", {}).get("strategy", []),
        "greek_exposure": dashboard_payload.get("exposures", {}).get("greeks", []),
        "trade_blotter": dashboard_payload.get("trades", {}).get("blotter", []),
        "trades_by_symbol": dashboard_payload.get("trades", {}).get("by_symbol", []),
        "trades_by_strategy": dashboard_payload.get("trades", {}).get("by_strategy", []),
        "attribution_by_symbol": dashboard_payload.get("attribution", {}).get("by_symbol", []),
        "attribution_by_sector": dashboard_payload.get("attribution", {}).get("by_sector", []),
        "attribution_by_strategy": dashboard_payload.get("attribution", {}).get("by_strategy", []),
        "attribution_by_period": dashboard_payload.get("attribution", {}).get("by_period", []),
        "contribution_matrix": dashboard_payload.get("attribution", {}).get("contribution_matrix", []),
        "returns": dashboard_payload.get("time_series", {}).get("returns", []),
        "cumulative_returns": dashboard_payload.get("time_series", {}).get("cumulative_returns", []),
        "equity_curve": dashboard_payload.get("time_series", {}).get("equity_curve", []),
        "drawdowns": dashboard_payload.get("time_series", {}).get("drawdowns", []),
        "rolling_volatility": dashboard_payload.get("time_series", {}).get("rolling_volatility", []),
    }

    extension = "parquet" if resolved_format == "pq" else resolved_format

    for table_name, records in table_sections.items():
        if not records:
            continue

        output_path = output_directory / f"{table_name}.{extension}"

        results.append(
            export_table(
                records,
                output_path,
                file_format=resolved_format,
            )
        )

    return results


def export_report_bundle(
    dashboard_payload: Mapping[str, Any],
    output_dir: PathLike,
    *,
    include_dashboard_json: bool = True,
    include_tables: bool = True,
    table_format: str = "csv",
    manifest_filename: str = "manifest.json",
) -> dict[str, Any]:
    output_directory = Path(output_dir)
    output_directory.mkdir(parents=True, exist_ok=True)

    results: list[ExportResult] = []

    if include_dashboard_json:
        results.append(
            export_dashboard_json(
                dashboard_payload,
                output_directory,
            )
        )

    if include_tables:
        results.extend(
            export_dashboard_tables(
                dashboard_payload,
                output_directory,
                file_format=table_format,
            )
        )

    manifest = {
        "output_dir": str(output_directory),
        "file_count": len(results),
        "files": [result.to_dict() for result in results],
    }

    manifest_result = export_json(
        manifest,
        output_directory / manifest_filename,
    )

    manifest["manifest"] = manifest_result.to_dict()

    return _json_safe(manifest)


def read_json(path: PathLike) -> Any:
    input_path = Path(path)

    with input_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def read_csv(path: PathLike) -> pd.DataFrame:
    return pd.read_csv(path)


def read_parquet(path: PathLike) -> pd.DataFrame:
    return pd.read_parquet(path)
