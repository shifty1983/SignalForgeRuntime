from __future__ import annotations

import json
from pathlib import Path
from typing import Any


OUTPUT_ROOT = Path("artifacts/migrated_workflow_dry_run_20210601_20260531")
STAGE1_MANIFEST_PATH = (
    OUTPUT_ROOT / "signalforge_migrated_workflow_stage1_artifact_mirror_replay.json"
)


EXPECTED_RELATIONSHIPS = [
    {
        "name": "candidate_rows_cover_expectancy_rows",
        "left_stage": "historical_strategy_candidate_rows",
        "right_stage": "walk_forward_expectancy",
        "operator": ">=",
    },
    {
        "name": "candidate_rows_cover_selection_rows",
        "left_stage": "historical_strategy_candidate_rows",
        "right_stage": "historical_strategy_selection_rows",
        "operator": ">=",
    },
    {
        "name": "expectancy_rows_cover_selection_rows",
        "left_stage": "walk_forward_expectancy",
        "right_stage": "historical_strategy_selection_rows",
        "operator": ">=",
    },
    {
        "name": "leg_rows_cover_selection_rows",
        "left_stage": "historical_strategy_leg_selection_rows",
        "right_stage": "historical_strategy_selection_rows",
        "operator": ">=",
    },
    {
        "name": "position_sizing_preserves_selection_rows",
        "left_stage": "portfolio_position_sizing_replay",
        "right_stage": "historical_strategy_selection_rows",
        "operator": "==",
    },
    {
        "name": "trade_sequence_preserves_position_sizing_rows",
        "left_stage": "portfolio_selected_trade_sequence",
        "right_stage": "portfolio_position_sizing_replay",
        "operator": "==",
    },
    {
        "name": "trade_sequence_covers_layer_enrichment_rows",
        "left_stage": "portfolio_selected_trade_sequence",
        "right_stage": "layer_field_carry_forward_enrichment_v2",
        "operator": ">=",
    },
    {
        "name": "layer_enrichment_covers_quote_join_rows",
        "left_stage": "layer_field_carry_forward_enrichment_v2",
        "right_stage": "quote_join",
        "operator": ">=",
    },
    {
        "name": "pruning_rows_not_larger_than_quote_join_rows",
        "left_stage": "quote_join",
        "right_stage": "v3_2_2_pruning",
        "operator": ">=",
    },
]


REQUIRED_NON_EMPTY_STAGES = {
    "historical_decision_rows",
    "historical_strategy_candidate_rows",
    "walk_forward_expectancy",
    "historical_strategy_selection_rows",
    "historical_strategy_leg_selection_rows",
    "portfolio_position_sizing_replay",
    "portfolio_selected_trade_sequence",
    "quote_join",
    "quote_attribution",
    "v3_2_2_pruning",
    "ruleset_lock",
    "stress_validation",
}


def load_stage1_manifest() -> dict[str, Any]:
    if not STAGE1_MANIFEST_PATH.exists():
        raise FileNotFoundError(
            f"Stage 1 manifest not found: {STAGE1_MANIFEST_PATH}. "
            "Run stage1 artifact mirror replay first."
        )

    return json.loads(STAGE1_MANIFEST_PATH.read_text(encoding="utf-8-sig"))


def sample_rows(path: Path, limit: int = 20) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8-sig", errors="ignore") as handle:
        for line in handle:
            if not line.strip():
                continue

            parsed = json.loads(line)
            if isinstance(parsed, dict):
                rows.append(parsed)

            if len(rows) >= limit:
                break

    return rows


def _compare(left: int, right: int, operator: str) -> bool:
    if operator == ">=":
        return left >= right
    if operator == "==":
        return left == right
    if operator == "<=":
        return left <= right
    raise ValueError(f"Unsupported operator: {operator}")


def build_stage3_semantic_continuity_replay() -> dict[str, Any]:
    stage1 = load_stage1_manifest()

    stage_rows: dict[str, dict[str, Any]] = {}
    blockers: list[str] = []
    warnings: list[str] = []

    for stage in stage1["stage_results"]:
        stage_name = stage["stage"]
        row_artifact = stage.get("row_artifact")

        if not row_artifact:
            if stage_name in REQUIRED_NON_EMPTY_STAGES:
                blockers.append(f"{stage_name}_row_artifact_missing")
            continue

        row_path = Path(row_artifact["destination_path"])
        row_count = int(row_artifact.get("row_count") or 0)

        if stage_name in REQUIRED_NON_EMPTY_STAGES and row_count <= 0:
            blockers.append(f"{stage_name}_row_count_not_positive")

        rows = sample_rows(row_path)
        sample_keys = sorted({key for row in rows for key in row.keys()})

        if not rows and stage_name in REQUIRED_NON_EMPTY_STAGES:
            blockers.append(f"{stage_name}_sample_rows_missing")

        common_lineage_keys = [
            key for key in sample_keys
            if key in {
                "symbol",
                "underlying",
                "date",
                "as_of_date",
                "entry_date",
                "strategy",
                "strategy_name",
                "strategy_family",
                "candidate_id",
                "request_id",
                "trade_id",
                "position_id",
                "regime",
                "regime_label",
            }
        ]

        if stage_name in {
            "historical_decision_rows",
            "historical_strategy_candidate_rows",
            "historical_strategy_selection_rows",
            "portfolio_position_sizing_replay",
            "portfolio_selected_trade_sequence",
        } and not common_lineage_keys:
            warnings.append(f"{stage_name}_no_common_lineage_keys_in_sample")

        stage_rows[stage_name] = {
            "stage": stage_name,
            "row_path": str(row_path),
            "row_count": row_count,
            "sample_row_count": len(rows),
            "sample_key_count": len(sample_keys),
            "sample_keys": sample_keys,
            "common_lineage_keys": common_lineage_keys,
            "is_non_empty": row_count > 0,
        }

    relationship_results: list[dict[str, Any]] = []

    for relationship in EXPECTED_RELATIONSHIPS:
        left_stage = relationship["left_stage"]
        right_stage = relationship["right_stage"]
        operator = relationship["operator"]

        left = stage_rows.get(left_stage)
        right = stage_rows.get(right_stage)

        if not left or not right:
            passed = False
            blockers.append(f'{relationship["name"]}_stage_missing')
            left_count = None
            right_count = None
        else:
            left_count = left["row_count"]
            right_count = right["row_count"]
            passed = _compare(left_count, right_count, operator)

            if not passed:
                blockers.append(f'{relationship["name"]}_failed')

        relationship_results.append({
            "name": relationship["name"],
            "left_stage": left_stage,
            "right_stage": right_stage,
            "operator": operator,
            "left_row_count": left_count,
            "right_row_count": right_count,
            "passed": passed,
        })

    return {
        "adapter_type": "migrated_workflow_stage3_semantic_continuity_replay_builder",
        "artifact_type": "signalforge_migrated_workflow_stage3_semantic_continuity_replay",
        "candidate_id": "signalforge_v3_2_2_paper_candidate",
        "stage_count": len(stage_rows),
        "stage_rows": stage_rows,
        "relationship_count": len(relationship_results),
        "relationship_results": relationship_results,
        "blocker_count": len(blockers),
        "warning_count": len(warnings),
        "blockers": blockers,
        "warnings": warnings,
        "is_ready": len(blockers) == 0,
        "readiness_scope": "mirrored_artifacts_have_semantic_row_count_continuity_and_parseable_lineage_samples",
    }


def main() -> int:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    result = build_stage3_semantic_continuity_replay()
    output_path = OUTPUT_ROOT / "signalforge_migrated_workflow_stage3_semantic_continuity_replay.json"
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())


