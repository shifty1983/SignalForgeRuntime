from pathlib import Path
import argparse
import base64
import gzip
import json

def extract_between(lines, begin, end):
    inside = False
    out = []
    for line in lines:
        line = line.rstrip("\n")
        if line.strip() == begin:
            inside = True
            continue
        if line.strip() == end:
            inside = False
            continue
        if inside and line.strip():
            out.append(line)
    return out

parser = argparse.ArgumentParser()
parser.add_argument("--pages-dir", required=True)
parser.add_argument("--output-dir", required=True)
args = parser.parse_args()

pages_dir = Path(args.pages_dir)
output_dir = Path(args.output_dir)
output_dir.mkdir(parents=True, exist_ok=True)

page_files = sorted(pages_dir.glob("page_*.txt"))

if not page_files:
    raise SystemExit(f"No page_*.txt files found in {pages_dir}")

chunk_map = {}
manifests = []

for page_file in page_files:
    lines = page_file.read_text(encoding="utf-8-sig").splitlines()

    manifest_lines = extract_between(
        lines,
        "SF_SYMBOL_DATE_PAGE_MANIFEST_BEGIN",
        "SF_SYMBOL_DATE_PAGE_MANIFEST_END",
    )

    for line in manifest_lines:
        manifests.append(json.loads(line))

    chunk_lines = extract_between(
        lines,
        "SF_SYMBOL_DATE_METRICS_EXPORT_BEGIN",
        "SF_SYMBOL_DATE_METRICS_EXPORT_END",
    )

    if not chunk_lines:
        raise SystemExit(f"No chunks found in {page_file}")

    for line in chunk_lines:
        obj = json.loads(line)
        idx = int(obj["chunk_index"])
        payload = obj["payload"]

        if idx in chunk_map and chunk_map[idx] != payload:
            raise SystemExit(f"Duplicate conflicting chunk_index={idx}")

        chunk_map[idx] = payload

if not manifests:
    raise SystemExit("No page manifests found")

expected_total_chunks = max(int(m["total_chunks"]) for m in manifests)
missing = [i for i in range(expected_total_chunks) if i not in chunk_map]

if missing:
    raise SystemExit(json.dumps({
        "error": "missing_chunks",
        "expected_total_chunks": expected_total_chunks,
        "actual_chunk_count": len(chunk_map),
        "missing_first_50": missing[:50],
    }, indent=2))

encoded = "".join(chunk_map[i] for i in range(expected_total_chunks))
payload = json.loads(gzip.decompress(base64.b64decode(encoded.encode("ascii"))).decode("utf-8"))

rows = payload["rows"]
summary = payload["summary"]

rows_path = output_dir / "signalforge_options_execution_symbol_date_metrics.jsonl"
summary_path = output_dir / "signalforge_options_execution_symbol_date_metrics_summary.json"

with rows_path.open("w", encoding="utf-8", newline="\n") as handle:
    for row in rows:
        handle.write(json.dumps(row, sort_keys=True) + "\n")

summary.update({
    "local_extractor_adapter_type": "research_symbol_date_metrics_paged_output_extractor",
    "local_output_row_count": len(rows),
    "page_file_count": len(page_files),
    "expected_total_chunks": expected_total_chunks,
    "actual_chunk_count": len(chunk_map),
    "paths": {
        "rows_path": str(rows_path),
        "summary_path": str(summary_path),
    }
})

summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

print(json.dumps(summary, indent=2, sort_keys=True))
