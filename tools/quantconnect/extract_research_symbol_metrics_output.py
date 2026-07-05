from pathlib import Path
import argparse
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
parser.add_argument("--input", required=True)
parser.add_argument("--output-dir", required=True)
args = parser.parse_args()

input_path = Path(args.input)
output_dir = Path(args.output_dir)
output_dir.mkdir(parents=True, exist_ok=True)

lines = input_path.read_text(encoding="utf-8-sig").splitlines()

metric_lines = extract_between(
    lines,
    "SF_SYMBOL_METRICS_JSONL_BEGIN",
    "SF_SYMBOL_METRICS_JSONL_END",
)

summary_lines = extract_between(
    lines,
    "SF_SYMBOL_METRICS_SUMMARY_BEGIN",
    "SF_SYMBOL_METRICS_SUMMARY_END",
)

if not metric_lines:
    raise SystemExit("No symbol metric lines found")

rows_path = output_dir / "signalforge_options_execution_symbol_metrics.jsonl"
summary_path = output_dir / "signalforge_options_execution_symbol_metrics_summary.json"

rows = []
with rows_path.open("w", encoding="utf-8", newline="\n") as handle:
    for line in metric_lines:
        row = json.loads(line)
        rows.append(row)
        handle.write(json.dumps(row, sort_keys=True) + "\n")

summary = json.loads(summary_lines[-1]) if summary_lines else {}
summary.update({
    "local_extractor_adapter_type": "research_symbol_metrics_output_extractor",
    "local_output_row_count": len(rows),
    "paths": {
        "rows_path": str(rows_path),
        "summary_path": str(summary_path),
    }
})

summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

print(json.dumps(summary, indent=2, sort_keys=True))
