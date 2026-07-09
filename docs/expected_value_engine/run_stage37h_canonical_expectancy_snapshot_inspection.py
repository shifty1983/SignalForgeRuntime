import json
from pathlib import Path
from typing import Any, Dict, List


OUT_DIR = Path("docs/expected_value_engine")

CANONICAL_DIR = Path("data/canonical/signalforge_pipeline/18_walk_forward_expectancy")

COMPARISON_DIRS = [
    Path("artifacts/sf18_walk_forward_expectancy"),
    Path("artifacts/sf20_pruned_expectancy_core_plus_credit"),
    Path("artifacts/walk_forward_expectancy_v13_v21_primary_term_hpd5_exit10_20210601_20260531"),
    Path("artifacts/walk_forward_expectancy_v13_v21_primary_term_hpd5_exit10_pruned_core_plus_credit_20210601_20260531"),
]

ROW_PATTERNS = [
    "*.jsonl",
    "**/*.jsonl",
]

SUMMARY_PATTERNS = [
    "*summary*.json",
    "**/*summary*.json",
]


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return {"__read_error__": str(exc)}


def count_jsonl(path: Path) -> int:
    count = 0
    with path.open("r", encoding="utf-8-sig") as f:
        for line in f:
            if line.strip():
                count += 1
    return count


def first_jsonl_rows(path: Path, limit: int = 25) -> list[dict[str, Any]]:
    rows = []

    with path.open("r", encoding="utf-8-sig") as f:
        for line in f:
            text = line.strip()
            if not text:
                continue

            try:
                item = json.loads(text)
            except Exception:
                continue

            if isinstance(item, dict):
                rows.append(item)

            if len(rows) >= limit:
                break

    return rows


def find_rows(root: Path) -> list[Path]:
    found = []
    if not root.exists():
        return found

    for pattern in ROW_PATTERNS:
        found.extend(root.glob(pattern))

    return sorted(set(path for path in found if path.is_file()))


def find_summaries(root: Path) -> list[Path]:
    found = []
    if not root.exists():
        return found

    for pattern in SUMMARY_PATTERNS:
        found.extend(root.glob(pattern))

    return sorted(set(path for path in found if path.is_file()))


def best_summary_for_rows(rows_path: Path, summaries: list[Path]) -> Path | None:
    if not summaries:
        return None

    row_name = rows_path.name.lower()

    def score(path: Path) -> tuple[int, float]:
        name = path.name.lower()
        s = 0

        if "summary" in name:
            s += 10
        if "walk_forward_expectancy" in name:
            s += 5
        if "pruned" in row_name and "pruned" in name:
            s += 4
        if "core_plus_credit" in row_name and "core_plus_credit" in name:
            s += 4
        if "rows" not in name:
            s += 2

        return (s, path.stat().st_mtime)

    return sorted(summaries, key=score, reverse=True)[0]


def key_profile(rows: list[dict[str, Any]]) -> dict[str, Any]:
    keys = sorted(set().union(*(row.keys() for row in rows))) if rows else []
    return {
        "key_count": len(keys),
        "keys": keys,
        "has_expectancy_fields": bool(
            rows and {"expectancy_state", "expectancy_sample_count"}.intersection(rows[0].keys())
        ),
        "has_no_lookahead_fields": bool(
            rows and {"uses_current_row_outcome", "uses_future_rows"}.intersection(rows[0].keys())
        ),
    }


def compact_sample(row: dict[str, Any]) -> dict[str, Any]:
    preferred = [
        "symbol",
        "strategy",
        "strategy_name",
        "candidate_strategy",
        "strategy_candidate_id",
        "candidate_id",
        "decision_date",
        "date",
        "expectancy_state",
        "expectancy_scope",
        "expectancy_sample_count",
        "expectancy_minimum_sample_count",
        "expectancy_average_return",
        "expectancy_median_return",
        "expectancy_win_rate",
        "is_sample_limited",
        "uses_current_row_outcome",
        "uses_future_rows",
        "training_window_start",
        "training_window_end",
    ]

    return {key: row.get(key) for key in preferred if key in row}


