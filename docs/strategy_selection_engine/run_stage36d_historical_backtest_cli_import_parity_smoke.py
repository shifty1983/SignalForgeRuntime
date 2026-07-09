import importlib
import json
from pathlib import Path


OUT_DIR = Path("docs/strategy_selection_engine")

MODULES = [
    "signalforge.options_execution.strategy_structure_availability_v21",
    "signalforge.options_execution.resolved_strategy_execution_rules_v21",
    "signalforge.options_execution.execution_qualified_historical_strategy_candidates_v21",
    "signalforge.options_execution.repaired_historical_strategy_candidates_v13_v21",

    "signalforge.backtesting.historical_strategy_candidate_rows_cli",
    "signalforge.backtesting.historical_strategy_selection_rows_cli",
    "signalforge.backtesting.historical_strategy_leg_selection_rows_cli",
    "signalforge.backtesting.walk_forward_expectancy_cli",
    "signalforge.backtesting.walk_forward_expectancy_availability_safe_cli",

    "signalforge.engines.strategy_selection.strategy_family_eligibility",
    "signalforge.engines.strategy_selection.strategy_structure_availability_v21",
    "signalforge.engines.strategy_selection.resolved_strategy_execution_rules_v21",
    "signalforge.engines.strategy_selection.execution_qualified_historical_strategy_candidates_v21",
    "signalforge.engines.strategy_selection.repaired_historical_strategy_candidates_v13_v21",
    "signalforge.engines.strategy_selection.selector",
    "signalforge.engines.strategy_selection.ranking",
    "signalforge.engines.strategy_selection.filters",
    "signalforge.engines.strategy_selection.portfolio_candidate_input",
]

rows = []
blockers = []

for module_name in MODULES:
    try:
        module = importlib.import_module(module_name)
        rows.append({
            "module": module_name,
            "import_ok": True,
            "file": getattr(module, "__file__", None),
            "error": None,
        })
    except Exception as exc:
        rows.append({
            "module": module_name,
            "import_ok": False,
            "file": None,
            "error": str(exc),
        })
        blockers.append(f"import_failed_{module_name}: {exc}")

summary = {
    "adapter_type": "historical_backtest_cli_import_parity_smoke_builder",
    "artifact_type": "signalforge_historical_backtest_cli_import_parity_smoke",
    "contract": "historical_backtest_cli_import_parity_smoke",
    "is_ready": len(blockers) == 0,
    "blocker_count": len(blockers),
    "blockers": blockers,
    "module_count": len(MODULES),
    "import_ok_count": sum(1 for row in rows if row["import_ok"]),
    "paper_order_created": False,
    "live_order_created": False,
    "live_trade_supported": False,
    "next_step": "stage36e_update_backtesting_imports_or_run_targeted_replay_parity",
}

summary_path = OUT_DIR / "signalforge_stage36d_historical_backtest_cli_import_parity_smoke_summary.json"
rows_path = OUT_DIR / "signalforge_stage36d_historical_backtest_cli_import_parity_smoke_rows.jsonl"
md_path = OUT_DIR / "signalforge_stage36d_historical_backtest_cli_import_parity_smoke.md"

summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

with rows_path.open("w", encoding="utf-8") as f:
    for row in rows:
        f.write(json.dumps(row) + "\n")

md = [
    "# Stage 36D Historical Backtest CLI Import Parity Smoke",
    "",
    f"- is_ready: {summary['is_ready']}",
    f"- blocker_count: {summary['blocker_count']}",
    f"- module_count: {summary['module_count']}",
    f"- import_ok_count: {summary['import_ok_count']}",
    f"- paper_order_created: {summary['paper_order_created']}",
    f"- live_order_created: {summary['live_order_created']}",
    f"- live_trade_supported: {summary['live_trade_supported']}",
    "",
    "| module | import_ok | file | error |",
    "|---|---:|---|---|",
]

for row in rows:
    md.append(
        f"| `{row['module']}` | {row['import_ok']} | `{row['file']}` | {row['error'] or ''} |"
    )

if blockers:
    md.extend(["", "## Blockers", ""])
    for blocker in blockers:
        md.append(f"- {blocker}")

md_path.write_text("\n".join(md), encoding="utf-8")

print("\n--- Stage 36D historical backtest CLI import parity smoke compact ---")
for key in [
    "is_ready",
    "blocker_count",
    "module_count",
    "import_ok_count",
    "paper_order_created",
    "live_order_created",
    "live_trade_supported",
]:
    print(f"{key}: {summary[key]}")

print(f"summary_path: {summary_path}")
print(f"rows_path: {rows_path}")
print(f"md_path: {md_path}")

print("\n--- Stage 36D import rows ---")
print("import_ok\tmodule")
for row in rows:
    print(f"{row['import_ok']}\t{row['module']}")
    if row["error"]:
        print(row["error"])

if blockers:
    raise SystemExit(1)
