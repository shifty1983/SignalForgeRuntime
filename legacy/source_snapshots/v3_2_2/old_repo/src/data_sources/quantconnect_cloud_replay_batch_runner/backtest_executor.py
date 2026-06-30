from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from src.signalforge.data_sources.quantconnect_cloud_replay_batch_runner.compile_executor import (
    EXPLICIT_EXCLUSIONS,
    ScriptGenerator,
    _default_script_generator,
    _extract_compile_id,
    _write_batch_handoff,
)


ARTIFACT_TYPE = "signalforge_quantconnect_cloud_replay_backtest_execution"
SCHEMA_VERSION = "signalforge_quantconnect_cloud_replay_backtest_execution.v1"
CONTRACT = "quantconnect_cloud_replay_backtest_execution"


def execute_signalforge_quantconnect_cloud_replay_backtest_only(
    scaleout_plan_source: Mapping[str, Any] | None,
    *,
    client: Any,
    quantconnect_project_id: str,
    quantconnect_organization_id: str,
    output_dir: str | Path,
    quantconnect_project_file_name: str = "main.py",
    batch_limit: int = 1,
    script_generator: ScriptGenerator | None = None,
) -> dict[str, Any]:
    blocked_reasons: list[str] = []

    if not isinstance(scaleout_plan_source, Mapping):
        blocked_reasons.append("missing_scaleout_plan_source")
        scaleout_plan_source = {}

    if scaleout_plan_source.get("artifact_type") != "signalforge_quantconnect_historical_replay_scaleout_plan":
        blocked_reasons.append("invalid_scaleout_plan_artifact_type")

    if not str(quantconnect_project_id or "").strip():
        blocked_reasons.append("missing_quantconnect_project_id")

    if not str(quantconnect_organization_id or "").strip():
        blocked_reasons.append("missing_quantconnect_organization_id")

    batches = [
        batch for batch in scaleout_plan_source.get("batches", [])
        if isinstance(batch, Mapping)
    ]

    if not batches:
        blocked_reasons.append("missing_scaleout_batches")

    output_path = Path(output_dir)
    batch_root = output_path / "batches"
    batch_limit = max(int(batch_limit or 1), 1)
    selected_batches = batches[:batch_limit]

    execution_batches: list[dict[str, Any]] = []

    if not blocked_reasons:
        for batch in selected_batches:
            execution_batches.append(
                _execute_backtest_batch(
                    batch=batch,
                    client=client,
                    quantconnect_project_id=int(quantconnect_project_id),
                    quantconnect_project_file_name=quantconnect_project_file_name,
                    batch_root=batch_root,
                    script_generator=script_generator or _default_script_generator,
                )
            )

    failed_batches = [
        batch["batch_id"]
        for batch in execution_batches
        if batch.get("backtest_status") != "backtest_completed"
    ]

    if failed_batches:
        blocked_reasons.append("one_or_more_batches_failed_backtest")

    is_ready = not blocked_reasons

    return {
        "adapter_type": "quantconnect_cloud_replay_backtest_execution_builder",
        "artifact_type": ARTIFACT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "contract": CONTRACT,
        "status": "ready" if is_ready else "blocked",
        "is_ready": is_ready,
        "mode": "execute_backtest_only",
        "requires_manual_approval": True,
        "review_scope": "cloud_replay_backtest_only_not_order_intent_or_execution",
        "blocked_reasons": list(dict.fromkeys(blocked_reasons)),
        "covered_capabilities": [
            "quantconnect_cloud_replay_backtest_execution",
            "quantconnect_cloud_project_file_upsert",
            "quantconnect_cloud_compile_check",
            "quantconnect_cloud_backtest_create_and_wait",
            "backtest_only_no_object_store_download_no_object_store_delete",
        ],
        "depends_on_capabilities": [
            "quantconnect_cloud_api_client",
            "quantconnect_historical_replay_scaleout_plan",
            "quantconnect_compact_replay_script",
        ],
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
        "source_artifacts": {
            "scaleout_plan_source": str(scaleout_plan_source.get("artifact_type") or "provided_unknown_artifact"),
        },
        "quantconnect_project_id": str(quantconnect_project_id),
        "quantconnect_organization_id": str(quantconnect_organization_id),
        "quantconnect_project_file_name": quantconnect_project_file_name,
        "output_dir": str(output_path),
        "batch_limit": batch_limit,
        "selected_batch_count": len(selected_batches),
        "backtested_batch_count": len(execution_batches),
        "failed_backtest_batch_count": len(failed_batches),
        "failed_backtest_batch_ids": failed_batches,
        "execution_batches": execution_batches,
        "backtest_execution_summary": {
            "mode": "execute_backtest_only",
            "selected_batch_count": len(selected_batches),
            "backtested_batch_count": len(execution_batches),
            "failed_backtest_batch_count": len(failed_batches),
            "stopped_before_object_store_download": True,
            "stopped_before_object_store_delete": True,
        },
        "next_build_recommendations": [
            {
                "capability": "quantconnect_cloud_object_store_download_mode",
                "priority": "high",
                "recommendation": "After backtest execution succeeds, add guarded Object Store result download without delete.",
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


def _execute_backtest_batch(
    *,
    batch: Mapping[str, Any],
    client: Any,
    quantconnect_project_id: int,
    quantconnect_project_file_name: str,
    batch_root: Path,
    script_generator: ScriptGenerator,
) -> dict[str, Any]:
    batch_id = str(batch.get("batch_id") or "unknown_batch")
    request_id = str(batch.get("request_id") or batch_id)
    batch_dir = batch_root / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)

    batch_handoff_path = batch_dir / f"{batch_id}_quantconnect_historical_replay_handoff.json"
    _write_batch_handoff(batch, batch_handoff_path)

    generated_script_path = script_generator(batch, batch_handoff_path, batch_dir)
    script_text = generated_script_path.read_text(encoding="utf-8")

    upsert_project_file_results = []

    upsert_result = client.upsert_project_file(
        project_id=quantconnect_project_id,
        name=quantconnect_project_file_name,
        content=script_text,
    )
    upsert_project_file_results.append(
        {
            "name": quantconnect_project_file_name,
            "local_path": str(generated_script_path),
            "response": dict(upsert_result),
        }
    )

    compile_create_result = client.create_compile(project_id=quantconnect_project_id)
    compile_id = _extract_compile_id(compile_create_result)

    if not compile_id:
        return _stopped_batch_result(
            batch=batch,
            batch_dir=batch_dir,
            batch_handoff_path=batch_handoff_path,
            generated_script_path=generated_script_path,
            quantconnect_project_file_name=quantconnect_project_file_name,
            compile_status="compile_id_missing",
            compile_id=None,
            compile_state="",
            upsert_result=upsert_result,
            compile_create_result=compile_create_result,
            compile_read_result={},
            backtest_status="not_created_compile_id_missing",
            backtest_id=None,
            backtest_create_result={},
            backtest_read_result={},
        )

    compile_read_result = client.wait_for_compile(
        project_id=quantconnect_project_id,
        compile_id=compile_id,
    )
    compile_state = str(compile_read_result.get("state") or "")
    compile_status = "compile_succeeded" if compile_state == "BuildSuccess" else "compile_failed"

    if compile_status != "compile_succeeded":
        return _stopped_batch_result(
            batch=batch,
            batch_dir=batch_dir,
            batch_handoff_path=batch_handoff_path,
            generated_script_path=generated_script_path,
            quantconnect_project_file_name=quantconnect_project_file_name,
            compile_status=compile_status,
            compile_id=compile_id,
            compile_state=compile_state,
            upsert_result=upsert_result,
            compile_create_result=compile_create_result,
            compile_read_result=compile_read_result,
            backtest_status="not_created_compile_failed",
            backtest_id=None,
            backtest_create_result={},
            backtest_read_result={},
        )

    backtest_name = f"SignalForge {batch_id} {batch.get('start')} to {batch.get('end')}"
    try:
        backtest_create_result = client.create_backtest(
            project_id=quantconnect_project_id,
            compile_id=compile_id,
            backtest_name=backtest_name,
            parameters={
                "signalforge_batch_id": batch_id,
                "signalforge_request_id": request_id,
            },
        )
    except Exception as exc:
        error_text = str(exc)
        backtest_status = (
            "not_created_no_spare_nodes"
            if "no spare nodes" in error_text.lower()
            else "not_created_quantconnect_api_error"
        )
        return _stopped_batch_result(
            batch=batch,
            batch_dir=batch_dir,
            batch_handoff_path=batch_handoff_path,
            generated_script_path=generated_script_path,
            quantconnect_project_file_name=quantconnect_project_file_name,
            compile_status=compile_status,
            compile_id=compile_id,
            compile_state=compile_state,
            upsert_result=upsert_result,
            compile_create_result=compile_create_result,
            compile_read_result=compile_read_result,
            backtest_status=backtest_status,
            backtest_id=None,
            backtest_create_result={
                "error": error_text,
                "exception_type": type(exc).__name__,
            },
            backtest_read_result={},
        )

    backtest_id = _extract_backtest_id(backtest_create_result)
    if not backtest_id:
        return _stopped_batch_result(
            batch=batch,
            batch_dir=batch_dir,
            batch_handoff_path=batch_handoff_path,
            generated_script_path=generated_script_path,
            quantconnect_project_file_name=quantconnect_project_file_name,
            compile_status=compile_status,
            compile_id=compile_id,
            compile_state=compile_state,
            upsert_result=upsert_result,
            compile_create_result=compile_create_result,
            compile_read_result=compile_read_result,
            backtest_status="backtest_id_missing",
            backtest_id=None,
            backtest_create_result=backtest_create_result,
            backtest_read_result={},
        )

    backtest_read_result = client.wait_for_backtest(
        project_id=quantconnect_project_id,
        backtest_id=backtest_id,
    )

    backtest_read_response_path = batch_dir / "backtest_read_response.json"
    backtest_read_response_path.write_text(
        json.dumps(backtest_read_result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    backtest_status = (
        "backtest_completed"
        if _backtest_completed(backtest_read_result)
        else "backtest_not_completed"
    )

    return _stopped_batch_result(
        batch=batch,
        batch_dir=batch_dir,
        batch_handoff_path=batch_handoff_path,
        generated_script_path=generated_script_path,
        quantconnect_project_file_name=quantconnect_project_file_name,
        compile_status=compile_status,
        compile_id=compile_id,
        compile_state=compile_state,
        upsert_result=upsert_result,
        compile_create_result=compile_create_result,
        compile_read_result=compile_read_result,
        backtest_status=backtest_status,
        backtest_id=backtest_id,
        backtest_create_result=backtest_create_result,
        backtest_read_result=backtest_read_result,
    )


def _stopped_batch_result(
    *,
    batch: Mapping[str, Any],
    batch_dir: Path,
    batch_handoff_path: Path,
    generated_script_path: Path,
    quantconnect_project_file_name: str,
    compile_status: str,
    compile_id: str | None,
    compile_state: str,
    upsert_result: Mapping[str, Any],
    compile_create_result: Mapping[str, Any],
    compile_read_result: Mapping[str, Any],
    backtest_status: str,
    backtest_id: str | None,
    backtest_create_result: Mapping[str, Any],
    backtest_read_result: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "batch_id": str(batch.get("batch_id") or "unknown_batch"),
        "request_id": batch.get("request_id"),
        "start": batch.get("start"),
        "end": batch.get("end"),
        "symbols": list(batch.get("symbols", [])),
        "candidate_ids": list(batch.get("candidate_ids", [])),
        "object_store_prefix": batch.get("object_store_prefix"),
        "local_batch_dir": str(batch_dir),
        "batch_handoff_path": str(batch_handoff_path),
        "generated_script_path": str(generated_script_path),
        "quantconnect_project_file_name": quantconnect_project_file_name,
        "compile_status": compile_status,
        "compile_id": compile_id,
        "compile_state": compile_state,
        "backtest_status": backtest_status,
        "backtest_id": backtest_id,
        "backtest_created": backtest_id is not None,
        "backtest_completed": backtest_status == "backtest_completed",
        "object_store_downloaded": False,
        "object_store_deleted": False,
        "upsert_project_file_response": dict(upsert_result),
        "upsert_project_file_responses": [
            {
                "name": quantconnect_project_file_name,
                "local_path": str(generated_script_path),
                "response": dict(upsert_result),
            }
        ],
        "compile_create_response": dict(compile_create_result),
        "compile_read_response": dict(compile_read_result),
        "backtest_create_response": dict(backtest_create_result),
        "backtest_read_response": dict(backtest_read_result),
        "backtest_read_response_path": str(batch_dir / "backtest_read_response.json"),
    }


def _extract_backtest_id(response: Mapping[str, Any]) -> str:
    for key in ["backtestId", "backtest_id"]:
        value = response.get(key)
        if value:
            return str(value)

    backtest = response.get("backtest")
    if isinstance(backtest, Mapping):
        for key in ["backtestId", "backtest_id", "id"]:
            value = backtest.get(key)
            if value:
                return str(value)

    return ""


def _backtest_completed(response: Mapping[str, Any]) -> bool:
    if response.get("completed") is True:
        return True

    backtest = response.get("backtest")
    if isinstance(backtest, Mapping):
        if backtest.get("completed") is True:
            return True

    return False
