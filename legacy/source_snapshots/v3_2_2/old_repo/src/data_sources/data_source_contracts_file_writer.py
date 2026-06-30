from __future__ import annotations

import json
from collections.abc import Mapping
from os import PathLike
from pathlib import Path
from typing import Any

from src.signalforge.data_sources.data_source_contracts import build_signalforge_data_source_contracts


FILE_WRITER_SCHEMA_VERSION = "signalforge_data_source_contracts_files.v1"
OPERATION_TYPE = "signalforge_data_source_contracts_file_writer"

DEFAULT_FILENAMES = {
    "contracts": "signalforge_data_source_contracts.json",
    "summary": "signalforge_data_source_contracts_summary.json",
}


def write_signalforge_data_source_contracts_files(
    source: Any | None = None,
    *,
    output_dir: str | PathLike[str],
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    contracts = build_signalforge_data_source_contracts(source)

    files = {
        "contracts": output_path / DEFAULT_FILENAMES["contracts"],
        "summary": output_path / DEFAULT_FILENAMES["summary"],
    }

    summary = _build_summary(contracts=contracts, output_dir=output_path, files=files)

    _write_json(files["contracts"], contracts)
    _write_json(files["summary"], summary)

    return {
        "schema_version": FILE_WRITER_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": contracts.get("status", "needs_review"),
        "output_dir": str(output_path),
        "files": {key: str(path) for key, path in files.items()},
        "file_summary": _build_file_summary(files),
        "contracts": contracts,
        "summary": summary,
        "explicit_exclusions": list(contracts.get("explicit_exclusions", [])),
    }


def _build_summary(
    *,
    contracts: Mapping[str, Any],
    output_dir: Path,
    files: Mapping[str, Path],
) -> dict[str, Any]:
    return {
        "schema_version": "signalforge_data_source_contracts_summary.v1",
        "artifact_type": "signalforge_data_source_contracts_summary",
        "status": contracts.get("status", "needs_review"),
        "is_ready": contracts.get("is_ready", False),
        "output_dir": str(output_dir),
        "files": {key: str(path) for key, path in files.items()},
        "contract_summary": dict(_as_mapping(contracts.get("contract_summary"))),
        "category_summary": dict(_as_mapping(contracts.get("category_summary"))),
        "open_source_count": _safe_int(contracts.get("open_source_count")),
        "resolved_source_count": _safe_int(contracts.get("resolved_source_count")),
        "blocked_items": list(_as_list(contracts.get("blocked_items"))),
        "requires_manual_approval": contracts.get("requires_manual_approval") is True,
        "order_intent": contracts.get("order_intent"),
        "broker_order_id": contracts.get("broker_order_id"),
        "automatic_action": contracts.get("automatic_action"),
        "automatic_strategy_change": contracts.get("automatic_strategy_change"),
        "automatic_parameter_change": contracts.get("automatic_parameter_change"),
        "automatic_pause_action": contracts.get("automatic_pause_action"),
        "explicit_exclusions": list(_as_list(contracts.get("explicit_exclusions"))),
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

