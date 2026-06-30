from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


ASSET_MULTI_HORIZON_BEHAVIOR_RESULT_FILENAME = (
    "signalforge_asset_multi_horizon_behavior.json"
)
ASSET_MULTI_HORIZON_BEHAVIOR_SUMMARY_FILENAME = (
    "signalforge_asset_multi_horizon_behavior_summary.json"
)
ASSET_MULTI_HORIZON_BEHAVIOR_CLI_SUMMARY_SCHEMA_VERSION = (
    "signalforge_asset_multi_horizon_behavior_cli_summary.v1"
)


def write_asset_multi_horizon_behavior_result(
    result: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    result_path = output_path / ASSET_MULTI_HORIZON_BEHAVIOR_RESULT_FILENAME
    summary_path = output_path / ASSET_MULTI_HORIZON_BEHAVIOR_SUMMARY_FILENAME

    result_path.write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    summary = build_asset_multi_horizon_behavior_summary(
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


def build_asset_multi_horizon_behavior_summary(
    *,
    result: Mapping[str, Any],
    result_path: Path,
    summary_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    return {
        "schema_version": ASSET_MULTI_HORIZON_BEHAVIOR_CLI_SUMMARY_SCHEMA_VERSION,
        "operation_type": "signalforge_asset_multi_horizon_behavior_cli",
        "artifact_type": result.get("artifact_type"),
        "contract": result.get("contract"),
        "adapter_type": result.get("adapter_type"),
        "status": result.get("status"),
        "is_ready": result.get("is_ready"),
        "requires_manual_approval": result.get("requires_manual_approval"),
        "source_artifact_type": result.get("source_artifact_type"),
        "source_status": result.get("source_status"),
        "horizons": result.get("horizons"),
        "annualization_factor": result.get("annualization_factor"),
        "positive_return_threshold": result.get("positive_return_threshold"),
        "negative_return_threshold": result.get("negative_return_threshold"),
        "multi_horizon_summary": result.get("multi_horizon_summary"),
        "blocker_count": len(result.get("blocker_items") or []),
        "warning_count": len(result.get("warning_items") or []),
        "skipped_row_count": len(result.get("skipped_rows") or []),
        "output_dir": str(output_dir),
        "files": {
            "asset_multi_horizon_behavior_result": str(result_path),
            "summary": str(summary_path),
        },
        "file_summary": {
            "file_count": 2,
            "written_file_count": 2,
            "missing_files": [],
            "empty_files": [],
            "file_sizes": {
                "asset_multi_horizon_behavior_result": (
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


