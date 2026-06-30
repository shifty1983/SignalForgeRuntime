from __future__ import annotations

import json
from collections.abc import Mapping
from os import PathLike
from pathlib import Path
from typing import Any

from src.signalforge.data_sources.market_price_history_import import (
    build_signalforge_market_price_history_import,
)


FILE_WRITER_SCHEMA_VERSION = "signalforge_market_price_history_import_files.v1"
OPERATION_TYPE = "signalforge_market_price_history_import_file_writer"

DEFAULT_FILENAMES = {
    "import_result": "signalforge_market_price_history_import.json",
    "summary": "signalforge_market_price_history_import_summary.json",
}


def write_signalforge_market_price_history_import_files(
    source: Any,
    *,
    output_dir: str | PathLike[str],
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    import_result = build_signalforge_market_price_history_import(source)

    files = {
        "import_result": output_path / DEFAULT_FILENAMES["import_result"],
        "summary": output_path / DEFAULT_FILENAMES["summary"],
    }

    summary = _build_summary(
        import_result=import_result,
        output_dir=output_path,
        files=files,
    )

    _write_json(files["import_result"], import_result)
    _write_json(files["summary"], summary)

    return {
        "schema_version": FILE_WRITER_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": import_result.get("status", "needs_review"),
        "output_dir": str(output_path),
        "files": {key: str(path) for key, path in files.items()},
        "file_summary": _build_file_summary(files),
        "import_result": import_result,
        "summary": summary,
        "explicit_exclusions": list(import_result.get("explicit_exclusions", [])),
    }


def _build_summary(
    *,
    import_result: Mapping[str, Any],
    output_dir: Path,
    files: Mapping[str, Path],
) -> dict[str, Any]:
    return {
        "schema_version": "signalforge_market_price_history_import_summary.v1",
        "artifact_type": "signalforge_market_price_history_import_summary",
        "status": import_result.get("status", "needs_review"),
        "is_ready": import_result.get("is_ready", False),
        "output_dir": str(output_dir),
        "files": {key: str(path) for key, path in files.items()},
        "contract": import_result.get("contract"),
        "adapter_type": import_result.get("adapter_type"),
        "source_kind": import_result.get("source_kind"),
        "normalized_payload_summary": dict(
            _as_mapping(import_result.get("normalized_payload_summary"))
        ),
        "price_history_summary": dict(
            _as_mapping(import_result.get("price_history_summary"))
        ),
        "universe_symbol_coverage": dict(
            _as_mapping(import_result.get("universe_symbol_coverage"))
        ),
        "raw_payload_summary": dict(_as_mapping(import_result.get("raw_payload_summary"))),
        "validation_row_count": len(_as_list(import_result.get("validation_artifacts"))),
        "missing_required_field_count": len(
            _as_list(import_result.get("missing_required_fields"))
        ),
        "missing_preferred_field_count": len(
            _as_list(import_result.get("missing_preferred_fields"))
        ),
        "blocker_count": len(_as_list(import_result.get("blocker_items"))),
        "warning_count": len(_as_list(import_result.get("warning_items"))),
        "requires_manual_approval": import_result.get("requires_manual_approval") is True,
        "order_intent": import_result.get("order_intent"),
        "broker_order_id": import_result.get("broker_order_id"),
        "automatic_action": import_result.get("automatic_action"),
        "automatic_strategy_change": import_result.get("automatic_strategy_change"),
        "automatic_parameter_change": import_result.get("automatic_parameter_change"),
        "automatic_pause_action": import_result.get("automatic_pause_action"),
        "explicit_exclusions": list(_as_list(import_result.get("explicit_exclusions"))),
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

