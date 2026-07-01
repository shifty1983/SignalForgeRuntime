"""QC manifest for portfolio construction rule sensitivity."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ADAPTER_TYPE = "portfolio_construction_rule_sensitivity_qc_manifest_builder"
ARTIFACT_TYPE = "signalforge_portfolio_construction_rule_sensitivity_qc_manifest"
CONTRACT = "portfolio_construction_rule_sensitivity_qc_manifest"


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")


def _best_by_capital(rows: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("starting_capital"))].append(row)
    output: dict[str, Any] = {}
    for capital, items in grouped.items():
        passing = [row for row in items if row.get("passes_portfolio_construction_gate")]
        candidates = passing or items
        if not candidates:
            continue
        best = max(candidates, key=lambda row: float(row.get("robustness_score") or -1.0))
        output[capital] = {
            "scenario_name": best.get("scenario_name"),
            "risk_per_trade_pct": best.get("risk_per_trade_pct"),
            "max_trade_risk_dollars": best.get("max_trade_risk_dollars"),
            "passes_portfolio_construction_gate": best.get("passes_portfolio_construction_gate"),
            "robustness_score": best.get("robustness_score"),
            "total_return": best.get("total_return"),
            "max_drawdown_pct": best.get("max_drawdown_pct"),
            "profit_factor": best.get("profit_factor"),
            "trade_retention_rate": best.get("trade_retention_rate"),
        }
    return output


def build(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_path = Path(args.sensitivity_summary)
    scenarios_path = Path(args.sensitivity_scenarios)
    summary = _read_json(summary_path)
    scenarios = _read_jsonl(scenarios_path)

    blockers: list[str] = []
    warnings: list[str] = []

    actual_count = len(scenarios)
    expected_count = args.expected_scenario_count
    if expected_count is not None and actual_count != expected_count:
        blockers.append("scenario_count_mismatch")
    if not summary.get("is_ready"):
        blockers.append("input_summary_not_ready")
    if summary.get("contract") != "portfolio_construction_rule_sensitivity":
        blockers.append("unexpected_input_contract")
    if actual_count == 0:
        blockers.append("no_scenario_rows")

    passing = [row for row in scenarios if row.get("passes_portfolio_construction_gate")]
    if len(passing) < args.minimum_passing_scenario_count:
        blockers.append("passing_scenario_count_below_minimum")

    failed_missing_reasons = [
        row.get("scenario_name")
        for row in scenarios
        if not row.get("passes_portfolio_construction_gate") and not row.get("failure_reasons")
    ]
    if failed_missing_reasons:
        blockers.append("failed_scenarios_missing_failure_reasons")

    capital_values = sorted({float(row.get("starting_capital")) for row in scenarios if row.get("starting_capital") is not None})
    capitals_with_passing = sorted({float(row.get("starting_capital")) for row in passing if row.get("starting_capital") is not None})
    missing_passing_capitals = [capital for capital in capital_values if capital not in capitals_with_passing]
    if missing_passing_capitals:
        warnings.append("some_starting_capitals_have_no_passing_rule_variant")

    gate_failure_counts = Counter(reason for row in scenarios for reason in row.get("failure_reasons", []))
    best_by_capital = _best_by_capital(scenarios)
    best_overall = max(passing or scenarios, key=lambda row: float(row.get("robustness_score") or -1.0)) if scenarios else None

    manifest_path = output_dir / "signalforge_portfolio_construction_rule_sensitivity_qc_manifest.json"
    manifest: dict[str, Any] = {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": ARTIFACT_TYPE,
        "contract": CONTRACT,
        "is_ready": not blockers,
        "readiness_state": "pass" if not blockers else "blocked",
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,
        "sensitivity_summary_path": str(summary_path),
        "sensitivity_scenarios_path": str(scenarios_path),
        "input_summary_readiness_state": summary.get("readiness_state"),
        "scenario_validation": {
            "actual_scenario_count": actual_count,
            "expected_scenario_count": expected_count,
            "passing_scenario_count": len(passing),
            "minimum_passing_scenario_count": args.minimum_passing_scenario_count,
            "capital_count": len(capital_values),
            "capitals_with_passing_count": len(capitals_with_passing),
            "missing_passing_capitals": missing_passing_capitals,
        },
        "diagnostics": {
            "gate_failure_counts": dict(sorted(gate_failure_counts.items())),
            "failed_scenarios_missing_failure_reasons": failed_missing_reasons,
            "best_overall_scenario": best_overall,
            "best_by_capital": best_by_capital,
        },
        "explicit_exclusions": [
            "strategy_reselection",
            "expectancy_rebuild",
            "entry_rule_optimization",
            "exit_rule_optimization",
            "defensive_adjustment_simulation",
            "broker_margin_model",
            "live_execution",
        ],
        "paths": {"manifest_path": str(manifest_path)},
    }
    _write_json(manifest_path, manifest)
    return manifest


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build QC manifest for portfolio construction rule sensitivity.")
    parser.add_argument("--sensitivity-summary", required=True)
    parser.add_argument("--sensitivity-scenarios", required=True)
    parser.add_argument("--expected-scenario-count", type=int, default=None)
    parser.add_argument("--minimum-passing-scenario-count", type=int, default=1)
    parser.add_argument("--output-dir", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    manifest = build(args)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0 if manifest.get("is_ready") else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

