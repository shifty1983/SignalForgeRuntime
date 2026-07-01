from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


PNL_FIELDS = [
    "realized_pnl_dollars",
    "allocated_pnl",
    "strategy_pnl",
    "portfolio_pnl",
    "pnl",
    "trade_pnl",
    "net_pnl",
]

QUANTITY_FIELDS = [
    "quantity",
    "adjusted_quantity",
    "contract_count",
    "allocated_contract_count",
    "contracts",
    "position_size",
]

RISK_FIELDS = [
    "position_risk_dollars",
    "risk_capital",
    "allocated_risk_dollars",
    "max_loss_dollars",
]

RETURN_FIELDS = [
    "realized_return",
    "strategy_adjusted_return",
    "strategy_return",
]


def read_jsonl(path: Path):
    with path.open("r", encoding="utf-8-sig", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, default=str), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True, default=str) + "\n")


def pick(row: dict[str, Any], names: list[str], default=None):
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


def get_strategy(row: dict[str, Any]) -> str:
    return str(pick(row, ["selected_strategy", "strategy", "strategy_family"], "unknown"))


def get_option_behavior(row: dict[str, Any]) -> str:
    direct = pick(row, ["option_behavior_state", "selected_option_behavior_state"])
    if direct not in (None, ""):
        return str(direct)

    rc = row.get("research_context") or {}
    if isinstance(rc, dict):
        ob = rc.get("option_behavior") or {}
        if isinstance(ob, dict):
            state = ob.get("state")
            if state not in (None, ""):
                return str(state)

    return "unknown_option_behavior"


def pnl_value(row: dict[str, Any]) -> float:
    for field in PNL_FIELDS:
        if row.get(field) not in (None, ""):
            return fnum(row.get(field))

    risk = fnum(pick(row, RISK_FIELDS, 0.0))
    ret = fnum(pick(row, RETURN_FIELDS, 0.0))
    return risk * ret


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

    qtys = []
    for k in QUANTITY_FIELDS:
        if k in row:
            qtys.append(fnum(row.get(k), None))

    qtys = [x for x in qtys if x is not None]

    if qtys and max(qtys) <= 0:
        return False

    return True


def should_skip(row: dict[str, Any]) -> bool:
    return (
        is_active(row)
        and get_strategy(row) == "long_put"
        and get_option_behavior(row) == "iv_low_liquid"
    )


def zero_trade(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)

    parent_pnl = pnl_value(row)

    out["v1_3_parent_pnl_dollars"] = parent_pnl
    out["v1_3_filter_action"] = "skip"
    out["v1_3_filter_reason"] = "long_put_iv_low_liquid"
    out["v1_3_rule_id"] = "cohort_risk_rejection_gate_v1_3_long_put_iv_low_liquid_filter"
    out["row_state"] = "skipped_by_cohort_risk_rejection_gate_v1_3_long_put_iv_low_liquid_filter"

    for field in PNL_FIELDS + QUANTITY_FIELDS + RISK_FIELDS:
        if field in out:
            out[field] = 0

    return out


def run(args: argparse.Namespace) -> dict[str, Any]:
    input_path = Path(args.input_ledger)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    output_rows = []
    skipped_rows = []

    input_count = 0
    active_count = 0
    skipped_count = 0
    skipped_original_pnl = 0.0

    for row in read_jsonl(input_path):
        input_count += 1

        if is_active(row):
            active_count += 1

        if should_skip(row):
            skipped_count += 1
            skipped_original_pnl += pnl_value(row)

            skipped = zero_trade(row)
            output_rows.append(skipped)
            skipped_rows.append(skipped)
        else:
            output_rows.append(row)

    summary = {
        "adapter_type": "cohort_risk_rejection_gate_v1_3_long_put_iv_low_liquid_filter_builder",
        "artifact_type": "signalforge_cohort_risk_rejection_gate_v1_3_long_put_iv_low_liquid_filter",
        "contract": "cohort_risk_rejection_gate_v1_3_long_put_iv_low_liquid_filter",
        "is_ready": True,
        "readiness_state": "materialized_candidate",
        "parent_candidate": "allocator_v2_1_2210_strat30_plus_cohort_gate_v1_2_allocator_calibrated",
        "rule_id": "cohort_risk_rejection_gate_v1_3_long_put_iv_low_liquid_filter",
        "rule": {
            "action": "skip",
            "selected_strategy": "long_put",
            "option_behavior_state": "iv_low_liquid",
            "classification": "behavior_based_loss_pocket_filter",
            "diagnostic_basis": "long_put_iv_low_liquid_loss_attribution_and_split_validation",
        },
        "input_ledger": str(input_path),
        "input_row_count": input_count,
        "active_trade_count_before_filter": active_count,
        "skipped_row_count": skipped_count,
        "skipped_original_pnl_dollars": skipped_original_pnl,
        "expected_delta_pnl_dollars": -skipped_original_pnl,
        "paths": {
            "ledger": str(output_dir / "signalforge_cohort_risk_rejection_gate_v1_3_long_put_iv_low_liquid_filter_ledger.jsonl"),
            "skipped_rows": str(output_dir / "signalforge_cohort_risk_rejection_gate_v1_3_long_put_iv_low_liquid_filter_skipped_rows.jsonl"),
            "summary": str(output_dir / "signalforge_cohort_risk_rejection_gate_v1_3_long_put_iv_low_liquid_filter_summary.json"),
        },
        "blockers": [],
        "warnings": [
            "static_full_period_loss_pocket_filter_requires_robustness_validation_before_promotion",
            "not_live_safe_until_converted_to_asof_or_paper_validated_rule",
        ],
    }

    write_jsonl(output_dir / "signalforge_cohort_risk_rejection_gate_v1_3_long_put_iv_low_liquid_filter_ledger.jsonl", output_rows)
    write_jsonl(output_dir / "signalforge_cohort_risk_rejection_gate_v1_3_long_put_iv_low_liquid_filter_skipped_rows.jsonl", skipped_rows)
    write_json(output_dir / "signalforge_cohort_risk_rejection_gate_v1_3_long_put_iv_low_liquid_filter_summary.json", summary)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-ledger", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    summary = run(args)

    print(json.dumps({
        "is_ready": summary["is_ready"],
        "readiness_state": summary["readiness_state"],
        "rule_id": summary["rule_id"],
        "input_row_count": summary["input_row_count"],
        "active_trade_count_before_filter": summary["active_trade_count_before_filter"],
        "skipped_row_count": summary["skipped_row_count"],
        "skipped_original_pnl_dollars": summary["skipped_original_pnl_dollars"],
        "expected_delta_pnl_dollars": summary["expected_delta_pnl_dollars"],
        "paths": summary["paths"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
