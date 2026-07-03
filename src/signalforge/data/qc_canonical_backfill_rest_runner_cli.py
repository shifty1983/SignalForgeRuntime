from __future__ import annotations

import argparse
import base64
import json
import os
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

import requests


BASE_URL = "https://www.quantconnect.com/api/v2"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


@dataclass
class RunState:
    batch_id: str
    batch_json: str
    payload_b64_path: str
    backtest_name: str
    compile_id: str | None = None
    compile_state: str | None = None
    backtest_id: str | None = None
    backtest_status: str | None = None
    backtest_completed: bool | None = None
    manifest_key: str | None = None
    failure_key: str | None = None
    row_count: int | None = None
    part_count: int | None = None
    error: str | None = None


class QuantConnectRestClient:
    def __init__(self, user_id: str, api_token: str, project_id: int):
        self.user_id = user_id
        self.api_token = api_token
        self.project_id = project_id

    def _headers(self) -> dict[str, str]:
        stamp = str(int(time.time()))
        token_hash = sha256(f"{self.api_token}:{stamp}".encode("utf-8")).hexdigest()
        authentication = f"{self.user_id}:{token_hash}".encode("utf-8")
        authentication = base64.b64encode(authentication).decode("ascii")
        return {
            "Authorization": "Basic " + authentication,
            "Timestamp": stamp,
            "Content-Type": "application/json",
        }

    def post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = requests.post(
            BASE_URL + endpoint,
            headers=self._headers(),
            json=payload,
            timeout=120,
        )
        try:
            value = response.json()
        except Exception:
            value = {"status_code": response.status_code, "text": response.text}
        if response.status_code >= 400:
            raise RuntimeError(f"QuantConnect REST error endpoint={endpoint} status={response.status_code} payload={value}")
        return value

    def upsert_file(self, name: str, content: str) -> dict[str, Any]:
        payload = {
            "projectId": self.project_id,
            "name": name,
            "content": content,
        }

        update = self.post("/files/update", payload)
        if update.get("success") is True:
            return update

        create = self.post("/files/create", payload)
        if create.get("success") is not True:
            raise RuntimeError(f"Failed to create/update QC file {name}: update={update} create={create}")
        return create

    def create_compile(self) -> str:
        result = self.post("/compile/create", {"projectId": self.project_id})
        compile_id = result.get("compileId")
        if not compile_id:
            raise RuntimeError(f"Compile response missing compileId: {result}")
        return str(compile_id)

    def read_compile(self, compile_id: str) -> dict[str, Any]:
        return self.post("/compile/read", {"projectId": self.project_id, "compileId": compile_id})

    def wait_for_compile(self, compile_id: str, poll_seconds: int, timeout_seconds: int) -> dict[str, Any]:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            result = self.read_compile(compile_id)
            state = str(result.get("state") or result.get("compile", {}).get("state") or "")
            if state.lower() in {"buildsuccess", "success", "completed"}:
                return result
            if state.lower() in {"builderror", "error", "failed"}:
                raise RuntimeError(f"Compile failed: {result}")
            time.sleep(poll_seconds)
        raise TimeoutError(f"Compile timed out compile_id={compile_id}")

    def create_backtest(self, compile_id: str, backtest_name: str) -> dict[str, Any]:
        return self.post(
            "/backtests/create",
            {
                "projectId": self.project_id,
                "compileId": compile_id,
                "backtestName": backtest_name,
            },
        )

    def read_backtest(self, backtest_id: str) -> dict[str, Any]:
        return self.post("/backtests/read", {"projectId": self.project_id, "backtestId": backtest_id})

    def wait_for_backtest(self, backtest_id: str, poll_seconds: int, timeout_seconds: int) -> dict[str, Any]:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            result = self.read_backtest(backtest_id)
            backtest = result.get("backtest") or {}
            completed = bool(backtest.get("completed"))
            status = str(backtest.get("status") or "")
            if completed:
                return result
            if status.lower() in {"error", "runtimeerror", "stopped"}:
                raise RuntimeError(f"Backtest failed: {result}")
            time.sleep(poll_seconds)
        raise TimeoutError(f"Backtest timed out backtest_id={backtest_id}")


def render_template(template_text: str, batch_id: str, payload_b64: str) -> str:
    return (
        template_text
        .replace("__BATCH_ID__", batch_id)
        .replace("__BATCH_PAYLOAD_B64__", payload_b64.strip())
    )


