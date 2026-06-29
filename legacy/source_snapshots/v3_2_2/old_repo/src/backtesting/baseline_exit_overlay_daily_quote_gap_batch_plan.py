from __future__ import annotations

import argparse
import base64
import gzip
import json
from pathlib import Path
from typing import Any, Iterable


def _read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", errors="ignore") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc
            if isinstance(payload, dict):
                yield payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _gzip_base64_jsonl(rows: list[dict[str, Any]]) -> str:
    payload = "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows)
    compressed = gzip.compress(payload.encode("utf-8"))
    return base64.b64encode(compressed).decode("ascii")


def build_batch_plan(
    *,
    gap_requests_path: Path,
    output_dir: Path,
    max_request_rows_per_batch: int,
    max_missing_quote_dates_per_batch: int,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    batches_dir = output_dir / "batches"
    batches_dir.mkdir(parents=True, exist_ok=True)

    requests = list(_read_jsonl(gap_requests_path))

    batches: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []

    for row in requests:
        if current and (
            len(current) >= max_request_rows_per_batch
            or len(current) >= max_missing_quote_dates_per_batch
        ):
            batches.append(current)
            current = []
        current.append(row)

    if current:
        batches.append(current)

    manifest_path = output_dir / "baseline_exit_overlay_daily_quote_gap_export_batch_manifest.jsonl"
    summary_path = output_dir / "baseline_exit_overlay_daily_quote_gap_export_batch_plan_summary.json"

    manifest_rows: list[dict[str, Any]] = []

    with manifest_path.open("w", encoding="utf-8", newline="\n") as manifest_handle:
        for i, batch in enumerate(batches, start=1):
            batch_id = f"baseline_exit_overlay_daily_quote_gap_batch_{i:06d}"
            payload_path = batches_dir / f"{batch_id}_payload_gzip_base64.txt"
            preview_path = batches_dir / f"{batch_id}_preview.jsonl"

            payload_path.write_text(_gzip_base64_jsonl(batch), encoding="utf-8")
            with preview_path.open("w", encoding="utf-8", newline="\n") as preview_handle:
                for row in batch[:100]:
                    preview_handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")

            quote_dates = [str(row.get("quote_date")) for row in batch if row.get("quote_date")]
            contracts = {str(row.get("contract_symbol")) for row in batch if row.get("contract_symbol")}

            manifest_row = {
                "adapter_type": "baseline_exit_overlay_daily_quote_gap_export_batch_plan_builder",
                "artifact_type": "signalforge_baseline_exit_overlay_daily_quote_gap_export_batch",
                "contract": "baseline_exit_overlay_daily_quote_gap_export_batch_plan",
                "batch_id": batch_id,
                "batch_index": i,
                "request_row_count": len(batch),
                "missing_quote_date_count": len(batch),
                "unique_contract_count": len(contracts),
                "min_quote_date": min(quote_dates) if quote_dates else None,
                "max_quote_date": max(quote_dates) if quote_dates else None,
                "payload_format": "gzip_base64_encoded_jsonl",
                "payload_path": str(payload_path),
                "preview_path": str(preview_path),
                "object_store_key": batch_id,
                "expected_quantconnect_output_grain": "one row per contract_symbol and quote_date",
            }
            manifest_rows.append(manifest_row)
            manifest_handle.write(json.dumps(manifest_row, sort_keys=True, separators=(",", ":")) + "\n")

    request_counts = [len(batch) for batch in batches]
    unique_contracts_all = {str(row.get("contract_symbol")) for row in requests if row.get("contract_symbol")}
    quote_dates_all = [str(row.get("quote_date")) for row in requests if row.get("quote_date")]

    summary = {
        "adapter_type": "baseline_exit_overlay_daily_quote_gap_export_batch_plan_builder",
        "artifact_type": "signalforge_baseline_exit_overlay_daily_quote_gap_export_batch_plan",
        "contract": "baseline_exit_overlay_daily_quote_gap_export_batch_plan",
        "is_ready": len(batches) > 0,
        "readiness_state": "ready_for_quantconnect_gap_batch_exports" if batches else "blocked_no_gap_batches",
        "blocker_count": 0 if batches else 1,
        "blockers": [] if batches else ["no_gap_batches"],
        "input_gap_export_request_row_count": len(requests),
        "batch_count": len(batches),
        "batch_payload_format": "gzip_base64_encoded_jsonl",
        "max_request_rows_per_batch": max_request_rows_per_batch,
        "max_missing_quote_dates_per_batch": max_missing_quote_dates_per_batch,
        "largest_batch_request_row_count": max(request_counts) if request_counts else 0,
        "smallest_batch_request_row_count": min(request_counts) if request_counts else 0,
        "total_missing_contract_quote_dates_requested": len(requests),
        "unique_gap_contract_count": len(unique_contracts_all),
        "min_quote_date": min(quote_dates_all) if quote_dates_all else None,
        "max_quote_date": max(quote_dates_all) if quote_dates_all else None,
        "does_call_quantconnect": False,
        "does_download_from_quantconnect": False,
        "does_generate_quote_data": False,
        "requires_quantconnect_export": len(batches) > 0,
        "requires_local_decode": True,
        "paths": {
            "batches_dir": str(batches_dir),
            "manifest_path": str(manifest_path),
            "summary_path": str(summary_path),
        },
    }
    _write_json(summary_path, summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch missing locked baseline quote requests for QC export.")
    parser.add_argument("--gap-export-requests", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--max-request-rows-per-batch", type=int, default=5000)
    parser.add_argument("--max-missing-quote-dates-per-batch", type=int, default=50000)
    args = parser.parse_args()

    summary = build_batch_plan(
        gap_requests_path=Path(args.gap_export_requests),
        output_dir=Path(args.output_dir),
        max_request_rows_per_batch=args.max_request_rows_per_batch,
        max_missing_quote_dates_per_batch=args.max_missing_quote_dates_per_batch,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
