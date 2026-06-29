# src/backtesting/historical_records_file_loader.py

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Mapping


LOADER_TYPE = "historical_records_file_loader"

EXPLICIT_EXCLUSIONS = [
    "broker_api_calls",
    "order_routing",
    "order_submission",
    "fills",
    "live_execution",
    "slippage_modeling",
]

SUPPORTED_FORMATS = {"csv", "json", "jsonl", "parquet"}


def load_historical_records_from_files(
    candidate_file_path: str | Path,
    price_file_path: str | Path,
    *,
    candidate_format: str | None = None,
    price_format: str | None = None,
    candidate_read_options: Mapping[str, Any] | None = None,
    price_read_options: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    metadata_dict = dict(metadata or {})
    candidate_options = dict(candidate_read_options or {})
    price_options = dict(price_read_options or {})

    validation_errors: list[str] = []
    warnings: list[str] = []

    candidate_path = Path(candidate_file_path)
    price_path = Path(price_file_path)

    candidate_format_resolved = _resolve_format(
        candidate_path,
        candidate_format,
        validation_errors,
        file_label="candidate_file",
    )
    price_format_resolved = _resolve_format(
        price_path,
        price_format,
        validation_errors,
        file_label="price_file",
    )

    candidate_records: list[dict[str, Any]] = []
    price_records: list[dict[str, Any]] = []

    if candidate_format_resolved is not None:
        candidate_records = _load_records(
            candidate_path,
            candidate_format_resolved,
            candidate_options,
            validation_errors,
            file_label="candidate_file",
        )

    if price_format_resolved is not None:
        price_records = _load_records(
            price_path,
            price_format_resolved,
            price_options,
            validation_errors,
            file_label="price_file",
        )

    if not candidate_records and not any(
        error.startswith("candidate_file") for error in validation_errors
    ):
        validation_errors.append("candidate_file produced no records")

    if not price_records and not any(
        error.startswith("price_file") for error in validation_errors
    ):
        validation_errors.append("price_file produced no records")

    if candidate_path.resolve() == price_path.resolve():
        warnings.append("candidate_file and price_file point to the same path")

    blocked_reasons = list(validation_errors)
    loader_status = "blocked" if validation_errors else "ready"

    return {
        "loader_type": LOADER_TYPE,
        "loader_status": loader_status,
        "is_ready": loader_status == "ready",
        "is_blocked": loader_status == "blocked",
        "validation_errors": validation_errors,
        "warnings": warnings,
        "blocked_reasons": blocked_reasons,
        "candidate_records": candidate_records,
        "price_records": price_records,
        "file_summary": {
            "candidate_file_path": str(candidate_path),
            "price_file_path": str(price_path),
            "candidate_format": candidate_format_resolved,
            "price_format": price_format_resolved,
            "candidate_record_count": len(candidate_records),
            "price_record_count": len(price_records),
            "validation_error_count": len(validation_errors),
            "warning_count": len(warnings),
            "blocked_reason_count": len(blocked_reasons),
        },
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
        "metadata": metadata_dict,
    }


def _resolve_format(
    path: Path,
    requested_format: str | None,
    validation_errors: list[str],
    *,
    file_label: str,
) -> str | None:
    if not path.exists():
        validation_errors.append(f"{file_label} does not exist: {path}")
        return None

    if not path.is_file():
        validation_errors.append(f"{file_label} is not a file: {path}")
        return None

    if requested_format is not None:
        normalized_format = requested_format.strip().lower().lstrip(".")
    else:
        normalized_format = path.suffix.lower().lstrip(".")

    if normalized_format not in SUPPORTED_FORMATS:
        validation_errors.append(
            f"{file_label} unsupported format: {normalized_format}"
        )
        return None

    return normalized_format


def _load_records(
    path: Path,
    file_format: str,
    read_options: Mapping[str, Any],
    validation_errors: list[str],
    *,
    file_label: str,
) -> list[dict[str, Any]]:
    try:
        if file_format == "csv":
            return _load_csv_records(path, read_options)

        if file_format == "json":
            return _load_json_records(path)

        if file_format == "jsonl":
            return _load_jsonl_records(path)

        if file_format == "parquet":
            return _load_parquet_records(path)

    except Exception as error:  # noqa: BLE001 - loader should return structured failure
        validation_errors.append(f"{file_label} failed to load: {error}")
        return []

    validation_errors.append(f"{file_label} unsupported format: {file_format}")
    return []


def _load_csv_records(
    path: Path,
    read_options: Mapping[str, Any],
) -> list[dict[str, Any]]:
    encoding = str(read_options.get("encoding", "utf-8"))
    delimiter = str(read_options.get("delimiter", ","))

    with path.open("r", encoding=encoding, newline="") as file:
        reader = csv.DictReader(file, delimiter=delimiter)

        if reader.fieldnames is None:
            return []

        return [
            _normalize_record_values(dict(row))
            for row in reader
            if any(value not in {None, ""} for value in row.values())
        ]


def _load_json_records(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)

    if isinstance(payload, list):
        return [
            _normalize_record_values(dict(item))
            for item in payload
            if isinstance(item, Mapping)
        ]

    if isinstance(payload, Mapping):
        records = payload.get("records")
        if isinstance(records, list):
            return [
                _normalize_record_values(dict(item))
                for item in records
                if isinstance(item, Mapping)
            ]

        return [_normalize_record_values(dict(payload))]

    return []


def _load_jsonl_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8") as file:
        for line in file:
            text = line.strip()
            if not text:
                continue

            payload = json.loads(text)
            if isinstance(payload, Mapping):
                records.append(_normalize_record_values(dict(payload)))

    return records


def _load_parquet_records(path: Path) -> list[dict[str, Any]]:
    try:
        import pandas as pd  # type: ignore[import-not-found]
    except ImportError as error:
        raise RuntimeError(
            "parquet loading requires pandas with a parquet engine installed"
        ) from error

    dataframe = pd.read_parquet(path)

    return [
        _normalize_record_values(dict(record))
        for record in dataframe.to_dict(orient="records")
    ]


def _normalize_record_values(record: Mapping[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}

    for key, value in record.items():
        if value == "":
            normalized[str(key)] = None
        elif _is_nan(value):
            normalized[str(key)] = None
        else:
            normalized[str(key)] = value

    return normalized


def _is_nan(value: Any) -> bool:
    try:
        return value != value
    except Exception:
        return False