def runtime_stats(backtest_result: dict[str, Any]) -> dict[str, Any]:
    backtest = backtest_result.get("backtest") or {}
    for key in ["runtimeStatistics", "runtime_statistics", "RuntimeStatistics", "statistics"]:
        value = backtest.get(key)
        if isinstance(value, dict):
            return value
    return {}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", type=int, required=False)
    parser.add_argument("--batch-json", required=True)
    parser.add_argument("--payload-b64-path", required=True)
    parser.add_argument("--template", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--qc-file-name", default="main.py")
    parser.add_argument("--poll-seconds", type=int, default=20)
    parser.add_argument("--compile-timeout-seconds", type=int, default=600)
    parser.add_argument("--backtest-timeout-seconds", type=int, default=3600)
    args = parser.parse_args()

    user_id = os.environ.get("QC_USER_ID") or os.environ.get("QUANTCONNECT_USER_ID")
    api_token = os.environ.get("QC_API_TOKEN") or os.environ.get("QUANTCONNECT_API_TOKEN")
    project_id = args.project_id or os.environ.get("QC_PROJECT_ID") or os.environ.get("QUANTCONNECT_PROJECT_ID")

    if not user_id or not api_token:
        raise SystemExit("Missing QuantConnect credentials. Set QC_USER_ID and QC_API_TOKEN.")

    if not project_id:
        raise SystemExit("Missing QuantConnect project id. Set QC_PROJECT_ID or pass --project-id.")

    project_id = int(project_id)

    batch = json.loads(Path(args.batch_json).read_text(encoding="utf-8-sig"))
    batch_id = str(batch.get("batch_id") or Path(args.batch_json).stem)

    payload_b64 = Path(args.payload_b64_path).read_text(encoding="utf-8").strip()
    template_text = Path(args.template).read_text(encoding="utf-8")
    code = render_template(template_text, batch_id=batch_id, payload_b64=payload_b64)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    state = RunState(
        batch_id=batch_id,
        batch_json=args.batch_json,
        payload_b64_path=args.payload_b64_path,
        backtest_name=f"SignalForge canonical option quote backfill {batch_id}",
    )

    client = QuantConnectRestClient(user_id=user_id, api_token=api_token, project_id=project_id)

    try:
        client.upsert_file(args.qc_file_name, code)

        compile_id = client.create_compile()
        state.compile_id = compile_id
        state.compile_state = "created"
        write_json(output_dir / f"{batch_id}_execution_state.json", asdict(state))

        compile_result = client.wait_for_compile(
            compile_id=compile_id,
            poll_seconds=args.poll_seconds,
            timeout_seconds=args.compile_timeout_seconds,
        )
        state.compile_state = str(compile_result.get("state") or compile_result.get("compile", {}).get("state") or "unknown")

        bt_create = client.create_backtest(compile_id=compile_id, backtest_name=state.backtest_name)
        backtest = bt_create.get("backtest") or {}
        backtest_id = backtest.get("backtestId") or bt_create.get("backtestId")
        if not backtest_id:
            raise RuntimeError(f"Backtest create missing backtestId: {bt_create}")

        state.backtest_id = str(backtest_id)
        state.backtest_status = str(backtest.get("status") or "")
        write_json(output_dir / f"{batch_id}_execution_state.json", asdict(state))

        bt_result = client.wait_for_backtest(
            backtest_id=str(backtest_id),
            poll_seconds=args.poll_seconds,
            timeout_seconds=args.backtest_timeout_seconds,
        )

        final_bt = bt_result.get("backtest") or {}
        state.backtest_status = str(final_bt.get("status") or "")
        state.backtest_completed = bool(final_bt.get("completed"))

        stats = runtime_stats(bt_result)
        state.manifest_key = stats.get("SignalForgeBackfillManifestKey")
        state.failure_key = stats.get("SignalForgeBackfillFailureKey")
        state.part_count = int(stats.get("SignalForgeBackfillPartCount")) if stats.get("SignalForgeBackfillPartCount") else None
        state.row_count = int(stats.get("SignalForgeBackfillRowCount")) if stats.get("SignalForgeBackfillRowCount") else None

        write_json(output_dir / f"{batch_id}_backtest_read.json", bt_result)

    except Exception as exc:
        state.error = str(exc)

    success = (
        state.error is None
        and state.backtest_completed is True
        and state.manifest_key
        and not state.failure_key
    )

    blockers = []
    if state.error is not None:
        blockers.append("qc_backfill_rest_runner_error")
    if state.backtest_completed is not True:
        blockers.append("qc_backfill_backtest_not_completed")
    if state.failure_key:
        blockers.append("qc_backfill_algorithm_failure_written_to_object_store")
    if not state.manifest_key:
        blockers.append("qc_backfill_manifest_key_missing")

    result = {
        "adapter_type": "qc_canonical_backfill_rest_runner",
        "artifact_type": "signalforge_qc_canonical_backfill_rest_execution",
        "is_ready": bool(success),
        "readiness_state": "object_store_manifest_available" if success else "backtest_completed_but_manifest_unavailable",
        "execution_state": asdict(state),
        "next_step": "run_research_notebook_object_store_text_export_for_manifest_key" if success else "read_object_store_failure_key",
        "blockers": blockers,
    }

    write_json(output_dir / f"{batch_id}_execution_state.json", asdict(state))
    write_json(output_dir / f"{batch_id}_execution_result.json", result)

    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()




