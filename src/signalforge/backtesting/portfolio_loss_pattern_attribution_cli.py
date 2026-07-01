from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime
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

    qtys = [fnum(row.get(k), None) for k in QUANTITY_FIELDS if k in row]
    qtys = [x for x in qtys if x is not None]

    if qtys and max(qtys) <= 0:
        return False

    return True


def pnl_value(row: dict[str, Any]) -> float:
    for field in PNL_FIELDS:
        if row.get(field) not in (None, ""):
            return fnum(row.get(field))

    risk = fnum(pick(row, RISK_FIELDS, 0.0))
    ret = fnum(pick(row, RETURN_FIELDS, 0.0))
    return risk * ret


def get_date(row: dict[str, Any]) -> str:
    return str(
        pick(
            row,
            [
                "portfolio_realization_date",
                "realization_date",
                "exit_date",
                "close_date",
                "outcome_date",
                "decision_date",
                "entry_date",
                "trade_date",
                "date",
            ],
            "",
        )
    )[:10]


def get_year(row: dict[str, Any]) -> str:
    d = get_date(row)
    return d[:4] if len(d) >= 4 else "unknown"


def get_month(row: dict[str, Any]) -> str:
    d = get_date(row)
    return d[:7] if len(d) >= 7 else "unknown"


def get_strategy(row: dict[str, Any]) -> str:
    return cat(pick(row, ["selected_strategy", "strategy", "strategy_family"]), "unknown_strategy")


def get_symbol(row: dict[str, Any]) -> str:
    return cat(pick(row, ["symbol", "underlying_symbol"]), "unknown_symbol")


def get_bucket(row: dict[str, Any]) -> str:
    return cat(
        pick(
            row,
            [
                "bucket",
                "final_bucket",
                "allocation_bucket",
                "rank_bucket",
                "strategy_rank_bucket",
                "selected_bucket",
                "selected_allocation_bucket",
            ],
        ),
        "unknown_bucket",
    )


def get_regime(row: dict[str, Any]) -> str:
    return cat(pick(row, ["regime_state", "regime"]), "unknown_regime")


def get_asset_behavior(row: dict[str, Any]) -> str:
    direct = pick(row, ["asset_behavior_state", "selected_asset_behavior_state"])
    if direct not in (None, ""):
        return cat(direct)

    rc = row.get("research_context") or {}
    if isinstance(rc, dict):
        ab = rc.get("asset_behavior") or {}
        if isinstance(ab, dict):
            return cat(ab.get("state"), "unknown_asset_behavior")

    return "unknown_asset_behavior"


def get_option_behavior(row: dict[str, Any]) -> str:
    direct = pick(row, ["option_behavior_state", "selected_option_behavior_state"])
    if direct not in (None, ""):
        return cat(direct)

    rc = row.get("research_context") or {}
    if isinstance(rc, dict):
        ob = rc.get("option_behavior") or {}
        if isinstance(ob, dict):
            return cat(ob.get("state"), "unknown_option_behavior")

    return "unknown_option_behavior"


def get_expectancy_state(row: dict[str, Any]) -> str:
    return cat(
        pick(
            row,
            [
                "selected_expectancy_state",
                "historical_edge_state",
                "expectancy_state",
                "edge_state",
            ],
        ),
        "unknown_expectancy",
    )


def expectancy_score(row: dict[str, Any]) -> float:
    return fnum(
        pick(
            row,
            [
                "selected_expectancy_score",
                "historical_edge_score",
                "risk_adjusted_edge_score",
                "expectancy_score",
            ],
            0.0,
        )
    )


def expectancy_bucket(row: dict[str, Any]) -> str:
    score = expectancy_score(row)
    if score >= 1.0:
        return "score_ge_1"
    if score >= 0.5:
        return "score_0p5_to_1"
    if score > 0:
        return "score_0_to_0p5"
    if score == 0:
        return "score_0"
    return "score_negative"


def spread_bucket(row: dict[str, Any]) -> str:
    spreads = []

    legs = row.get("selected_legs") or row.get("legs") or []
    if isinstance(legs, list):
        for leg in legs:
            if not isinstance(leg, dict):
                continue
            bid = fnum(leg.get("bid"), None)
            ask = fnum(leg.get("ask"), None)
            mid = fnum(leg.get("mid"), None)
            spread = fnum(leg.get("spread"), None)

            if spread is None and bid is not None and ask is not None:
                spread = abs(ask - bid)

            if spread is not None:
                spreads.append(spread)

    direct = fnum(pick(row, ["spread", "spread_width", "entry_spread_width"], None), None)
    if direct is not None:
        spreads.append(direct)

    if not spreads:
        return "spread_unknown"

    avg = sum(spreads) / len(spreads)

    if avg <= 0.05:
        return "spread_le_0p05"
    if avg <= 0.10:
        return "spread_0p05_to_0p10"
    if avg <= 0.25:
        return "spread_0p10_to_0p25"
    if avg <= 0.50:
        return "spread_0p25_to_0p50"
    return "spread_gt_0p50"


