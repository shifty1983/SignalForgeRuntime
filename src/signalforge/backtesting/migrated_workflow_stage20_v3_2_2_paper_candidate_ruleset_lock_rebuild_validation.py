from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


OUTPUT_ROOT = Path("artifacts/migrated_workflow_dry_run_20210601_20260531")

SOURCE_DIR = OUTPUT_ROOT / "stage1_artifact_mirror" / "17b_v3_2_2_paper_candidate_ruleset_lock"
GENERATED_DIR = OUTPUT_ROOT / "stage20_v3_2_2_paper_candidate_ruleset_lock_rebuild"

FILE_CHECKS = [
    {
        "label": "lock_json",
        "source": SOURCE_DIR / "v3_2_2_paper_candidate_ruleset_lock.json",
        "generated": GENERATED_DIR / "signalforge_v3_2_2_paper_candidate_ruleset_lock.json",
    },
    {
        "label": "lock_md",
        "source": SOURCE_DIR / "v3_2_2_paper_candidate_ruleset_lock.md",
        "generated": GENERATED_DIR / "signalforge_v3_2_2_paper_candidate_ruleset_lock.md",
    },
]

GENERATED_LOCK_JSON = GENERATED_DIR / "signalforge_v3_2_2_paper_candidate_ruleset_lock.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_stage20_v3_2_2_paper_candidate_ruleset_lock_rebuild_validation() -> dict[str, Any]:
    blockers: list[str] = []
    checks: list[dict[str, Any]] = []

    for check in FILE_CHECKS:
        label = check["label"]
        source = check["source"]
        generated = check["generated"]

        if not source.exists():
            blockers.append(f"{label}_source_missing")
            continue

        if not generated.exists():
            blockers.append(f"{label}_generated_missing")
            continue

        source_bytes = source.stat().st_size
        generated_bytes = generated.stat().st_size
        source_sha256 = sha256_file(source)
        generated_sha256 = sha256_file(generated)

        byte_count_matches = source_bytes == generated_bytes
        sha256_matches = source_sha256 == generated_sha256

        if not byte_count_matches:
            blockers.append(f"{label}_byte_count_mismatch")

        if not sha256_matches:
            blockers.append(f"{label}_sha256_mismatch")

        checks.append({
            "label": label,
            "source": str(source),
            "generated": str(generated),
            "source_bytes": source_bytes,
            "generated_bytes": generated_bytes,
            "byte_count_matches": byte_count_matches,
            "source_sha256": source_sha256,
            "generated_sha256": generated_sha256,
            "sha256_matches": sha256_matches,
        })

    lock_payload: dict[str, Any] = {}
    if GENERATED_LOCK_JSON.exists():
        lock_payload = json.loads(GENERATED_LOCK_JSON.read_text(encoding="utf-8-sig"))
    else:
        blockers.append("generated_lock_json_missing")

    return {
        "adapter_type": "migrated_workflow_stage20_v3_2_2_paper_candidate_ruleset_lock_rebuild_validation_builder",
        "artifact_type": "signalforge_migrated_workflow_stage20_v3_2_2_paper_candidate_ruleset_lock_rebuild_validation",
        "candidate_id": "signalforge_v3_2_2_paper_candidate",
        "source_dir": str(SOURCE_DIR),
        "generated_dir": str(GENERATED_DIR),
        "file_checks": checks,
        "all_byte_counts_match": all(item["byte_count_matches"] for item in checks) if checks else False,
        "all_sha256_match": all(item["sha256_matches"] for item in checks) if checks else False,
        "generated_lock_core": {
            "adapter_type": lock_payload.get("adapter_type"),
            "artifact_type": lock_payload.get("artifact_type"),
            "is_ready": lock_payload.get("is_ready"),
            "readiness_state": lock_payload.get("readiness_state"),
            "decision": lock_payload.get("decision"),
            "paper_candidate_id": lock_payload.get("paper_candidate_id"),
            "paper_candidate_state": lock_payload.get("paper_candidate_state"),
            "live_candidate_state": lock_payload.get("live_candidate_state"),
            "parent_candidate": lock_payload.get("parent_candidate"),
        },
        "blocker_count": len(blockers),
        "blockers": blockers,
        "is_ready": len(blockers) == 0,
        "readiness_scope": "migrated_v3_2_2_paper_candidate_ruleset_lock_static_pack_matches_source_bytes_and_hash",
    }


def main() -> int:
    result = build_stage20_v3_2_2_paper_candidate_ruleset_lock_rebuild_validation()

    output_path = OUTPUT_ROOT / "signalforge_migrated_workflow_stage20_v3_2_2_paper_candidate_ruleset_lock_rebuild_validation.json"
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
