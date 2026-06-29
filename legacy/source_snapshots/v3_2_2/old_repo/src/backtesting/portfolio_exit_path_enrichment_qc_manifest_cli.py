from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _read_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return payload


def _count_jsonl(path: str | Path) -> int:
    count = 0
    with Path(path).open("r", encoding="utf-8-sig", errors="ignore") as handle:
        for line in handle:
            if line.strip():
                count += 1
    return count


def _write_json(path: str | Path, payload: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build QC manifest for portfolio exit path enrichment.")
    parser.add_argument("--enrichment-summary", required=True)
    parser.add_argument("--enrichment-rows", required=True)
    parser.add_argument("--minimum-enriched-row-count", type=int, default=1)
    parser.add_argument("--minimum-final-outcome-path-coverage", type=float, default=0.95)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    summary = _read_json(args.enrichment_summary)
    row_count = _count_jsonl(args.enrichment_rows)
    coverage = summary.get("coverage") if isinstance(summary.get("coverage"), dict) else {}

    blockers: list[str] = []
    warnings: list[str] = []

    if summary.get("contract") != "portfolio_exit_path_enrichment":
        blockers.append("unexpected_enrichment_contract")
    if not summary.get("is_ready"):
        blockers.append("enrichment_summary_not_ready")
    if row_count < args.minimum_enriched_row_count:
        blockers.append("enriched_row_count_below_minimum")
    if row_count != summary.get("enriched_row_count"):
        blockers.append("summary_row_count_mismatch")

    final_coverage = coverage.get("final_outcome_path_coverage")
    if final_coverage is None or float(final_coverage) < args.minimum_final_outcome_path_coverage:
        blockers.append("final_outcome_path_coverage_below_qc_minimum")

    exit_policy_readiness = str(summary.get("exit_policy_readiness_state") or "missing")
    if exit_policy_readiness == "final_outcome_only":
        warnings.append("exit_path_enrichment_is_final_outcome_only_not_true_path_ready")
    elif exit_policy_readiness == "mae_mfe_ready":
        warnings.append("exit_path_enrichment_is_mae_mfe_ready_not_true_path_ready")

    manifest = {
        "adapter_type": "portfolio_exit_path_enrichment_qc_manifest_builder",
        "artifact_type": "signalforge_portfolio_exit_path_enrichment_qc_manifest",
        "contract": "portfolio_exit_path_enrichment_qc_manifest",
        "is_ready": len(blockers) == 0,
        "readiness_state": "pass" if len(blockers) == 0 else "blocked",
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,
        "enrichment_summary_path": str(args.enrichment_summary),
        "enrichment_rows_path": str(args.enrichment_rows),
        "diagnostics": {
            "actual_enriched_row_count": row_count,
            "summary_enriched_row_count": summary.get("enriched_row_count"),
            "exit_policy_readiness_state": exit_policy_readiness,
            "coverage": coverage,
            "path_enrichment_state_counts": summary.get("path_enrichment_state_counts"),
            "minimum_enriched_row_count": args.minimum_enriched_row_count,
            "minimum_final_outcome_path_coverage": args.minimum_final_outcome_path_coverage,
        },
        "explicit_exclusions": [
            "exit_rule_optimization",
            "defensive_adjustment_simulation",
            "synthetic_daily_quote_path_generation",
            "synthetic_mae_mfe_generation",
            "broker_margin_model",
            "live_execution",
        ],
        "paths": {
            "manifest_path": str(Path(args.output_dir) / "signalforge_portfolio_exit_path_enrichment_qc_manifest.json"),
        },
    }

    _write_json(Path(args.output_dir) / "signalforge_portfolio_exit_path_enrichment_qc_manifest.json", manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0 if manifest["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
