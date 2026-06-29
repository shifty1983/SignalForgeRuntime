import json
from pathlib import Path
from collections import Counter

OUT_DIR = Path("artifacts/warmstart_source_inventory_20210601_20221231")
OUT_DIR.mkdir(parents=True, exist_ok=True)

ROOTS = [
    Path("artifacts"),
]

OUT_PATH = OUT_DIR / "warmstart_source_inventory.json"

DATE_KEYS = ["decision_date", "entry_date", "trade_date", "date"]
STRATEGY_KEYS = ["selected_strategy", "strategy", "strategy_family"]
QTY_KEYS = ["quantity", "contract_count", "allocated_contract_count", "contracts"]
PNL_KEYS = ["allocated_pnl", "allocated_pnl_dollars", "realized_pnl_dollars", "pnl_dollars", "realized_pnl"]

START = "2021-06-01"
END = "2022-12-31"

def read_jsonl_sample(path, limit=20000):
    try:
        with path.open("r", encoding="utf-8-sig", errors="ignore") as f:
            for i, line in enumerate(f):
                if i >= limit:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except Exception:
                    continue
    except Exception:
        return

def pick(row, keys):
    for k in keys:
        if k in row and row[k] is not None and str(row[k]).strip() != "":
            return row[k]
    return None

def in_warm_window(row):
    d = pick(row, DATE_KEYS)
    if not d:
        return False
    s = str(d)[:10]
    return START <= s <= END

def has_any(row, keys):
    return pick(row, keys) is not None

rows = []

for root in ROOTS:
    for path in root.rglob("*.jsonl"):
        path_text = str(path).lower()

        # Skip huge quote/path files if obvious.
        if any(x in path_text for x in ["quote_path", "option_chain", "daily_quote", "contract_path"]):
            continue

        total_sampled = 0
        warm_rows = 0
        usable_warm_rows = 0
        date_counter = Counter()
        strategy_counter = Counter()
        keys_seen = Counter()

        for row in read_jsonl_sample(path):
            total_sampled += 1
            for k in row.keys():
                keys_seen[k] += 1

            if in_warm_window(row):
                warm_rows += 1

                d = str(pick(row, DATE_KEYS))[:7]
                date_counter[d] += 1

                strat = pick(row, STRATEGY_KEYS)
                if strat:
                    strategy_counter[str(strat)] += 1

                if (
                    has_any(row, DATE_KEYS)
                    and has_any(row, STRATEGY_KEYS)
                    and has_any(row, QTY_KEYS)
                    and has_any(row, PNL_KEYS)
                ):
                    usable_warm_rows += 1

        if warm_rows or usable_warm_rows:
            rows.append({
                "path": str(path),
                "total_sampled": total_sampled,
                "warm_rows_20210601_20221231": warm_rows,
                "usable_warm_rows": usable_warm_rows,
                "has_date": any(k in keys_seen for k in DATE_KEYS),
                "has_strategy": any(k in keys_seen for k in STRATEGY_KEYS),
                "has_quantity": any(k in keys_seen for k in QTY_KEYS),
                "has_pnl": any(k in keys_seen for k in PNL_KEYS),
                "top_months": dict(date_counter.most_common(10)),
                "top_strategies": dict(strategy_counter.most_common(10)),
                "sample_keys": sorted(list(keys_seen.keys()))[:100],
            })

rows = sorted(
    rows,
    key=lambda r: (
        r["usable_warm_rows"],
        r["warm_rows_20210601_20221231"],
        r["total_sampled"],
    ),
    reverse=True,
)

summary = {
    "is_ready": True,
    "artifact_type": "warmstart_source_inventory",
    "candidate_file_count": len(rows),
    "top_candidates": rows[:50],
    "paths": {
        "inventory_path": str(OUT_PATH),
    },
}

OUT_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(json.dumps(summary, indent=2, sort_keys=True))