def dte_bucket(row: dict[str, Any]) -> str:
    dte = fnum(pick(row, ["dte", "expiration_dte", "selected_dte", "days_to_expiration"], None), None)

    if dte is None:
        return "dte_unknown"
    if dte <= 7:
        return "dte_le_7"
    if dte <= 21:
        return "dte_8_to_21"
    if dte <= 45:
        return "dte_22_to_45"
    if dte <= 90:
        return "dte_46_to_90"
    return "dte_gt_90"


def get_features(row: dict[str, Any]) -> dict[str, str]:
    strategy = get_strategy(row)
    symbol = get_symbol(row)
    regime = get_regime(row)
    asset_behavior = get_asset_behavior(row)
    option_behavior = get_option_behavior(row)
    bucket = get_bucket(row)
    exp_state = get_expectancy_state(row)
    exp_bucket = expectancy_bucket(row)
    spread = spread_bucket(row)
    dte = dte_bucket(row)
    year = get_year(row)
    month = get_month(row)

    return {
        "strategy": strategy,
        "symbol": symbol,
        "bucket": bucket,
        "regime_state": regime,
        "asset_behavior_state": asset_behavior,
        "option_behavior_state": option_behavior,
        "expectancy_state": exp_state,
        "expectancy_bucket": exp_bucket,
        "spread_bucket": spread,
        "dte_bucket": dte,
        "year": year,
        "month": month,
        "strategy_regime": f"{strategy}|{regime}",
        "strategy_asset_behavior": f"{strategy}|{asset_behavior}",
        "strategy_option_behavior": f"{strategy}|{option_behavior}",
        "strategy_bucket": f"{strategy}|{bucket}",
        "strategy_regime_asset_option": f"{strategy}|{bucket}|{regime}|{asset_behavior}|{option_behavior}",
        "symbol_strategy": f"{symbol}|{strategy}",
        "symbol_regime": f"{symbol}|{regime}",
        "month_strategy": f"{month}|{strategy}",
    }


