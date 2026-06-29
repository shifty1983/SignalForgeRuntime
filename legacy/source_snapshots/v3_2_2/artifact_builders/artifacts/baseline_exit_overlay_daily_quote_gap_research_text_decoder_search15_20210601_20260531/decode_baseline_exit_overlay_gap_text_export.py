import base64
import gzip
import json
import re
from pathlib import Path

input_path = Path(r"data\manual\baseline_exit_overlay_daily_quote_gap_research_text_export.txt")
out_dir = Path(r"artifacts\baseline_exit_overlay_daily_quote_gap_research_text_decoder_search15_20210601_20260531")
out_dir.mkdir(parents=True, exist_ok=True)

text = input_path.read_text(encoding="utf-8", errors="ignore")

parts = re.findall(
    r"---SIGNALFORGE_PART\s+\d+\s+OF\s+\d+---\s*([A-Za-z0-9+/=\s]+?)(?=\n---SIGNALFORGE_PART|\n---SIGNALFORGE_TEXT_EXPORT_END---)",
    text,
    flags=re.DOTALL,
)

if not parts:
    raise SystemExit("No SIGNALFORGE_PART blocks found.")

encoded = "".join("".join(p.split()) for p in parts)
transport_json = gzip.decompress(base64.b64decode(encoded.encode("ascii"))).decode("utf-8")
transport = json.loads(transport_json)

gap_fills_jsonl = gzip.decompress(
    base64.b64decode(transport["gap_fills_jsonl_gzip_base64"].encode("ascii"))
).decode("utf-8")

rows_path = out_dir / "baseline_exit_overlay_daily_quote_gap_fills.jsonl"
summary_path = out_dir / "baseline_exit_overlay_daily_quote_gap_fills_decoder_summary.json"

rows_path.write_text(gap_fills_jsonl, encoding="utf-8")

summary = dict(transport.get("summary") or {})
summary.update({
    "adapter_type": "baseline_exit_overlay_daily_quote_gap_research_text_decoder",
    "artifact_type": "signalforge_baseline_exit_overlay_daily_quote_gap_fills_decoder",
    "contract": "baseline_exit_overlay_daily_quote_gap_fills_decoder",
    "is_ready": True,
    "decoded_part_count": len(parts),
    "rows_path": str(rows_path),
    "summary_path": str(summary_path),
})

summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

print(json.dumps(summary, indent=2, sort_keys=True))
