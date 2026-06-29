from __future__ import annotations

import base64
import gzip
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


ARTIFACT_TYPE = "signalforge_quantconnect_backtest_result_transport_feasibility"
SCHEMA_VERSION = "signalforge_quantconnect_backtest_result_transport_feasibility.v1"
CONTRACT = "quantconnect_backtest_result_transport_feasibility"

EXPECTED_RESULT_FILES = [
    "signalforge_qc_replay_manifest.json",
    "signalforge_qc_market_price_snapshots.json",
    "signalforge_qc_filtered_option_rows.json",
    "signalforge_qc_contract_outcome_snapshots.json",
    "signalforge_qc_maintenance_trigger_snapshots.json",
    "signalforge_qc_portfolio_replay_snapshots.json",
]

EXPLICIT_EXCLUSIONS = [
    "broker_api_calls",
    "order_routing",
    "order_submission",
    "fills",
    "live_execution",
    "slippage_modeling",
    "automatic_close_orders",
    "automatic_roll_orders",
    "automatic_defense_orders",
    "automatic_strategy_changes",
    "automatic_parameter_changes",
    "automatic_pause_actions",
    "object_store_delete",
]


def evaluate_signalforge_backtest_result_transport_feasibility(
    *,
    replay_result_dir: str | Path,
    output_dir: str | Path,
    runtime_stat_chunk_size: int = 750,
    runtime_stat_chunk_budget: int = 250,
    chart_point_budget: int = 4000,
    chart_bytes_per_point_budget: int = 6,
) -> dict[str, Any]:
    blocked_reasons: list[str] = []

    replay_path = Path(replay_result_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    if not replay_path.exists():
        blocked_reasons.append("missing_replay_result_dir")

    files: dict[str, str] = {}
    file_summaries: dict[str, dict[str, Any]] = {}

    if not blocked_reasons:
        for filename in EXPECTED_RESULT_FILES:
            path = replay_path / filename

            if not path.exists():
                blocked_reasons.append(f"missing_result_file:{filename}")
                continue

            text = path.read_text(encoding="utf-8-sig")
            file_size = path.stat().st_size

            try:
                json.loads(text)
                json_valid = True
            except json.JSONDecodeError:
                json_valid = False
                blocked_reasons.append(f"invalid_json:{filename}")

            files[filename] = text
            file_summaries[filename] = {
                "path": str(path),
                "file_size": file_size,
                "char_count": len(text),
                "json_valid": json_valid,
            }

    raw_payload_json = ""
    compressed_bytes = b""
    encoded = ""

    if not blocked_reasons:
        raw_payload = {
            "artifact_type": "signalforge_quantconnect_backtest_result_transport_payload",
            "schema_version": "signalforge_quantconnect_backtest_result_transport_payload.v1",
            "expected_result_files": EXPECTED_RESULT_FILES,
            "file_summaries": file_summaries,
            "files": files,
            "object_store_delete_performed": False,
        }

        raw_payload_json = json.dumps(raw_payload, separators=(",", ":"), sort_keys=True)
        compressed_bytes = gzip.compress(raw_payload_json.encode("utf-8"))
        encoded = base64.b64encode(compressed_bytes).decode("ascii")

    raw_payload_bytes = len(raw_payload_json.encode("utf-8"))
    compressed_byte_count = len(compressed_bytes)
    encoded_char_count = len(encoded)

    runtime_stat_chunk_size = max(int(runtime_stat_chunk_size or 1), 1)
    runtime_stat_chunk_budget = max(int(runtime_stat_chunk_budget or 1), 1)
    chart_point_budget = max(int(chart_point_budget or 1), 1)
    chart_bytes_per_point_budget = max(int(chart_bytes_per_point_budget or 1), 1)

    runtime_stat_required_chunks = _ceil_div(encoded_char_count, runtime_stat_chunk_size)
    runtime_stat_capacity_chars = runtime_stat_chunk_size * runtime_stat_chunk_budget

    chart_estimated_byte_capacity = chart_point_budget * chart_bytes_per_point_budget
    chart_transport_feasible = compressed_byte_count <= chart_estimated_byte_capacity

    runtime_stat_transport_feasible = encoded_char_count <= runtime_stat_capacity_chars

    if blocked_reasons:
        transport_state = "blocked_invalid_replay_result_source"
    elif runtime_stat_transport_feasible:
        transport_state = "runtime_statistics_transport_feasible"
    elif chart_transport_feasible:
        transport_state = "chart_numeric_transport_feasible"
    else:
        transport_state = "backtest_result_transport_not_feasible_for_current_batch"

    payload_path = output_path / "signalforge_backtest_result_transport_payload.txt"
    if encoded:
        payload_path.write_text(encoded, encoding="utf-8")

    result = {
        "adapter_type": "quantconnect_backtest_result_transport_feasibility_builder",
        "artifact_type": ARTIFACT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "contract": CONTRACT,
        "status": "ready" if not blocked_reasons else "blocked",
        "is_ready": not blocked_reasons,
        "requires_manual_approval": True,
        "review_scope": "backtest_result_transport_feasibility_not_order_intent_or_execution",
        "blocked_reasons": list(dict.fromkeys(blocked_reasons)),
        "covered_capabilities": [
            "quantconnect_backtest_result_transport_feasibility",
            "compressed_six_file_payload_estimation",
            "runtime_statistics_transport_estimation",
            "chart_numeric_transport_estimation",
        ],
        "depends_on_capabilities": [
            "quantconnect_replay_result_import_validator",
            "quantconnect_cloud_replay_backtest_execution",
        ],
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
        "replay_result_dir": str(replay_path),
        "output_dir": str(output_path),
        "expected_result_files": EXPECTED_RESULT_FILES,
        "file_summaries": file_summaries,
        "raw_payload_bytes": raw_payload_bytes,
        "compressed_payload_bytes": compressed_byte_count,
        "encoded_payload_chars": encoded_char_count,
        "compression_ratio": _safe_ratio(compressed_byte_count, raw_payload_bytes),
        "runtime_stat_transport": {
            "chunk_size": runtime_stat_chunk_size,
            "chunk_budget": runtime_stat_chunk_budget,
            "required_chunks": runtime_stat_required_chunks,
            "capacity_chars": runtime_stat_capacity_chars,
            "feasible": runtime_stat_transport_feasible,
        },
        "chart_numeric_transport": {
            "chart_point_budget": chart_point_budget,
            "bytes_per_point_budget": chart_bytes_per_point_budget,
            "estimated_byte_capacity": chart_estimated_byte_capacity,
            "feasible": chart_transport_feasible,
        },
        "transport_state": transport_state,
        "payload_path": str(payload_path) if encoded else None,
        "object_store_delete_performed": False,
        "next_build_recommendations": _recommendations(transport_state),
        "order_intent": None,
        "broker_order_id": None,
        "portfolio_action": None,
        "position_size": None,
        "automatic_action": None,
        "automatic_close_order": None,
        "automatic_roll_order": None,
        "automatic_defense_order": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
    }

    result_path = output_path / "signalforge_quantconnect_backtest_result_transport_feasibility.json"
    summary_path = output_path / "signalforge_quantconnect_backtest_result_transport_feasibility_summary.json"

    result["files"] = {
        "feasibility_result": str(result_path),
        "summary": str(summary_path),
        "payload": str(payload_path) if encoded else None,
    }

    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    summary = {
        "operation_type": "signalforge_quantconnect_backtest_result_transport_feasibility_cli",
        "adapter_type": result["adapter_type"],
        "artifact_type": result["artifact_type"],
        "schema_version": "signalforge_quantconnect_backtest_result_transport_feasibility_cli_summary.v1",
        "contract": result["contract"],
        "status": result["status"],
        "is_ready": result["is_ready"],
        "requires_manual_approval": result["requires_manual_approval"],
        "review_scope": result["review_scope"],
        "blocked_reasons": result["blocked_reasons"],
        "covered_capabilities": result["covered_capabilities"],
        "depends_on_capabilities": result["depends_on_capabilities"],
        "explicit_exclusions": result["explicit_exclusions"],
        "replay_result_dir": result["replay_result_dir"],
        "output_dir": result["output_dir"],
        "raw_payload_bytes": result["raw_payload_bytes"],
        "compressed_payload_bytes": result["compressed_payload_bytes"],
        "encoded_payload_chars": result["encoded_payload_chars"],
        "compression_ratio": result["compression_ratio"],
        "runtime_stat_transport": result["runtime_stat_transport"],
        "chart_numeric_transport": result["chart_numeric_transport"],
        "transport_state": result["transport_state"],
        "files": result["files"],
        "object_store_delete_performed": False,
        "next_build_recommendations": result["next_build_recommendations"],
        "order_intent": None,
        "broker_order_id": None,
        "portfolio_action": None,
        "position_size": None,
        "automatic_action": None,
        "automatic_close_order": None,
        "automatic_roll_order": None,
        "automatic_defense_order": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
    }

    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def _ceil_div(numerator: int, denominator: int) -> int:
    if numerator <= 0:
        return 0
    return (numerator + denominator - 1) // denominator


def _safe_ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 6)


