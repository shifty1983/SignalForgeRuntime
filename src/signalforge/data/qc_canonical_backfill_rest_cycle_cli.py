from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


def read_jsonl(path: Path):
    with path.open("r", encoding="utf-8-sig", errors="ignore") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def write_lines(path: Path, rows: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(rows) + ("\n" if rows else ""), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-index", required=True)
    parser.add_argument("--template", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--qc-file-name", default="main.py")
    parser.add_argument("--start-at", default="")
    parser.add_argument("--max-batches", type=int, default=0)
    parser.add_argument("--sleep-between-batches-seconds", type=int, default=5)
    parser.add_argument("--poll-seconds", type=int, default=20)
    parser.add_argument("--compile-timeout-seconds", type=int, default=600)
    parser.add_argument("--backtest-timeout-seconds", type=int, default=3600)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    batch_index_path = Path(args.batch_index)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = list(read_jsonl(batch_index_path))

    if args.start_at:
        found = False
        filtered = []
        for row in rows:
            if row.get("batch_id") == args.start_at:
                found = True
            if found:
                filtered.append(row)
        rows = filtered

    if args.max_batches and args.max_batches > 0:
        rows = rows[: args.max_batches]

    execution_rows: list[dict[str, Any]] = []
    manifest_keys: list[str] = []
    failed_rows: list[dict[str, Any]] = []

    for i, row in enumerate(rows, start=1):
        batch_id = str(row["batch_id"])
        result_path = output_dir / f"{batch_id}_execution_result.json"

        if args.resume and result_path.exists():
            result = read_json(result_path)
            print(f"[{i}/{len(rows)}] SKIP existing {batch_id}")
        else:
            print(f"[{i}/{len(rows)}] RUN {batch_id}")

            cmd = [
                sys.executable,
                "-m",
                "signalforge.data.qc_canonical_backfill_rest_runner_cli",
                "--batch-json",
                str(row["batch_json"]),
                "--payload-b64-path",
                str(row["payload_b64_path"]),
                "--template",
                args.template,
                "--output-dir",
                str(output_dir),
                "--qc-file-name",
                args.qc_file_name,
                "--poll-seconds",
                str(args.poll_seconds),
                "--compile-timeout-seconds",
                str(args.compile_timeout_seconds),
                "--backtest-timeout-seconds",
                str(args.backtest_timeout_seconds),
            ]

            proc = subprocess.run(cmd, capture_output=True, text=True)

            log_path = output_dir / f"{batch_id}_cycle_stdout_stderr.txt"
            log_path.write_text(
                "STDOUT:\n" + proc.stdout + "\n\nSTDERR:\n" + proc.stderr,
                encoding="utf-8",
            )

            if result_path.exists():
                result = read_json(result_path)
            else:
                result = {
                    "is_ready": False,
                    "readiness_state": "runner_result_missing",
                    "execution_state": {
                        "batch_id": batch_id,
                        "error": f"runner exited rc={proc.returncode}",
                    },
                    "blockers": ["runner_result_missing"],
                }
                write_json(result_path, result)

            if args.sleep_between_batches_seconds > 0:
                time.sleep(args.sleep_between_batches_seconds)

        state = result.get("execution_state") or {}
        manifest_key = state.get("manifest_key")
        failure_key = state.get("failure_key")

        execution_row = {
            "batch_id": batch_id,
            "is_ready": bool(result.get("is_ready")),
            "readiness_state": result.get("readiness_state"),
            "manifest_key": manifest_key,
            "failure_key": failure_key,
            "row_count": state.get("row_count"),
            "part_count": state.get("part_count"),
            "backtest_id": state.get("backtest_id"),
            "compile_id": state.get("compile_id"),
            "blockers": result.get("blockers") or [],
            "batch_json": row.get("batch_json"),
            "payload_b64_path": row.get("payload_b64_path"),
        }
        execution_rows.append(execution_row)

        if result.get("is_ready") and manifest_key:
            manifest_keys.append(str(manifest_key))
        else:
            failed_rows.append(execution_row)

        write_json(output_dir / "signalforge_qc_canonical_backfill_cycle_progress.json", {
            "processed_count": len(execution_rows),
            "success_count": len(manifest_keys),
            "failed_count": len(failed_rows),
            "latest_batch_id": batch_id,
        })

    summary = {
        "adapter_type": "qc_canonical_backfill_rest_cycle_runner",
        "artifact_type": "signalforge_qc_canonical_backfill_rest_cycle",
        "is_ready": len(failed_rows) == 0 and len(manifest_keys) > 0,
        "readiness_state": "cycle_complete" if len(failed_rows) == 0 and len(manifest_keys) > 0 else "cycle_completed_with_failures",
        "batch_index": str(batch_index_path),
        "requested_batch_count": len(rows),
        "success_count": len(manifest_keys),
        "failed_count": len(failed_rows),
        "manifest_key_count": len(manifest_keys),
        "paths": {
            "summary": str(output_dir / "signalforge_qc_canonical_backfill_cycle_summary.json"),
            "execution_rows": str(output_dir / "signalforge_qc_canonical_backfill_cycle_execution_rows.jsonl"),
            "manifest_keys_txt": str(output_dir / "signalforge_qc_canonical_backfill_manifest_keys.txt"),
            "manifest_keys_json": str(output_dir / "signalforge_qc_canonical_backfill_manifest_keys.json"),
            "failed_rows": str(output_dir / "signalforge_qc_canonical_backfill_failed_batches.jsonl"),
        },
        "blockers": [] if not failed_rows else ["one_or_more_batches_failed"],
    }

    with (output_dir / "signalforge_qc_canonical_backfill_cycle_execution_rows.jsonl").open("w", encoding="utf-8") as f:
        for r in execution_rows:
            f.write(json.dumps(r, sort_keys=True, default=str) + "\n")

    with (output_dir / "signalforge_qc_canonical_backfill_failed_batches.jsonl").open("w", encoding="utf-8") as f:
        for r in failed_rows:
            f.write(json.dumps(r, sort_keys=True, default=str) + "\n")

    write_lines(output_dir / "signalforge_qc_canonical_backfill_manifest_keys.txt", manifest_keys)
    write_json(output_dir / "signalforge_qc_canonical_backfill_manifest_keys.json", {
        "artifact_type": "signalforge_qc_canonical_backfill_manifest_key_list",
        "manifest_key_count": len(manifest_keys),
        "manifest_keys": manifest_keys,
    })
    write_json(output_dir / "signalforge_qc_canonical_backfill_cycle_summary.json", summary)

    print(json.dumps(summary, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
