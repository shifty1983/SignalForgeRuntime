from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


STATUS_MAP_FIELDS = [
    "strategy_family_statuses",
    "strategy_family_status_map",
    "strategy_family_eligibility_statuses",
    "strategy_family_eligibility",
    "family_statuses",
    "strategy_statuses",
]

STATUS_FIELDS = [
    "status",
    "state",
    "eligibility_state",
    "strategy_family_status",
    "family_status",
    "decision",
]


def read_jsonl(path: Path):
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if line:
                yield line_number, json.loads(line)


def status_from_value(value: Any) -> str | None:
    if isinstance(value, str):
        return value.strip()

    if isinstance(value, dict):
        for field in STATUS_FIELDS:
            v = value.get(field)
            if isinstance(v, str) and v.strip():
                return v.strip()

    return None


def extract_status_map(row: dict[str, Any]) -> dict[str, str]:
    for field in STATUS_MAP_FIELDS:
        value = row.get(field)

        if value in (None, "", [], {}):
            continue

        out = {}

        if isinstance(value, dict):
            for k, v in value.items():
                status = status_from_value(v)
                if status:
                    out[str(k)] = status

        elif isinstance(value, list):
            for item in value:
                if not isinstance(item, dict):
                    continue

                family = (
                    item.get("strategy_family")
                    or item.get("family")
                    or item.get("strategy")
                    or item.get("strategy_name")
                    or item.get("name")
                )
                status = status_from_value(item)

                if family and status:
                    out[str(family)] = status

        if out:
            return out

    return {}


def inspect(
    eligibility_rows: Path,
    candidate_rows: Path,
    audit_rows: Path | None,
    max_rows: int,
) -> dict[str, Any]:
    family_status_counts = Counter()
    family_counts = Counter()
    status_counts = Counter()
    map_field_counts = Counter()
    eligibility_field_counts = Counter()

    first_eligibility_compact = None
    first_status_map = None

    row_count = 0

    for _, row in read_jsonl(eligibility_rows):
        row_count += 1

        for field in row.keys():
            eligibility_field_counts[field] += 1

        for field in STATUS_MAP_FIELDS:
            value = row.get(field)
            if value not in (None, "", [], {}):
                map_field_counts[field] += 1

        status_map = extract_status_map(row)

        if status_map and first_status_map is None:
            first_status_map = status_map
            first_eligibility_compact = {
                "symbol": row.get("symbol") or row.get("underlying_symbol"),
                "date": row.get("date") or row.get("decision_date") or row.get("quote_date"),
                "data_state": row.get("data_state"),
                "status_map": status_map,
            }

        for family, status in status_map.items():
            family_status_counts[(family, status)] += 1
            family_counts[family] += 1
            status_counts[status] += 1

        if row_count >= max_rows:
            break

    first_candidate = None
    candidate_field_counts = Counter()
    candidate_row_count_sampled = 0

    for _, row in read_jsonl(candidate_rows):
        candidate_row_count_sampled += 1

        if first_candidate is None:
            first_candidate = row

        for field in row.keys():
            candidate_field_counts[field] += 1

        if candidate_row_count_sampled >= max_rows:
            break

    missing_positive_sample = None

    if audit_rows and audit_rows.exists():
        for _, row in read_jsonl(audit_rows):
            if (
                row.get("classification") == "positive_eligible_but_no_candidate"
                and row.get("data_state") == "complete"
            ):
                missing_positive_sample = row
                break

    return {
        "eligibility_rows_path": str(eligibility_rows),
        "candidate_rows_path": str(candidate_rows),
        "sampled_eligibility_row_count": row_count,
        "sampled_candidate_row_count": candidate_row_count_sampled,
        "status_map_field_counts": dict(sorted(map_field_counts.items())),
        "status_counts": dict(sorted(status_counts.items())),
        "family_counts": dict(sorted(family_counts.items())),
        "family_status_counts": [
            {
                "family": family,
                "status": status,
                "count": count,
            }
            for (family, status), count in family_status_counts.most_common(200)
        ],
        "eligibility_fields": sorted(eligibility_field_counts.keys()),
        "candidate_fields": sorted(candidate_field_counts.keys()),
        "first_eligibility_compact": first_eligibility_compact,
        "first_candidate_row": first_candidate,
        "missing_positive_complete_sample": missing_positive_sample,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eligibility-rows", required=True)
    parser.add_argument("--candidate-rows", required=True)
    parser.add_argument("--audit-rows", default=None)
    parser.add_argument("--max-rows", type=int, default=5000)
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args()

    result = inspect(
        eligibility_rows=Path(args.eligibility_rows),
        candidate_rows=Path(args.candidate_rows),
        audit_rows=Path(args.audit_rows) if args.audit_rows else None,
        max_rows=args.max_rows,
    )

    output_path = Path(args.output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")

    print(json.dumps({
        "output_json": str(output_path),
        "sampled_eligibility_row_count": result["sampled_eligibility_row_count"],
        "sampled_candidate_row_count": result["sampled_candidate_row_count"],
        "status_map_field_counts": result["status_map_field_counts"],
        "status_counts": result["status_counts"],
        "family_counts": result["family_counts"],
        "candidate_fields": result["candidate_fields"],
    }, indent=2, sort_keys=True))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
