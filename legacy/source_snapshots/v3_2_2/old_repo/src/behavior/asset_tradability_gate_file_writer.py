from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


ASSET_TRADABILITY_GATE_RESULT_FILENAME = "signalforge_asset_tradability_gate.json"
ASSET_TRADABILITY_GATE_SUMMARY_FILENAME = "signalforge_asset_tradability_gate_summary.json"
ASSET_TRADABILITY_GATE_CLI_SUMMARY_SCHEMA_VERSION = (
    "signalforge_asset_tradability_gate_cli_summary.v1"
)


def write_asset_tradability_gate_result(
    result: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    result_path = output_path / ASSET_TRADABILITY_GATE_RESULT_FILENAME
    summary_path = output_path / ASSET_TRADABILITY_GATE_SUMMARY_FILENAME

    result_path.write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    summary = build_asset_tradability_gate_summary(
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


def build_asset_tradability_gate_summary(
    *,
    result: Mapping[str, Any],
    result_path: Path,
    summary_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    summary = result.get("tradability_gate_summary") or {}

    return {
        "schema_version": ASSET_TRADABILITY_GATE_CLI_SUMMARY_SCHEMA_VERSION,
        "operation_type": "signalforge_asset_tradability_gate_cli",
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
        "thresholds": result.get("thresholds"),
        "tradability_gate_summary": summary,
        "top_tradable_symbols": summary.get("top_tradable_symbols", []),
        "review_required_symbols": summary.get("review_required_symbols", []),
        "blocked_symbols": summary.get("blocked_symbols", []),
        "top_tradable_long_symbols": summary.get("top_tradable_long_symbols", []),
        "top_tradable_short_symbols": summary.get("top_tradable_short_symbols", []),
        "top_tradable_neutral_symbols": summary.get("top_tradable_neutral_symbols", []),
        "blocker_count": len(result.get("blocker_items") or []),
        "warning_count": len(result.get("warning_items") or []),
        "skipped_count": len(result.get("skipped_items") or []),
        "output_dir": str(output_dir),
        "files": {
            "asset_tradability_gate_result": str(result_path),
            "summary": str(summary_path),
        },
        "file_summary": {
            "file_count": 2,
            "written_file_count": 2,
            "missing_files": [],
            "empty_files": [],
            "file_sizes": {
                "asset_tradability_gate_result": (
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
