from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from src.strategy_selection.historical_replay_matrix_metadata_stamp import (
    MATRIX_CELL_KEY_KEY,
    MATRIX_METADATA_KEY,
    MATRIX_METADATA_MISSING_FIELDS_KEY,
    MATRIX_METADATA_STATE_KEY,
    REQUIRED_MATRIX_METADATA_FIELDS,
    extract_candidate_matrix_metadata,
    matrix_metadata_coverage,
    normalize_horizon_days,
    stamp_matrix_metadata,
)


ARTIFACT_TYPE = "signalforge_quantconnect_cloud_replay_batch_runner_plan"
SCHEMA_VERSION = "signalforge_quantconnect_cloud_replay_batch_runner_plan.v2"
CONTRACT = "quantconnect_cloud_replay_batch_runner"

EXPECTED_RESULT_FILES = [
    "signalforge_qc_replay_manifest.json",
    "signalforge_qc_market_price_snapshots.json",
    "signalforge_qc_filtered_option_rows.json",
    "signalforge_qc_contract_outcome_snapshots.json",
    "signalforge_qc_maintenance_trigger_snapshots.json",
    "signalforge_qc_portfolio_replay_snapshots.json",
]

COVERED_CAPABILITIES = [
    "quantconnect_cloud_replay_batch_runner",
    "quantconnect_cloud_api_dry_run_operation_plan",
    "object_store_download_then_delete_batch_lifecycle",
    "cloud_replay_batch_runner_not_order_intent_or_execution",
]

