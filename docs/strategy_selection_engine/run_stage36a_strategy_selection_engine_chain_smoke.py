import ast
import importlib
import json
import py_compile
from pathlib import Path
from typing import Any, Dict, List


ENGINE_ROOT = Path("src/signalforge/engines/strategy_selection")
OUT_DIR = Path("docs/strategy_selection_engine")

CHAIN = [
    {
        "stage": "family_eligibility",
        "module": "signalforge.engines.strategy_selection.strategy_family_eligibility",
        "role": "regime_asset_behavior_option_behavior_to_eligible_strategy_families",
    },
    {
        "stage": "structure_availability",
        "module": "signalforge.engines.strategy_selection.strategy_structure_availability_v21",
        "role": "eligible_strategy_families_to_buildable_strategy_structures",
    },
    {
        "stage": "resolved_execution_rules",
        "module": "signalforge.engines.strategy_selection.resolved_strategy_execution_rules_v21",
        "role": "structure_rows_to_allowed_conditional_manual_review_block_execution_state",
    },
    {
        "stage": "execution_qualified_candidates",
        "module": "signalforge.engines.strategy_selection.execution_qualified_historical_strategy_candidates_v21",
        "role": "execution_rule_rows_to_execution_qualified_strategy_candidates",
    },
    {
        "stage": "repaired_strategy_candidates",
        "module": "signalforge.engines.strategy_selection.repaired_historical_strategy_candidates_v13_v21",
        "role": "repair_or_normalize_historical_strategy_candidates",
    },
    {
        "stage": "candidate_models",
        "module": "signalforge.engines.strategy_selection.candidates",
        "role": "candidate_data_models_and_helpers",
    },
    {
        "stage": "contract_candidate_scoring",
        "module": "signalforge.engines.strategy_selection.contract_candidate_scoring",
        "role": "contract_level_candidate_scoring",
    },
    {
        "stage": "expected_value_scoring",
        "module": "signalforge.engines.strategy_selection.expected_value_scoring",
        "role": "expected_value_scoring_support",
    },
    {
        "stage": "filters",
        "module": "signalforge.engines.strategy_selection.filters",
        "role": "post_expectancy_filtering",
    },
    {
        "stage": "ranking",
        "module": "signalforge.engines.strategy_selection.ranking",
        "role": "post_expectancy_candidate_ranking",
    },
    {
        "stage": "selector",
        "module": "signalforge.engines.strategy_selection.selector",
        "role": "grouped_ranked_selection_one_strategy_per_symbol_date",
    },
    {
        "stage": "portfolio_candidate_input",
        "module": "signalforge.engines.strategy_selection.portfolio_candidate_input",
        "role": "selected_candidates_to_portfolio_construction_input",
    },
    {
        "stage": "allocation",
        "module": "signalforge.engines.strategy_selection.allocation",
        "role": "allocation_support_for_selected_candidates",
    },
    {
        "stage": "selection_report",
        "module": "signalforge.engines.strategy_selection.selection_report",
        "role": "selection_reporting_support",
    },
]


def module_to_path(module_name: str) -> Path:
    relative = module_name.replace("signalforge.engines.strategy_selection.", "")
    return ENGINE_ROOT / f"{relative}.py"