def inspect_root(root: Path, source_group: str) -> list[dict[str, Any]]:
    rows = []
    row_files = find_rows(root)
    summaries = find_summaries(root)

    for rows_path in row_files:
        sample_rows = first_jsonl_rows(rows_path, limit=25)
        summary_path = best_summary_for_rows(rows_path, summaries)
        summary = read_json(summary_path) if summary_path else None
        profile = key_profile(sample_rows)

        rows.append({
            "source_group": source_group,
            "root": str(root),
            "rows_path": str(rows_path),
            "row_count": count_jsonl(rows_path),
            "summary_path": str(summary_path) if summary_path else None,
            "summary_exists": summary_path is not None,
            "summary_is_ready": summary.get("is_ready") if isinstance(summary, dict) else None,
            "summary_artifact_type": summary.get("artifact_type") if isinstance(summary, dict) else None,
            "summary_contract": summary.get("contract") if isinstance(summary, dict) else None,
            "sample_key_count": profile["key_count"],
            "has_expectancy_fields": profile["has_expectancy_fields"],
            "has_no_lookahead_fields": profile["has_no_lookahead_fields"],
            "sample_compact_row": compact_sample(sample_rows[0]) if sample_rows else {},
        })

    return rows


def main() -> None:
    blockers: List[str] = []
    warnings: List[str] = []

    if not CANONICAL_DIR.exists():
        blockers.append(f"missing_canonical_expectancy_dir_{CANONICAL_DIR}")

    artifact_rows: List[Dict[str, Any]] = []

    artifact_rows.extend(inspect_root(CANONICAL_DIR, "canonical_pipeline"))

    for root in COMPARISON_DIRS:
        artifact_rows.extend(inspect_root(root, "artifact_comparison"))

    canonical_rows = [
        row for row in artifact_rows
        if row["source_group"] == "canonical_pipeline"
    ]

    non_empty_canonical_rows = [
        row for row in canonical_rows
        if row["row_count"] > 0
    ]

    ready_canonical_rows = [
        row for row in non_empty_canonical_rows
        if row["summary_is_ready"] is True
        and row["has_expectancy_fields"]
        and row["has_no_lookahead_fields"]
    ]

    preferred_canonical_snapshot = ready_canonical_rows[0] if ready_canonical_rows else (
        non_empty_canonical_rows[0] if non_empty_canonical_rows else None
    )

    if CANONICAL_DIR.exists() and not non_empty_canonical_rows:
        blockers.append("canonical_expectancy_dir_exists_but_has_no_non_empty_rows")

    if preferred_canonical_snapshot is None:
        warnings.append("no_preferred_canonical_snapshot_selected")

    warnings.append("stage37h_is_read_only_no_logic_moved")
    warnings.append("canonical_pipeline_expectancy_should_be_preferred_for_locked_snapshot_if_ready")
    warnings.append("data_canonical_is_runtime_source_and_should_not_be_force_added_to_git")

    summary = {
        "adapter_type": "canonical_expectancy_snapshot_inspection_builder",
        "artifact_type": "signalforge_canonical_expectancy_snapshot_inspection",
        "contract": "canonical_expectancy_snapshot_inspection",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,
        "canonical_dir": str(CANONICAL_DIR),
        "artifact_row_count": len(artifact_rows),
        "canonical_artifact_count": len(canonical_rows),
        "non_empty_canonical_artifact_count": len(non_empty_canonical_rows),
        "ready_canonical_artifact_count": len(ready_canonical_rows),
        "preferred_canonical_snapshot": preferred_canonical_snapshot,
        "paper_snapshot_selection_rule": (
            "prefer data/canonical/signalforge_pipeline/18_walk_forward_expectancy "
            "when it is ready, no-lookahead safe, and matches the locked paper candidate scope"
        ),
        "paper_order_created": False,
        "live_order_created": False,
        "live_trade_supported": False,
        "next_step": "stage37i_design_expectancy_snapshot_adapter_against_canonical_snapshot",
    }

    summary_path = OUT_DIR / "signalforge_stage37h_canonical_expectancy_snapshot_inspection_summary.json"
    rows_path = OUT_DIR / "signalforge_stage37h_canonical_expectancy_snapshot_inspection_rows.jsonl"
    md_path = OUT_DIR / "signalforge_stage37h_canonical_expectancy_snapshot_inspection.md"

    summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    with rows_path.open("w", encoding="utf-8") as f:
        for row in artifact_rows:
            f.write(json.dumps(row, default=str) + "\n")

    md = [
        "# Stage 37H Canonical Expectancy Snapshot Inspection",
        "",
        f"- is_ready: {summary['is_ready']}",
        f"- blocker_count: {summary['blocker_count']}",
        f"- canonical_dir: `{summary['canonical_dir']}`",
        f"- canonical_artifact_count: {summary['canonical_artifact_count']}",
        f"- non_empty_canonical_artifact_count: {summary['non_empty_canonical_artifact_count']}",
        f"- ready_canonical_artifact_count: {summary['ready_canonical_artifact_count']}",
        f"- paper_snapshot_selection_rule: {summary['paper_snapshot_selection_rule']}",
        f"- paper_order_created: {summary['paper_order_created']}",
        f"- live_order_created: {summary['live_order_created']}",
        f"- live_trade_supported: {summary['live_trade_supported']}",
        "",
        "## Preferred Canonical Snapshot",
        "",
        "```json",
        json.dumps(preferred_canonical_snapshot, indent=2, default=str),
        "```",
        "",
        "## Artifact Rows",
        "",
        "| source | row count | ready | artifact type | expectancy fields | no-lookahead fields | rows path | summary path |",
        "|---|---:|---:|---|---:|---:|---|---|",
    ]

    for row in artifact_rows:
        md.append(
            f"| {row['source_group']} | {row['row_count']} | {row['summary_is_ready']} | "
            f"{row['summary_artifact_type']} | {row['has_expectancy_fields']} | "
            f"{row['has_no_lookahead_fields']} | `{row['rows_path']}` | `{row['summary_path']}` |"
        )

    if blockers:
        md.extend(["", "## Blockers", ""])
        for blocker in blockers:
            md.append(f"- {blocker}")

    if warnings:
        md.extend(["", "## Warnings", ""])
        for warning in warnings:
            md.append(f"- {warning}")

    md_path.write_text("\n".join(md), encoding="utf-8")

    print("\n--- Stage 37H canonical expectancy snapshot inspection compact ---")
    for key in [
        "is_ready",
        "blocker_count",
        "warning_count",
        "artifact_row_count",
        "canonical_artifact_count",
        "non_empty_canonical_artifact_count",
        "ready_canonical_artifact_count",
        "paper_order_created",
        "live_order_created",
        "live_trade_supported",
    ]:
        print(f"{key}: {summary[key]}")

    print(f"summary_path: {summary_path}")
    print(f"rows_path: {rows_path}")
    print(f"md_path: {md_path}")

    print("\n--- Stage 37H preferred canonical snapshot ---")
    print(json.dumps(preferred_canonical_snapshot, indent=2, default=str))

    print("\n--- Stage 37H artifact rows compact ---")
    print("source\trow_count\tready\tartifact_type\texpectancy_fields\tno_lookahead_fields\trows_path\tsummary_path")
    for row in artifact_rows:
        print(
            f"{row['source_group']}\t{row['row_count']}\t{row['summary_is_ready']}\t"
            f"{row['summary_artifact_type']}\t{row['has_expectancy_fields']}\t"
            f"{row['has_no_lookahead_fields']}\t{row['rows_path']}\t{row['summary_path']}"
        )

    if blockers:
        print("\n--- Stage 37H blockers ---")
        for blocker in blockers:
            print(blocker)
        raise SystemExit(1)

    if warnings:
        print("\n--- Stage 37H warnings ---")
        for warning in warnings:
            print(warning)


if __name__ == "__main__":
    main()
