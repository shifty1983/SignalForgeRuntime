from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REQUIRED_SCENARIOS = {
    "baseline",
    "risk_scale_0.5",
    "risk_scale_0.75",
    "risk_scale_1.25",
    "win_haircut_0.1",
    "win_haircut_0.2",
    "win_haircut_0.25",
    "loss_inflation_0.1",
    "loss_inflation_0.2",
    "loss_inflation_0.25",
    "combined_adverse_0.1",
    "combined_adverse_0.2",
    "cap_winners_p95",
    "cap_winners_p90",
    "remove_top_winners_1",
    "remove_top_winners_5",
    "remove_top_winners_1pct",
    "remove_top_winners_5pct",
    "exclude_best_year",
    "exclude_worst_year",
    "remove_top_symbol",
    "remove_top5_symbols",
    "remove_top_strategy",
    "remove_top3_strategies",
    "execution_worse_fills_0.25",
    "execution_worse_fills_0.5",
    "execution_worse_fills_1.0",
    "execution_no_mid_bid_ask_conservative",
    "execution_skip_wide_spreads",
    "execution_ibkr_like_commissions_and_fees",
    "execution_live_realism_spread10_no_mid_fees",
    "execution_live_realism_spread05_no_mid_fees",
}

MILD_STRESS_SCENARIOS = {
    "win_haircut_0.1",
    "loss_inflation_0.1",
    "combined_adverse_0.1",
    "cap_winners_p95",
    "remove_top_winners_1",
    "execution_worse_fills_0.25",
    "execution_ibkr_like_commissions_and_fees",
    "execution_live_realism_spread10_no_mid_fees",
}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing JSON file: {path}")

    with path.open("r", encoding="utf-8-sig") as f:
        payload = json.load(f)

    if not isinstance(payload, dict):
        raise ValueError(f"Expected object JSON: {path}")

    return payload


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Missing JSONL file: {path}")

    rows: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8-sig") as f:
        for line_number, line in enumerate(f, start=1):
            stripped = line.strip()
            if not stripped:
                continue

            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at line {line_number}: {path}") from exc

            if not isinstance(payload, dict):
                raise ValueError(f"JSONL line {line_number} is not an object: {path}")

            rows.append(payload)

    return rows


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)


def scenario_by_name(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}

    for row in rows:
        name = row.get("scenario_name")
        if isinstance(name, str):
            output[name] = row

    return output


def as_float(value: Any) -> float | None:
    if value is None:
        return None

    if isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        return float(value)

    return None


