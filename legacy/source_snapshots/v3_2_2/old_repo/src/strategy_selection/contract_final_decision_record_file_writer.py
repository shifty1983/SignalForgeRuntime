from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


CONTRACT_FINAL_DECISION_RECORD_RESULT_FILENAME = "signalforge_contract_final_decision_record.json"
CONTRACT_FINAL_DECISION_RECORD_SUMMARY_FILENAME = "signalforge_contract_final_decision_record_summary.json"
CONTRACT_FINAL_DECISION_RECORD_CLI_SUMMARY_SCHEMA_VERSION = "signalforge_contract_final_decision_record_cli_summary.v1"


def write_contract_final_decision_record_result(
    result: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    result_path = output_path / CONTRACT_FINAL_DECISION_RECORD_RESULT_FILENAME
    summary_path = output_path / CONTRACT_FINAL_DECISION_RECORD_SUMMARY_FILENAME

    result_path.write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    summary = build_contract_final_decision_record_summary(
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


def build_contract_final_decision_record_summary(
    *,
    result: Mapping[str, Any],
    result_path: Path,
    summary_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    decision_summary = result.get("contract_final_decision_record_summary") or {}

    return {
        "schema_version": CONTRACT_FINAL_DECISION_RECORD_CLI_SUMMARY_SCHEMA_VERSION,
        "operation_type": "signalforge_contract_final_decision_record_cli",
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
        "contract_final_decision_record_summary": decision_summary,
        "symbol_count": decision_summary.get("symbol_count", 0),
        "source_contract_final_review_symbol_count": decision_summary.get("source_contract_final_review_symbol_count", 0),
        "source_contract_final_review_queue_count": decision_summary.get("source_contract_final_review_queue_count", 0),
        "source_ranked_contract_final_review_count": decision_summary.get("source_ranked_contract_final_review_count", 0),
        "contract_final_decision_count": decision_summary.get("contract_final_decision_count", 0),
        "contract_final_decision_symbol_count": decision_summary.get("contract_final_decision_symbol_count", 0),
        "explicit_contract_final_decision_count": decision_summary.get("explicit_contract_final_decision_count", 0),
        "approved_contract_final_decision_count": decision_summary.get("approved_contract_final_decision_count", 0),
        "rejected_contract_final_decision_count": decision_summary.get("rejected_contract_final_decision_count", 0),
        "deferred_contract_final_decision_count": decision_summary.get("deferred_contract_final_decision_count", 0),
        "pending_contract_final_decision_count": decision_summary.get("pending_contract_final_decision_count", 0),
        "invalid_contract_final_decision_count": decision_summary.get("invalid_contract_final_decision_count", 0),
        "approved_contract_final_decision_symbol_count": decision_summary.get("approved_contract_final_decision_symbol_count", 0),
        "rejected_contract_final_decision_symbol_count": decision_summary.get("rejected_contract_final_decision_symbol_count", 0),
        "deferred_contract_final_decision_symbol_count": decision_summary.get("deferred_contract_final_decision_symbol_count", 0),
        "pending_contract_final_decision_symbol_count": decision_summary.get("pending_contract_final_decision_symbol_count", 0),
        "invalid_contract_final_decision_symbol_count": decision_summary.get("invalid_contract_final_decision_symbol_count", 0),
        "data_review_symbol_count": decision_summary.get("data_review_symbol_count", 0),
        "blocked_symbol_count": decision_summary.get("blocked_symbol_count", 0),
        "needs_review_symbol_count": decision_summary.get("needs_review_symbol_count", 0),
        "manual_review_symbol_count": decision_summary.get("manual_review_symbol_count", 0),
        "option_row_count": decision_summary.get("option_row_count", 0),
        "output_dir": str(output_dir),
        "files": {
            "contract_final_decision_record_result": str(result_path),
            "summary": str(summary_path),
        },
        "file_summary": {
            "file_count": 2,
            "written_file_count": 2,
            "missing_files": [],
            "empty_files": [],
            "file_sizes": {
                "contract_final_decision_record_result": result_path.stat().st_size if result_path.exists() else 0,
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
