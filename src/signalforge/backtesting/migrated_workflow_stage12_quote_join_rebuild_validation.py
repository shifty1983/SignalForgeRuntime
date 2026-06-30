from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


OUTPUT_ROOT = Path("artifacts/migrated_workflow_dry_run_20210601_20260531")

SOURCE_ROWS = (
    OUTPUT_ROOT
    / "stage1_artifact_mirror"
    / "08_quote_join"
    / "quote_join_rows.jsonl"
)

GENERATED_DIR = OUTPUT_ROOT / "stage12_quote_join_rebuild"
GENERATED_ROWS = GENERATED_DIR / "signalforge_v3_2_1_native_quote_join_row_audit.jsonl"
GENERATED_SUMMARY = GENERATED_DIR / "signalforge_v3_2_1_native_quote_join_summary.json"


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


def build_stage12_quote_join_rebuild_validation() -> dict[str, Any]:
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
            "adapter_type": "migrated_workflow_stage12_quote_join_rebuild_validation_builder",
            "artifact_type": "signalforge_migrated_workflow_stage12_quote_join_rebuild_validation",
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
        blockers.append("quote_join_row_count_mismatch")

    if source_keys != generated_keys:
        blockers.append("quote_join_sample_schema_mismatch")

    if source_sha256 != generated_sha256:
        blockers.append("quote_join_sha256_mismatch")

    summary = json.loads(GENERATED_SUMMARY.read_text(encoding="utf-8-sig"))

    return {
        "adapter_type": "migrated_workflow_stage12_quote_join_rebuild_validation_builder",
        "artifact_type": "signalforge_migrated_workflow_stage12_quote_join_rebuild_validation",
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
        "generated_summary_core": {
            "adapter_type": summary.get("adapter_type"),
            "artifact_type": summary.get("artifact_type"),
            "is_ready": summary.get("is_ready"),
            "decision": summary.get("decision"),
            "required_quote_key_count": summary.get("required_quote_key_count"),
            "matched_quote_key_count": summary.get("matched_quote_key_count"),
            "quote_source_count": summary.get("quote_source_count"),
            "quote_candidate_count": summary.get("quote_candidate_count"),
        },
        "scenario_summary_core": [
            {
                "capital_label": item.get("capital_label"),
                "active_trade_count": item.get("active_trade_count"),
                "complete_entry_exit_quote_rows": item.get("complete_entry_exit_quote_rows"),
                "complete_entry_exit_quote_row_coverage": item.get("complete_entry_exit_quote_row_coverage"),
                "entry_leg_quote_match_count": item.get("entry_leg_quote_match_count"),
                "exit_leg_quote_match_count": item.get("exit_leg_quote_match_count"),
            }
            for item in summary.get("scenario_summaries", [])
            if isinstance(item, dict)
        ],
        "blocker_count": len(blockers),
        "blockers": blockers,
        "is_ready": len(blockers) == 0,
        "readiness_scope": "migrated_quote_join_rebuild_matches_source_row_count_schema_and_hash",
    }


def main() -> int:
    result = build_stage12_quote_join_rebuild_validation()

    output_path = OUTPUT_ROOT / "signalforge_migrated_workflow_stage12_quote_join_rebuild_validation.json"
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())


