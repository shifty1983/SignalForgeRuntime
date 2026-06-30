from __future__ import annotations

import json
from pathlib import Path
from typing import Any


OUTPUT_ROOT = Path("artifacts/migrated_workflow_dry_run_20210601_20260531")

INPUT_MANIFESTS = {
    "workflow_manifest": Path("artifacts/migrated_workflow_manifest_debug.json"),
    "exact_artifact_paths": Path("artifacts/migrated_workflow_exact_artifact_paths.json"),
    "dry_run_plan": OUTPUT_ROOT / "signalforge_migrated_workflow_dry_run_plan.json",
    "stage0_artifact_contract": OUTPUT_ROOT / "signalforge_migrated_workflow_stage0_artifact_contract_replay.json",
    "stage1_artifact_mirror": OUTPUT_ROOT / "signalforge_migrated_workflow_stage1_artifact_mirror_replay.json",
    "stage2_artifact_parity": OUTPUT_ROOT / "signalforge_migrated_workflow_stage2_artifact_parity_replay.json",
    "stage3_semantic_continuity": OUTPUT_ROOT / "signalforge_migrated_workflow_stage3_semantic_continuity_replay.json",
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _manifest_status(name: str, path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "name": name,
            "path": str(path),
            "exists": False,
            "is_ready": False,
            "blocker_count": 1,
            "blockers": [f"{name}_manifest_missing"],
            "warning_count": 0,
            "warnings": [],
        }

    data = read_json(path)

    return {
        "name": name,
        "path": str(path),
        "exists": True,
        "is_ready": bool(data.get("is_ready", False)),
        "blocker_count": int(data.get("blocker_count", 0) or 0),
        "blockers": list(data.get("blockers", [])),
        "warning_count": int(data.get("warning_count", 0) or 0),
        "warnings": list(data.get("warnings", [])),
        "adapter_type": data.get("adapter_type"),
        "artifact_type": data.get("artifact_type"),
    }


def build_stage4_migrated_workflow_readiness_rollup() -> dict[str, Any]:
    statuses = [
        _manifest_status(name, path)
        for name, path in INPUT_MANIFESTS.items()
    ]

    blockers: list[str] = []
    warnings: list[str] = []

    for status in statuses:
        if not status["exists"]:
            blockers.append(f'{status["name"]}_manifest_missing')
            continue

        if not status["is_ready"]:
            blockers.append(f'{status["name"]}_not_ready')

        for blocker in status["blockers"]:
            blockers.append(f'{status["name"]}:{blocker}')

        for warning in status["warnings"]:
            warnings.append(f'{status["name"]}:{warning}')

    stage3_path = INPUT_MANIFESTS["stage3_semantic_continuity"]
    stage3 = read_json(stage3_path) if stage3_path.exists() else {}
    relationships = stage3.get("relationship_results", [])

    failed_relationships = [
        item.get("name")
        for item in relationships
        if not item.get("passed")
    ]

    for relationship in failed_relationships:
        blockers.append(f"semantic_relationship_failed:{relationship}")

    return {
        "adapter_type": "migrated_workflow_stage4_readiness_rollup_builder",
        "artifact_type": "signalforge_migrated_workflow_stage4_readiness_rollup",
        "candidate_id": "signalforge_v3_2_2_paper_candidate",
        "date_window": {
            "source_start": "2021-06-01",
            "source_end": "2026-05-31",
            "locked_ruleset_start": "2023-01-01",
            "locked_ruleset_end": "2026-05-31",
        },
        "input_manifest_count": len(statuses),
        "input_manifest_statuses": statuses,
        "semantic_relationship_count": len(relationships),
        "failed_semantic_relationships": failed_relationships,
        "blocker_count": len(blockers),
        "warning_count": len(warnings),
        "blockers": blockers,
        "warnings": warnings,
        "is_ready": len(blockers) == 0,
        "readiness_scope": "migrated_source_imports_and_mirrored_artifact_workflow_are_ready_for_first_artifact_producing_rebuild",
        "next_recommended_step": "run_first_migrated_artifact_producing_stage_with_controlled_inputs",
    }


def main() -> int:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    result = build_stage4_migrated_workflow_readiness_rollup()
    output_path = OUTPUT_ROOT / "signalforge_migrated_workflow_stage4_readiness_rollup.json"
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())




