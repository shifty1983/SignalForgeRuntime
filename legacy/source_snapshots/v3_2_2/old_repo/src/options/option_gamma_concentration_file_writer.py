from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


OPTION_GAMMA_CONCENTRATION_RESULT_FILENAME = "signalforge_option_gamma_concentration.json"
OPTION_GAMMA_CONCENTRATION_SUMMARY_FILENAME = "signalforge_option_gamma_concentration_summary.json"
OPTION_GAMMA_CONCENTRATION_CLI_SUMMARY_SCHEMA_VERSION = (
    "signalforge_option_gamma_concentration_cli_summary.v1"
)


def write_option_gamma_concentration_result(
    result: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    result_path = output_path / OPTION_GAMMA_CONCENTRATION_RESULT_FILENAME
    summary_path = output_path / OPTION_GAMMA_CONCENTRATION_SUMMARY_FILENAME

    result_path.write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    summary = build_option_gamma_concentration_summary(
        result=result,
        result_path=result_path,
        summary_path=summary_path,
        output_dir=output_path,
    )

    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    return summary


def build_option_gamma_concentration_summary(
    *,
    result: Mapping[str, Any],
    result_path: Path,
    summary_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    gamma_summary = result.get("option_gamma_concentration_summary") or {}

    return {
        "schema_version": OPTION_GAMMA_CONCENTRATION_CLI_SUMMARY_SCHEMA_VERSION,
        "operation_type": "signalforge_option_gamma_concentration_cli",
        "artifact_type": result.get("artifact_type"),
        "contract": result.get("contract"),
        "adapter_type": result.get("adapter_type"),
        "status": result.get("status"),
        "is_ready": result.get("is_ready"),
        "requires_manual_approval": result.get("requires_manual_approval"),
        "review_scope": result.get("review_scope"),
        "source_artifact": result.get("source_artifact"),
        "thresholds": result.get("thresholds"),
        "covered_capabilities": result.get("covered_capabilities"),
        "next_build_recommendations": result.get("next_build_recommendations"),
        "option_gamma_concentration_summary": gamma_summary,
        "symbol_count": gamma_summary.get("symbol_count", 0),
        "ready_symbol_count": gamma_summary.get("ready_symbol_count", 0),
        "needs_review_symbol_count": gamma_summary.get("needs_review_symbol_count", 0),
        "malformed_row_count": gamma_summary.get("malformed_row_count", 0),
        "output_dir": str(output_dir),
        "files": {
            "option_gamma_concentration_result": str(result_path),
            "summary": str(summary_path),
        },
        "file_summary": {
            "file_count": 2,
            "written_file_count": 2,
            "missing_files": [],
            "empty_files": [],
            "file_sizes": {
                "option_gamma_concentration_result": (
                    result_path.stat().st_size if result_path.exists() else 0
                ),
                "summary": summary_path.stat().st_size if summary_path.exists() else 0,
            },
        },
        "order_intent": result.get("order_intent"),
        "broker_order_id": result.get("broker_order_id"),
        "automatic_action": result.get("automatic_action"),
        "automatic_strategy_change": result.get("automatic_strategy_change"),
        "automatic_parameter_change": result.get("automatic_parameter_change"),
        "automatic_pause_action": result.get("automatic_pause_action"),
        "explicit_exclusions": result.get("explicit_exclusions"),
    }
