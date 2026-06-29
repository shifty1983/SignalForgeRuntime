import base64
import gzip
import json
import re
from pathlib import Path


text_export = Path("data/manual/baseline_exit_overlay_daily_quote_gap_research_text_export_research_pull_v1.txt")
out_dir = Path("artifacts/baseline_exit_overlay_daily_quote_gap_research_text_decoder_research_pull_v1")
out_dir.mkdir(parents=True, exist_ok=True)

raw_rows_path = out_dir / "baseline_exit_overlay_daily_quote_gap_fills_raw.jsonl"
compatible_rows_path = out_dir / "baseline_exit_overlay_daily_quote_gap_fills_path_compatible.jsonl"
summary_path = out_dir / "baseline_exit_overlay_daily_quote_gap_fills_decoder_summary.json"

text = text_export.read_text(encoding="utf-8-sig", errors="ignore")

begin = "SIGNALFORGE_TEXT_EXPORT_BEGIN"
end = "---SIGNALFORGE_TEXT_EXPORT_END---"

if begin not in text:
    raise SystemExit(f"Missing begin marker: {begin}")
if end not in text:
    raise SystemExit(f"Missing end marker: {end}")

body = text.split(begin, 1)[1].split(end, 1)[0]

part_count_match = re.search(r"part_count:\s*(\d+)", body)
expected_part_count = int(part_count_match.group(1)) if part_count_match else None

parts = []
current = []

for line in body.splitlines():
    line = line.strip()
    if not line:
        continue

    if line.startswith("---SIGNALFORGE_PART "):
        if current:
            parts.append("".join(current))
            current = []
        continue

    if line.startswith("part_count:"):
        continue
    if line.startswith("gap_fill_row_count:"):
        continue
    if line.startswith("error_count:"):
        continue
    if line.startswith("quote_status_counts:"):
        continue
    if line.startswith("history_method_counts:"):
        continue
    if line.startswith("copy_everything_between_begin_and_end"):
        continue

    # Base64 payload lines only.
    if re.fullmatch(r"[A-Za-z0-9+/=]+", line):
        current.append(line)

if current:
    parts.append("".join(current))

if expected_part_count is not None and len(parts) != expected_part_count:
    raise SystemExit(f"Part count mismatch: expected {expected_part_count}, found {len(parts)}")

transport_encoded = "".join(parts)
transport_json = gzip.decompress(base64.b64decode(transport_encoded.encode("ascii"))).decode("utf-8")
transport = json.loads(transport_json)

source_summary = transport.get("summary", {})
gap_fills_b64 = transport.get("gap_fills_jsonl_gzip_base64")

if not gap_fills_b64:
    raise SystemExit("Missing gap_fills_jsonl_gzip_base64 in decoded transport payload.")

gap_jsonl = gzip.decompress(base64.b64decode(gap_fills_b64.encode("ascii"))).decode("utf-8")

raw_rows = []
for line in gap_jsonl.splitlines():
    line = line.strip()
    if line:
        raw_rows.append(json.loads(line))

raw_status_counts = {}
compatible_status_counts = {}
usable_raw_count = 0
usable_compatible_count = 0
compatible_rows = []

with raw_rows_path.open("w", encoding="utf-8") as raw_out:
    for row in raw_rows:
        raw_out.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")

        status = str(row.get("quote_status") or "unknown")
        raw_status_counts[status] = raw_status_counts.get(status, 0) + 1

        bid = row.get("bid")
        ask = row.get("ask")
        mid = row.get("mid")

        try:
            bid_f = float(bid) if bid is not None else None
            ask_f = float(ask) if ask is not None else None
            mid_f = float(mid) if mid is not None else None
        except Exception:
            bid_f = ask_f = mid_f = None

        compatible = dict(row)

        if bid_f is not None and ask_f is not None and ask_f >= bid_f:
            if mid_f is None:
                mid_f = (bid_f + ask_f) / 2.0
                compatible["mid"] = mid_f

            compatible["bid"] = bid_f
            compatible["ask"] = ask_f
            compatible["quote_status"] = "complete"
            compatible["path_state"] = "complete"
            compatible["quote_source"] = compatible.get("quote_source") or "quantconnect_research_quotebar_history"
            usable_raw_count += 1
            usable_compatible_count += 1
        else:
            compatible["quote_status"] = status
            compatible["path_state"] = "no_quote" if status == "missing_from_quantconnect_history" else "partial"

        compatible_status = str(compatible.get("quote_status") or "unknown")
        compatible_status_counts[compatible_status] = compatible_status_counts.get(compatible_status, 0) + 1
        compatible_rows.append(compatible)

with compatible_rows_path.open("w", encoding="utf-8") as out:
    for row in compatible_rows:
        out.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")

summary = {
    "adapter_type": "baseline_exit_overlay_daily_quote_gap_research_text_decoder",
    "artifact_type": "signalforge_baseline_exit_overlay_daily_quote_gap_fills_decoder",
    "contract": "baseline_exit_overlay_daily_quote_gap_fills_decoder",
    "is_ready": True,
    "text_export_path": str(text_export),
    "decoded_part_count": len(parts),
    "expected_part_count": expected_part_count,
    "source_summary": source_summary,
    "gap_fill_row_count": len(raw_rows),
    "raw_quote_status_counts": raw_status_counts,
    "compatible_quote_status_counts": compatible_status_counts,
    "usable_raw_count": usable_raw_count,
    "usable_compatible_count": usable_compatible_count,
    "raw_rows_path": str(raw_rows_path),
    "compatible_rows_path": str(compatible_rows_path),
    "summary_path": str(summary_path),
}

summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

print(json.dumps(summary, indent=2, sort_keys=True))
