from __future__ import annotations

import argparse
import base64
import gzip
import json
import os
import re
import sys
import time
from hashlib import sha256
from pathlib import Path
from typing import Any

import requests


BASE_URL = "https://www.quantconnect.com/api/v2"


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def get_headers() -> dict[str, str]:
    user_id = require_env("QC_USER_ID")
    api_token = require_env("QC_API_TOKEN")

    timestamp = f"{int(time.time())}"
    token_hash = sha256(f"{api_token}:{timestamp}".encode("utf-8")).hexdigest()
    auth = base64.b64encode(f"{user_id}:{token_hash}".encode("utf-8")).decode("ascii")

    return {
        "Authorization": f"Basic {auth}",
        "Timestamp": timestamp,
    }


def qc_post(endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = requests.post(
        f"{BASE_URL}{endpoint}",
        headers=get_headers(),
        json=payload,
        timeout=120,
    )

    try:
        data = response.json()
    except Exception:
        raise RuntimeError(
            f"Non-JSON response from {endpoint}: "
            f"status={response.status_code}, text={response.text[:1000]}"
        )

    if response.status_code >= 400:
        raise RuntimeError(
            f"HTTP error from {endpoint}: status={response.status_code}, payload={data}"
        )

    if data.get("success") is False:
        raise RuntimeError(f"QC API failure from {endpoint}: {data}")

    return data


def create_qc_file(project_id: int, qc_file_name: str, content: str) -> dict[str, Any]:
    return qc_post(
        "/files/create",
        {
            "projectId": project_id,
            "name": qc_file_name,
            "content": content,
            "codeSourceId": "SignalForge Option Behavior V2 REST Runner",
        },
    )


def update_qc_file(project_id: int, qc_file_name: str, content: str) -> dict[str, Any]:
    return qc_post(
        "/files/update",
        {
            "projectId": project_id,
            "name": qc_file_name,
            "content": content,
            "codeSourceId": "SignalForge Option Behavior V2 REST Runner",
        },
    )


def create_or_update_qc_file(project_id: int, qc_file_name: str, content: str) -> dict[str, Any]:
    try:
        result = update_qc_file(project_id, qc_file_name, content)
        result["file_write_mode"] = "update"
        return result
    except RuntimeError as update_error:
        message = str(update_error)

        # New payload modules will often fail update because they don't exist yet.
        # Fall back to create. If create fails because it already exists, retry update.
        try:
            result = create_qc_file(project_id, qc_file_name, content)
            result["file_write_mode"] = "create"
            return result
        except RuntimeError as create_error:
            create_message = str(create_error)

            already_exists_tokens = [
                "already exists",
                "exists already",
                "file exists",
                "same name",
            ]

            if any(token in create_message.lower() for token in already_exists_tokens):
                result = update_qc_file(project_id, qc_file_name, content)
                result["file_write_mode"] = "update_after_create_conflict"
                return result

            raise RuntimeError(
                "Failed to update or create QC file. "
                f"update_error={message}; create_error={create_message}"
            )


def create_compile(project_id: int) -> str:
    data = qc_post("/compile/create", {"projectId": project_id})
    compile_id = data.get("compileId")
    if not compile_id:
        raise RuntimeError(f"Compile response missing compileId: {data}")
    return compile_id


def wait_for_compile(project_id: int, compile_id: str, timeout_seconds: int, poll_seconds: int) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds

    while time.time() < deadline:
        data = qc_post(
            "/compile/read",
            {
                "projectId": project_id,
                "compileId": compile_id,
            },
        )

        state = data.get("state")
        print(f"compile_state={state}", flush=True)

        if state == "BuildSuccess":
            return data

        if state == "BuildError":
            raise RuntimeError(f"Compile failed: {json.dumps(data, indent=2)}")

        time.sleep(poll_seconds)

    raise TimeoutError(f"Compile did not finish within {timeout_seconds} seconds")


def create_backtest(project_id: int, compile_id: str, backtest_name: str) -> dict[str, Any]:
    return qc_post(
        "/backtests/create",
        {
            "projectId": project_id,
            "compileId": compile_id,
            "backtestName": backtest_name,
        },
    )


def chunk_text(text: str, chunk_size: int) -> list[str]:
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]


