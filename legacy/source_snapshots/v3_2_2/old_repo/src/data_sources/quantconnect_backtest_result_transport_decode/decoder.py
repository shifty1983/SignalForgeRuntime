from __future__ import annotations

import base64
import gzip
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


ARTIFACT_TYPE = "signalforge_quantconnect_backtest_result_transport_decode"
SCHEMA_VERSION = "signalforge_quantconnect_backtest_result_transport_decode.v1"
CONTRACT = "quantconnect_backtest_result_transport_decode"

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


def decode_signalforge_backtest_result_transport(
    *,
    backtest_read_source: Mapping[str, Any] | None,
    output_dir: str | Path,
    expected_result_files: list[str] | None = None,
) -> dict[str, Any]:
    blocked_reasons: list[str] = []
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    expected_files = expected_result_files or list(EXPECTED_RESULT_FILES)

    if not isinstance(backtest_read_source, Mapping):
        blocked_reasons.append("missing_backtest_read_source")
        backtest_read_source = {}

    runtime_stats = _extract_runtime_statistics(backtest_read_source)

    if not runtime_stats:
        blocked_reasons.append("missing_runtime_statistics")

    transport_state = str(runtime_stats.get("SignalForgeTransportState") or "")

    if transport_state != "ready" and not blocked_reasons:
        blocked_reasons.append(f"runtime_transport_not_ready:{transport_state or 'missing'}")

    encoded = ""
    payload: dict[str, Any] = {}

    if not blocked_reasons:
        try:
            chunk_count = int(runtime_stats.get("SignalForgeTransportChunkCount") or 0)
            if chunk_count <= 0:
                raise ValueError("SignalForgeTransportChunkCount is missing or zero.")

            chunks = []
            for index in range(1, chunk_count + 1):
                key = "SignalForgeTransportChunk" + str(index).zfill(6)
                chunk = runtime_stats.get(key)
                if chunk is None:
                    raise ValueError(f"Missing runtime transport chunk: {key}")
                chunks.append(str(chunk))

            encoded = "".join(chunks)
            payload = _decode_transport_payload(encoded)

        except Exception as exc:
            blocked_reasons.append("runtime_transport_decode_failed")
            payload = {"decode_error": str(exc)}

    files = payload.get("files", {}) if isinstance(payload, Mapping) else {}
    if not isinstance(files, Mapping):
        files = {}

    missing_files = [filename for filename in expected_files if filename not in files]
    if missing_files and not blocked_reasons:
        blocked_reasons.append("decoded_payload_missing_expected_files")

    written_files: dict[str, str] = {}
    validation_results: list[dict[str, Any]] = []

    if not blocked_reasons:
        for filename in expected_files:
            file_path = output_path / filename
            file_path.write_text(str(files.get(filename) or ""), encoding="utf-8")
            written_files[filename] = str(file_path)
            validation_results.append(_validate_json_file(file_path))

    invalid_files = [
        result["filename"]
        for result in validation_results
        if result.get("validation_status") != "valid"
    ]

    if invalid_files and not blocked_reasons:
        blocked_reasons.append("decoded_file_validation_failed")

    manifest_path = output_path / "backtest_result_transport_decode_manifest.json"
    is_ready = not blocked_reasons

    result = {
        "adapter_type": "quantconnect_backtest_result_transport_decode_builder",
        "artifact_type": ARTIFACT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "contract": CONTRACT,
        "status": "ready" if is_ready else "blocked",
        "is_ready": is_ready,
        "requires_manual_approval": True,
        "review_scope": "backtest_result_transport_decode_not_order_intent_or_execution",
        "blocked_reasons": list(dict.fromkeys(blocked_reasons)),
        "covered_capabilities": [
            "quantconnect_backtest_result_transport_decode",
            "runtime_statistics_transport_decode",
            "six_file_replay_result_reconstruction",
            "decoded_replay_result_validation",
            "transport_decode_no_object_store_delete",
        ],
        "depends_on_capabilities": [
            "quantconnect_cloud_replay_backtest_execution",
            "quantconnect_backtest_result_transport_feasibility",
            "quantconnect_replay_result_import_validator",
        ],
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
        "output_dir": str(output_path),
        "transport_state": transport_state,
        "runtime_stat_key_count": len(runtime_stats),
        "encoded_payload_chars": len(encoded),
        "expected_result_files": expected_files,
        "expected_result_file_count": len(expected_files),
        "decoded_file_count": len(written_files),
        "missing_files": missing_files,
        "invalid_files": invalid_files,
        "written_files": written_files,
        "validation_results": validation_results,
        "batch_request_id": payload.get("request_id"),
        "object_store_prefix": payload.get("object_store_prefix"),
        "object_store_delete_performed": False,
        "decode_manifest_path": str(manifest_path),
        "decode_summary": {
            "decoded_file_count": len(written_files),
            "expected_result_file_count": len(expected_files),
            "missing_file_count": len(missing_files),
            "invalid_file_count": len(invalid_files),
            "object_store_delete_performed": False,
            "next_step": "quantconnect_replay_result_import_validator",
        },
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

    manifest_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def _extract_runtime_statistics(source: Mapping[str, Any]) -> dict[str, Any]:
    candidates = [
        source.get("runtimeStatistics"),
        source.get("runtime_statistics"),
        source.get("RuntimeStatistics"),
        source.get("statistics"),
    ]

    backtest = source.get("backtest")
    if isinstance(backtest, Mapping):
        candidates.extend(
            [
                backtest.get("runtimeStatistics"),
                backtest.get("runtime_statistics"),
                backtest.get("RuntimeStatistics"),
                backtest.get("statistics"),
            ]
        )

    result = source.get("result")
    if isinstance(result, Mapping):
        candidates.extend(
            [
                result.get("runtimeStatistics"),
                result.get("runtime_statistics"),
                result.get("RuntimeStatistics"),
                result.get("statistics"),
            ]
        )

    for candidate in candidates:
        if isinstance(candidate, Mapping) and any(
            str(key).startswith("SignalForgeTransport") for key in candidate.keys()
        ):
            return {str(key): value for key, value in candidate.items()}

    return {}


def _decode_transport_payload(encoded: str) -> dict[str, Any]:
    raw = base64.b64decode(encoded)
    decoded = gzip.decompress(raw).decode("utf-8")
    value = json.loads(decoded)

    if not isinstance(value, dict):
        raise ValueError("Decoded payload root is not a JSON object.")

    if value.get("artifact_type") != "signalforge_quantconnect_backtest_result_transport_payload":
        raise ValueError("Decoded payload artifact_type is not a backtest result transport payload.")

    return value


def _validate_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "filename": path.name,
            "local_path": str(path),
            "validation_status": "missing",
            "file_size": 0,
        }

    file_size = path.stat().st_size

    if file_size <= 0:
        return {
            "filename": path.name,
            "local_path": str(path),
            "validation_status": "empty",
            "file_size": file_size,
        }

    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        return {
            "filename": path.name,
            "local_path": str(path),
            "validation_status": "invalid_json",
            "file_size": file_size,
            "error": str(exc),
        }

    return {
        "filename": path.name,
        "local_path": str(path),
        "validation_status": "valid",
        "file_size": file_size,
        "json_root_type": type(value).__name__,
    }
