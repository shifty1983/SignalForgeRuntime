from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


ARTIFACT_TYPE = "signalforge_quantconnect_cloud_object_store_download"
SCHEMA_VERSION = "signalforge_quantconnect_cloud_object_store_download.v1"
CONTRACT = "quantconnect_cloud_object_store_download"

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
]


def execute_signalforge_quantconnect_cloud_object_store_download_only(
    backtest_execution_source: Mapping[str, Any] | None,
    *,
    client: Any,
    quantconnect_organization_id: str,
    output_dir: str | Path,
    batch_limit: int = 1,
    max_full_json_parse_bytes: int = 50_000_000,
) -> dict[str, Any]:
    blocked_reasons: list[str] = []

    if not isinstance(backtest_execution_source, Mapping):
        blocked_reasons.append("missing_backtest_execution_source")
        backtest_execution_source = {}

    if backtest_execution_source.get("artifact_type") != "signalforge_quantconnect_cloud_replay_backtest_execution":
        blocked_reasons.append("invalid_backtest_execution_artifact_type")

    if not str(quantconnect_organization_id or "").strip():
        blocked_reasons.append("missing_quantconnect_organization_id")

    batches = [
        batch for batch in backtest_execution_source.get("execution_batches", [])
        if isinstance(batch, Mapping)
    ]

    if not batches:
        blocked_reasons.append("missing_backtest_execution_batches")

    completed_batches = [
        batch for batch in batches
        if batch.get("backtest_completed") is True
        or batch.get("backtest_status") == "backtest_completed"
    ]

    if not completed_batches:
        blocked_reasons.append("missing_completed_backtest_batches")

    output_path = Path(output_dir)
    batch_root = output_path / "batches"
    batch_limit = max(int(batch_limit or 1), 1)
    selected_batches = completed_batches[:batch_limit]

    download_batches: list[dict[str, Any]] = []

    if not blocked_reasons:
        for batch in selected_batches:
            download_batches.append(
                _download_batch_object_store_files(
                    batch=batch,
                    client=client,
                    quantconnect_organization_id=str(quantconnect_organization_id),
                    batch_root=batch_root,
                    max_full_json_parse_bytes=max_full_json_parse_bytes,
                )
            )

    failed_batches = [
        batch["batch_id"]
        for batch in download_batches
        if batch.get("download_status") != "downloaded_and_locally_validated"
    ]

    if failed_batches:
        blocked_reasons.append("one_or_more_batches_failed_object_store_download_or_validation")

    downloaded_file_count = sum(batch.get("downloaded_file_count", 0) for batch in download_batches)
    expected_file_count = sum(batch.get("expected_result_file_count", 0) for batch in download_batches)

    is_ready = not blocked_reasons

    return {
        "adapter_type": "quantconnect_cloud_object_store_download_builder",
        "artifact_type": ARTIFACT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "contract": CONTRACT,
        "status": "ready" if is_ready else "blocked",
        "is_ready": is_ready,
        "mode": "download_object_store_only",
        "requires_manual_approval": True,
        "review_scope": "cloud_object_store_download_only_not_order_intent_or_execution",
        "blocked_reasons": list(dict.fromkeys(blocked_reasons)),
        "covered_capabilities": [
            "quantconnect_cloud_object_store_download",
            "quantconnect_cloud_result_file_download",
            "local_replay_result_file_validation",
            "download_only_no_object_store_delete",
        ],
        "depends_on_capabilities": [
            "quantconnect_cloud_api_client",
            "quantconnect_cloud_replay_backtest_execution",
            "quantconnect_replay_result_import_validator",
        ],
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
        "source_artifacts": {
            "backtest_execution_source": str(
                backtest_execution_source.get("artifact_type") or "provided_unknown_artifact"
            ),
        },
        "quantconnect_organization_id": str(quantconnect_organization_id),
        "output_dir": str(output_path),
        "batch_limit": batch_limit,
        "selected_batch_count": len(selected_batches),
        "downloaded_batch_count": len(download_batches),
        "failed_download_batch_count": len(failed_batches),
        "failed_download_batch_ids": failed_batches,
        "expected_result_file_count": expected_file_count,
        "downloaded_file_count": downloaded_file_count,
        "download_batches": download_batches,
        "object_store_download_summary": {
            "mode": "download_object_store_only",
            "selected_batch_count": len(selected_batches),
            "downloaded_batch_count": len(download_batches),
            "failed_download_batch_count": len(failed_batches),
            "expected_result_file_count": expected_file_count,
            "downloaded_file_count": downloaded_file_count,
            "stopped_before_object_store_delete": True,
            "local_validation_required_before_delete": True,
        },
        "next_build_recommendations": [
            {
                "capability": "quantconnect_cloud_guarded_object_store_delete",
                "priority": "high",
                "recommendation": "After downloaded files pass import validation, add guarded delete for the batch Object Store prefix.",
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


def _download_batch_object_store_files(
    *,
    batch: Mapping[str, Any],
    client: Any,
    quantconnect_organization_id: str,
    batch_root: Path,
    max_full_json_parse_bytes: int,
) -> dict[str, Any]:
    batch_id = str(batch.get("batch_id") or "unknown_batch")
    object_store_prefix = str(batch.get("object_store_prefix") or "").rstrip("/")
    local_batch_dir = batch_root / batch_id
    local_batch_dir.mkdir(parents=True, exist_ok=True)

    expected_files = list(EXPECTED_RESULT_FILES)
    object_store_keys = [f"{object_store_prefix}/{filename}" for filename in expected_files]

    list_response = client.list_object_store_files(
        organization_id=quantconnect_organization_id,
        path=object_store_prefix,
    )

    downloaded_files: list[dict[str, Any]] = []
    validation_results: list[dict[str, Any]] = []

    for filename, key in zip(expected_files, object_store_keys, strict=False):
        output_path = local_batch_dir / filename

        try:
            download_response = client.download_object_store_file(
                organization_id=quantconnect_organization_id,
                key=key,
                output_path=output_path,
            )

            validation = _validate_downloaded_json_file(
                output_path,
                max_full_json_parse_bytes=max_full_json_parse_bytes,
            )

        except Exception as exc:
            error_text = str(exc)
            download_response = {
                "success": False,
                "key": key,
                "output_path": str(output_path),
                "error": error_text,
            }

            validation_status = "download_failed"
            if "Institutional accounts" in error_text or "data licensing restrictions" in error_text:
                validation_status = "object_store_export_blocked_by_account_tier"

            validation = {
                "filename": filename,
                "local_path": str(output_path),
                "validation_status": validation_status,
                "file_size": 0,
                "full_json_parse_performed": False,
                "error": error_text,
            }

        downloaded_files.append(
            {
                "filename": filename,
                "object_store_key": key,
                "local_path": str(output_path),
                "download_response": download_response,
            }
        )
        validation_results.append(validation)

    invalid_files = [
        result["filename"]
        for result in validation_results
        if result.get("validation_status") != "valid"
    ]

    download_status = (
        "downloaded_and_locally_validated"
        if not invalid_files and len(downloaded_files) == len(expected_files)
        else "download_or_local_validation_failed"
    )

    manifest = {
        "batch_id": batch_id,
        "object_store_prefix": object_store_prefix,
        "expected_result_files": expected_files,
        "object_store_keys": object_store_keys,
        "downloaded_files": downloaded_files,
        "validation_results": validation_results,
        "invalid_files": invalid_files,
        "download_status": download_status,
        "object_store_deleted": False,
    }

    manifest_path = local_batch_dir / "object_store_download_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return {
        "batch_id": batch_id,
        "request_id": batch.get("request_id"),
        "backtest_id": batch.get("backtest_id"),
        "backtest_status": batch.get("backtest_status"),
        "object_store_prefix": object_store_prefix,
        "local_batch_dir": str(local_batch_dir),
        "download_manifest_path": str(manifest_path),
        "expected_result_files": expected_files,
        "expected_result_file_count": len(expected_files),
        "downloaded_file_count": len(downloaded_files),
        "invalid_file_count": len(invalid_files),
        "invalid_files": invalid_files,
        "download_status": download_status,
        "object_store_list_response": list_response,
        "downloaded_files": downloaded_files,
        "validation_results": validation_results,
        "object_store_downloaded": download_status == "downloaded_and_locally_validated",
        "object_store_deleted": False,
    }


def _validate_downloaded_json_file(
    path: Path,
    *,
    max_full_json_parse_bytes: int,
) -> dict[str, Any]:
    filename = path.name

    if not path.exists():
        return {
            "filename": filename,
            "local_path": str(path),
            "validation_status": "missing",
            "file_size": 0,
            "full_json_parse_performed": False,
        }

    file_size = path.stat().st_size

    if file_size <= 0:
        return {
            "filename": filename,
            "local_path": str(path),
            "validation_status": "empty",
            "file_size": file_size,
            "full_json_parse_performed": False,
        }

    if file_size <= max_full_json_parse_bytes:
        try:
            value = json.loads(path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as exc:
            return {
                "filename": filename,
                "local_path": str(path),
                "validation_status": "invalid_json",
                "file_size": file_size,
                "full_json_parse_performed": True,
                "error": str(exc),
            }

        return {
            "filename": filename,
            "local_path": str(path),
            "validation_status": "valid",
            "file_size": file_size,
            "full_json_parse_performed": True,
            "json_root_type": type(value).__name__,
        }

    boundary_status = _validate_large_json_boundaries(path)
    return {
        "filename": filename,
        "local_path": str(path),
        "validation_status": boundary_status,
        "file_size": file_size,
        "full_json_parse_performed": False,
        "large_file_parse_skipped": True,
    }


def _validate_large_json_boundaries(path: Path) -> str:
    with path.open("rb") as file:
        first_chunk = file.read(4096)
        if not first_chunk:
            return "empty"

        file.seek(max(path.stat().st_size - 4096, 0))
        last_chunk = file.read(4096)

    first = first_chunk.strip()[:1]
    last = last_chunk.strip()[-1:]

    if first in {b"{", b"["} and last in {b"}", b"]"}:
        return "valid"

    return "invalid_json_boundary"
