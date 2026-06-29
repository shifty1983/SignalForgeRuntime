from __future__ import annotations

import base64
import gzip
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


ARTIFACT_TYPE = "signalforge_quantconnect_research_object_store_export_decode"
SCHEMA_VERSION = "signalforge_quantconnect_research_object_store_export_decode.v1"
CONTRACT = "quantconnect_research_object_store_export_decode"

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


def decode_signalforge_research_object_store_export_payload(
    *,
    payload_source: str | Path,
    output_dir: str | Path,
    expected_result_files: list[str] | None = None,
) -> dict[str, Any]:
    blocked_reasons: list[str] = []

    payload_path = Path(payload_source)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    expected_files = expected_result_files or list(EXPECTED_RESULT_FILES)

    if not payload_path.exists():
        blocked_reasons.append("missing_payload_source")
        payload_text = ""
    else:
        payload_text = payload_path.read_text(encoding="utf-8-sig")

    payload: dict[str, Any] = {}

    if not blocked_reasons:
        try:
            encoded = _extract_encoded_payload(payload_text)
            payload = _decode_payload(encoded)
        except Exception as exc:
            blocked_reasons.append("payload_decode_failed")
            payload = {
                "decode_error": str(exc),
            }

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
            text = str(files.get(filename) or "")
            file_path = output_path / filename
            file_path.write_text(text, encoding="utf-8")
            written_files[filename] = str(file_path)
            validation_results.append(_validate_json_file(file_path))

    invalid_files = [
        result["filename"]
        for result in validation_results
        if result.get("validation_status") != "valid"
    ]

    if invalid_files and not blocked_reasons:
        blocked_reasons.append("decoded_file_validation_failed")

    decode_manifest_path = output_path / "research_export_decode_manifest.json"
    is_ready = not blocked_reasons

    result = {
        "adapter_type": "quantconnect_research_object_store_export_decode_builder",
        "artifact_type": ARTIFACT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "contract": CONTRACT,
        "status": "ready" if is_ready else "blocked",
        "is_ready": is_ready,
        "requires_manual_approval": True,
        "review_scope": "research_object_store_export_decode_not_order_intent_or_execution",
        "blocked_reasons": list(dict.fromkeys(blocked_reasons)),
        "covered_capabilities": [
            "quantconnect_research_object_store_export_decode",
            "local_research_payload_decode",
            "six_file_replay_result_reconstruction",
            "decoded_replay_result_validation",
            "research_bridge_no_object_store_delete",
        ],
        "depends_on_capabilities": [
            "quantconnect_research_object_store_export_bridge",
            "quantconnect_cloud_replay_backtest_execution",
            "quantconnect_replay_result_import_validator",
        ],
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
        "payload_source": str(payload_path),
        "output_dir": str(output_path),
        "batch_id": payload.get("batch_id"),
        "request_id": payload.get("request_id"),
        "backtest_id": payload.get("backtest_id"),
        "object_store_prefix": payload.get("object_store_prefix"),
        "expected_result_files": expected_files,
        "expected_result_file_count": len(expected_files),
        "decoded_file_count": len(written_files),
        "missing_files": missing_files,
        "invalid_files": invalid_files,
        "written_files": written_files,
        "validation_results": validation_results,
        "decode_manifest_path": str(decode_manifest_path),
        "object_store_delete_performed": False,
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

    decode_manifest_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def _extract_encoded_payload(text: str) -> str:
    chunks: list[tuple[int, str]] = []

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        if line.startswith("SIGNALFORGE_RESEARCH_EXPORT_CHUNK "):
            parts = line.split(" ", 2)
            if len(parts) != 3:
                raise ValueError(f"Invalid chunk line: {line[:100]}")
            chunks.append((int(parts[1]), parts[2].strip()))

    if chunks:
        chunks.sort(key=lambda item: item[0])
        return "".join(chunk for _, chunk in chunks)

    compact = "".join(line.strip() for line in text.splitlines() if line.strip())
    if compact:
        return compact

    raise ValueError("No payload chunks or base64 payload text found.")


def _decode_payload(encoded: str) -> dict[str, Any]:
    raw = base64.b64decode(encoded)
    decoded = gzip.decompress(raw).decode("utf-8")
    value = json.loads(decoded)

    if not isinstance(value, dict):
        raise ValueError("Decoded payload root is not a JSON object.")

    if value.get("artifact_type") != "signalforge_quantconnect_research_object_store_export_payload":
        raise ValueError("Decoded payload artifact_type is not a research Object Store export payload.")

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
