from __future__ import annotations

import argparse
import json
from datetime import datetime, date
from pathlib import Path
from typing import Any

from signalforge.backtesting.portfolio_loss_pocket_rule_sweep_cli import (
    read_jsonl,
    metrics,
    scenario_rules,
    pick,
)


def parse_date(value: Any) -> date:
    text = str(value or "")[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except Exception:
        return date(1900, 1, 1)


def decision_date(row: dict[str, Any]) -> date:
    return parse_date(
        pick(
            row,
            [
                "decision_date",
                "entry_date",
                "trade_date",
                "date",
                "portfolio_realization_date",
                "realization_date",
                "exit_date",
                "close_date",
                "outcome_date",
            ],
            "1900-01-01",
        )
    )


def write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, default=str), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True, default=str) + "\n")


def evaluate_period(
    period_name: str,
    rows: list[dict[str, Any]],
    starting_capital: float,
) -> list[dict[str, Any]]:
    baseline = metrics(rows, starting_capital, None)
    out = []

    for rule in scenario_rules():
        candidate = metrics(rows, starting_capital, rule)

        delta_pnl = candidate["total_pnl_dollars"] - baseline["total_pnl_dollars"]
        delta_pf = (candidate["profit_factor"] or 0.0) - (baseline["profit_factor"] or 0.0)
        delta_dd = candidate["max_drawdown_pct"] - baseline["max_drawdown_pct"]

        out.append(
            {
                "period": period_name,
                "label": rule["label"],
                "kind": rule["kind"],
                "action": rule["action"],
                "multiplier": rule["multiplier"],
                "affected_original_pnl": candidate["affected_original_pnl"],
                "skipped_count": candidate["skipped_count"],
                "throttled_count": candidate["throttled_count"],
                "baseline_trade_count": baseline["trade_count"],
                "candidate_trade_count": candidate["trade_count"],
                "baseline_total_return_pct": baseline["total_return_pct"],
                "candidate_total_return_pct": candidate["total_return_pct"],
                "delta_pnl_dollars": delta_pnl,
                "baseline_profit_factor": baseline["profit_factor"],
                "candidate_profit_factor": candidate["profit_factor"],
                "delta_profit_factor": delta_pf,
                "baseline_max_drawdown_pct": baseline["max_drawdown_pct"],
                "candidate_max_drawdown_pct": candidate["max_drawdown_pct"],
                "delta_max_drawdown_pct": delta_dd,
                "return_non_degradation": delta_pnl >= 0,
                "profit_factor_non_degradation": delta_pf >= 0,
                "drawdown_non_degradation": delta_dd >= 0,
                "passes_period": (
                    delta_pnl >= 0
                    and delta_pf >= 0
                    and delta_dd >= 0
                    and (candidate["skipped_count"] > 0 or candidate["throttled_count"] > 0)
                ),
                "rule": rule,
            }
        )

    return out


def run(args: argparse.Namespace) -> dict[str, Any]:
    rows = read_jsonl(Path(args.input_ledger))
    split = parse_date(args.validation_start)

    train_rows = [r for r in rows if decision_date(r) < split]
    validation_rows = [r for r in rows if decision_date(r) >= split]

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    scenario_rows = []
    scenario_rows.extend(evaluate_period("train", train_rows, args.starting_capital))
    scenario_rows.extend(evaluate_period("validation", validation_rows, args.starting_capital))

    labels = sorted({r["label"] for r in scenario_rows})
    label_rows = []

    for label in labels:
        train = next((r for r in scenario_rows if r["label"] == label and r["period"] == "train"), None)
        validation = next((r for r in scenario_rows if r["label"] == label and r["period"] == "validation"), None)

        if not train or not validation:
            continue

        label_rows.append(
            {
                "label": label,
                "action": validation["action"],
                "multiplier": validation["multiplier"],
                "train_pass": train["passes_period"],
                "validation_pass": validation["passes_period"],
                "both_pass": train["passes_period"] and validation["passes_period"],
                "train_delta_pnl": train["delta_pnl_dollars"],
                "validation_delta_pnl": validation["delta_pnl_dollars"],
                "train_delta_pf": train["delta_profit_factor"],
                "validation_delta_pf": validation["delta_profit_factor"],
                "train_delta_dd": train["delta_max_drawdown_pct"],
                "validation_delta_dd": validation["delta_max_drawdown_pct"],
                "train_affected_pnl": train["affected_original_pnl"],
                "validation_affected_pnl": validation["affected_original_pnl"],
                "train_skipped": train["skipped_count"],
                "validation_skipped": validation["skipped_count"],
                "train_throttled": train["throttled_count"],
                "validation_throttled": validation["throttled_count"],
                "validation_candidate_return": validation["candidate_total_return_pct"],
                "validation_candidate_pf": validation["candidate_profit_factor"],
            }
        )

    label_rows.sort(
        key=lambda r: (
            r["both_pass"],
            r["validation_delta_pnl"],
            r["validation_delta_pf"],
        ),
        reverse=True,
    )

    summary = {
        "adapter_type": "portfolio_loss_pocket_split_validation_builder",
        "artifact_type": "signalforge_portfolio_loss_pocket_split_validation",
        "contract": "portfolio_loss_pocket_split_validation",
        "is_ready": True,
        "readiness_state": "diagnostic_train_validation_split",
        "input_ledger": args.input_ledger,
        "validation_start": args.validation_start,
        "train_row_count": len(train_rows),
        "validation_row_count": len(validation_rows),
        "scenario_count": len(scenario_rows),
        "candidate_count": len(label_rows),
        "both_pass_count": len([r for r in label_rows if r["both_pass"]]),
        "policy": {
            "diagnostic_only": True,
            "chronological_split": True,
            "not_live_safe_until_converted_to_walk_forward_or_prior_rule": True,
        },
        "paths": {
            "summary": str(output_dir / "signalforge_portfolio_loss_pocket_split_validation_summary.json"),
            "scenario_rows": str(output_dir / "signalforge_portfolio_loss_pocket_split_validation_rows.jsonl"),
            "candidate_rows": str(output_dir / "signalforge_portfolio_loss_pocket_split_validation_candidates.jsonl"),
        },
        "top_candidates": label_rows[:10],
    }

    write_json(output_dir / "signalforge_portfolio_loss_pocket_split_validation_summary.json", summary)
    write_jsonl(output_dir / "signalforge_portfolio_loss_pocket_split_validation_rows.jsonl", scenario_rows)
    write_jsonl(output_dir / "signalforge_portfolio_loss_pocket_split_validation_candidates.jsonl", label_rows)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-ledger", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--starting-capital", type=float, required=True)
    parser.add_argument("--validation-start", required=True)
    args = parser.parse_args()

    summary = run(args)

    print(json.dumps({
        "is_ready": summary["is_ready"],
        "readiness_state": summary["readiness_state"],
        "validation_start": summary["validation_start"],
        "train_row_count": summary["train_row_count"],
        "validation_row_count": summary["validation_row_count"],
        "candidate_count": summary["candidate_count"],
        "both_pass_count": summary["both_pass_count"],
        "paths": summary["paths"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
