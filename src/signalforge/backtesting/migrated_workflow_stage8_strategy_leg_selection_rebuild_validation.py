from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


OUTPUT_ROOT = Path("artifacts/migrated_workflow_dry_run_20210601_20260531")

SOURCE_ROWS = (
    OUTPUT_ROOT
    / "stage1_artifact_mirror"
    / "05_historical_strategy_leg_selection_rows"
    / "historical_strategy_leg_selection_rows_rows.jsonl"
)

GENERATED_DIR = OUTPUT_ROOT / "stage8_strategy_leg_selection_rebuild"
GENERATED_ROWS = GENERATED_DIR / "signalforge_historical_strategy_leg_selection_rows.jsonl"
GENERATED_SUMMARY = GENERATED_DIR / "signalforge_historical_strategy_leg_selection_rows_summary.json"


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


def sample_keys(path: Path, limit: int = 5) -> list[str]:
    keys: set[str] = set()

    with path.open("r", encoding="utf-8-sig", errors="ignore") as handle:
        for line in handle:
            if not line.strip():
                continue

            row = json.loads(line)
            if isinstance(row, dict):
                keys.update(row.keys())

            limit -= 1
            if limit <= 0:
                break

    return sorted(keys)


def build_stage8_strategy_leg_selection_rebuild_validation() -> dict[str, Any]:
    blockers: list[str] = []

    for label, path in {
        "source_rows": SOURCE_ROWS,
        "generated_rows": GENERATED_ROWS,
        "generated_summary": GENERATED_SUMMARY,
    }.items():
        if not path.exists():
            blockers.append(f"{label}_missing")

    if blockers:
        return {
            "adapter_type": "migrated_workflow_stage8_strategy_leg_selection_rebuild_validation_builder",
            "artifact_type": "signalforge_migrated_workflow_stage8_strategy_leg_selection_rebuild_validation",
            "is_ready": False,
            "blocker_count": len(blockers),
            "blockers": blockers,
        }

    source_count = count_jsonl(SOURCE_ROWS)
    generated_count = count_jsonl(GENERATED_ROWS)

    source_sha256 = sha256_file(SOURCE_ROWS)
    generated_sha256 = sha256_file(GENERATED_ROWS)

    source_keys = sample_keys(SOURCE_ROWS)
    generated_keys = sample_keys(GENERATED_ROWS)

    if source_count != generated_count:
        blockers.append("leg_selection_row_count_mismatch")

    if source_keys != generated_keys:
        blockers.append("leg_selection_sample_schema_mismatch")

    summary = json.loads(GENERATED_SUMMARY.read_text(encoding="utf-8-sig"))

    return {
        "adapter_type": "migrated_workflow_stage8_strategy_leg_selection_rebuild_validation_builder",
        "artifact_type": "signalforge_migrated_workflow_stage8_strategy_leg_selection_rebuild_validation",
        "candidate_id": "signalforge_v3_2_2_paper_candidate",
        "source_rows": str(SOURCE_ROWS),
        "generated_rows": str(GENERATED_ROWS),
        "generated_summary": str(GENERATED_SUMMARY),
        "source_count": source_count,
        "generated_count": generated_count,
        "row_count_matches": source_count == generated_count,
        "source_sha256": source_sha256,
        "generated_sha256": generated_sha256,
        "sha256_matches": source_sha256 == generated_sha256,
        "source_sample_keys": source_keys,
        "generated_sample_keys": generated_keys,
        "sample_schema_matches": source_keys == generated_keys,
        "generated_summary_keys": sorted(summary.keys()),
        "generated_summary_core": {
            "is_ready": summary.get("is_ready"),
            "blocker_count": summary.get("blocker_count"),
            "input_candidate_row_count": summary.get("input_candidate_row_count"),
            "output_row_count": summary.get("output_row_count"),
            "selected_leg_row_count": summary.get("selected_leg_row_count"),
            "blocked_leg_row_count": summary.get("blocked_leg_row_count"),
            "emit_blocked_rows": summary.get("emit_blocked_rows"),
        },
        "blocker_count": len(blockers),
        "blockers": blockers,
        "is_ready": len(blockers) == 0,
        "readiness_scope": "migrated_strategy_leg_selection_rebuild_matches_source_row_count_schema_and_hash",
    }


def main() -> int:
    result = build_stage8_strategy_leg_selection_rebuild_validation()

    output_path = OUTPUT_ROOT / "signalforge_migrated_workflow_stage8_strategy_leg_selection_rebuild_validation.json"
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

