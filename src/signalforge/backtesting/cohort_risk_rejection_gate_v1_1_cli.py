from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path
from typing import Any


RULE = {
    "rule_id": "cohort_risk_rejection_gate_v1_1",
    "parent_rule_id": "cohort_risk_rejection_gate_v1",
    "scope_name": "strategy_bucket_regime_asset_option",
    "scope": "strategy + bucket + regime_state + asset_behavior_state + option_behavior_state",
    "prior_mode": "realization_date_available_prior_live_safe",
    "min_prior": 6,
    "prior_avg_pnl_threshold": -500.0,
    "prior_final_negative_rate_threshold": 0.50,
    "action": "skip entire same-day weak-prior cohort",
    "classification": "faster_acting_return_enhancement_gate_not_drawdown_control",
}


PNL_FIELDS = [
    "realized_pnl_dollars",
    "allocated_pnl",
    "strategy_pnl",
    "portfolio_pnl",
    "pnl",
    "trade_pnl",
    "net_pnl",
]

RETURN_FIELDS = [
    "realized_return",
    "strategy_adjusted_return",
    "strategy_return",
]

RISK_FIELDS = [
    "position_risk_dollars",
    "risk_capital",
    "allocated_risk_dollars",
    "max_loss_dollars",
]

QUANTITY_FIELDS = [
    "quantity",
    "adjusted_quantity",
    "contract_count",
    "allocated_contract_count",
    "contracts",
    "position_size",
]


@dataclass(frozen=True)
class CohortKey:
    decision_date: str
    selected_strategy: str
    bucket: str
    regime_state: str
    asset_behavior_state: str
    option_behavior_state: str


@dataclass
class CohortSummary:
    key: CohortKey
    scope_key: tuple[str, str, str, str, str]
    decision_date_obj: date
    available_date_obj: date
    total_pnl: float
    trade_count: int
    final_negative: bool


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", errors="ignore") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, default=str) + "\n")


def pick(row: dict[str, Any], names: list[str], default: Any = None) -> Any:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return value
    return default


