from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


RESULT_FILENAME = "signalforge_quantconnect_cloud_replay_backtest_execution.json"
SUMMARY_FILENAME = "signalforge_quantconnect_cloud_replay_backtest_execution_summary.json"


def write_signalforge_quantconnect_cloud_replay_backtest_execution(
    result: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    result_path = output_path / RESULT_FILENAME
    summary_path = output_path / SUMMARY_FILENAME

    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    summary = {
        "operation_type": "signalforge_quantconnect_cloud_replay_backtest_execution_cli",
        "adapter_type": result.get("adapter_type"),
        "artifact_type": result.get("artifact_type"),
        "schema_version": "signalforge_quantconnect_cloud_replay_backtest_execution_cli_summary.v1",
        "contract": result.get("contract"),
        "status": result.get("status"),
        "is_ready": result.get("is_ready"),
        "mode": result.get("mode"),
        "requires_manual_approval": result.get("requires_manual_approval"),
        "review_scope": result.get("review_scope"),
        "blocked_reasons": list(result.get("blocked_reasons", [])),
        "covered_capabilities": list(result.get("covered_capabilities", [])),
        "depends_on_capabilities": list(result.get("depends_on_capabilities", [])),
        "explicit_exclusions": list(result.get("explicit_exclusions", [])),
        "source_artifacts": dict(result.get("source_artifacts", {})),
        "output_dir": str(output_path),
        "files": {
            "backtest_execution_result": str(result_path),
            "summary": str(summary_path),
        },
        "file_summary": {
            "file_count": 2,
            "written_file_count": 2,
            "missing_files": [],
            "empty_files": [],
            "file_sizes": {
                "backtest_execution_result": result_path.stat().st_size if result_path.exists() else 0,
                "summary": summary_path.stat().st_size if summary_path.exists() else 0,
            },
        },
        "quantconnect_project_id": result.get("quantconnect_project_id"),
        "quantconnect_organization_id": result.get("quantconnect_organization_id"),
        "quantconnect_project_file_name": result.get("quantconnect_project_file_name"),
        "batch_limit": result.get("batch_limit"),
        "selected_batch_count": result.get("selected_batch_count"),
        "backtested_batch_count": result.get("backtested_batch_count"),
        "failed_backtest_batch_count": result.get("failed_backtest_batch_count"),
        "failed_backtest_batch_ids": list(result.get("failed_backtest_batch_ids", [])),
        "backtest_execution_summary": dict(result.get("backtest_execution_summary", {})),
        "next_build_recommendations": list(result.get("next_build_recommendations", [])),
        "order_intent": result.get("order_intent"),
        "broker_order_id": result.get("broker_order_id"),
        "portfolio_action": result.get("portfolio_action"),
        "position_size": result.get("position_size"),
        "automatic_action": result.get("automatic_action"),
        "automatic_close_order": result.get("automatic_close_order"),
        "automatic_roll_order": result.get("automatic_roll_order"),
        "automatic_defense_order": result.get("automatic_defense_order"),
        "automatic_strategy_change": result.get("automatic_strategy_change"),
        "automatic_parameter_change": result.get("automatic_parameter_change"),
        "automatic_pause_action": result.get("automatic_pause_action"),
    }

    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary
