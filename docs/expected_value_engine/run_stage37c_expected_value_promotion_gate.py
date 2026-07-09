import ast
import json
from pathlib import Path
from typing import Any, Dict, List


OUT_DIR = Path("docs/expected_value_engine")

LEGACY_OPPORTUNITY_PATH = Path("src/paper_live_engine/legacy_domain/old_repo/src/expected_value/opportunity_score.py")
LEGACY_RISK_REWARD_PATH = Path("src/paper_live_engine/legacy_domain/old_repo/src/expected_value/risk_reward.py")

BACKTESTING_WALK_FORWARD_PATH = Path("src/signalforge/backtesting/walk_forward_expectancy_builder.py")
BACKTESTING_WALK_FORWARD_CLI_PATH = Path("src/signalforge/backtesting/walk_forward_expectancy_cli.py")
CURRENT_STRATEGY_EV_SCORING_PATH = Path("src/signalforge/engines/strategy_selection/expected_value_scoring.py")

LEGACY_EV_CLUSTER = [
    "normalize",
    "inverse_normalize",
    "score_vega",
    "OpportunityMetrics",
    "ComponentScores",
    "ScoringWeights",
    "OpportunityScoreResult",
    "score_delta",
    "score_expected_return",
    "score_gamma",
    "score_implied_volatility",
    "score_liquidity",
    "score_probability_of_profit",
    "score_reward_risk",
    "score_risk",
    "score_theta",
    "component_scores",
    "validate_weights",
    "total_weight",
    "weighted_score",
    "score_opportunity",
    "rank_opportunities",
    "passes_minimum_thresholds",
    "filter_opportunities",
    "profit_factor",
]

REPO_SEARCH_ROOTS = [
    Path("src/signalforge"),
    Path("src/paper_live_engine"),
]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def py_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*.py") if path.is_file())


def top_level_names(path: Path) -> set[str]:
    if not path.exists():
        return set()

    tree = ast.parse(read_text(path))
    names = set()

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            names.add(node.name)

    return names


def symbol_reference_rows(symbols: list[str]) -> list[dict[str, Any]]:
    rows = []

    for root in REPO_SEARCH_ROOTS:
        for path in py_files(root):
            text = read_text(path)

            for symbol in symbols:
                if symbol not in text:
                    continue

                rows.append({
                    "symbol": symbol,
                    "path": str(path).replace("\\", "/"),
                    "is_legacy_expected_value_source": str(path).replace("\\", "/") in {
                        str(LEGACY_OPPORTUNITY_PATH).replace("\\", "/"),
                        str(LEGACY_RISK_REWARD_PATH).replace("\\", "/"),
                    },
                    "is_backtesting_walk_forward": str(path).replace("\\", "/") in {
                        str(BACKTESTING_WALK_FORWARD_PATH).replace("\\", "/"),
                        str(BACKTESTING_WALK_FORWARD_CLI_PATH).replace("\\", "/"),
                    },
                    "is_current_strategy_ev_scoring": str(path).replace("\\", "/") == str(CURRENT_STRATEGY_EV_SCORING_PATH).replace("\\", "/"),
                })

    return rows


