import ast
import importlib
import inspect
import json
from pathlib import Path
from typing import Any, Dict, List


OUT_DIR = Path("docs/strategy_selection_engine")

BACKTESTING_FILES = [
    "src/signalforge/backtesting/historical_strategy_candidate_rows_builder.py",
    "src/signalforge/backtesting/historical_strategy_selection_rows_builder.py",
    "src/signalforge/backtesting/historical_strategy_selection_rows_cli.py",
    "src/signalforge/backtesting/walk_forward_expectancy_builder.py",
    "src/signalforge/backtesting/walk_forward_expectancy_cli.py",
    "src/signalforge/backtesting/portfolio_selected_trade_sequence.py",
]

ENGINE_MODULES = [
    "signalforge.engines.strategy_selection.candidates",
    "signalforge.engines.strategy_selection.contract_candidate_scoring",
    "signalforge.engines.strategy_selection.expected_value_scoring",
    "signalforge.engines.strategy_selection.filters",
    "signalforge.engines.strategy_selection.ranking",
    "signalforge.engines.strategy_selection.selector",
    "signalforge.engines.strategy_selection.portfolio_candidate_input",
    "signalforge.engines.strategy_selection.allocation",
    "signalforge.engines.strategy_selection.selection_report",
]

KEY_TERMS = [
    "expectancy",
    "rank",
    "ranking",
    "selector",
    "select",
    "score",
    "filter",
    "candidate",
    "strategy_selection",
    "one_strategy",
    "symbol",
    "trade_sequence",
    "portfolio_candidate",
]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def rel(path: Path) -> str:
    return str(path).replace("\\", "/")


def parse_file(path: Path) -> Dict[str, Any]:
    text = read_text(path)
    tree = ast.parse(text)

    classes = []
    functions = []
    imports = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            classes.append({
                "name": node.name,
                "lineno": node.lineno,
            })
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.col_offset == 0:
                functions.append({
                    "name": node.name,
                    "lineno": node.lineno,
                    "arg_count": len(node.args.args),
                })
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")

    term_hits = sorted({term for term in KEY_TERMS if term in text.lower() or term in path.name.lower()})

    return {
        "path": rel(path),
        "line_count": len(text.splitlines()),
        "classes": classes,
        "functions": functions,
        "imports": sorted(set(imports)),
        "term_hits": term_hits,
        "engine_import_hits": [
            module for module in ENGINE_MODULES
            if module in text or module in imports
        ],
        "contains_embedded_selection_terms": any(
            term in text.lower()
            for term in [
                "rank",
                "sort",
                "expectancy",
                "selected",
                "strategy_score",
                "selection_score",
                "candidate_score",
            ]
        ),
    }


def module_exports(module_name: str) -> List[Dict[str, Any]]:
    module = importlib.import_module(module_name)
    rows = []

    for name in sorted(n for n in dir(module) if not n.startswith("_")):
        obj = getattr(module, name)
        kind = None
        signature = None

        if inspect.isfunction(obj):
            kind = "function"
        elif inspect.isclass(obj):
            kind = "class"
        else:
            continue

        try:
            signature = str(inspect.signature(obj))
        except Exception:
            signature = None

        rows.append({
            "module": module_name,
            "name": name,
            "kind": kind,
            "signature": signature,
        })

    return rows


def score_possible_overlap(backtest_name: str, engine_name: str) -> int:
    bt = backtest_name.lower()
    en = engine_name.lower()
    score = 0

    for token in [
        "candidate",
        "select",
        "selection",
        "rank",
        "score",
        "filter",
        "expectancy",
        "portfolio",
        "allocation",
        "report",
    ]:
        if token in bt and token in en:
            score += 1

    if bt == en:
        score += 10

    return score


