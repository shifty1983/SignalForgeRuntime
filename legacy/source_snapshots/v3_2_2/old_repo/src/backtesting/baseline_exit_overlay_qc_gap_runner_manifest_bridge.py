from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable


def _iter_jsonl(path: str | Path) -> Iterable[dict[str, Any]]:
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


def build_compat_manifest(*, input_manifest: str | Path, output_dir: str | Path) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    rows_path = output_path / "baseline_exit_overlay_qc_gap_runner_compat_manifest.jsonl"
    summary_path = output_path / "baseline_exit_overlay_qc_gap_runner_compat_manifest_summary.json"

    rows = []
    for row in _iter_jsonl(input_manifest):
        batch_id = str(row["batch_id"])
        payload_path = row.get("batch_payload_b64_path") or row.get("payload_path")
        if not payload_path:
            raise ValueError(f"Batch {batch_id} missing payload_path/batch_payload_b64_path")

        compat = {
            **row,
            "adapter_type": "baseline_exit_overlay_qc_gap_runner_manifest_bridge",
            "artifact_type": "signalforge_baseline_exit_overlay_qc_gap_runner_compat_manifest_row",
            "contract": "baseline_exit_overlay_qc_gap_runner_compat_manifest",
            "batch_id": batch_id,
            "batch_index": int(row["batch_index"]),
            "request_row_count": int(row["request_row_count"]),
            "missing_quote_date_count": int(row.get("missing_quote_date_count") or row.get("request_row_count") or 0),
            "batch_payload_b64_path": str(payload_path),
            "expected_object_store_manifest_key": f"signalforge_portfolio_exit_contract_daily_quote_gap_{batch_id}_manifest",
            "expected_object_store_part_key_prefix": f"signalforge_portfolio_exit_contract_daily_quote_gap_{batch_id}_part_",
            "transfer_method": "inline_payload_in_quantconnect_project_file_then_object_store_to_research_notebook_text_to_local_decode",
            "does_select_strategy": False,
            "does_apply_exit_rule": False,
            "does_feed_exit_result_to_expectancy": False,
        }
        rows.append(compat)

    with rows_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")

    summary = {
        "adapter_type": "baseline_exit_overlay_qc_gap_runner_manifest_bridge",
        "artifact_type": "signalforge_baseline_exit_overlay_qc_gap_runner_compat_manifest",
        "contract": "baseline_exit_overlay_qc_gap_runner_compat_manifest",
        "is_ready": len(rows) > 0,
        "readiness_state": "ready_for_qc_gap_rest_runner" if rows else "blocked_no_rows",
        "blocker_count": 0 if rows else 1,
        "blockers": [] if rows else ["no_batch_rows"],
        "input_manifest": str(input_manifest),
        "output_row_count": len(rows),
        "total_missing_quote_date_count": sum(int(row["missing_quote_date_count"]) for row in rows),
        "paths": {"rows_path": str(rows_path), "summary_path": str(summary_path)},
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert baseline gap batch manifest to QC REST runner-compatible manifest.")
    parser.add_argument("--input-manifest", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    summary = build_compat_manifest(input_manifest=args.input_manifest, output_dir=args.output_dir)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
