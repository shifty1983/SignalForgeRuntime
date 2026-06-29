"""QC manifest for portfolio entry-filter sensitivity."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


ADAPTER_TYPE = "portfolio_entry_filter_sensitivity_qc_manifest_builder"
ARTIFACT_TYPE = "signalforge_portfolio_entry_filter_sensitivity_qc_manifest"
CONTRACT = "portfolio_entry_filter_sensitivity_qc_manifest"


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build QC manifest for portfolio entry-filter sensitivity.")
    parser.add_argument("--sensitivity-summary", required=True, type=Path)
    parser.add_argument("--sensitivity-scenarios", required=True, type=Path)
    parser.add_argument("--expected-scenario-count", required=True, type=int)
    parser.add_argument("--minimum-passing-scenario-count", type=int, default=1)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)

    summary = _read_json(args.sensitivity_summary)
    scenarios = _read_jsonl(args.sensitivity_scenarios)

    blockers: list[str] = []
    warnings: list[str] = []
    if not summary.get("is_ready"):
        blockers.append("input_summary_not_ready")
    if summary.get("readiness_state") != "pass":
        blockers.append("input_summary_readiness_not_pass")
    if len(scenarios) != args.expected_scenario_count:
        blockers.append("scenario_count_mismatch")

    passing = [row for row in scenarios if row.get("passes_entry_filter_gate")]
    if len(passing) < args.minimum_passing_scenario_count:
        blockers.append("passing_scenario_count_below_minimum")

    capitals = sorted({float(row.get("starting_capital")) for row in scenarios if row.get("starting_capital") is not None})
    passing_capitals = sorted({float(row.get("starting_capital")) for row in passing if row.get("starting_capital") is not None})
    missing_passing_capitals = [capital for capital in capitals if capital not in passing_capitals]
    if missing_passing_capitals:
        warnings.append("some_starting_capitals_have_no_passing_entry_filter_variant")

    failed_missing_reasons = [
        row.get("scenario_name")
        for row in scenarios
        if not row.get("passes_entry_filter_gate") and not row.get("failure_reasons")
    ]
    if failed_missing_reasons:
        blockers.append("failed_scenarios_missing_failure_reasons")

    failure_counts: Counter[str] = Counter()
    skip_counts: Counter[str] = Counter()
    for row in scenarios:
        for reason in row.get("failure_reasons", []):
            failure_counts[str(reason)] += 1
        for reason, count in row.get("skipped_entry_filter_reasons", {}).items():
            skip_counts[str(reason)] += int(count)

    manifest = {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": ARTIFACT_TYPE,
        "contract": CONTRACT,
        "is_ready": not blockers,
        "readiness_state": "pass" if not blockers else "blocked",
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,
        "input_summary_readiness_state": summary.get("readiness_state"),
        "sensitivity_summary_path": str(args.sensitivity_summary),
        "sensitivity_scenarios_path": str(args.sensitivity_scenarios),
        "scenario_validation": {
            "actual_scenario_count": len(scenarios),
            "expected_scenario_count": args.expected_scenario_count,
            "minimum_passing_scenario_count": args.minimum_passing_scenario_count,
            "passing_scenario_count": len(passing),
            "capital_count": len(capitals),
            "capitals_with_passing_count": len(passing_capitals),
            "missing_passing_capitals": missing_passing_capitals,
        },
        "diagnostics": {
            "best_overall_scenario": summary.get("best_overall_scenario"),
            "best_by_capital": summary.get("best_by_capital"),
            "gate_failure_counts": dict(sorted(failure_counts.items())),
            "aggregate_entry_filter_skip_reason_counts": dict(sorted(skip_counts.items())),
            "failed_scenarios_missing_failure_reasons": failed_missing_reasons,
        },
        "explicit_exclusions": [
            "strategy_reselection",
            "expectancy_rebuild",
            "exit_rule_optimization",
            "defensive_adjustment_simulation",
            "broker_margin_model",
            "live_execution",
            "realized_outcome_based_filter_selection",
        ],
        "paths": {
            "manifest_path": str(args.output_dir / "signalforge_portfolio_entry_filter_sensitivity_qc_manifest.json"),
        },
    }

    _write_json(args.output_dir / "signalforge_portfolio_entry_filter_sensitivity_qc_manifest.json", manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0 if manifest["is_ready"] else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
