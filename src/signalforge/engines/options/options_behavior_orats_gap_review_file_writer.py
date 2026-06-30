from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


OPTIONS_BEHAVIOR_ORATS_GAP_REVIEW_RESULT_FILENAME = (
    "signalforge_options_behavior_orats_gap_review.json"
)
OPTIONS_BEHAVIOR_ORATS_GAP_REVIEW_SUMMARY_FILENAME = (
    "signalforge_options_behavior_orats_gap_review_summary.json"
)
OPTIONS_BEHAVIOR_ORATS_GAP_REVIEW_CLI_SUMMARY_SCHEMA_VERSION = (
    "signalforge_options_behavior_orats_gap_review_cli_summary.v1"
)


def write_options_behavior_orats_gap_review_result(
    result: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    result_path = output_path / OPTIONS_BEHAVIOR_ORATS_GAP_REVIEW_RESULT_FILENAME
    summary_path = output_path / OPTIONS_BEHAVIOR_ORATS_GAP_REVIEW_SUMMARY_FILENAME

    result_path.write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    summary = build_options_behavior_orats_gap_review_summary(
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


def build_options_behavior_orats_gap_review_summary(
    *,
    result: Mapping[str, Any],
    result_path: Path,
    summary_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    gap_summary = result.get("orats_gap_review_summary") or {}

    return {
        "schema_version": OPTIONS_BEHAVIOR_ORATS_GAP_REVIEW_CLI_SUMMARY_SCHEMA_VERSION,
        "operation_type": "signalforge_options_behavior_orats_gap_review_cli",
        "artifact_type": result.get("artifact_type"),
        "contract": result.get("contract"),
        "adapter_type": result.get("adapter_type"),
        "status": result.get("status"),
        "is_ready": result.get("is_ready"),
        "requires_manual_approval": result.get("requires_manual_approval"),
        "benchmark_vendor": result.get("benchmark_vendor"),
        "benchmark_use": result.get("benchmark_use"),
        "review_scope": result.get("review_scope"),
        "etf_first": result.get("etf_first"),
        "orats_gap_review_summary": gap_summary,
        "covered_capabilities": gap_summary.get("covered_capabilities", []),
        "partial_capabilities": gap_summary.get("partial_capabilities", []),
        "gap_capabilities": gap_summary.get("gap_capabilities", []),
        "deferred_capabilities": gap_summary.get("deferred_capabilities", []),
        "vendor_enhancement_capabilities": gap_summary.get(
            "vendor_enhancement_capabilities",
            [],
        ),
        "next_build_recommendation_count": len(
            result.get("next_build_recommendations") or []
        ),
        "next_build_recommendations": result.get("next_build_recommendations"),
        "output_dir": str(output_dir),
        "files": {
            "options_behavior_orats_gap_review_result": str(result_path),
            "summary": str(summary_path),
        },
        "file_summary": {
            "file_count": 2,
            "written_file_count": 2,
            "missing_files": [],
            "empty_files": [],
            "file_sizes": {
                "options_behavior_orats_gap_review_result": (
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

