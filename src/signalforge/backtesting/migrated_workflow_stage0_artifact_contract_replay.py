from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from signalforge.backtesting.migrated_workflow_dry_run_plan import (
    build_migrated_workflow_dry_run_plan,
)


OUTPUT_DIR = Path("artifacts/migrated_workflow_dry_run_20210601_20260531")


KNOWN_ROW_COUNT_KEYS = (
    "row_count",
    "decision_row_count",
    "candidate_row_count",
    "selection_row_count",
    "leg_selection_row_count",
    "position_sizing_row_count",
    "selected_trade_count",
    "selected_trade_sequence_row_count",
    "input_row_count",
    "output_row_count",
    "scenario_count",
    "stress_scenario_count",
    "skipped_row_count",
    "action_row_count",
)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def count_jsonl(path: Path) -> int:
    count = 0
    with path.open("r", encoding="utf-8-sig", errors="ignore") as handle:
        for line in handle:
            if line.strip():
                count += 1
    return count


def sample_jsonl_keys(path: Path, limit: int = 3) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8-sig", errors="ignore") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                return {
                    "sample_parse_ready": False,
                    "parse_error": "json_decode_error",
                    "sample_row_count": len(rows),
                    "sample_keys": [],
                }

            if len(rows) >= limit:
                break

    keys = sorted({key for row in rows if isinstance(row, dict) for key in row.keys()})

    return {
        "sample_parse_ready": True,
        "parse_error": None,
        "sample_row_count": len(rows),
        "sample_keys": keys,
    }


def extract_summary_counts(summary: dict[str, Any]) -> dict[str, Any]:
    counts: dict[str, Any] = {}

    for key in KNOWN_ROW_COUNT_KEYS:
        if key in summary:
            counts[key] = summary[key]

    for key, value in summary.items():
        if key.endswith("_count") and isinstance(value, int):
            counts[key] = value

    return counts


def build_stage0_artifact_contract_replay() -> dict[str, Any]:
    plan = build_migrated_workflow_dry_run_plan()

    stage_results: list[dict[str, Any]] = []
    blockers: list[str] = []
    warnings: list[str] = []

    for stage in plan["stages"]:
        stage_name = stage["stage"]
        row_path_raw = stage.get("selected_row_path")
        json_path_raw = stage.get("selected_json_path")

        row_path = Path(row_path_raw) if row_path_raw else None
        json_path = Path(json_path_raw) if json_path_raw else None

        row_exists = bool(row_path and row_path.exists())
        json_exists = bool(json_path and json_path.exists())

        row_count = None
        sample = {
            "sample_parse_ready": None,
            "parse_error": None,
            "sample_row_count": 0,
            "sample_keys": [],
        }

        if row_exists and row_path is not None:
            row_count = count_jsonl(row_path)
            sample = sample_jsonl_keys(row_path)
            if row_count == 0:
                blockers.append(f"{stage_name}_row_file_empty")
            if not sample["sample_parse_ready"]:
                blockers.append(f"{stage_name}_row_sample_not_json_parseable")

        elif stage_name in {
            "historical_decision_rows",
            "historical_strategy_candidate_rows",
            "walk_forward_expectancy",
            "historical_strategy_selection_rows",
            "historical_strategy_leg_selection_rows",
            "portfolio_position_sizing_replay",
            "portfolio_selected_trade_sequence",
        }:
            blockers.append(f"{stage_name}_row_file_missing")

        summary_counts: dict[str, Any] = {}
        if json_exists and json_path is not None:
            try:
                summary_counts = extract_summary_counts(read_json(json_path))
            except Exception as exc:
                warnings.append(f"{stage_name}_summary_parse_warning_{type(exc).__name__}")
        else:
            warnings.append(f"{stage_name}_summary_json_missing")

        stage_results.append({
            "stage": stage_name,
            "module": stage.get("module"),
            "row_path": str(row_path) if row_path else None,
            "json_path": str(json_path) if json_path else None,
            "row_exists": row_exists,
            "json_exists": json_exists,
            "row_count": row_count,
            "summary_counts": summary_counts,
            "sample": sample,
            "planned_output_dir": stage.get("planned_output_dir"),
            "is_contract_readable": row_exists and (row_count is not None) and row_count > 0 and bool(sample["sample_parse_ready"]),
        })

    return {
        "adapter_type": "migrated_workflow_stage0_artifact_contract_replay_builder",
        "artifact_type": "signalforge_migrated_workflow_stage0_artifact_contract_replay",
        "candidate_id": "signalforge_v3_2_2_paper_candidate",
        "stage_count": len(stage_results),
        "stage_results": stage_results,
        "blocker_count": len(blockers),
        "warning_count": len(warnings),
        "blockers": blockers,
        "warnings": warnings,
        "is_ready": len(blockers) == 0,
        "readiness_scope": "selected_artifact_paths_are_readable_and_jsonl_parseable",
    }


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    result = build_stage0_artifact_contract_replay()

    output_path = OUTPUT_DIR / "signalforge_migrated_workflow_stage0_artifact_contract_replay.json"
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())


