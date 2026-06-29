from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


ASSET_DIRECTIONAL_CANDIDATE_RANK_RESULT_FILENAME = (
    "signalforge_asset_directional_candidate_rank.json"
)
ASSET_DIRECTIONAL_CANDIDATE_RANK_SUMMARY_FILENAME = (
    "signalforge_asset_directional_candidate_rank_summary.json"
)
ASSET_DIRECTIONAL_CANDIDATE_RANK_CLI_SUMMARY_SCHEMA_VERSION = (
    "signalforge_asset_directional_candidate_rank_cli_summary.v1"
)


def write_asset_directional_candidate_rank_result(
    result: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    result_path = output_path / ASSET_DIRECTIONAL_CANDIDATE_RANK_RESULT_FILENAME
    summary_path = output_path / ASSET_DIRECTIONAL_CANDIDATE_RANK_SUMMARY_FILENAME

    result_path.write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    summary = build_asset_directional_candidate_rank_summary(
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


def build_asset_directional_candidate_rank_summary(
    *,
    result: Mapping[str, Any],
    result_path: Path,
    summary_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    return {
        "schema_version": ASSET_DIRECTIONAL_CANDIDATE_RANK_CLI_SUMMARY_SCHEMA_VERSION,
        "operation_type": "signalforge_asset_directional_candidate_rank_cli",
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
        "top_n": result.get("top_n"),
        "candidate_rank_summary": result.get("candidate_rank_summary"),
        "ranked_long_symbols": [
            item.get("symbol") for item in result.get("ranked_long_candidates") or []
        ],
        "ranked_short_symbols": [
            item.get("symbol") for item in result.get("ranked_short_candidates") or []
        ],
        "ranked_neutral_symbols": [
            item.get("symbol") for item in result.get("ranked_neutral_candidates") or []
        ],
        "ranked_neutral_position_symbols": [
            item.get("symbol")
            for item in result.get("ranked_neutral_position_candidates") or []
        ],
        "ranked_review_symbols": [
            item.get("symbol") for item in result.get("ranked_review_candidates") or []
        ],
        "ranked_conflict_symbols": [
            item.get("symbol") for item in result.get("ranked_conflict_candidates") or []
        ],
        "ranked_regime_unconfirmed_symbols": [
            item.get("symbol")
            for item in result.get("ranked_regime_unconfirmed_candidates") or []
        ],
        "ranked_behavior_led_symbols": [
            item.get("symbol") for item in result.get("ranked_behavior_led_candidates") or []
        ],
        "blocker_count": len(result.get("blocker_items") or []),
        "warning_count": len(result.get("warning_items") or []),
        "skipped_count": len(result.get("skipped_items") or []),
        "output_dir": str(output_dir),
        "files": {
            "asset_directional_candidate_rank_result": str(result_path),
            "summary": str(summary_path),
        },
        "file_summary": {
            "file_count": 2,
            "written_file_count": 2,
            "missing_files": [],
            "empty_files": [],
            "file_sizes": {
                "asset_directional_candidate_rank_result": (
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
