from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any


ARTIFACT_TYPE = "signalforge_quantconnect_cloud_replay_compile_execution"
SCHEMA_VERSION = "signalforge_quantconnect_cloud_replay_compile_execution.v1"
CONTRACT = "quantconnect_cloud_replay_compile_execution"

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


ScriptGenerator = Callable[[Mapping[str, Any], Path, Path], Path]


def execute_signalforge_quantconnect_cloud_replay_compile_only(
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
                _execute_compile_batch(
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
        if batch.get("compile_status") != "compile_succeeded"
    ]

    if failed_batches:
        blocked_reasons.append("one_or_more_batches_failed_compile")

    is_ready = not blocked_reasons

    return {
        "adapter_type": "quantconnect_cloud_replay_compile_execution_builder",
        "artifact_type": ARTIFACT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "contract": CONTRACT,
        "status": "ready" if is_ready else "blocked",
        "is_ready": is_ready,
        "mode": "execute_compile_only",
        "requires_manual_approval": True,
        "review_scope": "cloud_replay_compile_only_not_order_intent_or_execution",
        "blocked_reasons": list(dict.fromkeys(blocked_reasons)),
        "covered_capabilities": [
            "quantconnect_cloud_replay_compile_execution",
            "quantconnect_cloud_project_file_upsert",
            "quantconnect_cloud_compile_check",
            "compile_only_no_backtest_no_object_store_delete",
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
        "compiled_batch_count": len(execution_batches),
        "failed_compile_batch_count": len(failed_batches),
        "failed_compile_batch_ids": failed_batches,
        "execution_batches": execution_batches,
        "compile_execution_summary": {
            "mode": "execute_compile_only",
            "selected_batch_count": len(selected_batches),
            "compiled_batch_count": len(execution_batches),
            "failed_compile_batch_count": len(failed_batches),
            "stopped_before_backtest": True,
            "stopped_before_object_store_download": True,
            "stopped_before_object_store_delete": True,
        },
        "next_build_recommendations": [
            {
                "capability": "quantconnect_cloud_replay_backtest_execute_mode",
                "priority": "high",
                "recommendation": "After compile-only succeeds, add guarded create-backtest and wait-backtest execution.",
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


def _execute_compile_batch(
    *,
    batch: Mapping[str, Any],
    client: Any,
    quantconnect_project_id: int,
    quantconnect_project_file_name: str,
    batch_root: Path,
    script_generator: ScriptGenerator,
) -> dict[str, Any]:
    batch_id = str(batch.get("batch_id") or "unknown_batch")
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
        return {
            "batch_id": batch_id,
            "request_id": batch.get("request_id"),
            "local_batch_dir": str(batch_dir),
            "batch_handoff_path": str(batch_handoff_path),
            "generated_script_path": str(generated_script_path),
            "compile_status": "compile_id_missing",
            "compile_id": None,
            "upsert_project_file_response": upsert_result,
            "compile_create_response": compile_create_result,
            "compile_read_response": {},
            "backtest_created": False,
            "object_store_downloaded": False,
            "object_store_deleted": False,
        }

    compile_read_result = client.wait_for_compile(
        project_id=quantconnect_project_id,
        compile_id=compile_id,
    )
    compile_state = str(compile_read_result.get("state") or "")
    compile_status = "compile_succeeded" if compile_state == "BuildSuccess" else "compile_failed"

    return {
        "batch_id": batch_id,
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
        "upsert_project_file_response": upsert_result,
        "compile_create_response": compile_create_result,
        "compile_read_response": compile_read_result,
        "backtest_created": False,
        "object_store_downloaded": False,
        "object_store_deleted": False,
    }


def _write_batch_handoff(batch: Mapping[str, Any], output_path: Path) -> None:
    payload = {
        "artifact_type": "signalforge_quantconnect_historical_replay_handoff",
        "schema_version": "signalforge_quantconnect_historical_replay_handoff.v1",
        "status": "ready",
        "is_ready": True,
        "quantconnect_replay_request_manifest": batch.get("quantconnect_replay_request_manifest", {}),
        "quantconnect_result_contract": {
            "expected_result_files": list(batch.get("expected_result_files", [])),
            "expected_result_file_count": batch.get("expected_result_file_count", 0),
        },
        "scaleout_batch": {
            "batch_id": batch.get("batch_id"),
            "batch_number": batch.get("batch_number"),
            "request_id": batch.get("request_id"),
            "object_store_prefix": batch.get("object_store_prefix"),
        },
        "order_intent": None,
        "broker_order_id": None,
        "portfolio_action": None,
        "position_size": None,
    }

    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _default_script_generator(
    batch: Mapping[str, Any],
    batch_handoff_path: Path,
    batch_dir: Path,
) -> Path:
    command = [
        sys.executable,
        "-m",
        "src.data_sources.quantconnect_compact_replay_script.cli",
        "--handoff-source",
        str(batch_handoff_path),
        "--output-dir",
        str(batch_dir),
        "--compressed-inline-manifest",
    ]

    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )

    stdout_path = batch_dir / "compact_replay_script_generation_stdout.txt"
    stderr_path = batch_dir / "compact_replay_script_generation_stderr.txt"
    command_path = batch_dir / "compact_replay_script_generation_command.json"

    stdout_path.write_text(completed.stdout or "", encoding="utf-8")
    stderr_path.write_text(completed.stderr or "", encoding="utf-8")
    command_path.write_text(
        json.dumps(
            {
                "returncode": completed.returncode,
                "command": command,
                "stdout_path": str(stdout_path),
                "stderr_path": str(stderr_path),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    if completed.returncode != 0:
        raise RuntimeError(
            "Compact replay script generation failed. "
            f"returncode={completed.returncode}, stderr_path={stderr_path}"
        )

    script_path = batch_dir / "SignalForgeCompactReplayAlgorithm.py"
    if script_path.exists():
        return script_path

    generated_scripts = sorted(batch_dir.glob("*.py"))
    if generated_scripts:
        return generated_scripts[0]

    raise RuntimeError(f"Compact replay script was not generated for batch: {batch.get('batch_id')}")


def _extract_compile_id(response: Mapping[str, Any]) -> str:
    for key in ["compileId", "compile_id"]:
        value = response.get(key)
        if value:
            return str(value)

    compile_result = response.get("compile")
    if isinstance(compile_result, Mapping):
        for key in ["compileId", "compile_id"]:
            value = compile_result.get(key)
            if value:
                return str(value)

    return ""
