from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


ASSET_BEHAVIOR_RESULT_FILENAME = "signalforge_asset_behavior_from_market_price_history.json"
ASSET_BEHAVIOR_SUMMARY_FILENAME = "signalforge_asset_behavior_from_market_price_history_summary.json"
ASSET_BEHAVIOR_CLI_SUMMARY_SCHEMA_VERSION = (
    "signalforge_asset_behavior_from_market_price_history_cli_summary.v1"
)


def write_asset_behavior_from_market_price_history_result(
    result: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    result_path = output_path / ASSET_BEHAVIOR_RESULT_FILENAME
    summary_path = output_path / ASSET_BEHAVIOR_SUMMARY_FILENAME

    result_path.write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    summary = build_asset_behavior_from_market_price_history_summary(
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


def build_asset_behavior_from_market_price_history_summary(
    *,
    result: Mapping[str, Any],
    result_path: Path,
    summary_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    result_size = result_path.stat().st_size if result_path.exists() else 0

    summary = {
        "schema_version": ASSET_BEHAVIOR_CLI_SUMMARY_SCHEMA_VERSION,
        "operation_type": "signalforge_asset_behavior_from_market_price_history_cli",
        "artifact_type": result.get("artifact_type"),
        "contract": result.get("contract"),
        "adapter_type": result.get("adapter_type"),
        "status": result.get("status"),
        "is_ready": result.get("is_ready"),
        "requires_manual_approval": result.get("requires_manual_approval"),
        "source_artifact_type": result.get("source_artifact_type"),
        "source_status": result.get("source_status"),
        "source_kind": result.get("source_kind"),
        "short_window": result.get("short_window"),
        "long_window": result.get("long_window"),
        "annualization_factor": result.get("annualization_factor"),
        "observed_symbol_count": result.get("observed_symbol_count"),
        "observed_symbols": result.get("observed_symbols"),
        "requested_symbols": result.get("requested_symbols"),
        "asset_behavior_summary": result.get("asset_behavior_summary"),
        "blocker_count": len(result.get("blocker_items") or []),
        "warning_count": len(result.get("warning_items") or []),
        "output_dir": str(output_dir),
        "files": {
            "asset_behavior_result": str(result_path),
            "summary": str(summary_path),
        },
        "file_summary": {
            "file_count": 2,
            "written_file_count": 2,
            "missing_files": [],
            "empty_files": [],
            "file_sizes": {
                "asset_behavior_result": result_size,
                "summary": 0,
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

    return summary