def _recommendations(transport_state: str) -> list[dict[str, Any]]:
    if transport_state == "runtime_statistics_transport_feasible":
        return [
            {
                "capability": "runtime_statistics_backtest_transport",
                "priority": "high",
                "recommendation": "Patch the compact replay script to emit compressed payload chunks through API-readable runtime statistics.",
            }
        ]

    if transport_state == "chart_numeric_transport_feasible":
        return [
            {
                "capability": "chart_numeric_backtest_transport",
                "priority": "medium",
                "recommendation": "Patch the compact replay script to emit compressed bytes through numeric chart series and decode from backtest read results.",
            }
        ]

    if transport_state == "backtest_result_transport_not_feasible_for_current_batch":
        return [
            {
                "capability": "reduce_batch_size_for_api_transport",
                "priority": "high",
                "recommendation": "Reduce scaleout batch size or payload scope, then rerun feasibility before falling back to the Research bridge.",
            },
            {
                "capability": "research_object_store_export_bridge",
                "priority": "medium",
                "recommendation": "Use the Research bridge only if API-readable backtest transport is too small for practical batches.",
            },
        ]

    return [
        {
            "capability": "fix_replay_result_source",
            "priority": "high",
            "recommendation": "Fix missing or invalid six-file replay result source before testing backtest result transport.",
        }
    ]