def summarize_group(rows: list[dict[str, Any]], total_loss_abs: float) -> dict[str, Any]:
    pnls = [r["_pnl"] for r in rows]
    losses = [x for x in pnls if x < 0]
    wins = [x for x in pnls if x > 0]

    net = sum(pnls)
    gross_loss = abs(sum(losses))
    gross_win = sum(wins)

    return {
        "trade_count": len(rows),
        "loss_trade_count": len(losses),
        "win_trade_count": len(wins),
        "net_pnl": net,
        "gross_loss": gross_loss,
        "gross_win": gross_win,
        "loss_share": gross_loss / total_loss_abs if total_loss_abs else None,
        "win_rate": len(wins) / len(rows) if rows else None,
        "avg_pnl": net / len(rows) if rows else None,
        "avg_loss": sum(losses) / len(losses) if losses else None,
        "profit_factor": gross_win / gross_loss if gross_loss else None,
        "worst_trade_pnl": min(pnls) if pnls else None,
        "best_trade_pnl": max(pnls) if pnls else None,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    input_path = Path(args.input_ledger)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    active_rows = []

    for raw in read_jsonl(input_path):
        if not is_active(raw):
            continue

        pnl = pnl_value(raw)
        features = get_features(raw)

        row = dict(raw)
        row["_pnl"] = pnl
        row["_features"] = features

        active_rows.append(row)

    total_gross_loss = abs(sum(r["_pnl"] for r in active_rows if r["_pnl"] < 0))
    total_gross_win = sum(r["_pnl"] for r in active_rows if r["_pnl"] > 0)
    total_net_pnl = sum(r["_pnl"] for r in active_rows)

    dimensions = [
        "strategy",
        "symbol",
        "bucket",
        "regime_state",
        "asset_behavior_state",
        "option_behavior_state",
        "expectancy_state",
        "expectancy_bucket",
        "spread_bucket",
        "dte_bucket",
        "year",
        "month",
        "strategy_regime",
        "strategy_asset_behavior",
        "strategy_option_behavior",
        "strategy_bucket",
        "strategy_regime_asset_option",
        "symbol_strategy",
        "symbol_regime",
        "month_strategy",
    ]

    all_group_rows = []
    top_by_dimension = {}

    for dim in dimensions:
        grouped = defaultdict(list)

        for row in active_rows:
            grouped[row["_features"].get(dim, "unknown")].append(row)

        dim_rows = []

        for value, rows in grouped.items():
            summary = summarize_group(rows, total_gross_loss)

            out = {
                "dimension": dim,
                "value": value,
                **summary,
            }

            if (
                out["loss_trade_count"] >= args.min_loss_trades
                and out["gross_loss"] >= args.min_gross_loss
            ):
                dim_rows.append(out)
                all_group_rows.append(out)

        dim_rows.sort(key=lambda x: (x["gross_loss"], -x["net_pnl"]), reverse=True)
        top_by_dimension[dim] = dim_rows[: args.top_n]

    loss_rows = [r for r in active_rows if r["_pnl"] < 0]
    loss_rows.sort(key=lambda x: x["_pnl"])

    worst_trade_rows = []
    for row in loss_rows[: args.top_n]:
        features = row["_features"]
        worst_trade_rows.append({
            "pnl": row["_pnl"],
            "date": get_date(row),
            "symbol": get_symbol(row),
            "selected_strategy": get_strategy(row),
            "bucket": get_bucket(row),
            "regime_state": features["regime_state"],
            "asset_behavior_state": features["asset_behavior_state"],
            "option_behavior_state": features["option_behavior_state"],
            "expectancy_state": features["expectancy_state"],
            "expectancy_bucket": features["expectancy_bucket"],
            "spread_bucket": features["spread_bucket"],
            "dte_bucket": features["dte_bucket"],
        })

    all_group_rows.sort(key=lambda x: (x["gross_loss"], -x["net_pnl"]), reverse=True)

    red_flags = [
        r for r in all_group_rows
        if r["loss_trade_count"] >= args.red_flag_min_loss_trades
        and (r["profit_factor"] is None or r["profit_factor"] < args.red_flag_max_profit_factor)
        and r["gross_loss"] >= args.red_flag_min_gross_loss
    ]
    red_flags.sort(key=lambda x: (x["gross_loss"], -x["net_pnl"]), reverse=True)

    summary = {
        "adapter_type": "portfolio_loss_pattern_attribution_builder",
        "artifact_type": "signalforge_portfolio_loss_pattern_attribution",
        "contract": "portfolio_loss_pattern_attribution",
        "is_ready": True,
        "readiness_state": "diagnostic_only",
        "input_ledger": str(input_path),
        "active_trade_count": len(active_rows),
        "loss_trade_count": len(loss_rows),
        "win_trade_count": len([r for r in active_rows if r["_pnl"] > 0]),
        "total_net_pnl": total_net_pnl,
        "total_gross_loss": total_gross_loss,
        "total_gross_win": total_gross_win,
        "profit_factor": total_gross_win / total_gross_loss if total_gross_loss else None,
        "loss_rate": len(loss_rows) / len(active_rows) if active_rows else None,
        "dimension_count": len(dimensions),
        "red_flag_count": len(red_flags),
        "policy": {
            "diagnostic_only": True,
            "uses_realized_outcomes": True,
            "not_live_safe_until_converted_to_walk_forward_rule": True,
            "uses_full_enriched_dataset": True,
        },
        "paths": {
            "summary": str(output_dir / "signalforge_portfolio_loss_pattern_attribution_summary.json"),
            "top_groups": str(output_dir / "signalforge_portfolio_loss_pattern_top_groups.jsonl"),
            "red_flags": str(output_dir / "signalforge_portfolio_loss_pattern_red_flags.jsonl"),
            "worst_trades": str(output_dir / "signalforge_portfolio_loss_pattern_worst_trades.jsonl"),
        },
        "top_by_dimension": top_by_dimension,
    }

    write_json(output_dir / "signalforge_portfolio_loss_pattern_attribution_summary.json", summary)
    write_jsonl(output_dir / "signalforge_portfolio_loss_pattern_top_groups.jsonl", all_group_rows)
    write_jsonl(output_dir / "signalforge_portfolio_loss_pattern_red_flags.jsonl", red_flags)
    write_jsonl(output_dir / "signalforge_portfolio_loss_pattern_worst_trades.jsonl", worst_trade_rows)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-ledger", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--top-n", type=int, default=25)
    parser.add_argument("--min-loss-trades", type=int, default=3)
    parser.add_argument("--min-gross-loss", type=float, default=500.0)
    parser.add_argument("--red-flag-min-loss-trades", type=int, default=5)
    parser.add_argument("--red-flag-min-gross-loss", type=float, default=1500.0)
    parser.add_argument("--red-flag-max-profit-factor", type=float, default=1.0)
    args = parser.parse_args()

    summary = run(args)

    print(json.dumps({
        "is_ready": summary["is_ready"],
        "readiness_state": summary["readiness_state"],
        "active_trade_count": summary["active_trade_count"],
        "loss_trade_count": summary["loss_trade_count"],
        "total_net_pnl": summary["total_net_pnl"],
        "total_gross_loss": summary["total_gross_loss"],
        "profit_factor": summary["profit_factor"],
        "red_flag_count": summary["red_flag_count"],
        "paths": summary["paths"],
    }, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
