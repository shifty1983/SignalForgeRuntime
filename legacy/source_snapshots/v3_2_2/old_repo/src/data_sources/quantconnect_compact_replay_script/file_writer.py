from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


QUANTCONNECT_COMPACT_REPLAY_SCRIPT_RESULT_FILENAME = "signalforge_quantconnect_compact_replay_script.json"
QUANTCONNECT_COMPACT_REPLAY_SCRIPT_SUMMARY_FILENAME = "signalforge_quantconnect_compact_replay_script_summary.json"
QUANTCONNECT_COMPACT_REPLAY_SCRIPT_CLI_SUMMARY_SCHEMA_VERSION = "signalforge_quantconnect_compact_replay_script_cli_summary.v1"


def write_quantconnect_compact_replay_script_result(
    result: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    result_path = output_path / QUANTCONNECT_COMPACT_REPLAY_SCRIPT_RESULT_FILENAME
    summary_path = output_path / QUANTCONNECT_COMPACT_REPLAY_SCRIPT_SUMMARY_FILENAME
    script_path = output_path / str(result.get("script_filename") or "SignalForgeCompactReplayAlgorithm.py")

    result_path.write_text(json.dumps(result, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    script_path.write_text(str(result.get("quantconnect_compact_replay_script") or ""), encoding="utf-8")

    supplemental_paths: dict[str, Path] = {}
    for supplemental_file in result.get("supplemental_project_files", []) or []:
        if not isinstance(supplemental_file, Mapping):
            continue
        filename = str(supplemental_file.get("filename") or "").strip()
        content_key = str(supplemental_file.get("content_key") or "").strip()
        if not filename or not content_key:
            continue
        supplemental_path = output_path / filename
        supplemental_path.write_text(str(result.get(content_key) or ""), encoding="utf-8")
        supplemental_paths[filename] = supplemental_path

    summary = build_quantconnect_compact_replay_script_summary(
        result=result,
        result_path=result_path,
        summary_path=summary_path,
        script_path=script_path,
        output_dir=output_path,
        supplemental_paths=supplemental_paths,
    )
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return summary


def build_quantconnect_compact_replay_script_summary(
    *,
    result: Mapping[str, Any],
    result_path: Path,
    summary_path: Path,
    script_path: Path,
    output_dir: Path,
    supplemental_paths: Mapping[str, Path] | None = None,
) -> dict[str, Any]:
    script_summary = result.get("quantconnect_compact_replay_script_summary") or {}
    supplemental_paths = supplemental_paths or {}
    files = {
        "quantconnect_compact_replay_script_result": result_path,
        "quantconnect_compact_replay_script": script_path,
        "summary": summary_path,
    }
    for filename, path in supplemental_paths.items():
        files[f"supplemental_project_file:{filename}"] = path
    return {
        "schema_version": QUANTCONNECT_COMPACT_REPLAY_SCRIPT_CLI_SUMMARY_SCHEMA_VERSION,
        "operation_type": "signalforge_quantconnect_compact_replay_script_cli",
        "artifact_type": result.get("artifact_type"),
        "contract": result.get("contract"),
        "adapter_type": result.get("adapter_type"),
        "status": result.get("status"),
        "is_ready": result.get("is_ready"),
        "requires_manual_approval": result.get("requires_manual_approval"),
        "review_scope": result.get("review_scope"),
        "source_artifacts": result.get("source_artifacts"),
        "covered_capabilities": result.get("covered_capabilities"),
        "depends_on_capabilities": result.get("depends_on_capabilities"),
        "next_build_recommendations": result.get("next_build_recommendations", []),
        "blocked_reasons": result.get("blocked_reasons", []),
        "quantconnect_compact_replay_script_summary": script_summary,
        "request_id": result.get("request_id"),
        "symbol_count": result.get("symbol_count", 0),
        "symbols": result.get("symbols", []),
        "replay_start": result.get("replay_start"),
        "replay_end": result.get("replay_end"),
        "benchmark_symbol": result.get("benchmark_symbol"),
        "script_filename": result.get("script_filename"),
        "class_name": result.get("class_name"),
        "manifest_object_store_key": result.get("manifest_object_store_key"),
        "embed_manifest": result.get("embed_manifest"),
        "external_manifest_module": script_summary.get("external_manifest_module"),
        "manifest_module_filename": script_summary.get("manifest_module_filename"),
        "supplemental_project_files": result.get("supplemental_project_files", []),
        "expected_result_file_count": result.get("expected_result_file_count", 0),
        "expected_result_files": result.get("expected_result_files", []),
        "forbidden_execution_call_count": script_summary.get("forbidden_execution_call_count", 0),
        "output_dir": str(output_dir),
        "files": {name: str(path) for name, path in files.items()},
        "file_summary": {
            "file_count": len(files),
            "written_file_count": len([path for path in files.values() if path.exists()]),
            "missing_files": [name for name, path in files.items() if not path.exists()],
            "empty_files": [name for name, path in files.items() if path.exists() and path.stat().st_size == 0],
            "file_sizes": {
                name: path.stat().st_size if path.exists() else 0
                for name, path in files.items()
            },
        },
        "execution_policy": result.get("execution_policy"),
        "portfolio_action": result.get("portfolio_action"),
        "position_size": result.get("position_size"),
        "order_intent": result.get("order_intent"),
        "broker_order_id": result.get("broker_order_id"),
        "automatic_action": result.get("automatic_action"),
        "automatic_strategy_change": result.get("automatic_strategy_change"),
        "automatic_parameter_change": result.get("automatic_parameter_change"),
        "automatic_pause_action": result.get("automatic_pause_action"),
        "automatic_close_order": result.get("automatic_close_order"),
        "automatic_roll_order": result.get("automatic_roll_order"),
        "automatic_defense_order": result.get("automatic_defense_order"),
        "explicit_exclusions": result.get("explicit_exclusions"),
    }
