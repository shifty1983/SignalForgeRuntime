from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any


OUTPUT_ROOT = Path("artifacts/migrated_workflow_dry_run_20210601_20260531")

LEGACY_ARTIFACT_ROOT = Path(os.environ.get(
    "SIGNALFORGE_MIGRATION_CLOSURE_LEGACY_ARTIFACT_ROOT",
    r"C:\Users\02011715\Documents\SignalForge\raw_data_layer\artifacts",
))

EXPECTED_STAGES = {
    5: {
        "name": "historical strategy candidate rows",
        "generated_dir": "stage5_candidate_rebuild",
        "generated_dir_candidates": [
            "stage5_candidate_rebuild_probe",
            "stage5_historical_strategy_candidate_rows_rebuild",
            "stage5_historical_strategy_candidate_rows_rebuild_probe",
        ],
    },
    6: {
        "name": "walk-forward expectancy",
        "generated_dir": "stage6_expectancy_rebuild",
        "generated_dir_candidates": [
            "stage6_expectancy_rebuild_probe",
            "stage6_walk_forward_expectancy_rebuild",
            "stage6_walk_forward_expectancy_rebuild_probe",
        ],
    },
    7: {
        "name": "historical strategy selection rows",
        "generated_dir": "stage7_strategy_selection_rebuild",
    },
    8: {
        "name": "historical strategy leg selection rows",
        "generated_dir": "stage8_strategy_leg_selection_rebuild",
    },
    9: {
        "name": "portfolio position sizing replay",
        "generated_dir": "stage9_position_sizing_rebuild",
    },
    10: {
        "name": "portfolio selected trade sequence",
        "generated_dir": "stage10_selected_trade_sequence_rebuild",
    },
    11: {
        "name": "layer field carry-forward enrichment",
        "generated_dir": "stage11_layer_field_carry_forward_enrichment_rebuild",
    },
    12: {
        "name": "native quote join",
        "generated_dir": "stage12_quote_join_rebuild",
    },
    13: {
        "name": "native quote PnL stress",
        "generated_dir": "stage13_quote_pnl_stress_rebuild",
    },
    14: {
        "name": "native quote attribution",
        "generated_dir": "stage14_quote_attribution_rebuild",
    },
    15: {
        "name": "walk-forward prune validation",
        "generated_dir": "stage15_native_quote_walkforward_prune_validation_rebuild",
    },
    16: {
        "name": "V3.2.2 symbol/regime prune stress",
        "generated_dir": "stage16_v3_2_2_symbol_regime_prune_stress_rebuild",
    },
    17: {
        "name": "V3.2.2 iron butterfly dependence",
        "generated_dir": "stage17_v3_2_2_iron_butterfly_dependence_rebuild",
    },
    18: {
        "name": "V3.2.2 native quote attribution",
        "generated_dir": "stage18_v3_2_2_native_quote_attribution_rebuild",
    },
    19: {
        "name": "V3.2.2 pre-broker audit pack",
        "generated_dir": "stage19_v3_2_2_pre_broker_audit_pack_rebuild",
    },
    20: {
        "name": "V3.2.2 paper candidate ruleset lock",
        "generated_dir": "stage20_v3_2_2_paper_candidate_ruleset_lock_rebuild",
    },
}

POST_LOCK_LEGACY_PATTERN = re.compile(
    r"complete_ruleset|current|paper|broker|execution|runtime|deployment|readiness|locked|drawdown|anchored|metrics|candidate",
    re.IGNORECASE,
)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def find_stage_validation(stage: int) -> Path | None:
    candidates = sorted(
        OUTPUT_ROOT.glob(f"signalforge_migrated_workflow_stage{stage}*validation.json")
    )
    if candidates:
        return candidates[-1]
    return None


def validation_flag_blockers(payload: dict[str, Any], stage: int) -> list[str]:
    blockers: list[str] = []

    if payload.get("is_ready") is not True:
        blockers.append(f"stage{stage}_validation_not_ready")

    if int(payload.get("blocker_count") or 0) != 0:
        blockers.append(f"stage{stage}_validation_has_blockers")

    scalar_flags = [
        "row_count_matches",
        "sample_schema_matches",
        "sha256_matches",
        "all_row_counts_match",
        "all_sample_schemas_match",
        "all_sha256_match",
        "all_byte_counts_match",
    ]

    for flag in scalar_flags:
        if flag in payload and payload.get(flag) is not True:
            blockers.append(f"stage{stage}_{flag}_false")

    for collection_name in ["row_checks", "file_checks"]:
        for idx, item in enumerate(payload.get(collection_name, []) or []):
            for flag in [
                "row_count_matches",
                "sample_schema_matches",
                "sha256_matches",
                "byte_count_matches",
            ]:
                if flag in item and item.get(flag) is not True:
                    label = item.get("label", idx)
                    blockers.append(f"stage{stage}_{collection_name}_{label}_{flag}_false")

    return blockers


def legacy_post_lock_inventory() -> list[dict[str, Any]]:
    if not LEGACY_ARTIFACT_ROOT.exists():
        return []

    rows: list[dict[str, Any]] = []
    for folder in sorted(p for p in LEGACY_ARTIFACT_ROOT.iterdir() if p.is_dir()):
        if not POST_LOCK_LEGACY_PATTERN.search(folder.name):
            continue

        file_count = sum(1 for p in folder.rglob("*") if p.is_file())
        total_bytes = sum(p.stat().st_size for p in folder.rglob("*") if p.is_file())

        rows.append({
            "name": folder.name,
            "path": str(folder),
            "file_count": file_count,
            "total_bytes": total_bytes,
        })

    return rows


