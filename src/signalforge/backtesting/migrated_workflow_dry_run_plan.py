from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from signalforge.backtesting.migrated_workflow_artifact_paths import (
    build_exact_artifact_path_manifest,
)


OUTPUT_ROOT = Path("artifacts/migrated_workflow_dry_run_20210601_20260531")


STAGE_MODULES = {
    "historical_decision_rows": "signalforge.backtesting.historical_decision_rows_cli",
    "historical_strategy_candidate_rows": "signalforge.backtesting.historical_strategy_candidate_rows_cli",
    "walk_forward_expectancy": "signalforge.backtesting.walk_forward_expectancy_cli",
    "historical_strategy_selection_rows": "signalforge.backtesting.historical_strategy_selection_rows_cli",
    "historical_strategy_leg_selection_rows": "signalforge.backtesting.historical_strategy_leg_selection_rows_cli",
    "portfolio_position_sizing_replay": "signalforge.backtesting.portfolio_position_sizing_replay_cli",
    "portfolio_selected_trade_sequence": "signalforge.backtesting.portfolio_selected_trade_sequence_cli",
}


ORDERED_STAGES = [
    "historical_decision_rows",
    "historical_strategy_candidate_rows",
    "walk_forward_expectancy",
    "historical_strategy_selection_rows",
    "historical_strategy_leg_selection_rows",
    "portfolio_position_sizing_replay",
    "portfolio_selected_trade_sequence",
    "layer_field_carry_forward_enrichment_v2",
    "quote_join",
    "quote_attribution",
    "v3_2_2_pruning",
    "ruleset_lock",
    "stress_validation",
]


def _score_path(path: str) -> tuple[int, str]:
    value = path.lower()
    score = 0

    if "20210601_20260531" in value:
        score -= 100
    if "safe_20210601_20260531" in value:
        score -= 25
    if "search15" in value:
        score += 50
    if "_curated" in value:
        score += 40
    if "preview" in value:
        score += 75
    if "inline_safe" in value:
        score += 30

    if value.endswith("_rows.jsonl"):
        score -= 20
    if value.endswith("_summary.json"):
        score -= 20
    if value.endswith("_scenarios.jsonl"):
        score -= 10
    if value.endswith("_ledger.jsonl"):
        score -= 5

    return score, value


def _jsonl_non_empty_penalty(path: str) -> int:
    candidate = Path(path)

    if candidate.suffix.lower() != ".jsonl":
        return 0

    try:
        with candidate.open("r", encoding="utf-8-sig", errors="ignore") as handle:
            for line in handle:
                if line.strip():
                    return 0
    except OSError:
        return 1000

    return 1000


def _choose(paths: list[str]) -> str | None:
    if not paths:
        return None

    return sorted(
        paths,
        key=lambda path: (
            _jsonl_non_empty_penalty(path),
            *_score_path(path),
        ),
    )[0]


def build_migrated_workflow_dry_run_plan() -> dict[str, Any]:
    exact_manifest = build_exact_artifact_path_manifest()
    groups = exact_manifest["groups"]

    stages: list[dict[str, Any]] = []
    blockers: list[str] = []

    for stage in ORDERED_STAGES:
        group = groups.get(stage)
        if not group:
            blockers.append(f"{stage}_artifact_group_missing")
            continue

        selected_row_path = _choose(group.get("sample_jsonl_files", []))
        selected_json_path = _choose(group.get("sample_json_files", []))

        if stage in STAGE_MODULES and not selected_row_path:
            blockers.append(f"{stage}_selected_row_path_missing")

        stages.append({
            "stage": stage,
            "module": STAGE_MODULES.get(stage),
            "selected_row_path": selected_row_path,
            "selected_json_path": selected_json_path,
            "source_folder_count": group.get("folder_count", 0),
            "source_jsonl_count": group.get("jsonl_count", 0),
            "source_json_count": group.get("json_count", 0),
            "planned_output_dir": str(OUTPUT_ROOT / stage),
            "execution_mode": "planned_not_executed",
        })

    return {
        "adapter_type": "migrated_workflow_dry_run_plan_builder",
        "artifact_type": "signalforge_migrated_workflow_dry_run_plan",
        "candidate_id": "signalforge_v3_2_2_paper_candidate",
        "date_window": {
            "start": "2021-06-01",
            "end": "2026-05-31",
            "locked_ruleset_start": "2023-01-01",
            "locked_ruleset_end": "2026-05-31",
        },
        "output_root": str(OUTPUT_ROOT),
        "stage_count": len(stages),
        "stages": stages,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "is_ready": len(blockers) == 0,
        "readiness_scope": "canonical_old_artifact_paths_resolved_for_migrated_dry_run",
    }


def main() -> int:
    plan = build_migrated_workflow_dry_run_plan()
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    plan_path = OUTPUT_ROOT / "signalforge_migrated_workflow_dry_run_plan.json"
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True), encoding="utf-8")

    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0 if plan["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())




