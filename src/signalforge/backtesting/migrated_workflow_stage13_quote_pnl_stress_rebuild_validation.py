from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


OUTPUT_ROOT = Path("artifacts/migrated_workflow_dry_run_20210601_20260531")

SOURCE_DIR = OUTPUT_ROOT / "stage1_artifact_mirror" / "10b_quote_pnl_stress"
GENERATED_DIR = OUTPUT_ROOT / "stage13_quote_pnl_stress_rebuild"

ROW_CHECKS = [
    {
        "label": "stress_results",
        "source": SOURCE_DIR / "quote_pnl_stress_results.jsonl",
        "generated": GENERATED_DIR / "signalforge_v3_2_1_native_quote_pnl_stress_results.jsonl",
    },
    {
        "label": "breakeven_rows",
        "source": SOURCE_DIR / "quote_pnl_breakeven_rows.jsonl",
        "generated": GENERATED_DIR / "signalforge_v3_2_1_native_quote_breakeven_curve.jsonl",
    },
    {
        "label": "30k_ledger",
        "source": SOURCE_DIR / "quote_pnl_stress_30k_ledger.jsonl",
        "generated": GENERATED_DIR / "v3_2_1_native_quote_30k" / "ledger.jsonl",
    },
    {
        "label": "40k_ledger",
        "source": SOURCE_DIR / "quote_pnl_stress_40k_ledger.jsonl",
        "generated": GENERATED_DIR / "v3_2_1_native_quote_40k" / "ledger.jsonl",
    },
]

GENERATED_SUMMARY = GENERATED_DIR / "signalforge_v3_2_1_native_quote_pnl_stress_summary.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def count_jsonl(path: Path) -> int:
    with path.open("r", encoding="utf-8-sig", errors="ignore") as handle:
        return sum(1 for line in handle if line.strip())


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


def build_stage13_quote_pnl_stress_rebuild_validation() -> dict[str, Any]:
    blockers: list[str] = []
    checks: list[dict[str, Any]] = []

    if not GENERATED_SUMMARY.exists():
        blockers.append("generated_summary_missing")

    for check in ROW_CHECKS:
        label = check["label"]
        source = check["source"]
        generated = check["generated"]

        if not source.exists():
            blockers.append(f"{label}_source_missing")
            continue

        if not generated.exists():
            blockers.append(f"{label}_generated_missing")
            continue

        source_count = count_jsonl(source)
        generated_count = count_jsonl(generated)
        source_sha256 = sha256_file(source)
        generated_sha256 = sha256_file(generated)
        source_keys = sample_keys(source)
        generated_keys = sample_keys(generated)

        row_count_matches = source_count == generated_count
        sha256_matches = source_sha256 == generated_sha256
        sample_schema_matches = source_keys == generated_keys

        if not row_count_matches:
            blockers.append(f"{label}_row_count_mismatch")

        if not sample_schema_matches:
            blockers.append(f"{label}_sample_schema_mismatch")

        if not sha256_matches:
            blockers.append(f"{label}_sha256_mismatch")

        checks.append({
            "label": label,
            "source": str(source),
            "generated": str(generated),
            "source_count": source_count,
            "generated_count": generated_count,
            "row_count_matches": row_count_matches,
            "source_sha256": source_sha256,
            "generated_sha256": generated_sha256,
            "sha256_matches": sha256_matches,
            "source_sample_keys": source_keys,
            "generated_sample_keys": generated_keys,
            "sample_schema_matches": sample_schema_matches,
        })

    summary: dict[str, Any] = {}
    if GENERATED_SUMMARY.exists():
        summary = json.loads(GENERATED_SUMMARY.read_text(encoding="utf-8-sig"))

    return {
        "adapter_type": "migrated_workflow_stage13_quote_pnl_stress_rebuild_validation_builder",
        "artifact_type": "signalforge_migrated_workflow_stage13_quote_pnl_stress_rebuild_validation",
        "candidate_id": "signalforge_v3_2_2_paper_candidate",
        "source_dir": str(SOURCE_DIR),
        "generated_dir": str(GENERATED_DIR),
        "generated_summary": str(GENERATED_SUMMARY),
        "row_checks": checks,
        "all_row_counts_match": all(item["row_count_matches"] for item in checks) if checks else False,
        "all_sample_schemas_match": all(item["sample_schema_matches"] for item in checks) if checks else False,
        "all_sha256_match": all(item["sha256_matches"] for item in checks) if checks else False,
        "generated_summary_core": {
            "adapter_type": summary.get("adapter_type"),
            "artifact_type": summary.get("artifact_type"),
            "is_ready": summary.get("is_ready"),
            "decision": summary.get("decision"),
            "promotion_checks": summary.get("promotion_checks"),
        },
        "blocker_count": len(blockers),
        "blockers": blockers,
        "is_ready": len(blockers) == 0,
        "readiness_scope": "migrated_native_quote_pnl_stress_rebuild_matches_source_row_count_schema_and_hash",
    }


def main() -> int:
    result = build_stage13_quote_pnl_stress_rebuild_validation()

    output_path = OUTPUT_ROOT / "signalforge_migrated_workflow_stage13_quote_pnl_stress_rebuild_validation.json"
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
