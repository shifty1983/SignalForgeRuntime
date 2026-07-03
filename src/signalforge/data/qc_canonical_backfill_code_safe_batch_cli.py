from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any


def read_jsonl(path: Path):
    with path.open("r", encoding="utf-8-sig", errors="ignore") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True, default=str) + "\n")


def build_payload(batch: dict[str, Any]) -> tuple[str, int, int, str]:
    raw = json.dumps(batch, separators=(",", ":"), sort_keys=True).encode("utf-8")
    compressed = gzip.compress(raw)
    payload_b64 = base64.b64encode(compressed).decode("ascii")
    sha = hashlib.sha256(compressed).hexdigest()
    return payload_b64, len(raw), len(compressed), sha


def rendered_length(template_text: str, batch_id: str, payload_b64: str) -> int:
    code = (
        template_text
        .replace("__BATCH_ID__", batch_id)
        .replace("__BATCH_PAYLOAD_B64__", payload_b64.strip())
    )
    return len(code)


def make_batch(batch_id: str, requests: list[dict[str, Any]], source_requests: str) -> dict[str, Any]:
    symbols = sorted({str(r.get("symbol") or "").upper() for r in requests})
    dates = sorted({str(r.get("quote_date") or "")[:10] for r in requests})
    contract_count = sum(int(r.get("contract_count") or len(r.get("contracts") or [])) for r in requests)

    return {
        "batch_id": batch_id,
        "request_type": "option_quote_backfill",
        "source_requests": source_requests,
        "symbol_date_request_count": len(requests),
        "contract_request_count": contract_count,
        "unique_symbol_count": len(symbols),
        "unique_quote_date_count": len(dates),
        "symbols": symbols,
        "quote_date_min": min(dates) if dates else "",
        "quote_date_max": max(dates) if dates else "",
        "requests": requests,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requests", required=True)
    parser.add_argument("--template", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--payload-dir", required=True)
    parser.add_argument("--batch-id-prefix", default="qc_option_quote_backfill_prod_batch")
    parser.add_argument("--max-rendered-chars", type=int, default=60000)
    parser.add_argument("--max-symbol-date-requests", type=int, default=400)
    parser.add_argument("--max-contracts", type=int, default=2000)
    args = parser.parse_args()

    requests_path = Path(args.requests)
    template_path = Path(args.template)
    output_dir = Path(args.output_dir)
    batch_dir = output_dir / "batches"
    payload_dir = Path(args.payload_dir)

    batch_dir.mkdir(parents=True, exist_ok=True)
    payload_dir.mkdir(parents=True, exist_ok=True)

    template_text = template_path.read_text(encoding="utf-8-sig")
    requests = list(read_jsonl(requests_path))

    batches: list[dict[str, Any]] = []
    batch_index_rows: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []

    current: list[dict[str, Any]] = []

    def candidate_fits(candidate_requests: list[dict[str, Any]], batch_number: int) -> tuple[bool, dict[str, Any]]:
        batch_id = f"{args.batch_id_prefix}_{batch_number:04d}"
        batch = make_batch(batch_id, candidate_requests, str(requests_path))
        payload_b64, raw_size, compressed_size, sha = build_payload(batch)
        rlen = rendered_length(template_text, batch_id, payload_b64)

        contract_count = batch["contract_request_count"]

        fits = (
            rlen <= args.max_rendered_chars
            and len(candidate_requests) <= args.max_symbol_date_requests
            and contract_count <= args.max_contracts
        )

        info = {
            "batch": batch,
            "payload_b64": payload_b64,
            "raw_size": raw_size,
            "compressed_size": compressed_size,
            "compressed_sha256": sha,
            "rendered_char_count": rlen,
            "fits": fits,
        }
        return fits, info

    batch_number = 1

    for req in requests:
        if not current:
            fits_single, single_info = candidate_fits([req], batch_number)
            if not fits_single:
                blockers.append({
                    "reason": "single_request_exceeds_limits",
                    "request_id": req.get("request_id"),
                    "symbol": req.get("symbol"),
                    "quote_date": req.get("quote_date"),
                    "rendered_char_count": single_info["rendered_char_count"],
                    "contract_count": single_info["batch"]["contract_request_count"],
                })
                continue
            current = [req]
            continue

        fits, info = candidate_fits(current + [req], batch_number)

        if fits:
            current.append(req)
            continue

        # Finalize current batch.
        _, final_info = candidate_fits(current, batch_number)
        batches.append(final_info)

        batch_number += 1

        fits_single, single_info = candidate_fits([req], batch_number)
        if not fits_single:
            blockers.append({
                "reason": "single_request_exceeds_limits",
                "request_id": req.get("request_id"),
                "symbol": req.get("symbol"),
                "quote_date": req.get("quote_date"),
                "rendered_char_count": single_info["rendered_char_count"],
                "contract_count": single_info["batch"]["contract_request_count"],
            })
            current = []
        else:
            current = [req]

    if current:
        _, final_info = candidate_fits(current, batch_number)
        batches.append(final_info)

    total_contracts = 0
    total_symbol_date_requests = 0

    for info in batches:
        batch = info["batch"]
        batch_id = batch["batch_id"]

        batch_path = batch_dir / f"{batch_id}.json"
        payload_path = payload_dir / f"{batch_id}_payload.b64.txt"
        payload_summary_path = payload_dir / f"{batch_id}_payload_summary.json"

        write_json(batch_path, batch)
        payload_path.write_text(info["payload_b64"] + "\n", encoding="utf-8")

        payload_summary = {
            "adapter_type": "qc_canonical_backfill_payload_builder",
            "artifact_type": "signalforge_qc_canonical_backfill_payload",
            "is_ready": True,
            "batch_id": batch_id,
            "batch_json": str(batch_path),
            "payload_b64_path": str(payload_path),
            "raw_size": info["raw_size"],
            "compressed_size": info["compressed_size"],
            "compressed_sha256": info["compressed_sha256"],
            "rendered_char_count": info["rendered_char_count"],
            "request_count": batch["symbol_date_request_count"],
            "contract_request_count": batch["contract_request_count"],
        }
        write_json(payload_summary_path, payload_summary)

        total_contracts += batch["contract_request_count"]
        total_symbol_date_requests += batch["symbol_date_request_count"]

        batch_index_rows.append({
            "batch_id": batch_id,
            "batch_json": str(batch_path),
            "payload_b64_path": str(payload_path),
            "payload_summary_path": str(payload_summary_path),
            "symbol_date_request_count": batch["symbol_date_request_count"],
            "contract_request_count": batch["contract_request_count"],
            "unique_symbol_count": batch["unique_symbol_count"],
            "unique_quote_date_count": batch["unique_quote_date_count"],
            "quote_date_min": batch["quote_date_min"],
            "quote_date_max": batch["quote_date_max"],
            "rendered_char_count": info["rendered_char_count"],
            "compressed_size": info["compressed_size"],
        })

    summary = {
        "adapter_type": "qc_canonical_backfill_code_safe_batch_builder",
        "artifact_type": "signalforge_qc_canonical_backfill_code_safe_batches",
        "is_ready": len(blockers) == 0 and len(batches) > 0,
        "readiness_state": "code_safe_batches_available" if len(blockers) == 0 and len(batches) > 0 else "code_safe_batch_blocked",
        "source_requests": str(requests_path),
        "template": str(template_path),
        "source_request_count": len(requests),
        "batch_count": len(batches),
        "symbol_date_request_count": total_symbol_date_requests,
        "contract_request_count": total_contracts,
        "max_rendered_chars": args.max_rendered_chars,
        "max_symbol_date_requests": args.max_symbol_date_requests,
        "max_contracts": args.max_contracts,
        "rendered_char_min": min([r["rendered_char_count"] for r in batch_index_rows], default=0),
        "rendered_char_max": max([r["rendered_char_count"] for r in batch_index_rows], default=0),
        "paths": {
            "summary": str(output_dir / "signalforge_qc_canonical_backfill_code_safe_batches_summary.json"),
            "batch_index": str(output_dir / "signalforge_qc_canonical_backfill_code_safe_batch_index.jsonl"),
            "batch_dir": str(batch_dir),
            "payload_dir": str(payload_dir),
        },
        "blockers": blockers,
    }

    write_json(output_dir / "signalforge_qc_canonical_backfill_code_safe_batches_summary.json", summary)
    write_jsonl(output_dir / "signalforge_qc_canonical_backfill_code_safe_batch_index.jsonl", batch_index_rows)

    print(json.dumps(summary, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