def build_payload_modules(
    batch: dict[str, Any],
    payload_output_dir: Path,
    module_prefix: str,
    chunk_size: int,
) -> tuple[list[dict[str, str]], list[str]]:
    compact_json = json.dumps(batch, separators=(",", ":"), sort_keys=True)
    compressed_b64 = base64.b64encode(
        gzip.compress(compact_json.encode("utf-8"), compresslevel=9)
    ).decode("ascii")

    chunks = chunk_text(compressed_b64, chunk_size)

    payload_output_dir.mkdir(parents=True, exist_ok=True)

    files = []
    module_names = []

    for idx, chunk in enumerate(chunks):
        module_name = f"{module_prefix}_{idx:04d}"
        file_name = f"{module_name}.py"
        content = (
            "# Auto-generated SignalForge QuantConnect batch payload chunk.\n"
            "# Do not edit manually.\n"
            f"PART = {chunk!r}\n"
        )

        if len(content) >= 64000:
            raise RuntimeError(
                f"Payload chunk file {file_name} is still too large: {len(content)} chars"
            )

        local_path = payload_output_dir / file_name
        local_path.write_text(content, encoding="utf-8")

        files.append(
            {
                "qc_file_name": file_name,
                "local_path": str(local_path),
                "content": content,
                "char_count": len(content),
            }
        )
        module_names.append(module_name)

    return files, module_names


def replace_initial_assignments_with_loader(
    template: str,
    batch_id: str,
    module_names: list[str],
) -> str:
    import_lines = [
        "import json",
        "import gzip",
        "import base64",
    ]

    part_imports = [
        f"from {module_name} import PART as _SF_BATCH_PART_{idx:04d}"
        for idx, module_name in enumerate(module_names)
    ]

    part_refs = ", ".join(
        [f"_SF_BATCH_PART_{idx:04d}" for idx in range(len(module_names))]
    )

    loader_block = "\n".join(
        import_lines
        + part_imports
        + [
            "",
            f"BATCH_ID = {batch_id!r}",
            f"BATCH_PAYLOAD_B64 = ''.join([{part_refs}])",
            "",
            "# Compatibility aliases for templates that use BATCH/BATCH_JSON directly.",
            "BATCH_JSON = gzip.decompress(base64.b64decode(BATCH_PAYLOAD_B64.encode('ascii'))).decode('utf-8')",
            "BATCH = json.loads(BATCH_JSON)",
        ]
    )

    rendered = template

    # Remove/neutralize any existing constants so the chunked loader is the source of truth.
    rendered = re.sub(
        r"^BATCH_PAYLOAD_B64\s*=.*$",
        "# BATCH_PAYLOAD_B64 loaded from compressed payload chunks above",
        rendered,
        flags=re.MULTILINE,
    )

    rendered = re.sub(
        r"^BATCH_JSON\s*=.*$",
        "# BATCH_JSON loaded from compressed payload chunks above",
        rendered,
        flags=re.MULTILINE,
    )

    rendered = re.sub(
        r"^BATCH\s*=.*$",
        "# BATCH loaded from compressed payload chunks above",
        rendered,
        flags=re.MULTILINE,
    )

    if re.search(r"^BATCH_ID\s*=.*$", rendered, flags=re.MULTILINE):
        rendered = re.sub(
            r"^BATCH_ID\s*=.*$",
            loader_block,
            rendered,
            count=1,
            flags=re.MULTILINE,
        )
    else:
        rendered = loader_block + "\n\n" + rendered

    return rendered


def render_algorithm(
    template_path: Path,
    batch_path: Path,
    rendered_output_path: Path,
    payload_output_dir: Path,
    module_prefix: str,
    chunk_size: int,
) -> dict[str, Any]:
    template = template_path.read_text(encoding="utf-8")
    batch = json.loads(batch_path.read_text(encoding="utf-8-sig"))

    batch_id = str(batch.get("batch_id") or batch_path.stem)

    payload_files, module_names = build_payload_modules(
        batch=batch,
        payload_output_dir=payload_output_dir,
        module_prefix=module_prefix,
        chunk_size=chunk_size,
    )

    rendered = replace_initial_assignments_with_loader(
        template=template,
        batch_id=batch_id,
        module_names=module_names,
    )

    rendered_output_path.parent.mkdir(parents=True, exist_ok=True)
    rendered_output_path.write_text(rendered, encoding="utf-8")

    if len(rendered) >= 64000:
        raise RuntimeError(
            f"Rendered main file is still too large: {len(rendered)} chars"
        )

    request_count = len(batch.get("requests") or [])
    contract_count = sum(len(req.get("contracts") or []) for req in batch.get("requests") or [])

    return {
        "batch_id": batch_id,
        "request_count": request_count,
        "contract_count": contract_count,
        "rendered_algorithm_path": str(rendered_output_path),
        "rendered_algorithm_char_count": len(rendered),
        "payload_file_count": len(payload_files),
        "payload_files": [
            {
                "qc_file_name": f["qc_file_name"],
                "local_path": f["local_path"],
                "char_count": f["char_count"],
            }
            for f in payload_files
        ],
    }, payload_files



