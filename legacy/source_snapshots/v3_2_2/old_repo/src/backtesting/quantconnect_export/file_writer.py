from __future__ import annotations

import json
from os import PathLike
from pathlib import Path
from typing import Any, Mapping

from src.backtesting.quantconnect_export.operation import run_quantconnect_export_operation


FILE_WRITER_SCHEMA_VERSION = "quantconnect_export_files.v1"
OPERATION_TYPE = "quantconnect_export_file_writer"

DEFAULT_FILENAMES = {
    "strategy_configs": "quantconnect_strategy_configs.json",
    "universe": "quantconnect_universe.json",
    "decision_rules": "quantconnect_decision_rules.json",
    "backtest_manifest": "quantconnect_backtest_manifest.json",
    "operation_result": "quantconnect_export_operation.json",
    "event_log": "quantconnect_export_operation.jsonl",
}


def write_quantconnect_export_files(
    source: Mapping[str, Any],
    *,
    output_dir: str | PathLike[str],
) -> dict[str, Any]:
    """Write QuantConnect export artifacts to local JSON/JSONL files.

    This writer does not call QuantConnect, brokers, market-data services,
    order-routing systems, live-trading APIs, fill engines, or slippage engines.
    It only writes deterministic local files from the export operation result.
    """

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    event_log_path = output_path / DEFAULT_FILENAMES["event_log"]

    operation_result = run_quantconnect_export_operation(
        source,
        event_log_path=event_log_path,
    )

    export = operation_result.get("export")
    export = export if isinstance(export, Mapping) else {}

    generated_payloads = export.get("generated_payloads")
    generated_payloads = generated_payloads if isinstance(generated_payloads, Mapping) else {}

    files = {
        "strategy_configs": output_path / DEFAULT_FILENAMES["strategy_configs"],
        "universe": output_path / DEFAULT_FILENAMES["universe"],
        "decision_rules": output_path / DEFAULT_FILENAMES["decision_rules"],
        "backtest_manifest": output_path / DEFAULT_FILENAMES["backtest_manifest"],
        "operation_result": output_path / DEFAULT_FILENAMES["operation_result"],
        "event_log": event_log_path,
    }

    _write_json(files["strategy_configs"], _as_list(generated_payloads.get("strategy_configs")))
    _write_json(files["universe"], _as_list(generated_payloads.get("universe")))
    _write_json(files["decision_rules"], _as_list(generated_payloads.get("decision_rules")))
    _write_json(files["backtest_manifest"], _as_mapping(generated_payloads.get("backtest_manifest")))
    _write_json(files["operation_result"], operation_result)

    file_summary = _build_file_summary(files)

    return {
        "schema_version": FILE_WRITER_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": operation_result.get("status", "needs_review"),
        "output_dir": str(output_path),
        "files": {key: str(path) for key, path in files.items()},
        "file_summary": file_summary,
        "operation_result": operation_result,
        "explicit_exclusions": list(operation_result.get("explicit_exclusions", [])),
    }


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _build_file_summary(files: Mapping[str, Path]) -> dict[str, Any]:
    return {
        "file_count": len(files),
        "written_files": sorted(files.keys()),
        "missing_files": sorted(
            key for key, path in files.items() if not path.exists()
        ),
        "empty_files": sorted(
            key for key, path in files.items() if path.exists() and path.stat().st_size == 0
        ),
    }


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}
