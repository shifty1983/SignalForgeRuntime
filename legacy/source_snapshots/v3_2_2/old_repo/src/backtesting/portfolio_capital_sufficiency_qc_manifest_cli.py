
"""QC manifest for SignalForge capital sufficiency scenarios."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
import argparse
import json


def _read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")


def build_qc_manifest(
    capital_summary: Path,
    capital_scenarios: Path,
    output_dir: Path,
    expected_scenario_count: int,
    minimum_required_capital: Optional[float],
    maximum_recommended_capital: Optional[float],
) -> Dict[str, Any]:
    summary = _read_json(capital_summary)
    scenarios = _read_jsonl(capital_scenarios)
    output_dir.mkdir(parents=True, exist_ok=True)

    blockers: List[str] = []
    warnings: List[str] = []
    if not summary.get("is_ready"):
        blockers.append("input_summary_not_ready")
    if summary.get("readiness_state") not in {"pass", "needs_review"}:
        blockers.append("invalid_input_readiness_state")
    if len(scenarios) != expected_scenario_count:
        blockers.append("scenario_count_mismatch")
    answers = summary.get("capital_answers", {})
    min_viable = answers.get("minimum_viable_deployment_capital")
    recommended = answers.get("recommended_starting_capital")
    absolute_min = answers.get("absolute_minimum_profitable_capital")
    if min_viable is None:
        blockers.append("minimum_viable_capital_missing")
    if recommended is None:
        blockers.append("recommended_starting_capital_missing")
    if minimum_required_capital is not None and min_viable is not None and min_viable > minimum_required_capital:
        warnings.append("minimum_viable_capital_above_requested_requirement")
    if maximum_recommended_capital is not None and recommended is not None and recommended > maximum_recommended_capital:
        warnings.append("recommended_capital_above_preferred_maximum")

    passing = [r for r in scenarios if r.get("passes_minimum_viable_gate")]
    failed = [r for r in scenarios if not r.get("passes_minimum_viable_gate")]
    if not passing:
        blockers.append("no_scenario_passed_minimum_viable_gate")

    failed_missing_gate_reasons = [
        r.get("capital_scenario")
        for r in failed
        if not r.get("failure_reasons") or not r.get("gate_failures")
    ]
    if failed_missing_gate_reasons:
        warnings.append("failed_scenarios_missing_explicit_gate_failure_reasons")

    gate_failure_counts: Dict[str, int] = {}
    gate_warning_counts: Dict[str, int] = {}
    for row in scenarios:
        for reason in row.get("failure_reasons") or row.get("capital_gate_blockers") or []:
            gate_failure_counts[reason] = gate_failure_counts.get(reason, 0) + 1
        for reason in row.get("warning_reasons") or row.get("capital_gate_warnings") or []:
            gate_warning_counts[reason] = gate_warning_counts.get(reason, 0) + 1

    retention_by_capital = {str(r.get("capital_scenario")): r.get("trade_retention_rate") for r in scenarios}
    min_pf_by_passing = min((r.get("profit_factor", 0.0) for r in passing if r.get("profit_factor") is not None), default=None)
    worst_dd_by_passing = min((r.get("max_drawdown_pct", 0.0) for r in passing), default=None)

    manifest = {
        "adapter_type": "portfolio_capital_sufficiency_qc_manifest_builder",
        "artifact_type": "signalforge_portfolio_capital_sufficiency_qc_manifest",
        "contract": "portfolio_capital_sufficiency_qc_manifest",
        "is_ready": len(blockers) == 0,
        "readiness_state": "pass" if len(blockers) == 0 else "blocked",
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,
        "scenario_validation": {
            "actual_scenario_count": len(scenarios),
            "expected_scenario_count": expected_scenario_count,
            "passing_scenario_count": len(passing),
        },
        "capital_answers": answers,
        "diagnostics": {
            "absolute_minimum_profitable_capital": absolute_min,
            "minimum_viable_deployment_capital": min_viable,
            "recommended_starting_capital": recommended,
            "minimum_profit_factor_among_passing": min_pf_by_passing,
            "worst_drawdown_among_passing": worst_dd_by_passing,
            "trade_retention_rate_by_capital": retention_by_capital,
            "gate_failure_counts": gate_failure_counts,
            "gate_warning_counts": gate_warning_counts,
            "failed_scenarios_missing_gate_reasons": failed_missing_gate_reasons,
        },
        "input_summary_readiness_state": summary.get("readiness_state"),
        "capital_summary_path": str(capital_summary),
        "capital_scenarios_path": str(capital_scenarios),
        "paths": {
            "manifest_path": str(output_dir / "signalforge_portfolio_capital_sufficiency_qc_manifest.json")
        },
        "explicit_exclusions": [
            "rule_optimization",
            "strategy_reselection",
            "expectancy_rebuild",
            "live_execution",
            "broker_margin_model",
        ],
    }
    _write_json(output_dir / "signalforge_portfolio_capital_sufficiency_qc_manifest.json", manifest)
    return manifest


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build SignalForge capital sufficiency QC manifest.")
    parser.add_argument("--capital-summary", required=True, type=Path)
    parser.add_argument("--capital-scenarios", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--expected-scenario-count", type=int, default=15)
    parser.add_argument("--minimum-required-capital", type=float, default=None)
    parser.add_argument("--maximum-recommended-capital", type=float, default=None)
    args = parser.parse_args(argv)
    manifest = build_qc_manifest(
        capital_summary=args.capital_summary,
        capital_scenarios=args.capital_scenarios,
        output_dir=args.output_dir,
        expected_scenario_count=args.expected_scenario_count,
        minimum_required_capital=args.minimum_required_capital,
        maximum_recommended_capital=args.maximum_recommended_capital,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