def read_backtest(project_id: int, backtest_id: str) -> dict[str, Any]:
    return qc_post(
        "/backtests/read",
        {
            "projectId": project_id,
            "backtestId": backtest_id,
        },
    )


def extract_backtest_id(backtest_result: dict[str, Any]) -> str | None:
    candidates = [
        backtest_result.get("backtestId"),
        backtest_result.get("backtest_id"),
        backtest_result.get("id"),
    ]

    backtest = backtest_result.get("backtest")
    if isinstance(backtest, dict):
        candidates.extend(
            [
                backtest.get("backtestId"),
                backtest.get("backtest_id"),
                backtest.get("id"),
            ]
        )

    for candidate in candidates:
        if candidate:
            return str(candidate)

    return None


def _find_value_recursive(obj: Any, names: set[str]) -> Any:
    if isinstance(obj, dict):
        for key, value in obj.items():
            if str(key).lower() in names and value not in (None, ""):
                return value
        for value in obj.values():
            found = _find_value_recursive(value, names)
            if found not in (None, ""):
                return found

    if isinstance(obj, list):
        for value in obj:
            found = _find_value_recursive(value, names)
            if found not in (None, ""):
                return found

    return None


def summarize_backtest_progress(read_result: dict[str, Any]) -> dict[str, Any]:
    """
    Summarize QuantConnect backtest progress.

    Important:
    The top-level API response can contain success=True simply meaning the
    /backtests/read request succeeded. That is NOT the same as the backtest
    being completed. Only the nested backtest.completed field should drive
    completion.
    """
    backtest = read_result.get("backtest")
    if not isinstance(backtest, dict):
        backtest = {}

    status = (
        backtest.get("status")
        or backtest.get("state")
        or backtest.get("backtestStatus")
        or backtest.get("backtestState")
    )

    completed = backtest.get("completed")
    if completed in ("true", "True", "TRUE", 1, "1"):
        completed = True
    elif completed in ("false", "False", "FALSE", 0, "0"):
        completed = False

    error = (
        backtest.get("error")
        or backtest.get("errors")
        or backtest.get("stacktrace")
        or backtest.get("runtimeError")
    )

    statistics = backtest.get("statistics")
    if not isinstance(statistics, dict):
        statistics = {}

    runtime_statistics = backtest.get("runtimeStatistics")
    if not isinstance(runtime_statistics, dict):
        runtime_statistics = {}

    return {
        "status": status,
        "completed": completed,
        "error": error,
        "statistics_count": len(statistics),
        "runtime_statistics_count": len(runtime_statistics),
    }


def is_backtest_terminal(progress: dict[str, Any]) -> bool:
    status_text = str(progress.get("status") or "").lower()
    completed = progress.get("completed")
    error = progress.get("error")

    if error not in (None, "", [], {}):
        return True

    if completed is True:
        return True

    terminal_tokens = [
        "completed",
        "complete",
        "finished",
        "success",
        "failed",
        "error",
        "cancelled",
        "canceled",
        "stopped",
    ]

    return any(token in status_text for token in terminal_tokens)


