from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


REGIME_DIRECTIONAL_POLICY_RESULT_FILENAME = "signalforge_regime_directional_policy.json"
REGIME_DIRECTIONAL_POLICY_SUMMARY_FILENAME = "signalforge_regime_directional_policy_summary.json"
REGIME_DIRECTIONAL_POLICY_CLI_SUMMARY_SCHEMA_VERSION = (
    "signalforge_regime_directional_policy_cli_summary.v1"
)


def write_regime_directional_policy_result(
    result: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    result_path = output_path / REGIME_DIRECTIONAL_POLICY_RESULT_FILENAME
    summary_path = output_path / REGIME_DIRECTIONAL_POLICY_SUMMARY_FILENAME

    result_path.write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    summary = build_regime_directional_policy_summary(
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


def build_regime_directional_policy_summary(
    *,
    result: Mapping[str, Any],
    result_path: Path,
    summary_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    return {
        "schema_version": REGIME_DIRECTIONAL_POLICY_CLI_SUMMARY_SCHEMA_VERSION,
        "operation_type": "signalforge_regime_directional_policy_cli",
        "artifact_type": result.get("artifact_type"),
        "contract": result.get("contract"),
        "adapter_type": result.get("adapter_type"),
        "status": result.get("status"),
        "is_ready": result.get("is_ready"),
        "requires_manual_approval": result.get("requires_manual_approval"),
        "source_artifact_type": result.get("source_artifact_type"),
        "source_status": result.get("source_status"),
        "macro_regime_label": result.get("macro_regime_label"),
        "policy_regime_label": result.get("policy_regime_label"),
        "weekly_planning_label": result.get("weekly_planning_label"),
        "market_confirmation": result.get("market_confirmation"),
        "aggregate_market_bias": result.get("aggregate_market_bias"),
        "risk_environment": result.get("risk_environment"),
        "rates_regime": result.get("rates_regime"),
        "liquidity_regime": result.get("liquidity_regime"),
        "volatility_regime": result.get("volatility_regime"),
        "regime_directional_summary": result.get("regime_directional_summary"),
        "blocker_count": len(result.get("blocker_items") or []),
        "warning_count": len(result.get("warning_items") or []),
        "output_dir": str(output_dir),
        "files": {
            "regime_directional_policy_result": str(result_path),
            "summary": str(summary_path),
        },
        "file_summary": {
            "file_count": 2,
            "written_file_count": 2,
            "missing_files": [],
            "empty_files": [],
            "file_sizes": {
                "regime_directional_policy_result": (
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
