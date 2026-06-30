from __future__ import annotations

import json
from collections.abc import Mapping
from os import PathLike
from pathlib import Path
from typing import Any

from src.signalforge.data_sources.data_source_contract_validator import (
    validate_signalforge_data_source_contract_payload,
)


FILE_WRITER_SCHEMA_VERSION = "signalforge_data_source_contract_validation_files.v1"
OPERATION_TYPE = "signalforge_data_source_contract_validation_file_writer"

DEFAULT_FILENAMES = {
    "validation": "signalforge_data_source_contract_validation.json",
    "summary": "signalforge_data_source_contract_validation_summary.json",
}


def write_signalforge_data_source_contract_validation_files(
    source: Any,
    *,
    output_dir: str | PathLike[str],
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    validation = validate_signalforge_data_source_contract_payload(source)

    files = {
        "validation": output_path / DEFAULT_FILENAMES["validation"],
        "summary": output_path / DEFAULT_FILENAMES["summary"],
    }

    summary = _build_summary(validation=validation, output_dir=output_path, files=files)

    _write_json(files["validation"], validation)
    _write_json(files["summary"], summary)

    return {
        "schema_version": FILE_WRITER_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": validation.get("status", "needs_review"),
        "output_dir": str(output_path),
        "files": {key: str(path) for key, path in files.items()},
        "file_summary": _build_file_summary(files),
        "validation": validation,
        "summary": summary,
        "explicit_exclusions": list(validation.get("explicit_exclusions", [])),
    }


def _build_summary(
    *,
    validation: Mapping[str, Any],
    output_dir: Path,
    files: Mapping[str, Path],
) -> dict[str, Any]:
    return {
        "schema_version": "signalforge_data_source_contract_validation_summary.v1",
        "artifact_type": "signalforge_data_source_contract_validation_summary",
        "status": validation.get("status", "needs_review"),
        "is_ready": validation.get("is_ready", False),
        "output_dir": str(output_dir),
        "files": {key: str(path) for key, path in files.items()},
        "contract": validation.get("contract"),
        "data_category": validation.get("data_category"),
        "adapter_type": validation.get("adapter_type"),
        "required_field_count": _safe_int(validation.get("required_field_count")),
        "preferred_field_count": _safe_int(validation.get("preferred_field_count")),
        "optional_field_count": _safe_int(validation.get("optional_field_count")),
        "present_required_field_count": _safe_int(
            validation.get("present_required_field_count")
        ),
        "present_preferred_field_count": _safe_int(
            validation.get("present_preferred_field_count")
        ),
        "present_optional_field_count": _safe_int(
            validation.get("present_optional_field_count")
        ),
        "missing_required_field_count": len(_as_list(validation.get("missing_required_fields"))),
        "missing_preferred_field_count": len(
            _as_list(validation.get("missing_preferred_fields"))
        ),
        "blocker_count": len(_as_list(validation.get("blocker_items"))),
        "warning_count": len(_as_list(validation.get("warning_items"))),
        "nested_validation": dict(_as_mapping(validation.get("nested_validation"))),
        "payload_summary": dict(_as_mapping(validation.get("payload_summary"))),
        "requires_manual_approval": validation.get("requires_manual_approval") is True,
        "order_intent": validation.get("order_intent"),
        "broker_order_id": validation.get("broker_order_id"),
        "automatic_action": validation.get("automatic_action"),
        "automatic_strategy_change": validation.get("automatic_strategy_change"),
        "automatic_parameter_change": validation.get("automatic_parameter_change"),
        "automatic_pause_action": validation.get("automatic_pause_action"),
        "explicit_exclusions": list(_as_list(validation.get("explicit_exclusions"))),
    }


def _build_file_summary(files: Mapping[str, Path]) -> dict[str, Any]:
    file_sizes = {key: path.stat().st_size if path.exists() else 0 for key, path in files.items()}
    missing_files = [key for key, path in files.items() if not path.exists()]
    empty_files = [key for key, size in file_sizes.items() if size <= 0]

    return {
        "file_count": len(files),
        "written_file_count": len(files) - len(missing_files),
        "missing_files": missing_files,
        "empty_files": empty_files,
        "file_sizes": file_sizes,
    }


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0

