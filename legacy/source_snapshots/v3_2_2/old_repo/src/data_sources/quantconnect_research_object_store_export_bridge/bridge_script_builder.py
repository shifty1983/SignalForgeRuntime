from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


ARTIFACT_TYPE = "signalforge_quantconnect_research_object_store_export_bridge"
SCHEMA_VERSION = "signalforge_quantconnect_research_object_store_export_bridge.v1"
CONTRACT = "quantconnect_research_object_store_export_bridge"

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


def build_signalforge_quantconnect_research_object_store_export_bridge(
    batch_source: Mapping[str, Any] | None,
    *,
    output_dir: str | Path,
    batch_id: str | None = None,
    chunk_size: int = 30_000,
) -> dict[str, Any]:
    blocked_reasons: list[str] = []

    if not isinstance(batch_source, Mapping):
        blocked_reasons.append("missing_batch_source")
        batch_source = {}

    batches = _extract_batches(batch_source)
    if not batches:
        blocked_reasons.append("missing_export_batches")

    if batch_id:
        batches = [batch for batch in batches if str(batch.get("batch_id")) == batch_id]
        if not batches:
            blocked_reasons.append("requested_batch_id_not_found")

    output_path = Path(output_dir)
    script_dir = output_path / "research_scripts"
    script_dir.mkdir(parents=True, exist_ok=True)

    script_records: list[dict[str, Any]] = []

    if not blocked_reasons:
        for batch in batches:
            script_records.append(
                _write_research_export_script(
                    batch=batch,
                    script_dir=script_dir,
                    chunk_size=max(int(chunk_size or 1), 1),
                )
            )

    is_ready = not blocked_reasons

    result = {
        "adapter_type": "quantconnect_research_object_store_export_bridge_builder",
        "artifact_type": ARTIFACT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "contract": CONTRACT,
        "status": "ready" if is_ready else "blocked",
        "is_ready": is_ready,
        "requires_manual_approval": True,
        "review_scope": "research_object_store_export_bridge_not_order_intent_or_execution",
        "blocked_reasons": list(dict.fromkeys(blocked_reasons)),
        "covered_capabilities": [
            "quantconnect_research_object_store_export_bridge",
            "research_notebook_object_store_read",
            "chunked_manual_transfer_payload",
            "local_research_payload_decoder",
            "research_bridge_no_object_store_delete",
        ],
        "depends_on_capabilities": [
            "quantconnect_cloud_replay_backtest_execution",
            "quantconnect_historical_replay_scaleout_plan",
            "quantconnect_replay_result_import_validator",
        ],
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
        "source_artifacts": {
            "batch_source": str(batch_source.get("artifact_type") or "provided_unknown_artifact"),
        },
        "output_dir": str(output_path),
        "batch_id_filter": batch_id,
        "chunk_size": chunk_size,
        "script_count": len(script_records),
        "research_scripts": script_records,
        "bridge_summary": {
            "script_count": len(script_records),
            "manual_research_execution_required": True,
            "payload_transfer_modes": ["workspace_file", "stdout_chunks"],
            "object_store_delete_performed": False,
            "next_local_step": "decode_research_export_payload",
        },
        "next_build_recommendations": [
            {
                "capability": "decode_research_export_payload",
                "priority": "high",
                "recommendation": "Run the generated Research script, save the payload locally, and decode the six replay result files.",
            }
        ],
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

    output_path.mkdir(parents=True, exist_ok=True)
    result_path = output_path / "signalforge_quantconnect_research_object_store_export_bridge.json"
    summary_path = output_path / "signalforge_quantconnect_research_object_store_export_bridge_summary.json"

    result["files"] = {
        "research_object_store_export_bridge": str(result_path),
        "summary": str(summary_path),
        "research_scripts": {
            record["batch_id"]: record["research_script_path"] for record in script_records
        },
    }

    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    summary = {
        "operation_type": "signalforge_quantconnect_research_object_store_export_bridge_cli",
        "adapter_type": result["adapter_type"],
        "artifact_type": result["artifact_type"],
        "schema_version": "signalforge_quantconnect_research_object_store_export_bridge_cli_summary.v1",
        "contract": result["contract"],
        "status": result["status"],
        "is_ready": result["is_ready"],
        "requires_manual_approval": result["requires_manual_approval"],
        "review_scope": result["review_scope"],
        "blocked_reasons": result["blocked_reasons"],
        "covered_capabilities": result["covered_capabilities"],
        "depends_on_capabilities": result["depends_on_capabilities"],
        "explicit_exclusions": result["explicit_exclusions"],
        "source_artifacts": result["source_artifacts"],
        "output_dir": str(output_path),
        "files": result["files"],
        "script_count": result["script_count"],
        "chunk_size": result["chunk_size"],
        "bridge_summary": result["bridge_summary"],
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


def _write_research_export_script(
    *,
    batch: Mapping[str, Any],
    script_dir: Path,
    chunk_size: int,
) -> dict[str, Any]:
    batch_id = str(batch.get("batch_id") or "unknown_batch")
    object_store_prefix = str(batch.get("object_store_prefix") or "").rstrip("/")
    expected_files = _expected_result_files(batch)
    expected_keys = [f"{object_store_prefix}/{filename}" for filename in expected_files]

    config = {
        "batch_id": batch_id,
        "request_id": batch.get("request_id"),
        "backtest_id": batch.get("backtest_id"),
        "object_store_prefix": object_store_prefix,
        "expected_result_files": expected_files,
        "expected_object_store_keys": expected_keys,
        "chunk_size": chunk_size,
        "payload_filename": f"signalforge_research_export_{batch_id}.txt",
    }

    script_text = _research_script_text(config)
    script_path = script_dir / f"{batch_id}_research_object_store_export.py"
    script_path.write_text(script_text, encoding="utf-8")

    return {
        "batch_id": batch_id,
        "request_id": batch.get("request_id"),
        "backtest_id": batch.get("backtest_id"),
        "object_store_prefix": object_store_prefix,
        "expected_result_files": expected_files,
        "expected_object_store_keys": expected_keys,
        "research_script_path": str(script_path),
        "payload_filename": config["payload_filename"],
        "transfer_modes": ["workspace_file", "stdout_chunks"],
        "object_store_delete_performed": False,
    }


def _research_script_text(config: Mapping[str, Any]) -> str:
    config_json = json.dumps(dict(config), indent=2, sort_keys=True)

    return f'''# SignalForge QuantConnect Research Object Store Export Bridge
# Paste/run this script in a QuantConnect Research notebook.
# It reads the six batch Object Store JSON files, packages them into a compressed base64 payload,
# writes a local notebook workspace transfer file, and prints chunked fallback output.
# It does not delete Object Store data.

import base64
import gzip
import json
import sys
import traceback

CONFIG = {config_json}

MARKER_BEGIN = "SIGNALFORGE_RESEARCH_EXPORT_BEGIN"
MARKER_META = "SIGNALFORGE_RESEARCH_EXPORT_META"
MARKER_CHUNK = "SIGNALFORGE_RESEARCH_EXPORT_CHUNK"
MARKER_END = "SIGNALFORGE_RESEARCH_EXPORT_END"


def _get_object_store():
    try:
        from QuantConnect.Research import QuantBook
        qb = QuantBook()
        return qb.ObjectStore
    except Exception:
        pass

    try:
        return ObjectStore
    except Exception as exc:
        raise RuntimeError("Could not resolve QuantConnect ObjectStore in Research notebook.") from exc


def _read_object_store_text(object_store, key):
    errors = []

    for method_name in ["Read", "ReadString", "ReadJson"]:
        method = getattr(object_store, method_name, None)
        if callable(method):
            try:
                value = method(key)
                if isinstance(value, bytes):
                    return value.decode("utf-8-sig")
                if method_name == "ReadJson":
                    return json.dumps(value, separators=(",", ":"), sort_keys=True)
                if value is not None:
                    return str(value)
            except Exception as exc:
                errors.append(f"{{method_name}} failed for {{key}}: {{exc}}")

    read_bytes = getattr(object_store, "ReadBytes", None)
    if callable(read_bytes):
        try:
            value = read_bytes(key)
            if isinstance(value, bytes):
                return value.decode("utf-8-sig")
            if value is not None:
                return bytes(value).decode("utf-8-sig")
        except Exception as exc:
            errors.append(f"ReadBytes failed for {{key}}: {{exc}}")

    get_file_path = getattr(object_store, "GetFilePath", None)
    if callable(get_file_path):
        try:
            path = get_file_path(key)
            with open(path, "r", encoding="utf-8-sig") as file:
                return file.read()
        except Exception as exc:
            errors.append(f"GetFilePath failed for {{key}}: {{exc}}")

    raise RuntimeError("Unable to read Object Store key: " + key + " | " + " | ".join(errors))


def _main():
    object_store = _get_object_store()

    files = {{}}
    file_summaries = {{}}
    errors = []

    for filename in CONFIG["expected_result_files"]:
        key = CONFIG["object_store_prefix"].rstrip("/") + "/" + filename
        try:
            text = _read_object_store_text(object_store, key)
            json.loads(text)
            files[filename] = text
            file_summaries[filename] = {{
                "object_store_key": key,
                "char_count": len(text),
                "json_valid": True,
            }}
        except Exception as exc:
            errors.append({{
                "filename": filename,
                "object_store_key": key,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }})

    payload = {{
        "artifact_type": "signalforge_quantconnect_research_object_store_export_payload",
        "schema_version": "signalforge_quantconnect_research_object_store_export_payload.v1",
        "batch_id": CONFIG["batch_id"],
        "request_id": CONFIG.get("request_id"),
        "backtest_id": CONFIG.get("backtest_id"),
        "object_store_prefix": CONFIG["object_store_prefix"],
        "expected_result_files": CONFIG["expected_result_files"],
        "file_summaries": file_summaries,
        "files": files,
        "errors": errors,
        "object_store_delete_performed": False,
    }}

    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    compressed = gzip.compress(payload_json.encode("utf-8"))
    encoded = base64.b64encode(compressed).decode("ascii")

    transfer_text_lines = [
        f"{{MARKER_BEGIN}} {{CONFIG['batch_id']}}",
        f"{{MARKER_META}} " + json.dumps({{
            "batch_id": CONFIG["batch_id"],
            "request_id": CONFIG.get("request_id"),
            "backtest_id": CONFIG.get("backtest_id"),
            "object_store_prefix": CONFIG["object_store_prefix"],
            "encoded_char_count": len(encoded),
            "chunk_size": CONFIG["chunk_size"],
            "file_count": len(files),
            "error_count": len(errors),
            "object_store_delete_performed": False,
        }}, sort_keys=True),
    ]

    for index in range(0, len(encoded), CONFIG["chunk_size"]):
        chunk_number = (index // CONFIG["chunk_size"]) + 1
        transfer_text_lines.append(
            f"{{MARKER_CHUNK}} {{chunk_number:06d}} " + encoded[index:index + CONFIG["chunk_size"]]
        )

    transfer_text_lines.append(f"{{MARKER_END}} {{CONFIG['batch_id']}}")
    transfer_text = "\\n".join(transfer_text_lines) + "\\n"

    payload_filename = CONFIG["payload_filename"]
    with open(payload_filename, "w", encoding="utf-8") as file:
        file.write(transfer_text)

    print(f"SignalForge Research export written to workspace file: {{payload_filename}}")
    print(f"SignalForge Research export file_count={{len(files)}} error_count={{len(errors)}}")
    print("Copy the file contents or the chunked output below into a local payload .txt file.")
    print(transfer_text)

    if errors:
        print("SignalForge Research export completed with errors:", file=sys.stderr)
        print(json.dumps(errors, indent=2), file=sys.stderr)


_main()
'''


def _extract_batches(source: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    artifact_type = source.get("artifact_type")

    if artifact_type == "signalforge_quantconnect_cloud_replay_backtest_execution":
        batches = _sequence_of_mappings(source.get("execution_batches"))
        return [
            batch for batch in batches
            if batch.get("backtest_completed") is True
            or batch.get("backtest_status") == "backtest_completed"
        ]

    if artifact_type == "signalforge_quantconnect_historical_replay_scaleout_plan":
        return _sequence_of_mappings(source.get("batches"))

    batches = source.get("batches") or source.get("execution_batches")
    return _sequence_of_mappings(batches)


def _expected_result_files(batch: Mapping[str, Any]) -> list[str]:
    files = batch.get("expected_result_files")
    if isinstance(files, Sequence) and not isinstance(files, (str, bytes, bytearray)):
        values = [str(item) for item in files if str(item)]
        if values:
            return values
    return list(EXPECTED_RESULT_FILES)


def _sequence_of_mappings(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [item for item in value if isinstance(item, Mapping)]
    return []
