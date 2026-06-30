from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from signalforge.backtesting.migrated_workflow_dry_run_plan import (
    build_migrated_workflow_dry_run_plan,
)


OUTPUT_ROOT = Path("artifacts/migrated_workflow_dry_run_20210601_20260531")
MIRROR_ROOT = OUTPUT_ROOT / "stage1_artifact_mirror"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def count_jsonl(path: Path) -> int:
    count = 0

    with path.open("r", encoding="utf-8-sig", errors="ignore") as handle:
        for line in handle:
            if line.strip():
                count += 1

    return count


def copy_if_requested(source: Path, destination: Path, copy_files: bool) -> None:
    if not copy_files:
        return

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def build_stage1_artifact_mirror_replay(copy_files: bool = False) -> dict[str, Any]:
    plan = build_migrated_workflow_dry_run_plan()

    blockers: list[str] = []
    stage_results: list[dict[str, Any]] = []

    for index, stage in enumerate(plan["stages"], start=1):
        stage_name = stage["stage"]
        stage_dir = MIRROR_ROOT / f"{index:02d}_{stage_name}"

        row_path = Path(stage["selected_row_path"]) if stage.get("selected_row_path") else None
        json_path = Path(stage["selected_json_path"]) if stage.get("selected_json_path") else None

        row_result: dict[str, Any] | None = None
        json_result: dict[str, Any] | None = None

        if row_path:
            if not row_path.exists():
                blockers.append(f"{stage_name}_row_source_missing")
            else:
                destination = stage_dir / f"{stage_name}_rows.jsonl"
                row_count = count_jsonl(row_path)

                if row_count <= 0:
                    blockers.append(f"{stage_name}_row_source_empty")

                copy_if_requested(row_path, destination, copy_files)

                row_result = {
                    "source_path": str(row_path),
                    "source_name": row_path.name,
                    "destination_path": str(destination),
                    "source_size_bytes": row_path.stat().st_size,
                    "source_sha256": sha256_file(row_path),
                    "row_count": row_count,
                    "copied": copy_files,
                }

        if json_path:
            if not json_path.exists():
                blockers.append(f"{stage_name}_json_source_missing")
            else:
                destination = stage_dir / f"{stage_name}_summary.json"
                copy_if_requested(json_path, destination, copy_files)

                json_result = {
                    "source_path": str(json_path),
                    "source_name": json_path.name,
                    "destination_path": str(destination),
                    "source_size_bytes": json_path.stat().st_size,
                    "source_sha256": sha256_file(json_path),
                    "copied": copy_files,
                }

        stage_results.append({
            "stage": stage_name,
            "stage_index": index,
            "module": stage.get("module"),
            "stage_dir": str(stage_dir),
            "row_artifact": row_result,
            "json_artifact": json_result,
            "is_mirrored": bool(row_result or json_result),
        })

    return {
        "adapter_type": "migrated_workflow_stage1_artifact_mirror_replay_builder",
        "artifact_type": "signalforge_migrated_workflow_stage1_artifact_mirror_replay",
        "candidate_id": "signalforge_v3_2_2_paper_candidate",
        "output_root": str(OUTPUT_ROOT),
        "mirror_root": str(MIRROR_ROOT),
        "copy_files": copy_files,
        "stage_count": len(stage_results),
        "stage_results": stage_results,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "is_ready": len(blockers) == 0,
        "readiness_scope": "canonical_old_artifacts_mirrored_into_clean_repo_dry_run_folder",
    }


def main() -> int:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    MIRROR_ROOT.mkdir(parents=True, exist_ok=True)

    result = build_stage1_artifact_mirror_replay(copy_files=True)

    output_path = OUTPUT_ROOT / "signalforge_migrated_workflow_stage1_artifact_mirror_replay.json"
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())




