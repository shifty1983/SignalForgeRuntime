from __future__ import annotations

import base64
import json
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterator

import requests


ADAPTER_TYPE = "baseline_exit_overlay_qc_gap_rest_runner"
ARTIFACT_TYPE = "signalforge_baseline_exit_overlay_qc_gap_rest_runner"
CONTRACT = "baseline_exit_overlay_qc_gap_rest_runner"
BASE_URL = "https://www.quantconnect.com/api/v2"


@dataclass
class BatchRunState:
    batch_id: str
    batch_index: int
    status: str
    request_row_count: int
    expected_missing_quote_date_count: int
    expected_manifest_key: str
    expected_part_key_prefix: str
    payload_b64_path: str

    compile_id: str | None = None
    compile_state: str | None = None
    backtest_id: str | None = None
    backtest_name: str | None = None
    backtest_status: str | None = None
    backtest_completed: bool | None = None
    error_message: str | None = None
    started_at_utc: str | None = None
    completed_at_utc: str | None = None
    updated_at_utc: str | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iter_jsonl(path: str | Path) -> Iterator[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8-sig", errors="ignore") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc
            if isinstance(value, dict):
                yield value


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class QuantConnectRestClient:
    def __init__(self, user_id: str, api_token: str, project_id: int, timeout_seconds: int = 60) -> None:
        self.user_id = str(user_id)
        self.api_token = str(api_token)
        self.project_id = int(project_id)
        self.timeout_seconds = int(timeout_seconds)

    def _headers(self) -> dict[str, str]:
        timestamp = f"{int(time.time())}"
        time_stamped_token = f"{self.api_token}:{timestamp}".encode("utf-8")
        hashed_token = sha256(time_stamped_token).hexdigest()
        authentication = f"{self.user_id}:{hashed_token}".encode("utf-8")
        authentication = base64.b64encode(authentication).decode("ascii")
        return {"Authorization": f"Basic {authentication}", "Timestamp": timestamp}

    def post(self, endpoint: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        response = requests.post(
            f"{BASE_URL}{endpoint}",
            headers=self._headers(),
            json=payload or {},
            timeout=self.timeout_seconds,
        )
        try:
            result = response.json()
        except Exception as exc:
            raise RuntimeError(
                f"QuantConnect API returned non-JSON for {endpoint}: "
                f"status={response.status_code} text={response.text[:500]}"
            ) from exc
        if response.status_code >= 400:
            raise RuntimeError(
                f"QuantConnect API HTTP error for {endpoint}: "
                f"status={response.status_code} result={result}"
            )
        if result.get("success") is False:
            raise RuntimeError(f"QuantConnect API unsuccessful for {endpoint}: {result}")
        return result

    def authenticate(self) -> dict[str, Any]:
        return self.post("/authenticate")

    def update_file(self, file_name: str, content: str) -> dict[str, Any]:
        payload = {
            "projectId": self.project_id,
            "name": file_name,
            "content": content,
            "codeSourceId": "SignalForge",
        }

        update_error = None
        try:
            return self.post("/files/update", payload)
        except RuntimeError as exc:
            update_error = str(exc)

        # Some QC accounts/projects reject update when the file record lookup is stale.
        # In that case create is valid only if the file does not already exist.
        try:
            return self.post("/files/create", payload)
        except RuntimeError as create_exc:
            create_error = str(create_exc)
            if "File already exist" in create_error or "already exist" in create_error:
                # Do not continue silently because compile would use the old file.
                raise RuntimeError(
                    "QuantConnect project file already exists but /files/update failed. "
                    f"file_name={file_name}; update_error={update_error}; create_error={create_error}"
                ) from create_exc
            raise

    def create_compile(self) -> str:
        result = self.post("/compile/create", {"projectId": self.project_id})
        compile_id = result.get("compileId")
        if not compile_id:
            raise RuntimeError(f"Compile create response missing compileId: {result}")
        return str(compile_id)

    def read_compile(self, compile_id: str) -> dict[str, Any]:
        return self.post("/compile/read", {"projectId": self.project_id, "compileId": compile_id})

    def wait_for_compile(self, compile_id: str, poll_seconds: int, timeout_seconds: int) -> dict[str, Any]:
        deadline = time.time() + timeout_seconds
        while True:
            result = self.read_compile(compile_id)
            state = str(result.get("state") or "")
            if state == "BuildSuccess":
                return result
            if state == "BuildError":
                raise RuntimeError(f"Compile failed: {result}")
            if time.time() >= deadline:
                raise TimeoutError(f"Compile timed out: compile_id={compile_id} last={result}")
            time.sleep(poll_seconds)

    def create_backtest(self, compile_id: str, backtest_name: str, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "projectId": self.project_id,
            "compileId": compile_id,
            "backtestName": backtest_name,
        }
        if parameters:
            payload["parameters"] = parameters
        return self.post("/backtests/create", payload)

    def read_backtest(self, backtest_id: str) -> dict[str, Any]:
        return self.post("/backtests/read", {"projectId": self.project_id, "backtestId": backtest_id})

    def wait_for_backtest(self, backtest_id: str, poll_seconds: int, timeout_seconds: int) -> dict[str, Any]:
        deadline = time.time() + timeout_seconds
        while True:
            result = self.read_backtest(backtest_id)
            backtest = result.get("backtest") or {}
            completed = bool(backtest.get("completed"))
            status = str(backtest.get("status") or "")
            error = backtest.get("error")
            stacktrace = backtest.get("stacktrace")
            has_initialize_error = bool(backtest.get("hasInitializeError"))

            if completed:
                if has_initialize_error or error or stacktrace:
                    raise RuntimeError(
                        "Backtest completed with error: "
                        f"backtest_id={backtest_id} status={status} error={error} stacktrace={stacktrace}"
                    )
                return result

            if "error" in status.lower() or "failed" in status.lower():
                raise RuntimeError(f"Backtest failed: backtest_id={backtest_id} result={result}")

            if time.time() >= deadline:
                raise TimeoutError(f"Backtest timed out: backtest_id={backtest_id} status={status}")

            time.sleep(poll_seconds)


def _render_template(template_text: str, batch_id: str, payload_b64: str) -> str:
    return (
        template_text
        .replace("__BATCH_ID__", batch_id)
        .replace("__BATCH_PAYLOAD_B64__", payload_b64.strip())
    )


def _state_rows_from_manifest(manifest_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in manifest_rows:
        batch_id = str(row["batch_id"])
        state = BatchRunState(
            batch_id=batch_id,
            batch_index=int(row["batch_index"]),
            status="pending",
            request_row_count=int(row["request_row_count"]),
            expected_missing_quote_date_count=int(row["missing_quote_date_count"]),
            expected_manifest_key=str(row["expected_object_store_manifest_key"]),
            expected_part_key_prefix=str(row["expected_object_store_part_key_prefix"]),
            payload_b64_path=str(row["batch_payload_b64_path"]),
        )
        rows[batch_id] = asdict(state)
    return rows


def _merge_existing_state(
    manifest_state_rows: dict[str, dict[str, Any]],
    existing_state: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    existing_rows = existing_state.get("batches", {})
    merged = dict(manifest_state_rows)
    for batch_id, existing_row in existing_rows.items():
        if batch_id not in merged:
            continue
        base = merged[batch_id]
        base.update(existing_row)
        base["expected_manifest_key"] = manifest_state_rows[batch_id]["expected_manifest_key"]
        base["expected_part_key_prefix"] = manifest_state_rows[batch_id]["expected_part_key_prefix"]
        base["request_row_count"] = manifest_state_rows[batch_id]["request_row_count"]
        base["expected_missing_quote_date_count"] = manifest_state_rows[batch_id]["expected_missing_quote_date_count"]
        base["payload_b64_path"] = manifest_state_rows[batch_id]["payload_b64_path"]
    return merged


def _completed_rows(state_rows: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row for row in sorted(state_rows.values(), key=lambda x: x["batch_index"])
        if row.get("status") == "completed"
    ]


def _write_research_pull_lists(output_dir: Path, state_rows: dict[str, dict[str, Any]]) -> dict[str, str]:
    pull_dir = output_dir / "research_pull_lists"
    pull_dir.mkdir(parents=True, exist_ok=True)
    completed = _completed_rows(state_rows)

    payload = {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": "signalforge_baseline_exit_overlay_qc_gap_research_pull_list",
        "contract": "baseline_exit_overlay_qc_gap_research_pull_list",
        "completed_batch_count": len(completed),
        "delete_after_research_export": False,
        "object_store_manifest_keys": [row["expected_manifest_key"] for row in completed],
        "batches": [
            {
                "batch_id": row["batch_id"],
                "batch_index": row["batch_index"],
                "backtest_id": row.get("backtest_id"),
                "expected_manifest_key": row["expected_manifest_key"],
                "expected_part_key_prefix": row["expected_part_key_prefix"],
                "expected_missing_quote_date_count": row["expected_missing_quote_date_count"],
            }
            for row in completed
        ],
    }

    json_path = pull_dir / "research_pull_list_all_completed_batches.json"
    txt_path = pull_dir / "research_pull_list_all_completed_batches.txt"
    _write_json(json_path, payload)
    txt_path.write_text("\n".join(payload["object_store_manifest_keys"]) + ("\n" if completed else ""), encoding="utf-8")
    return {"research_pull_list_json_path": str(json_path), "research_pull_list_txt_path": str(txt_path)}


def build_runner(
    *,
    batch_manifest: str | Path,
    template: str | Path,
    output_dir: str | Path,
    qc_project_file_name: str = "main.py",
    max_batches: int | None = None,
    resume: bool = False,
    skip_completed: bool = True,
    stop_on_failure: bool = True,
    poll_seconds: int = 20,
    compile_timeout_seconds: int = 600,
    backtest_timeout_seconds: int = 3600,
    execute: bool = False,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    state_path = output_path / "baseline_exit_overlay_qc_gap_rest_runner_state.json"
    summary_path = output_path / "baseline_exit_overlay_qc_gap_rest_runner_summary.json"

    manifest_rows = list(_iter_jsonl(batch_manifest))
    state_rows = _merge_existing_state(
        _state_rows_from_manifest(manifest_rows),
        _read_json(state_path, {"batches": {}}) if resume else {"batches": {}},
    )

    blockers = []
    if not Path(template).exists():
        blockers.append({"reason": "missing_template_file", "path": str(template)})

    user_id = os.environ.get("QC_USER_ID")
    api_token = os.environ.get("QC_API_TOKEN")
    project_id = os.environ.get("QC_PROJECT_ID")

    if execute:
        if not user_id:
            blockers.append({"reason": "missing_env_var", "env_var": "QC_USER_ID"})
        if not api_token:
            blockers.append({"reason": "missing_env_var", "env_var": "QC_API_TOKEN"})
        if not project_id:
            blockers.append({"reason": "missing_env_var", "env_var": "QC_PROJECT_ID"})

    for row in state_rows.values():
        if not Path(row["payload_b64_path"]).exists():
            blockers.append({"reason": "missing_payload_b64_path", "batch_id": row["batch_id"], "path": row["payload_b64_path"]})

    if blockers:
        summary = {
            "adapter_type": ADAPTER_TYPE,
            "artifact_type": ARTIFACT_TYPE,
            "contract": CONTRACT,
            "is_ready": False,
            "readiness_state": "blocked",
            "blocker_count": len(blockers),
            "blockers": blockers,
            "execute": execute,
            "paths": {"state_path": str(state_path), "summary_path": str(summary_path)},
        }
        _write_json(state_path, {"adapter_type": ADAPTER_TYPE, "artifact_type": ARTIFACT_TYPE, "contract": CONTRACT, "batches": state_rows})
        _write_json(summary_path, summary)
        return summary

    template_text = Path(template).read_text(encoding="utf-8")
    client = QuantConnectRestClient(user_id, api_token, int(project_id)) if execute else None
    if execute and client is not None:
        client.authenticate()

    started_count = 0
    completed_count_this_run = 0
    failed_count_this_run = 0
    skipped_count_this_run = 0
    run_errors = []

    for row in sorted(state_rows.values(), key=lambda x: x["batch_index"]):
        if skip_completed and row.get("status") == "completed":
            skipped_count_this_run += 1
            continue
        if max_batches is not None and started_count >= max_batches:
            break

        started_count += 1
        batch_id = row["batch_id"]
        row["status"] = "running" if execute else "dry_run_ready"
        row["started_at_utc"] = row.get("started_at_utc") or _utc_now()
        row["updated_at_utc"] = _utc_now()

        try:
            payload_b64 = Path(row["payload_b64_path"]).read_text(encoding="utf-8").strip()
            code = _render_template(template_text, batch_id=batch_id, payload_b64=payload_b64)

            batch_dir = output_path / "generated_scripts"
            batch_dir.mkdir(parents=True, exist_ok=True)
            generated_script_path = batch_dir / f"{batch_id}_{qc_project_file_name}"
            generated_script_path.write_text(code, encoding="utf-8")
            row["generated_script_path"] = str(generated_script_path)

            if not execute:
                continue

            assert client is not None
            backtest_name = f"SignalForge baseline exit overlay gap quote export {batch_id}"
            row["backtest_name"] = backtest_name

            client.update_file(qc_project_file_name, code)

            compile_id = client.create_compile()
            row["compile_id"] = compile_id
            row["compile_state"] = "InQueue"
            row["updated_at_utc"] = _utc_now()
            _write_json(state_path, {"adapter_type": ADAPTER_TYPE, "artifact_type": ARTIFACT_TYPE, "contract": CONTRACT, "batches": state_rows, "updated_at_utc": _utc_now()})

            compile_result = client.wait_for_compile(
                compile_id=compile_id,
                poll_seconds=poll_seconds,
                timeout_seconds=compile_timeout_seconds,
            )
            row["compile_state"] = compile_result.get("state")

            backtest_create = client.create_backtest(compile_id=compile_id, backtest_name=backtest_name)
            backtest = backtest_create.get("backtest") or {}
            backtest_id = backtest.get("backtestId") or backtest_create.get("backtestId")
            if not backtest_id:
                raise RuntimeError(f"Backtest create response missing backtestId: {backtest_create}")

            row["backtest_id"] = str(backtest_id)
            row["backtest_status"] = backtest.get("status")
            row["updated_at_utc"] = _utc_now()
            _write_json(state_path, {"adapter_type": ADAPTER_TYPE, "artifact_type": ARTIFACT_TYPE, "contract": CONTRACT, "batches": state_rows, "updated_at_utc": _utc_now()})

            backtest_result = client.wait_for_backtest(
                backtest_id=str(backtest_id),
                poll_seconds=poll_seconds,
                timeout_seconds=backtest_timeout_seconds,
            )
            final_backtest = backtest_result.get("backtest") or {}

            row["status"] = "completed"
            row["backtest_status"] = final_backtest.get("status")
            row["backtest_completed"] = bool(final_backtest.get("completed"))
            row["completed_at_utc"] = _utc_now()
            row["updated_at_utc"] = _utc_now()
            completed_count_this_run += 1

        except Exception as exc:
            failed_count_this_run += 1
            row["status"] = "failed"
            row["error_message"] = str(exc)
            row["updated_at_utc"] = _utc_now()
            run_errors.append({"batch_id": batch_id, "batch_index": row["batch_index"], "error_message": str(exc)})
            if stop_on_failure:
                break
        finally:
            _write_json(state_path, {"adapter_type": ADAPTER_TYPE, "artifact_type": ARTIFACT_TYPE, "contract": CONTRACT, "batches": state_rows, "updated_at_utc": _utc_now()})

    pull_paths = _write_research_pull_lists(output_path, state_rows)
    status_counts: dict[str, int] = {}
    for row in state_rows.values():
        status = str(row.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1

    completed_rows = _completed_rows(state_rows)

    summary = {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": ARTIFACT_TYPE,
        "contract": CONTRACT,
        "is_ready": True,
        "readiness_state": (
            "runner_complete"
            if status_counts.get("pending", 0) == 0 and status_counts.get("running", 0) == 0 and status_counts.get("failed", 0) == 0
            else "runner_partial_or_pending"
        ),
        "blocker_count": 0,
        "blockers": [],
        "warning_count": len(run_errors),
        "warnings": run_errors[:100],
        "does_download_from_quantconnect": False,
        "does_read_object_store_via_api": False,
        "requires_research_notebook_text_export": True,
        "execute": execute,
        "input_batch_count": len(manifest_rows),
        "status_counts": dict(sorted(status_counts.items())),
        "started_count_this_run": started_count,
        "completed_count_this_run": completed_count_this_run,
        "failed_count_this_run": failed_count_this_run,
        "skipped_count_this_run": skipped_count_this_run,
        "completed_batch_count": len(completed_rows),
        "completed_expected_manifest_keys_count": len(completed_rows),
        "qc_project_id": int(project_id) if project_id else None,
        "qc_project_file_name": qc_project_file_name,
        "next_step": "run_research_notebook_object_store_text_export_for_completed_manifest_keys",
        "paths": {
            "state_path": str(state_path),
            "summary_path": str(summary_path),
            **pull_paths,
        },
    }
    _write_json(summary_path, summary)
    return summary

