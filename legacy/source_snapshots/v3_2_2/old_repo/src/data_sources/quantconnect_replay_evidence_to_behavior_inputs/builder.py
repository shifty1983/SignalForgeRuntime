from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


ARTIFACT_TYPE = "signalforge_quantconnect_replay_evidence_to_behavior_inputs"
SCHEMA_VERSION = "signalforge_quantconnect_replay_evidence_to_behavior_inputs.v1"

MARKET_FILE = "signalforge_qc_replay_market_price_behavior_input.json"
OPTION_JSONL_FILE = "signalforge_qc_replay_option_behavior_input.jsonl"
OPTION_MANIFEST_FILE = "signalforge_qc_replay_option_behavior_input_manifest.json"
CONTRACT_FILE = "signalforge_qc_replay_contract_outcome_evidence.json"
SUMMARY_FILE = "signalforge_quantconnect_replay_evidence_to_behavior_inputs_summary.json"

EXPECTED_INPUT_FILES = {
    "manifest": "signalforge_qc_replay_manifest.json",
    "market": "signalforge_qc_market_price_snapshots.json",
    "options": "signalforge_qc_filtered_option_rows.json",
    "contracts": "signalforge_qc_contract_outcome_snapshots.json",
}

WRAPPER_KEYS = {
    "market": "market_price_snapshots",
    "options": "filtered_option_rows",
    "contracts": "contract_outcome_snapshots",
}

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
]