def iter_backtest_progress(
    project_id: int,
    backtest_id: str,
    poll_seconds: int,
    max_polls: int,
):
    poll_index = 0

    while True:
        poll_index += 1
        read_result = read_backtest(project_id, backtest_id)
        progress = summarize_backtest_progress(read_result)

        progress_row = {
            "poll_index": poll_index,
            "backtest_id": backtest_id,
            "status": progress.get("status"),
            "completed": progress.get("completed"),
            "statistics_count": progress.get("statistics_count"),
            "error": progress.get("error"),
        }

        print("backtest_progress=" + json.dumps(progress_row, sort_keys=True, default=str), flush=True)

        yield read_result, progress

        if is_backtest_terminal(progress):
            return

        if max_polls and poll_index >= max_polls:
            print(
                "backtest_progress_monitor_stopped=max_polls_reached "
                f"max_polls={max_polls}",
                flush=True,
            )
            return

        time.sleep(poll_seconds)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render and submit one SignalForge QC option behavior v2 batch."
    )
    parser.add_argument("--project-id", type=int, default=int(os.environ.get("QC_PROJECT_ID", "0")))
    parser.add_argument("--qc-file-name", default=os.environ.get("QC_FILE_NAME", "main.py"))
    parser.add_argument("--template", required=True)
    parser.add_argument("--batch", required=True)
    parser.add_argument("--rendered-output", required=True)
    parser.add_argument("--payload-output-dir", default=None)
    parser.add_argument("--payload-module-prefix", default="sf_option_behavior_v2_payload")
    parser.add_argument("--payload-chunk-size", type=int, default=45000)
    parser.add_argument("--backtest-name", default=None)
    parser.add_argument("--compile-timeout-seconds", type=int, default=900)
    parser.add_argument("--poll-seconds", type=int, default=10)
    parser.add_argument("--submit", action="store_true")
    parser.add_argument("--monitor-backtest", action="store_true")
    parser.add_argument("--backtest-poll-seconds", type=int, default=30)
    parser.add_argument("--backtest-max-polls", type=int, default=0)
    args = parser.parse_args()

    if not args.project_id:
        raise RuntimeError("Provide --project-id or set QC_PROJECT_ID.")

    template_path = Path(args.template)
    batch_path = Path(args.batch)
    rendered_path = Path(args.rendered_output)
    payload_output_dir = (
        Path(args.payload_output_dir)
        if args.payload_output_dir
        else rendered_path.parent / "payload_chunks"
    )

    render_meta, payload_files = render_algorithm(
        template_path=template_path,
        batch_path=batch_path,
        rendered_output_path=rendered_path,
        payload_output_dir=payload_output_dir,
        module_prefix=args.payload_module_prefix,
        chunk_size=args.payload_chunk_size,
    )

    backtest_name = args.backtest_name or f"sf_option_behavior_v2_{render_meta['batch_id']}"

    summary = {
        "adapter_type": "option_behavior_v2_qc_rest_runner",
        "artifact_type": "signalforge_option_behavior_v2_qc_rest_run",
        "is_ready": True,
        "blocker_count": 0,
        "blockers": [],
        "project_id": args.project_id,
        "qc_file_name": args.qc_file_name,
        "template": str(template_path),
        "batch": str(batch_path),
        "backtest_name": backtest_name,
        "render": render_meta,
        "submitted": False,
    }

    if not args.submit:
        print(json.dumps(summary, indent=2, sort_keys=True))
        print("\nRendered only. Add --submit to upload/compile/backtest.")
        return 0

    print("uploading_payload_chunks=true", flush=True)
    for payload_file in payload_files:
        print(
            f"updating_qc_file={payload_file['qc_file_name']} chars={len(payload_file['content'])}",
            flush=True,
        )
        create_or_update_qc_file(
            project_id=args.project_id,
            qc_file_name=payload_file["qc_file_name"],
            content=payload_file["content"],
        )

    print(f"updating_qc_file={args.qc_file_name} chars={render_meta['rendered_algorithm_char_count']}", flush=True)
    rendered_code = rendered_path.read_text(encoding="utf-8")
    create_or_update_qc_file(args.project_id, args.qc_file_name, rendered_code)

    print("creating_compile=true", flush=True)
    compile_id = create_compile(args.project_id)

    print(f"compile_id={compile_id}", flush=True)
    compile_result = wait_for_compile(
        project_id=args.project_id,
        compile_id=compile_id,
        timeout_seconds=args.compile_timeout_seconds,
        poll_seconds=args.poll_seconds,
    )

    print("creating_backtest=true", flush=True)
    backtest_result = create_backtest(args.project_id, compile_id, backtest_name)

    backtest_id = extract_backtest_id(backtest_result)

    summary["submitted"] = True
    summary["compile_id"] = compile_id
    summary["compile_state"] = compile_result.get("state")
    summary["backtest_id"] = backtest_id
    summary["backtest_response"] = backtest_result

    if args.monitor_backtest:
        if not backtest_id:
            print("backtest_progress_monitor_skipped=missing_backtest_id", flush=True)
        else:
            print(
                f"backtest_progress_monitor_started=true backtest_id={backtest_id} "
                f"poll_seconds={args.backtest_poll_seconds}",
                flush=True,
            )

            final_read_result = None
            final_progress = None

            for read_result, progress in iter_backtest_progress(
                project_id=args.project_id,
                backtest_id=backtest_id,
                poll_seconds=args.backtest_poll_seconds,
                max_polls=args.backtest_max_polls,
            ):
                final_read_result = read_result
                final_progress = progress

            summary["backtest_final_progress"] = final_progress

            if final_read_result is not None:
                summary["backtest_final_read_keys"] = sorted(final_read_result.keys())

    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