DEPENDS_ON_CAPABILITIES = [
    "quantconnect_cloud_api_client",
    "quantconnect_historical_replay_scaleout_plan",
    "quantconnect_compact_replay_script",
    "quantconnect_replay_result_import_validator",
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

MATRIX_METADATA_PATCH_CAPABILITIES = [
    "quantconnect_cloud_replay_batch_runner_matrix_metadata_preservation",
    "quantconnect_cloud_replay_batch_runner_matrix_metadata_operation_context",
    "matrix_metadata_no_regime_asset_option_strategy_inference",
]


def build_signalforge_quantconnect_cloud_replay_batch_runner_plan(
    scaleout_plan_source: Mapping[str, Any] | None,
    *,
    quantconnect_project_id: str,
    quantconnect_organization_id: str,
    output_dir: str | Path,
    mode: str = "dry_run",
    quantconnect_project_file_name: str = "main.py",
    local_batch_output_root: str | Path | None = None,
    delete_object_store_after_local_validation: bool = False,
) -> dict[str, Any]:
    blocked_reasons: list[str] = []
    warnings: list[str] = []

    if mode != "dry_run":
        blocked_reasons.append("execute_mode_not_enabled_yet")

    if not isinstance(scaleout_plan_source, Mapping):
        blocked_reasons.append("missing_scaleout_plan_source")
        scaleout_plan_source = {}

    if scaleout_plan_source.get("artifact_type") != "signalforge_quantconnect_historical_replay_scaleout_plan":
        blocked_reasons.append("invalid_scaleout_plan_artifact_type")

    if not str(quantconnect_project_id or "").strip():
        blocked_reasons.append("missing_quantconnect_project_id")

    if not str(quantconnect_organization_id or "").strip():
        blocked_reasons.append("missing_quantconnect_organization_id")

    batches = _sequence_of_mappings(scaleout_plan_source.get("batches"))
    if not batches:
        blocked_reasons.append("missing_scaleout_batches")

    output_path = Path(output_dir)
    batch_root = Path(local_batch_output_root) if local_batch_output_root else output_path / "batches"

    batch_plans = [
        _batch_operation_plan(
            batch=batch,
            quantconnect_project_id=str(quantconnect_project_id),
            quantconnect_organization_id=str(quantconnect_organization_id),
            quantconnect_project_file_name=quantconnect_project_file_name,
            local_batch_output_root=batch_root,
            delete_object_store_after_local_validation=delete_object_store_after_local_validation,
        )
        for batch in batches
    ]

    operation_count = sum(len(batch.get("operations", [])) for batch in batch_plans)
    api_operation_count = sum(
        len([op for op in batch.get("operations", []) if op.get("operation_kind") == "quantconnect_cloud_api"])
        for batch in batch_plans
    )
    matrix_metadata_batch_summary = _runner_matrix_metadata_summary(batch_plans)
    if batch_plans and matrix_metadata_batch_summary.get("needs_review_candidate_count", 0) > 0:
        warnings.append("cloud_replay_batch_runner_candidates_require_matrix_metadata_backfill")

    is_ready = not blocked_reasons

    return {
        "adapter_type": "quantconnect_cloud_replay_batch_runner_plan_builder",
        "artifact_type": ARTIFACT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "contract": CONTRACT,
        "status": "ready" if is_ready else "blocked",
        "is_ready": is_ready,
        "mode": mode,
        "requires_manual_approval": True,
        "review_scope": "cloud_replay_batch_runner_not_order_intent_or_execution",
        "blocked_reasons": list(dict.fromkeys(blocked_reasons)),
        "warnings": list(dict.fromkeys(warnings)),
        "covered_capabilities": [*COVERED_CAPABILITIES, *MATRIX_METADATA_PATCH_CAPABILITIES],
        "depends_on_capabilities": [
            *DEPENDS_ON_CAPABILITIES,
            "historical_replay_matrix_metadata_stamping_helpers",
        ],
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
        "source_artifacts": {
            "scaleout_plan_source": _source_artifact_type(scaleout_plan_source),
        },
        "quantconnect_project_id": str(quantconnect_project_id),
        "quantconnect_organization_id": str(quantconnect_organization_id),
        "quantconnect_project_file_name": quantconnect_project_file_name,
        "delete_object_store_after_local_validation": bool(delete_object_store_after_local_validation),
        "output_dir": str(output_path),
        "local_batch_output_root": str(batch_root),
        "source_request_id": scaleout_plan_source.get("source_request_id"),
        "source_start": scaleout_plan_source.get("source_start"),
        "source_end": scaleout_plan_source.get("source_end"),
        "matrix_metadata_envelope_key": MATRIX_METADATA_KEY,
        "matrix_cell_key_fields": list(REQUIRED_MATRIX_METADATA_FIELDS),
        "matrix_metadata_batch_summary": matrix_metadata_batch_summary,
        "ready_to_build_exact_matrix_edge_summary": bool(
            matrix_metadata_batch_summary.get("ready_to_build_exact_matrix_edge_summary")
        ),
        "batch_count": len(batch_plans),
        "operation_count": operation_count,
        "api_operation_count": api_operation_count,
        "batch_plans": batch_plans,
        "runner_plan_summary": {
            "mode": mode,
            "batch_count": len(batch_plans),
            "operation_count": operation_count,
            "api_operation_count": api_operation_count,
            "delete_object_store_after_local_validation": bool(delete_object_store_after_local_validation),
            "manual_review_required_before_execute": True,
            "matrix_metadata_batch_summary": matrix_metadata_batch_summary,
            "execution_note": (
                "Dry-run only. This artifact lists the Cloud API operations that execute mode will perform."
            ),
        },
        "next_build_recommendations": [
            {
                "capability": "quantconnect_replay_result_import_validator_matrix_metadata",
                "priority": "high",
                "recommendation": (
                    "Patch replay result import validation to require/preserve matrix_metadata "
                    "on downloaded QuantConnect replay result records."
                ),
            },
            {
                "capability": "quantconnect_cloud_replay_batch_runner_execute_mode",
                "priority": "medium",
                "recommendation": "Add guarded execute mode after reviewing dry-run operation manifests.",
            },
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


def _batch_operation_plan(
    *,
    batch: Mapping[str, Any],
    quantconnect_project_id: str,
    quantconnect_organization_id: str,
    quantconnect_project_file_name: str,
    local_batch_output_root: Path,
    delete_object_store_after_local_validation: bool,
) -> dict[str, Any]:
    batch_id = str(batch.get("batch_id") or "unknown_batch")
    request_id = str(batch.get("request_id") or batch_id)
    object_store_prefix = str(batch.get("object_store_prefix") or "").rstrip("/")
    expected_result_files = _expected_result_files(batch)

    local_batch_dir = local_batch_output_root / batch_id
    generated_script_path = local_batch_dir / "SignalForgeCompactReplayAlgorithm.py"

    object_store_keys = [
        f"{object_store_prefix}/{filename}" for filename in expected_result_files
    ]

    batch_manifest = _mapping_or_empty(batch.get("quantconnect_replay_request_manifest"))
    stamped_candidates = _stamp_batch_runner_candidates(
        batch=batch,
        batch_manifest=batch_manifest,
        batch_id=batch_id,
        request_id=request_id,
    )
    matrix_metadata_candidate_summary = _candidate_matrix_metadata_summary(stamped_candidates)
    matrix_metadata_source_patch_state = (
        "ready"
        if matrix_metadata_candidate_summary.get("ready_to_build_exact_matrix_edge_summary")
        else "needs_review"
    )

    operations: list[dict[str, Any]] = [
        {
            "operation_id": f"{batch_id}_001_generate_compact_replay_script",
            "operation_kind": "local_signalforge",
            "action": "generate_compact_replay_script",
            "input": {
                "scaleout_batch_id": batch_id,
                "request_id": request_id,
            },
            "output": {
                "generated_script_path": str(generated_script_path),
            },
            "safety": {
                "uses_credentials": False,
                "touches_quantconnect_cloud": False,
                "writes_local_artifact_only": True,
            },
        },
        {
            "operation_id": f"{batch_id}_002_upsert_project_file",
            "operation_kind": "quantconnect_cloud_api",
            "action": "upsert_project_file",
            "endpoint_group": "file_management",
            "payload": {
                "projectId": quantconnect_project_id,
                "name": quantconnect_project_file_name,
                "content_source": str(generated_script_path),
            },
            "safety": {
                "uses_credentials": True,
                "touches_quantconnect_cloud": True,
                "mutates_quantconnect_project_file": True,
            },
        },
        {
            "operation_id": f"{batch_id}_003_create_compile",
            "operation_kind": "quantconnect_cloud_api",
            "action": "create_compile",
            "endpoint_group": "compile_management",
            "payload": {
                "projectId": quantconnect_project_id,
            },
            "safety": {
                "uses_credentials": True,
                "touches_quantconnect_cloud": True,
                "mutates_quantconnect_project_file": False,
            },
        },
        {
            "operation_id": f"{batch_id}_004_wait_for_compile",
            "operation_kind": "quantconnect_cloud_api",
            "action": "wait_for_compile",
            "endpoint_group": "compile_management",
            "payload": {
                "projectId": quantconnect_project_id,
                "compileId_source": f"{batch_id}_003_create_compile",
            },
            "safety": {
                "uses_credentials": True,
                "touches_quantconnect_cloud": True,
                "mutates_quantconnect_project_file": False,
            },
        },
        {
            "operation_id": f"{batch_id}_005_create_backtest",
            "operation_kind": "quantconnect_cloud_api",
            "action": "create_backtest",
            "endpoint_group": "backtest_management",
            "payload": {
                "projectId": quantconnect_project_id,
                "compileId_source": f"{batch_id}_004_wait_for_compile",
                "backtestName": f"SignalForge {batch_id} {batch.get('start')} to {batch.get('end')}",
                "parameters": {
                    "signalforge_batch_id": batch_id,
                    "signalforge_request_id": request_id,
                    "signalforge_matrix_metadata_envelope_key": MATRIX_METADATA_KEY,
                    "signalforge_matrix_metadata_source_patch_state": matrix_metadata_source_patch_state,
                },
            },
            "safety": {
                "uses_credentials": True,
                "touches_quantconnect_cloud": True,
                "creates_backtest": True,
                "order_routing": False,
                "live_execution": False,
            },
        },
        {
            "operation_id": f"{batch_id}_006_wait_for_backtest",
            "operation_kind": "quantconnect_cloud_api",
            "action": "wait_for_backtest",
            "endpoint_group": "backtest_management",
            "payload": {
                "projectId": quantconnect_project_id,
                "backtestId_source": f"{batch_id}_005_create_backtest",
            },
            "safety": {
                "uses_credentials": True,
                "touches_quantconnect_cloud": True,
                "order_routing": False,
                "live_execution": False,
            },
        },
        {
            "operation_id": f"{batch_id}_007_list_object_store_prefix",
            "operation_kind": "quantconnect_cloud_api",
            "action": "list_object_store_files",
            "endpoint_group": "object_store_management",
            "payload": {
                "organizationId": quantconnect_organization_id,
                "path": object_store_prefix,
            },
            "safety": {
                "uses_credentials": True,
                "touches_quantconnect_cloud": True,
                "deletes_object_store": False,
            },
        },
    ]

    for index, key in enumerate(object_store_keys, start=8):
        filename = key.split("/")[-1]
        operations.append(
            {
                "operation_id": f"{batch_id}_{index:03d}_download_{filename}",
                "operation_kind": "quantconnect_cloud_api",
                "action": "download_object_store_file",
                "endpoint_group": "object_store_management",
                "payload": {
                    "organizationId": quantconnect_organization_id,
                    "key": key,
                    "output_path": str(local_batch_dir / filename),
                },
                "safety": {
                    "uses_credentials": True,
                    "touches_quantconnect_cloud": True,
                    "writes_local_artifact": True,
                    "deletes_object_store": False,
                },
            }
        )

    validate_operation_number = 8 + len(object_store_keys)
    operations.append(
        {
            "operation_id": f"{batch_id}_{validate_operation_number:03d}_validate_local_result_files",
            "operation_kind": "local_signalforge",
            "action": "validate_local_result_files",
            "input": {
                "local_batch_dir": str(local_batch_dir),
                "expected_result_files": expected_result_files,
            },
            "safety": {
                "uses_credentials": False,
                "touches_quantconnect_cloud": False,
                "must_pass_before_delete": True,
            },
        }
    )

    delete_start = validate_operation_number + 1
    for index, key in enumerate(object_store_keys, start=delete_start):
        filename = key.split("/")[-1]
        operations.append(
            {
                "operation_id": f"{batch_id}_{index:03d}_delete_{filename}",
                "operation_kind": "quantconnect_cloud_api",
                "action": (
                    "delete_object_store_file"
                    if delete_object_store_after_local_validation
                    else "skip_delete_object_store_file"
                ),
                "endpoint_group": "object_store_management",
                "payload": {
                    "organizationId": quantconnect_organization_id,
                    "key": key,
                    "requires_prior_operation_success": f"{batch_id}_{validate_operation_number:03d}_validate_local_result_files",
                },
                "safety": {
                    "uses_credentials": True,
                    "touches_quantconnect_cloud": True,
                    "deletes_object_store": bool(delete_object_store_after_local_validation),
                    "delete_only_after_local_validation": True,
                },
            }
        )

    return {
        "batch_id": batch_id,
        "request_id": request_id,
        "start": batch.get("start"),
        "end": batch.get("end"),
        "symbols": list(batch.get("symbols", [])),
        "symbol_count": batch.get("symbol_count"),
        "candidate_ids": list(batch.get("candidate_ids", [])),
        "candidate_count": batch.get("candidate_count"),
        "matrix_metadata_envelope_key": MATRIX_METADATA_KEY,
        "matrix_cell_key_fields": list(REQUIRED_MATRIX_METADATA_FIELDS),
        "matrix_metadata_source_patch_state": matrix_metadata_source_patch_state,
        "matrix_metadata_candidate_summary": matrix_metadata_candidate_summary,
        "ready_to_build_exact_matrix_edge_summary": bool(
            matrix_metadata_candidate_summary.get("ready_to_build_exact_matrix_edge_summary")
        ),
        "stamped_candidate_count": len(stamped_candidates),
        "stamped_candidates": stamped_candidates,
        "object_store_prefix": object_store_prefix,
        "object_store_keys": object_store_keys,
        "expected_result_files": expected_result_files,
        "local_batch_dir": str(local_batch_dir),
        "generated_script_path": str(generated_script_path),
        "quantconnect_project_file_name": quantconnect_project_file_name,
        "delete_object_store_after_local_validation": bool(delete_object_store_after_local_validation),
        "operation_count": len(operations),
        "operations": operations,
    }


def _stamp_batch_runner_candidates(
    *,
    batch: Mapping[str, Any],
    batch_manifest: Mapping[str, Any],
    batch_id: str,
    request_id: str,
) -> list[dict[str, Any]]:
    candidates = _candidate_records_for_batch(batch=batch, batch_manifest=batch_manifest)
    stamped: list[dict[str, Any]] = []

    for index, candidate in enumerate(candidates):
        supplemental_metadata = _supplemental_batch_runner_metadata(
            candidate,
            batch=batch,
            batch_manifest=batch_manifest,
            batch_id=batch_id,
        )
        source_refs = _batch_runner_source_refs(
            candidate,
            supplemental_metadata=supplemental_metadata,
            request_id=request_id,
            batch_id=batch_id,
            index=index,
        )
        stamped.append(
            stamp_matrix_metadata(
                candidate,
                supplemental_metadata,
                source_refs=source_refs,
                preserve_existing=True,
            )
        )

    return stamped


def _candidate_records_for_batch(
    *,
    batch: Mapping[str, Any],
    batch_manifest: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    manifest_candidates = _sequence_of_mappings(batch_manifest.get("candidates"))
    if manifest_candidates:
        return manifest_candidates

    batch_candidates = _sequence_of_mappings(batch.get("candidates"))
    if batch_candidates:
        return batch_candidates

    candidate_ids = [str(item) for item in batch.get("candidate_ids", []) if str(item)]
    symbols = [str(item) for item in batch.get("symbols", []) if str(item)]
    candidates: list[dict[str, Any]] = []

    for index, candidate_id in enumerate(candidate_ids):
        candidate: dict[str, Any] = {"candidate_id": candidate_id}
        if index < len(symbols):
            candidate["symbol"] = symbols[index]
        candidates.append(candidate)

    if not candidates and len(symbols) == 1:
        candidates.append({"symbol": symbols[0]})

    return candidates


def _supplemental_batch_runner_metadata(
    candidate: Mapping[str, Any],
    *,
    batch: Mapping[str, Any],
    batch_manifest: Mapping[str, Any],
    batch_id: str,
) -> dict[str, Any]:
    metadata = extract_candidate_matrix_metadata(candidate)

    # Copy only explicit batch/manifest fields or deterministic context. Do not infer
    # missing regime, asset behavior, option behavior, or strategy dimensions.
    for field in [
        "regime_state",
        "asset_behavior_state",
        "option_behavior_state",
        "strategy_id",
        "strategy_family",
        "symbol",
        "horizon_days",
        "asset_class",
        "strategy_direction",
        "risk_structure",
    ]:
        if metadata.get(field) is not None:
            continue
        value = _first_present(batch, [field])
        if value is None:
            value = _first_present(batch_manifest, [field])
        if value is not None:
            metadata[field] = value

    if metadata.get("symbol") is None:
        value = _first_present(candidate, ["ticker", "underlying", "underlying_symbol", "root_symbol"])
        if value is not None:
            metadata["symbol"] = value

    if metadata.get("horizon_days") is None:
        value = _first_present(
            candidate,
            ["horizon", "window_days", "selected_window_days", "target_horizon_days"],
        )
        if value is None:
            value = _single_horizon_days(batch_manifest)
        if value is None:
            value = _single_horizon_days(batch)
        if value is not None:
            metadata["horizon_days"] = value

    if metadata.get("strategy_id") is None:
        value = _first_present(candidate, ["strategy", "strategy_name", "setup_id", "scenario_id"])
        if value is not None:
            metadata["strategy_id"] = value

    if metadata.get("strategy_family") is None:
        value = _first_present(candidate, ["family", "strategy_type", "variant_id"])
        if value is not None:
            metadata["strategy_family"] = value

    metadata["replay_window_id"] = batch_id
    return metadata


def _batch_runner_source_refs(
    candidate: Mapping[str, Any],
    *,
    supplemental_metadata: Mapping[str, Any],
    request_id: str,
    batch_id: str,
    index: int,
) -> dict[str, Any]:
    refs: dict[str, Any] = {}
    for field, value in supplemental_metadata.items():
        if value is None:
            continue
        refs[field] = {
            "source_request_id": request_id,
            "source_scope": f"cloud_replay_batch_runner.{batch_id}.candidates",
            "source_index": index,
            "source_field": _source_field_for_batch_metadata(candidate, field),
        }
    return refs


def _source_field_for_batch_metadata(candidate: Mapping[str, Any], field: str) -> str:
    if field in candidate:
        return field
    aliases = {
        "symbol": ["ticker", "underlying", "underlying_symbol", "root_symbol"],
        "horizon_days": ["horizon", "window_days", "selected_window_days", "target_horizon_days"],
        "strategy_id": ["strategy", "strategy_name", "setup_id", "scenario_id"],
        "strategy_family": ["family", "strategy_type", "variant_id"],
    }
    for alias in aliases.get(field, []):
        if alias in candidate:
            return alias
    return "batch_or_manifest_context"


def _candidate_matrix_metadata_summary(candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    coverage = matrix_metadata_coverage(candidates)
    return {
        "candidate_count": len(candidates),
        "exact_matrix_cell_ready_candidate_count": coverage.get(
            "exact_matrix_cell_ready_record_count", 0
        ),
        "needs_review_candidate_count": coverage.get("needs_review_record_count", 0),
        "mapped_required_field_counts": dict(coverage.get("mapped_required_field_counts", {})),
        "missing_required_field_counts": dict(coverage.get("missing_required_field_counts", {})),
        "ready_to_build_exact_matrix_edge_summary": bool(
            coverage.get("ready_to_build_exact_matrix_edge_summary")
        ),
    }


def _runner_matrix_metadata_summary(batch_plans: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    candidate_count = 0
    ready_count = 0
    needs_review_count = 0
    mapped_counts = {field: 0 for field in REQUIRED_MATRIX_METADATA_FIELDS}
    missing_counts = {field: 0 for field in REQUIRED_MATRIX_METADATA_FIELDS}

    for batch in batch_plans:
        summary = batch.get("matrix_metadata_candidate_summary")
        if not isinstance(summary, Mapping):
            continue
        candidate_count += _as_int(summary.get("candidate_count"))
        ready_count += _as_int(summary.get("exact_matrix_cell_ready_candidate_count"))
        needs_review_count += _as_int(summary.get("needs_review_candidate_count"))
        for field, count in dict(summary.get("mapped_required_field_counts", {})).items():
            if field in mapped_counts:
                mapped_counts[field] += _as_int(count)
        for field, count in dict(summary.get("missing_required_field_counts", {})).items():
            if field in missing_counts:
                missing_counts[field] += _as_int(count)

    return {
        "batch_count": len(batch_plans),
        "candidate_count": candidate_count,
        "exact_matrix_cell_ready_candidate_count": ready_count,
        "needs_review_candidate_count": needs_review_count,
        "mapped_required_field_counts": mapped_counts,
        "missing_required_field_counts": missing_counts,
        "ready_to_build_exact_matrix_edge_summary": candidate_count > 0 and needs_review_count == 0,
    }


def _single_horizon_days(source: Mapping[str, Any]) -> int | None:
    for key in ["outcome_horizons", "horizons", "horizon_days", "target_horizon_days"]:
        value = source.get(key)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            normalized = [normalize_horizon_days(item) for item in value]
            normalized = [item for item in normalized if item is not None]
            unique = sorted(set(normalized))
            if len(unique) == 1:
                return unique[0]
            continue
        normalized_value = normalize_horizon_days(value)
        if normalized_value is not None:
            return normalized_value
    return None


def _first_present(source: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        value = source.get(key)
        if value is not None and value != "" and value != [] and value != {}:
            return value
    return None


def _mapping_or_empty(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return int(float(value.strip()))
        except ValueError:
            return 0
    return 0


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


def _source_artifact_type(source: Any) -> str:
    if isinstance(source, Mapping):
        return str(source.get("artifact_type") or "provided_unknown_artifact")
    if source is None:
        return "missing"
    return type(source).__name__