def fnum(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def parse_date(value: Any) -> date:
    if value in (None, ""):
        return date(1900, 1, 1)

    text = str(value)[:10]

    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except Exception:
        return date(1900, 1, 1)


def cat(value: Any, default: str = "unknown") -> str:
    if value in (None, ""):
        return default
    return str(value)


def is_active(row: dict[str, Any]) -> bool:
    state_text = " ".join(
        str(row.get(k) or "").lower()
        for k in [
            "row_state",
            "sizing_state",
            "allocation_state",
            "selection_state",
            "portfolio_state",
            "trade_state",
        ]
    )

    if "skip" in state_text or "reject" in state_text or "blocked" in state_text:
        return False

    quantity_values = [fnum(row.get(k), None) for k in QUANTITY_FIELDS if k in row]
    quantity_values = [x for x in quantity_values if x is not None]

    if quantity_values and max(quantity_values) <= 0:
        return False

    return True


def pnl_value(row: dict[str, Any]) -> float:
    for field in PNL_FIELDS:
        if row.get(field) not in (None, ""):
            return fnum(row.get(field))

    risk = fnum(pick(row, RISK_FIELDS, 0.0))
    ret = fnum(pick(row, RETURN_FIELDS, 0.0))
    return risk * ret


def infer_bucket(row: dict[str, Any]) -> str:
    explicit = pick(
        row,
        [
            "bucket",
            "final_bucket",
            "allocation_bucket",
            "rank_bucket",
            "strategy_rank_bucket",
            "selected_bucket",
            "selected_allocation_bucket",
            "allocation_bucket_label",
        ],
    )

    if explicit not in (None, ""):
        return str(explicit)

    # Fixed-risk ledgers often have no allocator bucket. Keep them valid,
    # but do not pretend they are allocator bucketed.
    return "fixed_risk"


def decision_date(row: dict[str, Any]) -> str:
    return str(
        pick(
            row,
            [
                "decision_date",
                "entry_date",
                "trade_date",
                "date",
                "as_of_date",
            ],
            "",
        )
    )[:10]


def available_date(row: dict[str, Any]) -> str:
    return str(
        pick(
            row,
            [
                "outcome_availability_date",
                "portfolio_realization_date",
                "realization_date",
                "exit_date",
                "close_date",
                "outcome_date",
                "target_exit_date",
                "decision_date",
            ],
            "",
        )
    )[:10]


def selected_strategy(row: dict[str, Any]) -> str:
    return cat(pick(row, ["selected_strategy", "strategy", "strategy_family"]), "unknown_strategy")


def get_regime_state(row: dict[str, Any]) -> str:
    return cat(pick(row, ["regime_state", "regime"]), "unknown_regime")


def get_asset_behavior_state(row: dict[str, Any]) -> str:
    direct = pick(row, ["asset_behavior_state", "selected_asset_behavior_state"])
    if direct not in (None, ""):
        return cat(direct)

    research_context = row.get("research_context") or {}
    if isinstance(research_context, dict):
        asset_behavior = research_context.get("asset_behavior") or {}
        if isinstance(asset_behavior, dict):
            state = asset_behavior.get("state")
            if state not in (None, ""):
                return cat(state)

    return "unknown_asset_behavior"


def get_option_behavior_state(row: dict[str, Any]) -> str:
    direct = pick(row, ["option_behavior_state", "selected_option_behavior_state"])
    if direct not in (None, ""):
        return cat(direct)

    research_context = row.get("research_context") or {}
    if isinstance(research_context, dict):
        option_behavior = research_context.get("option_behavior") or {}
        if isinstance(option_behavior, dict):
            state = option_behavior.get("state")
            if state not in (None, ""):
                return cat(state)

    return "unknown_option_behavior"


def make_cohort_key(row: dict[str, Any]) -> CohortKey:
    return CohortKey(
        decision_date=decision_date(row),
        selected_strategy=selected_strategy(row),
        bucket=infer_bucket(row),
        regime_state=get_regime_state(row),
        asset_behavior_state=get_asset_behavior_state(row),
        option_behavior_state=get_option_behavior_state(row),
    )


def make_scope_key(key: CohortKey) -> tuple[str, str, str, str, str]:
    return (
        key.selected_strategy,
        key.bucket,
        key.regime_state,
        key.asset_behavior_state,
        key.option_behavior_state,
    )


def build_cohorts(rows: list[dict[str, Any]]) -> list[CohortSummary]:
    grouped: dict[CohortKey, list[dict[str, Any]]] = defaultdict(list)

    for row in rows:
        if is_active(row):
            grouped[make_cohort_key(row)].append(row)

    cohorts: list[CohortSummary] = []

    for key, cohort_rows in grouped.items():
        pnl = sum(pnl_value(row) for row in cohort_rows)
        available = max(parse_date(available_date(row)) for row in cohort_rows)

        cohorts.append(
            CohortSummary(
                key=key,
                scope_key=make_scope_key(key),
                decision_date_obj=parse_date(key.decision_date),
                available_date_obj=available,
                total_pnl=pnl,
                trade_count=len(cohort_rows),
                final_negative=pnl < 0,
            )
        )

    return cohorts


def should_skip(target: CohortSummary, priors: list[CohortSummary], min_prior: int, avg_threshold: float, neg_rate_threshold: float) -> tuple[bool, dict[str, Any]]:
    prior_count = len(priors)

    if prior_count < min_prior:
        return False, {
            "prior_count": prior_count,
            "prior_avg_pnl": None,
            "prior_final_negative_rate": None,
            "cohort_gate_state": "insufficient_prior",
        }

    prior_avg_pnl = sum(c.total_pnl for c in priors) / prior_count
    prior_final_negative_rate = sum(1 for c in priors if c.final_negative) / prior_count

    weak = prior_avg_pnl <= avg_threshold and prior_final_negative_rate >= neg_rate_threshold

    return weak, {
        "prior_count": prior_count,
        "prior_avg_pnl": prior_avg_pnl,
        "prior_final_negative_rate": prior_final_negative_rate,
        "cohort_gate_state": "weak_prior_final_negative" if weak else "normal",
    }


def apply_skip(row: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)

    out["cohort_gate_parent_row_state"] = pick(row, ["row_state", "sizing_state", "allocation_state"], "accepted")
    out["cohort_gate_parent_pnl_dollars"] = pnl_value(row)
    out["cohort_gate_action"] = "skip_weak_prior_final_negative_candidate"
    out["cohort_gate_rule_id"] = RULE["rule_id"]
    out["cohort_gate_skip_reason"] = "cohort_risk_rejection_gate_v1_1_min_prior_6"
    out["cohort_gate_prior_count"] = decision.get("prior_count")
    out["cohort_gate_prior_avg_pnl"] = decision.get("prior_avg_pnl")
    out["cohort_gate_prior_final_negative_rate"] = decision.get("prior_final_negative_rate")
    out["cohort_gate_state"] = decision.get("cohort_gate_state")

    for field in QUANTITY_FIELDS:
        if field in out:
            out[field] = 0.0

    for field in RISK_FIELDS:
        if field in out:
            out[field] = 0.0

    for field in PNL_FIELDS:
        if field in out:
            out[field] = 0.0

    out["row_state"] = "skipped"
    out["skip_reason"] = "cohort_risk_rejection_gate_v1_1_min_prior_6"

    return out


def apply_normal(row: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["cohort_gate_action"] = "normal"
    out["cohort_gate_rule_id"] = RULE["rule_id"]
    out["cohort_gate_prior_count"] = decision.get("prior_count")
    out["cohort_gate_prior_avg_pnl"] = decision.get("prior_avg_pnl")
    out["cohort_gate_prior_final_negative_rate"] = decision.get("prior_final_negative_rate")
    out["cohort_gate_state"] = decision.get("cohort_gate_state")
    return out


def metrics(rows: list[dict[str, Any]], starting_capital: float) -> dict[str, Any]:
    active = [r for r in rows if is_active(r)]
    pnls = [pnl_value(r) for r in active]

    wins = [x for x in pnls if x > 0]
    losses = [abs(x) for x in pnls if x < 0]

    equity = starting_capital
    peak = starting_capital
    max_dd = 0.0

    by_close: dict[str, float] = defaultdict(float)
    for row in active:
        by_close[available_date(row)] += pnl_value(row)

    for d in sorted(by_close):
        equity += by_close[d]
        if equity > peak:
            peak = equity
        if peak:
            max_dd = min(max_dd, (equity - peak) / peak)

    return {
        "starting_capital": starting_capital,
        "ending_equity": equity,
        "total_pnl_dollars": equity - starting_capital,
        "total_return_pct": (equity - starting_capital) / starting_capital if starting_capital else None,
        "max_drawdown_pct": max_dd,
        "trade_count": len(active),
        "gross_win_dollars": sum(wins),
        "gross_loss_dollars": sum(losses),
        "trade_win_rate": len(wins) / len(pnls) if pnls else None,
        "trade_profit_factor": sum(wins) / sum(losses) if sum(losses) else None,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    input_path = Path(args.input_ledger)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = read_jsonl(input_path)
    cohorts = build_cohorts(rows)

    by_scope: dict[tuple[str, str, str, str, str], list[CohortSummary]] = defaultdict(list)
    for cohort in cohorts:
        by_scope[cohort.scope_key].append(cohort)

    cohort_decisions: dict[CohortKey, dict[str, Any]] = {}

    for target in cohorts:
        priors = [
            c for c in by_scope[target.scope_key]
            if c.available_date_obj < target.decision_date_obj
        ]

        skip, decision = should_skip(
            target=target,
            priors=priors,
            min_prior=args.min_prior,
            avg_threshold=args.prior_avg_pnl_threshold,
            neg_rate_threshold=args.prior_final_negative_rate_threshold,
        )

        decision.update(
            {
                "skip": skip,
                "decision_date": target.key.decision_date,
                "selected_strategy": target.key.selected_strategy,
                "bucket": target.key.bucket,
                "regime_state": target.key.regime_state,
                "asset_behavior_state": target.key.asset_behavior_state,
                "option_behavior_state": target.key.option_behavior_state,
                "target_cohort_trade_count": target.trade_count,
                "target_cohort_pnl_dollars": target.total_pnl,
            }
        )

        cohort_decisions[target.key] = decision

    output_rows: list[dict[str, Any]] = []
    skipped_rows: list[dict[str, Any]] = []
    action_counts = Counter()
    gate_state_counts = Counter()
    skipped_strategy_counts = Counter()

    for row in rows:
        if not is_active(row):
            out = dict(row)
            out.setdefault("cohort_gate_action", "not_active")
            output_rows.append(out)
            action_counts[out["cohort_gate_action"]] += 1
            continue

        key = make_cohort_key(row)
        decision = cohort_decisions.get(key, {"skip": False, "cohort_gate_state": "missing_decision"})

        if decision.get("skip"):
            out = apply_skip(row, decision)
            skipped_rows.append(out)
            skipped_strategy_counts[selected_strategy(row)] += 1
        else:
            out = apply_normal(row, decision)

        output_rows.append(out)
        action_counts[out["cohort_gate_action"]] += 1
        gate_state_counts[str(out.get("cohort_gate_state"))] += 1

    base_metrics = metrics(rows, args.starting_capital)
    gated_metrics = metrics(output_rows, args.starting_capital)

    ledger_path = output_dir / "signalforge_cohort_risk_rejection_gate_v1_1_ledger.jsonl"
    skipped_path = output_dir / "signalforge_cohort_risk_rejection_gate_v1_1_skipped_rows.jsonl"
    summary_path = output_dir / "signalforge_cohort_risk_rejection_gate_v1_1_summary.json"

    write_jsonl(ledger_path, output_rows)
    write_jsonl(skipped_path, skipped_rows)

    summary = {
        "adapter_type": "cohort_risk_rejection_gate_v1_1_builder",
        "artifact_type": "signalforge_cohort_risk_rejection_gate_v1_1",
        "contract": "cohort_risk_rejection_gate_v1_1",
        "is_ready": True,
        "readiness_state": "ready",
        "blocker_count": 0,
        "blockers": [],
        "input_ledger": str(input_path),
        "input_row_count": len(rows),
        "output_row_count": len(output_rows),
        "cohort_count": len(cohorts),
        "scope_count": len(by_scope),
        "skipped_row_count": len(skipped_rows),
        "action_counts": dict(action_counts),
        "cohort_gate_state_counts": dict(gate_state_counts),
        "skipped_strategy_counts": dict(skipped_strategy_counts),
        "baseline_metrics": base_metrics,
        "gated_metrics": gated_metrics,
        "delta_metrics": {
            "delta_pnl_dollars": gated_metrics["total_pnl_dollars"] - base_metrics["total_pnl_dollars"],
            "delta_return_pct": gated_metrics["total_return_pct"] - base_metrics["total_return_pct"],
            "delta_profit_factor": (gated_metrics["trade_profit_factor"] or 0) - (base_metrics["trade_profit_factor"] or 0),
            "delta_max_drawdown_pct": gated_metrics["max_drawdown_pct"] - base_metrics["max_drawdown_pct"],
            "delta_trade_count": gated_metrics["trade_count"] - base_metrics["trade_count"],
        },
        "policy": {
            "does_not_change_entry": True,
            "does_not_change_exit": True,
            "does_not_change_expectancy": True,
            "does_not_replace_skipped_trades": True,
            "prior_window_only": True,
            "same_decision_date_not_used_as_prior": True,
            "prior_mode": RULE["prior_mode"],
        },
        "rule": {
            **RULE,
            "min_prior": args.min_prior,
            "prior_avg_pnl_threshold": args.prior_avg_pnl_threshold,
            "prior_final_negative_rate_threshold": args.prior_final_negative_rate_threshold,
        },
        "paths": {
            "ledger": str(ledger_path),
            "skipped_rows": str(skipped_path),
            "summary": str(summary_path),
        },
    }

    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-ledger", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--starting-capital", type=float, required=True)
    parser.add_argument("--min-prior", type=int, default=6)
    parser.add_argument("--prior-avg-pnl-threshold", type=float, default=-500.0)
    parser.add_argument("--prior-final-negative-rate-threshold", type=float, default=0.50)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    summary = run(args)

    print(json.dumps({
        "is_ready": summary["is_ready"],
        "blocker_count": summary["blocker_count"],
        "input_row_count": summary["input_row_count"],
        "cohort_count": summary["cohort_count"],
        "scope_count": summary["scope_count"],
        "skipped_row_count": summary["skipped_row_count"],
        "action_counts": summary["action_counts"],
        "skipped_strategy_counts": summary["skipped_strategy_counts"],
        "baseline": {
            "trade_count": summary["baseline_metrics"]["trade_count"],
            "total_return_pct": summary["baseline_metrics"]["total_return_pct"],
            "profit_factor": summary["baseline_metrics"]["trade_profit_factor"],
            "max_drawdown_pct": summary["baseline_metrics"]["max_drawdown_pct"],
        },
        "gated": {
            "trade_count": summary["gated_metrics"]["trade_count"],
            "total_return_pct": summary["gated_metrics"]["total_return_pct"],
            "profit_factor": summary["gated_metrics"]["trade_profit_factor"],
            "max_drawdown_pct": summary["gated_metrics"]["max_drawdown_pct"],
        },
        "delta": summary["delta_metrics"],
        "paths": summary["paths"],
    }, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
