from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


RESULT_FILENAME = "signalforge_historical_edge_risk_overlay.json"
SUMMARY_FILENAME = "signalforge_historical_edge_risk_overlay_summary.json"


def write_signalforge_historical_edge_risk_overlay_result(
    result: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    result_path = output_path / RESULT_FILENAME
    summary_path = output_path / SUMMARY_FILENAME

    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    summary = _summary_payload(result, output_path, result_path, summary_path)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return summary


def _summary_payload(
    result: Mapping[str, Any],
    output_dir: Path,
    result_path: Path,
    summary_path: Path,
) -> dict[str, Any]:
    risk_overlay_summary = result.get("risk_overlay_summary", {})
    if not isinstance(risk_overlay_summary, Mapping):
        risk_overlay_summary = {}

    return {
        "operation_type": "signalforge_historical_edge_risk_overlay_cli",
        "adapter_type": result.get("adapter_type"),
        "artifact_type": result.get("artifact_type"),
        "schema_version": "signalforge_historical_edge_risk_overlay_cli_summary.v1",
        "contract": result.get("contract"),
        "status": result.get("status"),
        "is_ready": result.get("is_ready"),
        "requires_manual_approval": result.get("requires_manual_approval"),
        "review_scope": result.get("review_scope"),
        "blocked_reasons": list(result.get("blocked_reasons", [])),
        "covered_capabilities": list(result.get("covered_capabilities", [])),
        "depends_on_capabilities": list(result.get("depends_on_capabilities", [])),
        "explicit_exclusions": list(result.get("explicit_exclusions", [])),
        "source_artifacts": dict(result.get("source_artifacts", {})),
        "output_dir": str(output_dir),
        "files": {
            "historical_edge_risk_overlay_result": str(result_path),
            "summary": str(summary_path),
        },
        "file_summary": {
            "file_count": 2,
            "written_file_count": 2,
            "missing_files": [],
            "empty_files": [],
            "file_sizes": {
                "historical_edge_risk_overlay_result": result_path.stat().st_size if result_path.exists() else 0,
                "summary": summary_path.stat().st_size if summary_path.exists() else 0,
            },
        },
        "request_id": result.get("request_id"),
        "replay_start": result.get("replay_start"),
        "replay_end": result.get("replay_end"),
        "symbol_count": result.get("symbol_count"),
        "replay_candidate_count": result.get("replay_candidate_count"),
        "risk_overlay_state": result.get("risk_overlay_state"),
        "risk_overlay_review_status": result.get("risk_overlay_review_status"),
        "risk_adjusted_edge_score": result.get("risk_adjusted_edge_score"),
        "risk_overlay_flags": list(result.get("risk_overlay_flags", [])),
        "live_readiness_state": result.get("live_readiness_state"),
        "historical_edge_state": result.get("historical_edge_state"),
        "historical_edge_score": result.get("historical_edge_score"),
        "average_strategy_adjusted_return": result.get("average_strategy_adjusted_return"),
        "strategy_adjusted_win_rate": result.get("strategy_adjusted_win_rate"),
        "average_strategy_adjusted_max_adverse_excursion": result.get(
            "average_strategy_adjusted_max_adverse_excursion"
        ),
        "maintenance_trigger_rate": result.get("maintenance_trigger_rate"),
        "risk_overlay_summary": dict(risk_overlay_summary),
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
