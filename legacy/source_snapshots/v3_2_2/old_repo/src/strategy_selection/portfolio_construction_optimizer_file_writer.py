from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


PORTFOLIO_CONSTRUCTION_OPTIMIZER_RESULT_FILENAME = "signalforge_portfolio_construction_optimizer.json"
PORTFOLIO_CONSTRUCTION_OPTIMIZER_SUMMARY_FILENAME = "signalforge_portfolio_construction_optimizer_summary.json"
PORTFOLIO_CONSTRUCTION_OPTIMIZER_CLI_SUMMARY_SCHEMA_VERSION = "signalforge_portfolio_construction_optimizer_cli_summary.v1"


def write_portfolio_construction_optimizer_result(
    result: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    result_path = output_path / PORTFOLIO_CONSTRUCTION_OPTIMIZER_RESULT_FILENAME
    summary_path = output_path / PORTFOLIO_CONSTRUCTION_OPTIMIZER_SUMMARY_FILENAME

    result_path.write_text(json.dumps(result, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")

    summary = build_portfolio_construction_optimizer_summary(
        result=result,
        result_path=result_path,
        summary_path=summary_path,
        output_dir=output_path,
    )

    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return summary


def build_portfolio_construction_optimizer_summary(
    *,
    result: Mapping[str, Any],
    result_path: Path,
    summary_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    optimizer_summary = result.get("portfolio_construction_optimizer_summary") or {}
    return {
        "schema_version": PORTFOLIO_CONSTRUCTION_OPTIMIZER_CLI_SUMMARY_SCHEMA_VERSION,
        "operation_type": "signalforge_portfolio_construction_optimizer_cli",
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
        "portfolio_construction_optimizer_summary": optimizer_summary,
        "symbol_count": optimizer_summary.get("symbol_count", 0),
        "source_optimizer_candidate_count": optimizer_summary.get("source_optimizer_candidate_count", 0),
        "portfolio_construction_candidate_count": optimizer_summary.get("portfolio_construction_candidate_count", 0),
        "portfolio_construction_symbol_count": optimizer_summary.get("portfolio_construction_symbol_count", 0),
        "ready_portfolio_construction_symbol_count": optimizer_summary.get("ready_portfolio_construction_symbol_count", 0),
        "constrained_portfolio_construction_symbol_count": optimizer_summary.get("constrained_portfolio_construction_symbol_count", 0),
        "data_review_symbol_count": optimizer_summary.get("data_review_symbol_count", 0),
        "blocked_symbol_count": optimizer_summary.get("blocked_symbol_count", 0),
        "needs_review_symbol_count": optimizer_summary.get("needs_review_symbol_count", 0),
        "manual_review_symbol_count": optimizer_summary.get("manual_review_symbol_count", 0),
        "existing_exposure_preview": optimizer_summary.get("existing_exposure_preview", {}),
        "optimized_exposure_preview": optimizer_summary.get("optimized_exposure_preview", {}),
        "thresholds": result.get("thresholds"),
        "output_dir": str(output_dir),
        "files": {
            "portfolio_construction_optimizer_result": str(result_path),
            "summary": str(summary_path),
        },
        "file_summary": {
            "file_count": 2,
            "written_file_count": 2,
            "missing_files": [],
            "empty_files": [],
            "file_sizes": {
                "portfolio_construction_optimizer_result": result_path.stat().st_size if result_path.exists() else 0,
                "summary": summary_path.stat().st_size if summary_path.exists() else 0,
            },
        },
        "portfolio_action": result.get("portfolio_action"),
        "position_size": result.get("position_size"),
        "order_intent": result.get("order_intent"),
        "broker_order_id": result.get("broker_order_id"),
        "automatic_action": result.get("automatic_action"),
        "automatic_strategy_change": result.get("automatic_strategy_change"),
        "automatic_parameter_change": result.get("automatic_parameter_change"),
        "automatic_pause_action": result.get("automatic_pause_action"),
        "explicit_exclusions": result.get("explicit_exclusions"),
    }
