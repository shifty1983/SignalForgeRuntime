from __future__ import annotations

import json
from collections.abc import Mapping
from os import PathLike
from pathlib import Path
from typing import Any

from src.data_sources.data_source_adapter_plan import build_signalforge_data_source_adapter_plan


FILE_WRITER_SCHEMA_VERSION = "signalforge_data_source_adapter_plan_files.v1"
OPERATION_TYPE = "signalforge_data_source_adapter_plan_file_writer"

DEFAULT_FILENAMES = {
    "adapter_plan": "signalforge_data_source_adapter_plan.json",
    "summary": "signalforge_data_source_adapter_plan_summary.json",
}


def write_signalforge_data_source_adapter_plan_files(
    source: Any | None = None,
    *,
    output_dir: str | PathLike[str],
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    adapter_plan = build_signalforge_data_source_adapter_plan(source)

    files = {
        "adapter_plan": output_path / DEFAULT_FILENAMES["adapter_plan"],
        "summary": output_path / DEFAULT_FILENAMES["summary"],
    }

    summary = _build_summary(adapter_plan=adapter_plan, output_dir=output_path, files=files)

    _write_json(files["adapter_plan"], adapter_plan)
    _write_json(files["summary"], summary)

    return {
        "schema_version": FILE_WRITER_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": adapter_plan.get("status", "needs_review"),
        "output_dir": str(output_path),
        "files": {key: str(path) for key, path in files.items()},
        "file_summary": _build_file_summary(files),
        "adapter_plan": adapter_plan,
        "summary": summary,
        "explicit_exclusions": list(adapter_plan.get("explicit_exclusions", [])),
    }


def _build_summary(
    *,
    adapter_plan: Mapping[str, Any],
    output_dir: Path,
    files: Mapping[str, Path],
) -> dict[str, Any]:
    recommended_next_adapter = adapter_plan.get("recommended_next_adapter")

    return {
        "schema_version": "signalforge_data_source_adapter_plan_summary.v1",
        "artifact_type": "signalforge_data_source_adapter_plan_summary",
        "status": adapter_plan.get("status", "needs_review"),
        "is_ready": adapter_plan.get("is_ready", False),
        "output_dir": str(output_dir),
        "files": {key: str(path) for key, path in files.items()},
        "inventory_status": adapter_plan.get("inventory_status"),
        "contracts_status": adapter_plan.get("contracts_status"),
        "adapter_plan_summary": dict(_as_mapping(adapter_plan.get("adapter_plan_summary"))),
        "open_inventory_decision_count": _safe_int(
            adapter_plan.get("open_inventory_decision_count")
        ),
        "open_adapter_source_count": _safe_int(adapter_plan.get("open_adapter_source_count")),
        "resolved_adapter_source_count": _safe_int(
            adapter_plan.get("resolved_adapter_source_count")
        ),
        "recommended_next_adapter": dict(_as_mapping(recommended_next_adapter)),
        "blocked_items": list(_as_list(adapter_plan.get("blocked_items"))),
        "requires_manual_approval": adapter_plan.get("requires_manual_approval") is True,
        "order_intent": adapter_plan.get("order_intent"),
        "broker_order_id": adapter_plan.get("broker_order_id"),
        "automatic_action": adapter_plan.get("automatic_action"),
        "automatic_strategy_change": adapter_plan.get("automatic_strategy_change"),
        "automatic_parameter_change": adapter_plan.get("automatic_parameter_change"),
        "automatic_pause_action": adapter_plan.get("automatic_pause_action"),
        "explicit_exclusions": list(_as_list(adapter_plan.get("explicit_exclusions"))),
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

