from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


OPTION_BEHAVIOR_SOURCE_READINESS_RESULT_FILENAME = (
    "signalforge_option_behavior_source_readiness.json"
)
OPTION_BEHAVIOR_SOURCE_READINESS_SUMMARY_FILENAME = (
    "signalforge_option_behavior_source_readiness_summary.json"
)
OPTION_BEHAVIOR_SOURCE_READINESS_CLI_SUMMARY_SCHEMA_VERSION = (
    "signalforge_option_behavior_source_readiness_cli_summary.v1"
)


def write_option_behavior_source_readiness_result(
    result: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    result_path = output_path / OPTION_BEHAVIOR_SOURCE_READINESS_RESULT_FILENAME
    summary_path = output_path / OPTION_BEHAVIOR_SOURCE_READINESS_SUMMARY_FILENAME

    result_path.write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    summary = build_option_behavior_source_readiness_summary(
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


def build_option_behavior_source_readiness_summary(
    *,
    result: Mapping[str, Any],
    result_path: Path,
    summary_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    summary = result.get("option_behavior_source_readiness_summary") or {}

    return {
        "schema_version": OPTION_BEHAVIOR_SOURCE_READINESS_CLI_SUMMARY_SCHEMA_VERSION,
        "operation_type": "signalforge_option_behavior_source_readiness_cli",
        "artifact_type": result.get("artifact_type"),
        "contract": result.get("contract"),
        "adapter_type": result.get("adapter_type"),
        "status": result.get("status"),
        "is_ready": result.get("is_ready"),
        "requires_manual_approval": result.get("requires_manual_approval"),
        "source_artifacts": result.get("source_artifacts"),
        "source_statuses": result.get("source_statuses"),
        "macro_regime_label": result.get("macro_regime_label"),
        "policy_regime_label": result.get("policy_regime_label"),
        "weekly_planning_label": result.get("weekly_planning_label"),
        "market_confirmation": result.get("market_confirmation"),
        "aggregate_market_bias": result.get("aggregate_market_bias"),
        "option_behavior_source_readiness_summary": summary,
        "ready_symbols": summary.get("ready_symbols", []),
        "review_required_symbols": summary.get("review_required_symbols", []),
        "blocked_symbols": summary.get("blocked_symbols", []),
        "ready_long_symbols": summary.get("ready_long_symbols", []),
        "ready_short_symbols": summary.get("ready_short_symbols", []),
        "ready_neutral_symbols": summary.get("ready_neutral_symbols", []),
        "malformed_option_row_count": len(result.get("malformed_option_rows") or []),
        "blocker_count": len(result.get("blocker_items") or []),
        "warning_count": len(result.get("warning_items") or []),
        "skipped_count": len(result.get("skipped_items") or []),
        "output_dir": str(output_dir),
        "files": {
            "option_behavior_source_readiness_result": str(result_path),
            "summary": str(summary_path),
        },
        "file_summary": {
            "file_count": 2,
            "written_file_count": 2,
            "missing_files": [],
            "empty_files": [],
            "file_sizes": {
                "option_behavior_source_readiness_result": (
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