def build_signalforge_quantconnect_replay_evidence_to_behavior_inputs(
    inventory_source: Mapping[str, Any] | None,
    *,
    output_dir: str | Path,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    blocked_reasons: list[str] = []
    warnings: list[dict[str, Any]] = []

    if not isinstance(inventory_source, Mapping):
        blocked_reasons.append("inventory_source_must_be_mapping")
        inventory_source = {}

    result_dirs = _extract_result_dirs(inventory_source)
    if not result_dirs:
        blocked_reasons.append("missing_inventory_result_dirs")

    market_rows: list[dict[str, Any]] = []
    contract_rows: list[dict[str, Any]] = []
    option_row_count = 0

    observed_symbols: set[str] = set()
    observed_option_underlyings: set[str] = set()
    observed_contract_symbols: set[str] = set()
    observed_request_ids: set[str] = set()

    market_path = output_path / MARKET_FILE
    option_jsonl_path = output_path / OPTION_JSONL_FILE
    option_manifest_path = output_path / OPTION_MANIFEST_FILE
    contract_path = output_path / CONTRACT_FILE
    summary_path = output_path / SUMMARY_FILE

    if option_jsonl_path.exists():
        option_jsonl_path.unlink()

    option_jsonl_file = option_jsonl_path.open("w", encoding="utf-8", newline="\n")

    try:
        for result_dir_text in result_dirs:
            result_dir = Path(str(result_dir_text))
            if not result_dir.exists():
                blocked_reasons.append("result_dir_does_not_exist")
                warnings.append({"reason": "result_dir_does_not_exist", "result_dir": str(result_dir)})
                continue

            manifest = _read_json(result_dir / EXPECTED_INPUT_FILES["manifest"])
            request_id = str(manifest.get("request_id") or "")
            if request_id:
                observed_request_ids.add(request_id)

            market_payload = _read_json(result_dir / EXPECTED_INPUT_FILES["market"])
            option_payload = _read_json(result_dir / EXPECTED_INPUT_FILES["options"])
            contract_payload = _read_json(result_dir / EXPECTED_INPUT_FILES["contracts"])

            batch_market_rows = _extract_rows(market_payload, WRAPPER_KEYS["market"])
            batch_option_rows = _extract_rows(option_payload, WRAPPER_KEYS["options"])
            batch_contract_rows = _extract_rows(contract_payload, WRAPPER_KEYS["contracts"])

            for row in batch_market_rows:
                enriched = _augment_row(row, result_dir=result_dir, request_id=request_id)
                symbol = _clean_symbol(enriched.get("symbol"))
                if symbol:
                    observed_symbols.add(symbol)
                market_rows.append(enriched)

            for row in batch_option_rows:
                enriched = _augment_row(row, result_dir=result_dir, request_id=request_id)
                underlying = _clean_symbol(
                    enriched.get("underlying_symbol")
                    or enriched.get("symbol")
                    or enriched.get("underlying")
                )
                if underlying:
                    observed_option_underlyings.add(underlying)
                option_jsonl_file.write(json.dumps(enriched, sort_keys=True, separators=(",", ":")) + "\n")
                option_row_count += 1

            for row in batch_contract_rows:
                enriched = _augment_row(row, result_dir=result_dir, request_id=request_id)
                symbol = _clean_symbol(enriched.get("symbol"))
                if symbol:
                    observed_contract_symbols.add(symbol)
                contract_rows.append(enriched)

    except FileNotFoundError as exc:
        blocked_reasons.append("missing_required_replay_file")
        warnings.append({"reason": "missing_required_replay_file", "error": str(exc)})
    except json.JSONDecodeError as exc:
        blocked_reasons.append("invalid_json_replay_file")
        warnings.append({"reason": "invalid_json_replay_file", "error": str(exc)})
    finally:
        option_jsonl_file.close()

    if not market_rows:
        blocked_reasons.append("no_market_price_rows_written")

    if option_row_count == 0:
        blocked_reasons.append("no_option_rows_written")

    if not contract_rows:
        warnings.append({"reason": "no_contract_outcome_rows_written"})

    status = "ready" if not blocked_reasons else "blocked"

    market_output = {
        "artifact_type": "signalforge_qc_replay_market_price_behavior_input",
        "schema_version": "signalforge_qc_replay_market_price_behavior_input.v1",
        "status": status,
        "is_ready": status == "ready",
        "source_artifact_type": inventory_source.get("artifact_type"),
        "source_inventory_status": inventory_source.get("status"),
        "row_count": len(market_rows),
        "price_rows": market_rows,
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }

    contract_output = {
        "artifact_type": "signalforge_qc_replay_contract_outcome_evidence",
        "schema_version": "signalforge_qc_replay_contract_outcome_evidence.v1",
        "status": status,
        "is_ready": status == "ready",
        "source_artifact_type": inventory_source.get("artifact_type"),
        "source_inventory_status": inventory_source.get("status"),
        "row_count": len(contract_rows),
        "matrix_metadata_enrichment_state": "pending_regime_asset_option_behavior_join",
        "contract_outcome_snapshots": contract_rows,
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }

    option_manifest = {
        "artifact_type": "signalforge_qc_replay_option_behavior_input_manifest",
        "schema_version": "signalforge_qc_replay_option_behavior_input_manifest.v1",
        "status": status,
        "is_ready": status == "ready",
        "source_artifact_type": inventory_source.get("artifact_type"),
        "source_inventory_status": inventory_source.get("status"),
        "file_format": "jsonl",
        "option_rows_path": str(option_jsonl_path),
        "row_count": option_row_count,
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }

    summary = {
        "artifact_type": ARTIFACT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "blocked_reasons": list(dict.fromkeys(blocked_reasons)),
        "warning_items": warnings,
        "source_artifact_type": inventory_source.get("artifact_type"),
        "source_inventory_status": inventory_source.get("status"),
        "source_inventory_is_ready": inventory_source.get("is_ready"),
        "result_dir_count": len(result_dirs),
        "market_price_row_count": len(market_rows),
        "option_row_count": option_row_count,
        "contract_outcome_row_count": len(contract_rows),
        "observed_symbol_count": len(observed_symbols),
        "observed_option_underlying_count": len(observed_option_underlyings),
        "observed_contract_symbol_count": len(observed_contract_symbols),
        "observed_request_id_count": len(observed_request_ids),
        "files": {
            "market_price_behavior_input": str(market_path),
            "option_behavior_input_jsonl": str(option_jsonl_path),
            "option_behavior_input_manifest": str(option_manifest_path),
            "contract_outcome_evidence": str(contract_path),
            "summary": str(summary_path),
        },
        "next_step": "run_market_price_behavior_then_historical_option_behavior",
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }

    market_path.write_text(
        json.dumps(market_output, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    contract_path.write_text(
        json.dumps(contract_output, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    option_manifest_path.write_text(
        json.dumps(option_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return summary


def _extract_result_dirs(inventory_source: Mapping[str, Any]) -> list[str]:
    rows = inventory_source.get("results") or inventory_source.get("batches") or []
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)):
        return []

    result_dirs: list[str] = []
    for row in rows:
        if isinstance(row, Mapping):
            value = row.get("result_dir") or row.get("decoded_result_dir") or row.get("source_dir")
            if value:
                result_dirs.append(str(value))

    return sorted(dict.fromkeys(result_dirs))


def _read_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(str(path))
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _extract_rows(payload: Any, key: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(item) for item in payload if isinstance(item, Mapping)]

    if isinstance(payload, Mapping):
        rows = payload.get(key)
        if isinstance(rows, list):
            return [dict(item) for item in rows if isinstance(item, Mapping)]

    return []


def _augment_row(row: Mapping[str, Any], *, result_dir: Path, request_id: str) -> dict[str, Any]:
    enriched = dict(row)
    enriched["source_result_dir"] = str(result_dir)
    if request_id:
        enriched["source_request_id"] = request_id
    return enriched


def _clean_symbol(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    return text or None
