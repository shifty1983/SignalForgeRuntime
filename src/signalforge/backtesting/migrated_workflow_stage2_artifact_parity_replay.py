from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


OUTPUT_ROOT = Path("artifacts/migrated_workflow_dry_run_20210601_20260531")
STAGE1_MANIFEST_PATH = (
    OUTPUT_ROOT / "signalforge_migrated_workflow_stage1_artifact_mirror_replay.json"
)


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


def load_stage1_manifest() -> dict[str, Any]:
    if not STAGE1_MANIFEST_PATH.exists():
        raise FileNotFoundError(
            f"Stage 1 manifest not found: {STAGE1_MANIFEST_PATH}. "
            "Run python -m signalforge.backtesting.migrated_workflow_stage1_artifact_mirror_replay first."
        )

    return json.loads(STAGE1_MANIFEST_PATH.read_text(encoding="utf-8-sig"))


def _parity_for_artifact(
    stage_name: str,
    artifact_type: str,
    artifact: dict[str, Any] | None,
) -> dict[str, Any]:
    if artifact is None:
        return {
            "stage": stage_name,
            "artifact_type": artifact_type,
            "is_present": False,
            "is_ready": True,
            "reason": "artifact_not_required_or_not_selected",
        }

    source_path = Path(artifact["source_path"])
    destination_path = Path(artifact["destination_path"])

    source_exists = source_path.exists()
    destination_exists = destination_path.exists()

    result: dict[str, Any] = {
        "stage": stage_name,
        "artifact_type": artifact_type,
        "source_path": str(source_path),
        "destination_path": str(destination_path),
        "source_exists": source_exists,
        "destination_exists": destination_exists,
        "is_present": True,
        "is_ready": False,
        "mismatches": [],
    }

    if not source_exists:
        result["mismatches"].append("source_missing")

    if not destination_exists:
        result["mismatches"].append("destination_missing")

    if result["mismatches"]:
        return result

    source_size = source_path.stat().st_size
    destination_size = destination_path.stat().st_size
    source_sha256 = sha256_file(source_path)
    destination_sha256 = sha256_file(destination_path)

    result.update({
        "source_size_bytes": source_size,
        "destination_size_bytes": destination_size,
        "source_sha256": source_sha256,
        "destination_sha256": destination_sha256,
        "size_matches": source_size == destination_size,
        "sha256_matches": source_sha256 == destination_sha256,
    })

    if source_size != destination_size:
        result["mismatches"].append("size_mismatch")

    if source_sha256 != destination_sha256:
        result["mismatches"].append("sha256_mismatch")

    if source_path.suffix.lower() == ".jsonl" and destination_path.suffix.lower() == ".jsonl":
        source_row_count = count_jsonl(source_path)
        destination_row_count = count_jsonl(destination_path)

        result.update({
            "source_row_count": source_row_count,
            "destination_row_count": destination_row_count,
            "row_count_matches": source_row_count == destination_row_count,
        })

        if source_row_count != destination_row_count:
            result["mismatches"].append("row_count_mismatch")

    result["is_ready"] = len(result["mismatches"]) == 0
    return result


def build_stage2_artifact_parity_replay() -> dict[str, Any]:
    stage1 = load_stage1_manifest()

    artifact_results: list[dict[str, Any]] = []

    for stage in stage1["stage_results"]:
        stage_name = stage["stage"]

        artifact_results.append(
            _parity_for_artifact(
                stage_name,
                "row_artifact",
                stage.get("row_artifact"),
            )
        )
        artifact_results.append(
            _parity_for_artifact(
                stage_name,
                "json_artifact",
                stage.get("json_artifact"),
            )
        )

    blockers = [
        f'{result["stage"]}_{result["artifact_type"]}_parity_failed'
        for result in artifact_results
        if not result["is_ready"]
    ]

    compared_artifacts = [
        result for result in artifact_results if result.get("is_present")
    ]

    return {
        "adapter_type": "migrated_workflow_stage2_artifact_parity_replay_builder",
        "artifact_type": "signalforge_migrated_workflow_stage2_artifact_parity_replay",
        "candidate_id": "signalforge_v3_2_2_paper_candidate",
        "stage1_manifest_path": str(STAGE1_MANIFEST_PATH),
        "stage_count": stage1.get("stage_count"),
        "compared_artifact_count": len(compared_artifacts),
        "artifact_results": artifact_results,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "is_ready": len(blockers) == 0,
        "readiness_scope": "mirrored_clean_repo_artifacts_match_source_artifacts_by_sha256_size_and_row_count",
    }


def main() -> int:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    result = build_stage2_artifact_parity_replay()
    output_path = OUTPUT_ROOT / "signalforge_migrated_workflow_stage2_artifact_parity_replay.json"
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