def main() -> None:
    blockers: List[str] = []
    warnings: List[str] = []

    for path in [LEGACY_OPPORTUNITY_PATH, LEGACY_RISK_REWARD_PATH, BACKTESTING_WALK_FORWARD_PATH]:
        if not path.exists():
            blockers.append(f"missing_required_path_{path}")

    reference_rows = symbol_reference_rows(LEGACY_EV_CLUSTER)

    non_legacy_reference_rows = [
        row for row in reference_rows
        if not row["is_legacy_expected_value_source"]
    ]

    walk_forward_reference_rows = [
        row for row in reference_rows
        if row["is_backtesting_walk_forward"]
    ]

    current_strategy_ev_reference_rows = [
        row for row in reference_rows
        if row["is_current_strategy_ev_scoring"]
    ]

    active_backtest_uses_legacy_ev_cluster = bool(walk_forward_reference_rows)

    current_engine_already_contains_legacy_names = sorted(
        top_level_names(CURRENT_STRATEGY_EV_SCORING_PATH).intersection(set(LEGACY_EV_CLUSTER))
    )

    promotion_gate_decision = (
        "do_not_promote_legacy_expected_value_cluster_without_ab_backtest"
    )

    walk_forward_owner = "src/signalforge/backtesting/walk_forward_expectancy_builder.py"

    warnings.append("stage37c_is_read_only_no_logic_moved")
    warnings.append("legacy_expected_value_cluster_is_research_candidate_until_backtested")
    warnings.append("walk_forward_expectancy_builder_remains_backtesting_owned")

    summary = {
        "adapter_type": "expected_value_promotion_gate_builder",
        "artifact_type": "signalforge_expected_value_promotion_gate",
        "contract": "expected_value_promotion_gate",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,
        "legacy_ev_cluster_symbol_count": len(LEGACY_EV_CLUSTER),
        "reference_row_count": len(reference_rows),
        "non_legacy_reference_row_count": len(non_legacy_reference_rows),
        "walk_forward_reference_row_count": len(walk_forward_reference_rows),
        "current_strategy_ev_reference_row_count": len(current_strategy_ev_reference_rows),
        "active_backtest_uses_legacy_ev_cluster": active_backtest_uses_legacy_ev_cluster,
        "current_engine_already_contains_legacy_names": current_engine_already_contains_legacy_names,
        "promotion_gate_decision": promotion_gate_decision,
        "walk_forward_owner": walk_forward_owner,
        "expected_value_candidate_status": "research_candidate_only_until_ab_backtested",
        "paper_order_created": False,
        "live_order_created": False,
        "live_trade_supported": False,
        "next_step": "stage37d_design_expected_value_ab_backtest_before_promotion",
    }

    summary_path = OUT_DIR / "signalforge_stage37c_expected_value_promotion_gate_summary.json"
    reference_rows_path = OUT_DIR / "signalforge_stage37c_expected_value_promotion_gate_reference_rows.jsonl"
    md_path = OUT_DIR / "signalforge_stage37c_expected_value_promotion_gate.md"

    summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    with reference_rows_path.open("w", encoding="utf-8") as f:
        for row in reference_rows:
            f.write(json.dumps(row, default=str) + "\n")

    md = [
        "# Stage 37C Expected-Value Promotion Gate",
        "",
        f"- is_ready: {summary['is_ready']}",
        f"- blocker_count: {summary['blocker_count']}",
        f"- legacy_ev_cluster_symbol_count: {summary['legacy_ev_cluster_symbol_count']}",
        f"- reference_row_count: {summary['reference_row_count']}",
        f"- non_legacy_reference_row_count: {summary['non_legacy_reference_row_count']}",
        f"- walk_forward_reference_row_count: {summary['walk_forward_reference_row_count']}",
        f"- current_strategy_ev_reference_row_count: {summary['current_strategy_ev_reference_row_count']}",
        f"- active_backtest_uses_legacy_ev_cluster: {summary['active_backtest_uses_legacy_ev_cluster']}",
        f"- promotion_gate_decision: `{summary['promotion_gate_decision']}`",
        f"- walk_forward_owner: `{summary['walk_forward_owner']}`",
        f"- expected_value_candidate_status: `{summary['expected_value_candidate_status']}`",
        f"- paper_order_created: {summary['paper_order_created']}",
        f"- live_order_created: {summary['live_order_created']}",
        f"- live_trade_supported: {summary['live_trade_supported']}",
        "",
        "## Decision",
        "",
        "The legacy expected-value cluster is not promoted into production engines at this stage.",
        "It is classified as research-candidate logic until it is tested through a controlled A/B backtest.",
        "",
        "Walk-forward expectancy remains backtesting-owned because it performs historical training-window orchestration, as-of replay, artifact IO, and no-lookahead validation.",
        "",
        "## Legacy EV Cluster Symbols",
        "",
    ]

    for symbol in LEGACY_EV_CLUSTER:
        md.append(f"- `{symbol}`")

    md.extend([
        "",
        "## References",
        "",
        "| symbol | path | legacy source | walk-forward backtest | current EV scoring engine |",
        "|---|---|---:|---:|---:|",
    ])

    for row in reference_rows:
        md.append(
            f"| `{row['symbol']}` | `{row['path']}` | "
            f"{row['is_legacy_expected_value_source']} | "
            f"{row['is_backtesting_walk_forward']} | "
            f"{row['is_current_strategy_ev_scoring']} |"
        )

    if blockers:
        md.extend(["", "## Blockers", ""])
        for blocker in blockers:
            md.append(f"- {blocker}")

    if warnings:
        md.extend(["", "## Warnings", ""])
        for warning in warnings:
            md.append(f"- {warning}")

    md_path.write_text("\n".join(md), encoding="utf-8")

    print("\n--- Stage 37C expected-value promotion gate compact ---")
    for key in [
        "is_ready",
        "blocker_count",
        "warning_count",
        "legacy_ev_cluster_symbol_count",
        "reference_row_count",
        "non_legacy_reference_row_count",
        "walk_forward_reference_row_count",
        "current_strategy_ev_reference_row_count",
        "active_backtest_uses_legacy_ev_cluster",
        "promotion_gate_decision",
        "paper_order_created",
        "live_order_created",
        "live_trade_supported",
    ]:
        print(f"{key}: {summary[key]}")

    print(f"summary_path: {summary_path}")
    print(f"reference_rows_path: {reference_rows_path}")
    print(f"md_path: {md_path}")

    print("\n--- Stage 37C current engine legacy-name overlap ---")
    for name in current_engine_already_contains_legacy_names:
        print(name)

    print("\n--- Stage 37C non-legacy references compact ---")
    print("symbol\tpath\twalk_forward\tcurrent_ev_scoring")
    for row in non_legacy_reference_rows:
        print(
            f"{row['symbol']}\t{row['path']}\t"
            f"{row['is_backtesting_walk_forward']}\t{row['is_current_strategy_ev_scoring']}"
        )

    if blockers:
        print("\n--- Stage 37C blockers ---")
        for blocker in blockers:
            print(blocker)
        raise SystemExit(1)

    if warnings:
        print("\n--- Stage 37C warnings ---")
        for warning in warnings:
            print(warning)


if __name__ == "__main__":
    main()