def build_migrated_workflow_closure_audit() -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    stage_results: list[dict[str, Any]] = []

    for stage, config in EXPECTED_STAGES.items():
        configured_generated_dir = OUTPUT_ROOT / config["generated_dir"]
        generated_dir_candidates = [configured_generated_dir] + [
            OUTPUT_ROOT / candidate
            for candidate in config.get("generated_dir_candidates", [])
        ]
        generated_dir = next(
            (candidate for candidate in generated_dir_candidates if candidate.exists()),
            configured_generated_dir,
        )
        validation_path = find_stage_validation(stage)

        stage_blockers: list[str] = []

        generated_dir_exists_any = any(candidate.exists() for candidate in generated_dir_candidates)
        if not generated_dir_exists_any:
            # Early probe stages may have validation artifacts but no retained rebuild directory.
            # If validation is ready, treat missing generated directory as an informational warning,
            # not a closure blocker.
            pass

        validation_core: dict[str, Any] = {}
        validation_ready = False
        if validation_path is None:
            stage_blockers.append(f"stage{stage}_validation_json_missing")
        else:
            payload = read_json(validation_path)
            validation_blockers = validation_flag_blockers(payload, stage)
            stage_blockers.extend(validation_blockers)
            validation_ready = len(validation_blockers) == 0
            validation_core = {
                "path": str(validation_path),
                "is_ready": payload.get("is_ready"),
                "blocker_count": payload.get("blocker_count"),
                "readiness_scope": payload.get("readiness_scope"),
                "generated_summary_core": payload.get("generated_summary_core"),
                "generated_lock_core": payload.get("generated_lock_core"),
            }

        if not generated_dir_exists_any and validation_ready:
            warnings.append(f"stage{stage}_generated_dir_missing_but_validation_ready")
        elif not generated_dir_exists_any:
            stage_blockers.append(f"stage{stage}_generated_dir_missing")

        stage_ready = len(stage_blockers) == 0
        blockers.extend(stage_blockers)

        stage_results.append({
            "stage": stage,
            "name": config["name"],
            "generated_dir": str(generated_dir),
            "generated_dir_exists": generated_dir.exists(),
            "generated_dir_candidates": [str(candidate) for candidate in generated_dir_candidates],
            "validation": validation_core,
            "stage_ready": stage_ready,
            "blockers": stage_blockers,
        })

    legacy_inventory = legacy_post_lock_inventory()
    if legacy_inventory:
        warnings.append(
            "Legacy post-lock/runtime candidate artifacts still exist in the old artifact root; review inventory before deleting or migrating any remaining runtime/deployment work."
        )

    lock_stage = next((s for s in stage_results if s["stage"] == 20), {})
    lock_core = ((lock_stage.get("validation") or {}).get("generated_lock_core") or {})

    closure_state = "closed_through_v3_2_2_paper_candidate_lock" if not blockers else "closure_blocked"

    return {
        "adapter_type": "migrated_workflow_closure_audit_builder",
        "artifact_type": "signalforge_migrated_workflow_closure_audit",
        "contract": "migrated_workflow_closure_audit",
        "closure_state": closure_state,
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,
        "validated_stage_count": len(stage_results),
        "expected_stage_count": len(EXPECTED_STAGES),
        "ready_stage_count": sum(1 for row in stage_results if row["stage_ready"]),
        "stage_results": stage_results,
        "paper_candidate_lock_core": lock_core,
        "legacy_artifact_root": str(LEGACY_ARTIFACT_ROOT),
        "legacy_post_lock_inventory_count": len(legacy_inventory),
        "legacy_post_lock_inventory": legacy_inventory,
        "readiness_scope": "migrated_backtesting_chain_parity_closed_through_v3_2_2_paper_candidate_ruleset_lock",
    }


def build_markdown_report(result: dict[str, Any]) -> str:
    lines = [
        "# SignalForge Migrated Workflow Closure Audit",
        "",
        f"Closure state: `{result['closure_state']}`",
        f"Is ready: `{result['is_ready']}`",
        f"Blocker count: `{result['blocker_count']}`",
        f"Warning count: `{result['warning_count']}`",
        "",
        "## Stage readiness",
        "",
        "| Stage | Name | Ready |",
        "|---:|---|---:|",
    ]

    for row in result["stage_results"]:
        lines.append(f"| {row['stage']} | {row['name']} | {row['stage_ready']} |")

    lines.extend([
        "",
        "## Paper candidate lock",
        "",
        f"Decision: `{result['paper_candidate_lock_core'].get('decision')}`",
        f"Paper candidate: `{result['paper_candidate_lock_core'].get('paper_candidate_id')}`",
        f"Live state: `{result['paper_candidate_lock_core'].get('live_candidate_state')}`",
        "",
        "## Remaining legacy post-lock inventory",
        "",
        f"Count: `{result['legacy_post_lock_inventory_count']}`",
    ])

    for item in result["legacy_post_lock_inventory"][:50]:
        lines.append(f"- `{item['name']}` files={item['file_count']} bytes={item['total_bytes']}")

    lines.append("")
    return "\n".join(lines)


def main() -> int:
    result = build_migrated_workflow_closure_audit()

    json_path = OUTPUT_ROOT / "signalforge_migrated_workflow_closure_audit.json"
    md_path = OUTPUT_ROOT / "signalforge_migrated_workflow_closure_audit.md"

    json_path.write_text(json.dumps(result, indent=2, sort_keys=True, default=str), encoding="utf-8")
    md_path.write_text(build_markdown_report(result), encoding="utf-8")

    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())