def main() -> None:
    blockers: List[str] = []
    warnings: List[str] = []
    backtesting_rows: List[Dict[str, Any]] = []
    engine_export_rows: List[Dict[str, Any]] = []
    overlap_rows: List[Dict[str, Any]] = []

    for file_path in BACKTESTING_FILES:
        path = Path(file_path)
        if not path.exists():
            blockers.append(f"missing_backtesting_file_{file_path}")
            continue

        row = parse_file(path)
        backtesting_rows.append(row)

    for module_name in ENGINE_MODULES:
        try:
            engine_export_rows.extend(module_exports(module_name))
        except Exception as exc:
            blockers.append(f"engine_export_inspection_failed_{module_name}: {exc}")

    for bt_file in backtesting_rows:
        for fn in bt_file["functions"]:
            matches = []

            for export in engine_export_rows:
                overlap_score = score_possible_overlap(fn["name"], export["name"])
                if overlap_score > 0:
                    matches.append({
                        "engine_module": export["module"],
                        "engine_name": export["name"],
                        "engine_kind": export["kind"],
                        "engine_signature": export["signature"],
                        "overlap_score": overlap_score,
                    })

            matches = sorted(matches, key=lambda r: (-r["overlap_score"], r["engine_module"], r["engine_name"]))[:10]

            overlap_rows.append({
                "backtesting_path": bt_file["path"],
                "backtesting_function": fn["name"],
                "backtesting_lineno": fn["lineno"],
                "candidate_engine_matches": matches,
                "best_overlap_score": matches[0]["overlap_score"] if matches else 0,
            })

    high_priority_files = [
        row for row in backtesting_rows
        if row["contains_embedded_selection_terms"] and not row["engine_import_hits"]
    ]

    warnings.append("stage36g_is_read_only_no_backtesting_logic_modified")
    warnings.append("next_stage_should_migrate_one_backtesting_builder_to_engine_call_or_create_wrapper_parity_test")

    summary = {
        "adapter_type": "post_expectancy_selector_ownership_map_builder",
        "artifact_type": "signalforge_post_expectancy_selector_ownership_map",
        "contract": "post_expectancy_selector_ownership_map",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,
        "backtesting_file_count": len(backtesting_rows),
        "engine_module_count": len(ENGINE_MODULES),
        "engine_export_count": len(engine_export_rows),
        "overlap_row_count": len(overlap_rows),
        "high_priority_backtesting_file_count": len(high_priority_files),
        "high_priority_backtesting_files": [row["path"] for row in high_priority_files],
        "paper_order_created": False,
        "live_order_created": False,
        "live_trade_supported": False,
        "next_step": "stage36h_migrate_historical_strategy_selection_builder_boundary",
    }

    summary_path = OUT_DIR / "signalforge_stage36g_post_expectancy_selector_ownership_map_summary.json"
    backtesting_rows_path = OUT_DIR / "signalforge_stage36g_post_expectancy_backtesting_rows.jsonl"
    engine_exports_path = OUT_DIR / "signalforge_stage36g_strategy_selection_engine_exports.jsonl"
    overlaps_path = OUT_DIR / "signalforge_stage36g_post_expectancy_overlap_rows.jsonl"
    md_path = OUT_DIR / "signalforge_stage36g_post_expectancy_selector_ownership_map.md"

    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    with backtesting_rows_path.open("w", encoding="utf-8") as f:
        for row in backtesting_rows:
            f.write(json.dumps(row) + "\n")

    with engine_exports_path.open("w", encoding="utf-8") as f:
        for row in engine_export_rows:
            f.write(json.dumps(row) + "\n")

    with overlaps_path.open("w", encoding="utf-8") as f:
        for row in overlap_rows:
            f.write(json.dumps(row) + "\n")

    md = [
        "# Stage 36G Post-Expectancy Selector Ownership Map",
        "",
        f"- is_ready: {summary['is_ready']}",
        f"- blocker_count: {summary['blocker_count']}",
        f"- backtesting_file_count: {summary['backtesting_file_count']}",
        f"- engine_module_count: {summary['engine_module_count']}",
        f"- engine_export_count: {summary['engine_export_count']}",
        f"- high_priority_backtesting_file_count: {summary['high_priority_backtesting_file_count']}",
        f"- paper_order_created: {summary['paper_order_created']}",
        f"- live_order_created: {summary['live_order_created']}",
        f"- live_trade_supported: {summary['live_trade_supported']}",
        "",
        "## High Priority Backtesting Files",
        "",
    ]

    for path in summary["high_priority_backtesting_files"]:
        md.append(f"- `{path}`")

    md.extend([
        "",
        "## Backtesting Files",
        "",
        "| path | functions | engine imports | terms |",
        "|---|---:|---|---|",
    ])

    for row in backtesting_rows:
        md.append(
            f"| `{row['path']}` | {len(row['functions'])} | "
            f"{', '.join(row['engine_import_hits'])} | {', '.join(row['term_hits'])} |"
        )

    md.extend([
        "",
        "## Best Overlaps",
        "",
        "| backtesting file | function | best score | best engine candidates |",
        "|---|---|---:|---|",
    ])

    for row in overlap_rows:
        best = row["candidate_engine_matches"][:3]
        best_text = "; ".join(
            f"{m['engine_module']}.{m['engine_name']}" for m in best
        )
        md.append(
            f"| `{row['backtesting_path']}` | `{row['backtesting_function']}` | "
            f"{row['best_overlap_score']} | {best_text} |"
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

    print("\n--- Stage 36G post-expectancy selector ownership map compact ---")
    for key in [
        "is_ready",
        "blocker_count",
        "warning_count",
        "backtesting_file_count",
        "engine_module_count",
        "engine_export_count",
        "overlap_row_count",
        "high_priority_backtesting_file_count",
        "paper_order_created",
        "live_order_created",
        "live_trade_supported",
    ]:
        print(f"{key}: {summary[key]}")

    print(f"summary_path: {summary_path}")
    print(f"backtesting_rows_path: {backtesting_rows_path}")
    print(f"engine_exports_path: {engine_exports_path}")
    print(f"overlaps_path: {overlaps_path}")
    print(f"md_path: {md_path}")

    print("\n--- Stage 36G high-priority backtesting files ---")
    for path in summary["high_priority_backtesting_files"]:
        print(path)

    print("\n--- Stage 36G backtesting rows compact ---")
    print("path\tfunction_count\tengine_import_count\tterms")
    for row in backtesting_rows:
        print(
            f"{row['path']}\t{len(row['functions'])}\t"
            f"{len(row['engine_import_hits'])}\t{','.join(row['term_hits'])}"
        )

    if blockers:
        print("\n--- Stage 36G blockers ---")
        for blocker in blockers:
            print(blocker)
        raise SystemExit(1)

    if warnings:
        print("\n--- Stage 36G warnings ---")
        for warning in warnings:
            print(warning)


if __name__ == "__main__":
    main()