def inspect_file(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8-sig")
    tree = ast.parse(text)

    classes = []
    functions = []
    imports = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            classes.append(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.col_offset == 0:
                functions.append(node.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")

    return {
        "path": str(path),
        "line_count": len(text.splitlines()),
        "class_count": len(classes),
        "function_count": len(functions),
        "classes": classes[:30],
        "functions": functions[:40],
        "has_stale_src_signalforge_import": "src.signalforge" in text,
    }


def main() -> None:
    blockers: List[str] = []
    warnings: List[str] = []
    rows: List[Dict[str, Any]] = []

    if not ENGINE_ROOT.exists():
        blockers.append("strategy_selection_engine_root_missing")

    for item in CHAIN:
        module_name = item["module"]
        path = module_to_path(module_name)

        row = {
            **item,
            "path": str(path),
            "exists": path.exists(),
            "compile_ok": False,
            "import_ok": False,
            "stale_src_signalforge_import": None,
            "class_count": None,
            "function_count": None,
        }

        if not path.exists():
            blockers.append(f"missing_module_file_{item['stage']}")
            rows.append(row)
            continue

        try:
            py_compile.compile(str(path), doraise=True)
            row["compile_ok"] = True
        except Exception as exc:
            row["compile_error"] = str(exc)
            blockers.append(f"compile_failed_{item['stage']}")

        try:
            details = inspect_file(path)
            row.update({
                "line_count": details["line_count"],
                "class_count": details["class_count"],
                "function_count": details["function_count"],
                "classes": details["classes"],
                "functions": details["functions"],
                "stale_src_signalforge_import": details["has_stale_src_signalforge_import"],
            })

            if details["has_stale_src_signalforge_import"]:
                blockers.append(f"stale_src_signalforge_import_{item['stage']}")

        except Exception as exc:
            row["inspect_error"] = str(exc)
            blockers.append(f"inspect_failed_{item['stage']}")

        try:
            importlib.import_module(module_name)
            row["import_ok"] = True
        except Exception as exc:
            row["import_error"] = str(exc)
            blockers.append(f"import_failed_{item['stage']}")

        rows.append(row)

    expected_stage_count = len(CHAIN)
    ready_stage_count = sum(
        1 for row in rows
        if row.get("exists") and row.get("compile_ok") and row.get("import_ok") and not row.get("stale_src_signalforge_import")
    )

    if ready_stage_count != expected_stage_count:
        blockers.append("not_all_strategy_selection_engine_stages_ready")

    warnings.append("stage36a_is_import_and_chain_smoke_only_not_backtest_replay")
    warnings.append("next_stage_should_compare_backtesting_imports_to_engine_imports_before_deleting_old_paths")

    summary = {
        "adapter_type": "strategy_selection_engine_chain_smoke_builder",
        "artifact_type": "signalforge_strategy_selection_engine_chain_smoke",
        "contract": "strategy_selection_engine_chain_smoke",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,
        "engine_root": str(ENGINE_ROOT),
        "expected_stage_count": expected_stage_count,
        "ready_stage_count": ready_stage_count,
        "chain": rows,
        "chain_state": "engine_chain_import_ready" if len(blockers) == 0 else "engine_chain_not_ready",
        "live_trade_supported": False,
        "paper_order_created": False,
        "live_order_created": False,
        "next_step": "stage36b_backtesting_to_engine_import_boundary_map",
    }

    summary_path = OUT_DIR / "signalforge_stage36a_strategy_selection_engine_chain_smoke_summary.json"
    rows_path = OUT_DIR / "signalforge_stage36a_strategy_selection_engine_chain_smoke_rows.jsonl"
    md_path = OUT_DIR / "signalforge_stage36a_strategy_selection_engine_chain_smoke.md"

    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    with rows_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")

    md = [
        "# Stage 36A Strategy Selection Engine Chain Smoke",
        "",
        f"- is_ready: {summary['is_ready']}",
        f"- blocker_count: {summary['blocker_count']}",
        f"- chain_state: {summary['chain_state']}",
        f"- expected_stage_count: {summary['expected_stage_count']}",
        f"- ready_stage_count: {summary['ready_stage_count']}",
        f"- live_trade_supported: {summary['live_trade_supported']}",
        f"- paper_order_created: {summary['paper_order_created']}",
        f"- live_order_created: {summary['live_order_created']}",
        "",
        "## Chain",
        "",
        "| stage | module | role | compile | import | stale src import |",
        "|---|---|---|---:|---:|---:|",
    ]

    for row in rows:
        md.append(
            f"| {row['stage']} | `{row['module']}` | {row['role']} | "
            f"{row['compile_ok']} | {row['import_ok']} | {row['stale_src_signalforge_import']} |"
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

    print("\n--- Stage 36A strategy-selection engine chain smoke compact ---")
    for key in [
        "is_ready",
        "blocker_count",
        "warning_count",
        "chain_state",
        "expected_stage_count",
        "ready_stage_count",
        "live_trade_supported",
        "paper_order_created",
        "live_order_created",
    ]:
        print(f"{key}: {summary[key]}")

    print(f"summary_path: {summary_path}")
    print(f"rows_path: {rows_path}")
    print(f"md_path: {md_path}")

    print("\n--- Stage 36A chain rows compact ---")
    print("stage\tcompile_ok\timport_ok\tstale_src_import\tmodule")
    for row in rows:
        print(
            f"{row['stage']}\t{row['compile_ok']}\t{row['import_ok']}\t"
            f"{row['stale_src_signalforge_import']}\t{row['module']}"
        )

    if blockers:
        print("\n--- Stage 36A blockers ---")
        for blocker in blockers:
            print(blocker)

    if warnings:
        print("\n--- Stage 36A warnings ---")
        for warning in warnings:
            print(warning)

    if blockers:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

