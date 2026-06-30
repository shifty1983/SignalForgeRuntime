from __future__ import annotations

import json
from collections.abc import Mapping
from os import PathLike
from pathlib import Path
from typing import Any

from src.signalforge.data_sources.data_source_inventory import build_signalforge_data_source_inventory


FILE_WRITER_SCHEMA_VERSION = "signalforge_data_source_inventory_files.v1"
OPERATION_TYPE = "signalforge_data_source_inventory_file_writer"

DEFAULT_FILENAMES = {
    "inventory": "signalforge_data_source_inventory.json",
    "summary": "signalforge_data_source_inventory_summary.json",
}


def write_signalforge_data_source_inventory_files(
    source: Any | None = None,
    *,
    output_dir: str | PathLike[str],
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    inventory = build_signalforge_data_source_inventory(source)

    files = {
        "inventory": output_path / DEFAULT_FILENAMES["inventory"],
        "summary": output_path / DEFAULT_FILENAMES["summary"],
    }

    summary = _build_summary(inventory=inventory, output_dir=output_path, files=files)

    _write_json(files["inventory"], inventory)
    _write_json(files["summary"], summary)

    return {
        "schema_version": FILE_WRITER_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": inventory.get("status", "needs_review"),
        "output_dir": str(output_path),
        "files": {key: str(path) for key, path in files.items()},
        "file_summary": _build_file_summary(files),
        "inventory": inventory,
        "summary": summary,
        "explicit_exclusions": list(inventory.get("explicit_exclusions", [])),
    }


def _build_summary(
    *,
    inventory: Mapping[str, Any],
    output_dir: Path,
    files: Mapping[str, Path],
) -> dict[str, Any]:
    module_summary = _as_mapping(inventory.get("module_summary"))
    category_summary = _as_mapping(inventory.get("category_summary"))

    return {
        "schema_version": "signalforge_data_source_inventory_summary.v1",
        "artifact_type": "signalforge_data_source_inventory_summary",
        "status": inventory.get("status", "needs_review"),
        "is_ready": inventory.get("is_ready", False),
        "output_dir": str(output_dir),
        "files": {key: str(path) for key, path in files.items()},
        "module_summary": dict(module_summary),
        "category_summary": dict(category_summary),
        "open_decision_count": _safe_int(inventory.get("open_decision_count")),
        "adapter_backlog_count": _safe_int(inventory.get("adapter_backlog_count")),
        "recommended_build_order": list(_as_list(inventory.get("recommended_build_order"))),
        "requires_manual_approval": inventory.get("requires_manual_approval") is True,
        "order_intent": inventory.get("order_intent"),
        "broker_order_id": inventory.get("broker_order_id"),
        "automatic_action": inventory.get("automatic_action"),
        "automatic_strategy_change": inventory.get("automatic_strategy_change"),
        "automatic_parameter_change": inventory.get("automatic_parameter_change"),
        "automatic_pause_action": inventory.get("automatic_pause_action"),
        "explicit_exclusions": list(_as_list(inventory.get("explicit_exclusions"))),
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