def build_qc_manifest(
    robustness_summary_path: Path,
    robustness_scenarios_path: Path,
    output_dir: Path,
    expected_trade_count: int | None,
    expected_scenario_count: int,
    max_top_symbol_positive_contribution_pct: float,
    max_top_strategy_positive_contribution_pct: float,
    max_top_year_total_pnl_pct: float,
) -> dict[str, Any]:
    summary = read_json(robustness_summary_path)
    scenarios = read_jsonl(robustness_scenarios_path)
    scenarios_by_name = scenario_by_name(scenarios)

    blockers: list[str] = []
    warnings: list[str] = []

    artifact_type = summary.get("artifact_type")
    contract = summary.get("contract")

    if artifact_type != "signalforge_portfolio_robustness_stress_validation":
        blockers.append("unexpected_robustness_artifact_type")

    if contract != "portfolio_robustness_stress_validation":
        blockers.append("unexpected_robustness_contract")

    if summary.get("blocker_count", 0) != 0:
        blockers.append("upstream_robustness_summary_has_blockers")

    if summary.get("readiness_state") == "blocked":
        blockers.append("upstream_robustness_summary_blocked")

    if summary.get("is_ready") is not True:
        blockers.append("upstream_robustness_summary_not_ready")

    input_diagnostics = summary.get("input_diagnostics", {})
    if not isinstance(input_diagnostics, dict):
        blockers.append("missing_input_diagnostics")
        input_diagnostics = {}

    normalized_trade_count = input_diagnostics.get("normalized_trade_count")
    skipped_missing_pnl_count = input_diagnostics.get("skipped_missing_pnl_count")

    if expected_trade_count is not None and normalized_trade_count != expected_trade_count:
        blockers.append(
            f"normalized_trade_count_mismatch:expected_{expected_trade_count}:actual_{normalized_trade_count}"
        )

    if normalized_trade_count is None or normalized_trade_count <= 0:
        blockers.append("no_normalized_trades")

    if skipped_missing_pnl_count not in (0, None):
        blockers.append("sized_rows_missing_pnl")

    if len(scenarios) != expected_scenario_count:
        blockers.append(
            f"scenario_count_mismatch:expected_{expected_scenario_count}:actual_{len(scenarios)}"
        )

    missing_scenarios = sorted(REQUIRED_SCENARIOS - set(scenarios_by_name))
    extra_scenarios = sorted(set(scenarios_by_name) - REQUIRED_SCENARIOS)

    if missing_scenarios:
        blockers.append("missing_required_scenarios:" + ",".join(missing_scenarios))

    if extra_scenarios:
        warnings.append("extra_scenarios:" + ",".join(extra_scenarios))

    baseline_metrics = summary.get("baseline_metrics", {})
    if not isinstance(baseline_metrics, dict):
        blockers.append("missing_baseline_metrics")
        baseline_metrics = {}

    baseline_total_return = as_float(baseline_metrics.get("total_return"))
    baseline_total_pnl = as_float(baseline_metrics.get("total_pnl"))
    baseline_trade_count = baseline_metrics.get("trade_count")

    if baseline_total_return is None or baseline_total_return <= 0:
        blockers.append("baseline_total_return_not_positive")

    if baseline_total_pnl is None or baseline_total_pnl <= 0:
        blockers.append("baseline_total_pnl_not_positive")

    if expected_trade_count is not None and baseline_trade_count != expected_trade_count:
        blockers.append(
            f"baseline_trade_count_mismatch:expected_{expected_trade_count}:actual_{baseline_trade_count}"
        )

    for scenario_name in MILD_STRESS_SCENARIOS:
        scenario = scenarios_by_name.get(scenario_name)

        if scenario is None:
            continue

        total_return = as_float(scenario.get("total_return"))
        total_pnl = as_float(scenario.get("total_pnl"))

        if total_return is None or total_pnl is None:
            warnings.append(f"mild_stress_missing_return_or_pnl:{scenario_name}")
            continue

        if total_return <= 0 or total_pnl <= 0:
            warnings.append(f"mild_stress_non_positive:{scenario_name}")

    for scenario in scenarios:
        name = scenario.get("scenario_name", "unknown")
        trade_count = scenario.get("trade_count")
        total_return = as_float(scenario.get("total_return"))
        max_drawdown_pct = as_float(scenario.get("max_drawdown_pct"))

        if trade_count is None or trade_count <= 0:
            blockers.append(f"scenario_has_no_trades:{name}")

        if total_return is None:
            warnings.append(f"scenario_missing_total_return:{name}")

        if max_drawdown_pct is None:
            warnings.append(f"scenario_missing_max_drawdown_pct:{name}")

    concentration = summary.get("baseline_concentration", {})
    if not isinstance(concentration, dict):
        warnings.append("missing_baseline_concentration")
        concentration = {}

    top_symbols = concentration.get("top_symbols", [])
    if isinstance(top_symbols, list) and top_symbols:
        top_symbol = top_symbols[0]
        top_symbol_pct = as_float(top_symbol.get("positive_contribution_pct"))

        if (
            top_symbol_pct is not None
            and top_symbol_pct > max_top_symbol_positive_contribution_pct
        ):
            warnings.append("top_symbol_positive_contribution_exceeds_threshold")
    else:
        warnings.append("missing_top_symbol_concentration")

    top_strategies = concentration.get("top_strategies", [])
    if isinstance(top_strategies, list) and top_strategies:
        top_strategy = top_strategies[0]
        top_strategy_pct = as_float(top_strategy.get("positive_contribution_pct"))

        if (
            top_strategy_pct is not None
            and top_strategy_pct > max_top_strategy_positive_contribution_pct
        ):
            warnings.append("top_strategy_positive_contribution_exceeds_threshold")
    else:
        warnings.append("missing_top_strategy_concentration")

    years = concentration.get("years", [])
    if isinstance(years, list) and years:
        top_year = years[0]
        top_year_total_pnl_pct = as_float(top_year.get("total_pnl_pct"))

        if (
            top_year_total_pnl_pct is not None
            and top_year_total_pnl_pct > max_top_year_total_pnl_pct
        ):
            warnings.append("top_year_total_pnl_contribution_exceeds_threshold")
    else:
        warnings.append("missing_year_concentration")

    readiness_state = "blocked" if blockers else "needs_review" if warnings else "pass"

    output_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = output_dir / "signalforge_portfolio_robustness_qc_manifest.json"

    manifest = {
        "adapter_type": "portfolio_robustness_qc_manifest_builder",
        "artifact_type": "signalforge_portfolio_robustness_qc_manifest",
        "contract": "portfolio_robustness_qc_manifest",
        "is_ready": readiness_state != "blocked",
        "readiness_state": readiness_state,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,
        "robustness_summary_path": str(robustness_summary_path),
        "robustness_scenarios_path": str(robustness_scenarios_path),
        "input_summary_readiness_state": summary.get("readiness_state"),
        "input_summary_is_ready": summary.get("is_ready"),
        "input_diagnostics": input_diagnostics,
        "baseline_metrics": baseline_metrics,
        "scenario_validation": {
            "expected_scenario_count": expected_scenario_count,
            "actual_scenario_count": len(scenarios),
            "required_scenarios": sorted(REQUIRED_SCENARIOS),
            "missing_scenarios": missing_scenarios,
            "extra_scenarios": extra_scenarios,
            "mild_stress_scenarios": sorted(MILD_STRESS_SCENARIOS),
        },
        "concentration_thresholds": {
            "max_top_symbol_positive_contribution_pct": max_top_symbol_positive_contribution_pct,
            "max_top_strategy_positive_contribution_pct": max_top_strategy_positive_contribution_pct,
            "max_top_year_total_pnl_pct": max_top_year_total_pnl_pct,
        },
        "baseline_concentration_snapshot": {
            "top_symbol": top_symbols[0] if isinstance(top_symbols, list) and top_symbols else None,
            "top_strategy": top_strategies[0] if isinstance(top_strategies, list) and top_strategies else None,
            "top_year": years[0] if isinstance(years, list) and years else None,
        },
        "paths": {
            "manifest_path": str(manifest_path),
        },
        "explicit_exclusions": [
            "broker_api_calls",
            "order_routing",
            "order_submission",
            "fills",
            "live_execution",
            "trade_reselection",
            "expectancy_rebuild",
            "strategy_optimization",
            "parameter_tuning",
            "new_portfolio_construction",
        ],
    }

    write_json(manifest_path, manifest)

    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build Phase 7 portfolio robustness QC manifest."
    )

    parser.add_argument(
        "--robustness-summary",
        required=True,
        help="Phase 7 robustness stress validation summary JSON.",
    )
    parser.add_argument(
        "--robustness-scenarios",
        required=True,
        help="Phase 7 robustness scenario JSONL.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Output directory for Phase 7 QC manifest.",
    )
    parser.add_argument(
        "--expected-trade-count",
        type=int,
        default=None,
        help="Expected normalized sized trade count.",
    )
    parser.add_argument(
        "--expected-scenario-count",
        type=int,
        default=len(REQUIRED_SCENARIOS),
        help="Expected scenario count. Default: len(REQUIRED_SCENARIOS).",
    )
    parser.add_argument(
        "--max-top-symbol-positive-contribution-pct",
        type=float,
        default=0.10,
    )
    parser.add_argument(
        "--max-top-strategy-positive-contribution-pct",
        type=float,
        default=0.50,
    )
    parser.add_argument(
        "--max-top-year-total-pnl-pct",
        type=float,
        default=0.50,
    )
    parser.add_argument(
        "--fail-on-blocker",
        action="store_true",
    )

    args = parser.parse_args()

    manifest = build_qc_manifest(
        robustness_summary_path=Path(args.robustness_summary),
        robustness_scenarios_path=Path(args.robustness_scenarios),
        output_dir=Path(args.output_dir),
        expected_trade_count=args.expected_trade_count,
        expected_scenario_count=args.expected_scenario_count,
        max_top_symbol_positive_contribution_pct=args.max_top_symbol_positive_contribution_pct,
        max_top_strategy_positive_contribution_pct=args.max_top_strategy_positive_contribution_pct,
        max_top_year_total_pnl_pct=args.max_top_year_total_pnl_pct,
    )

    print(json.dumps(manifest, indent=2, sort_keys=True))

    if args.fail_on_blocker and manifest.get("blocker_count", 0) > 0:
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
