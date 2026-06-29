from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


EXPECTED_VALUE_SCORING_RESULT_FILENAME = "signalforge_expected_value_scoring.json"
EXPECTED_VALUE_SCORING_SUMMARY_FILENAME = "signalforge_expected_value_scoring_summary.json"
EXPECTED_VALUE_SCORING_CLI_SUMMARY_SCHEMA_VERSION = "signalforge_expected_value_scoring_cli_summary.v1"


def write_expected_value_scoring_result(
    result: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    result_path = output_path / EXPECTED_VALUE_SCORING_RESULT_FILENAME
    summary_path = output_path / EXPECTED_VALUE_SCORING_SUMMARY_FILENAME

    result_path.write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    summary = build_expected_value_scoring_summary(
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


def build_expected_value_scoring_summary(
    *,
    result: Mapping[str, Any],
    result_path: Path,
    summary_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    expected_value_summary = result.get("expected_value_summary") or {}

    return {
        "schema_version": EXPECTED_VALUE_SCORING_CLI_SUMMARY_SCHEMA_VERSION,
        "operation_type": "signalforge_expected_value_scoring_cli",
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
        "expected_value_summary": expected_value_summary,
        "symbol_count": expected_value_summary.get("symbol_count", 0),
        "ready_symbol_count": expected_value_summary.get("ready_symbol_count", 0),
        "constrained_symbol_count": expected_value_summary.get("constrained_symbol_count", 0),
        "ev_scoreable_symbol_count": expected_value_summary.get("ev_scoreable_symbol_count", 0),
        "risk_adjusted_ev_symbol_count": expected_value_summary.get("risk_adjusted_ev_symbol_count", 0),
        "data_review_symbol_count": expected_value_summary.get("data_review_symbol_count", 0),
        "blocked_symbol_count": expected_value_summary.get("blocked_symbol_count", 0),
        "needs_review_symbol_count": expected_value_summary.get("needs_review_symbol_count", 0),
        "positive_or_marginal_symbol_count": expected_value_summary.get("positive_or_marginal_symbol_count", 0),
        "scored_candidate_count": expected_value_summary.get("scored_candidate_count", 0),
        "output_dir": str(output_dir),
        "files": {
            "expected_value_scoring_result": str(result_path),
            "summary": str(summary_path),
        },
        "file_summary": {
            "file_count": 2,
            "written_file_count": 2,
            "missing_files": [],
            "empty_files": [],
            "file_sizes": {
                "expected_value_scoring_result": (
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
