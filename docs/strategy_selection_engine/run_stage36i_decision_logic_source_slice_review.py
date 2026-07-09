import ast
import json
from pathlib import Path


OUT_DIR = Path("docs/strategy_selection_engine")

TARGETS = [
    {
        "source_path": "src/signalforge/backtesting/historical_strategy_selection_rows_builder.py",
        "functions": [
            "_is_selectable",
            "_selection_score",
            "_sample_confidence_multiplier",
            "_scope_confidence_multiplier",
            "_confidence_adjusted_selection_score",
            "_rank_tuple",
            "_selection_row",
        ],
        "proposed_engine_target": "src/signalforge/engines/strategy_selection/selection_decision.py",
    },
    {
        "source_path": "src/signalforge/backtesting/portfolio_selected_trade_sequence.py",
        "functions": [
            "_extract_trade",
        ],
        "proposed_engine_target": "src/signalforge/engines/strategy_selection/selected_trade_sequence_decision.py",
    },
]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def function_source(lines, node):
    start = node.lineno
    end = getattr(node, "end_lineno", node.lineno)
    return "\n".join(lines[start - 1:end])


def names_used(node):
    used = set()
    assigned = set()
    args = set()

    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        for arg in node.args.args:
            args.add(arg.arg)
        for arg in node.args.kwonlyargs:
            args.add(arg.arg)
        if node.args.vararg:
            args.add(node.args.vararg.arg)
        if node.args.kwarg:
            args.add(node.args.kwarg.arg)

    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            if isinstance(child.ctx, ast.Load):
                used.add(child.id)
            elif isinstance(child.ctx, (ast.Store, ast.Del)):
                assigned.add(child.id)

    return sorted(used - assigned - args)


def calls_used(node):
    calls = set()

    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            fn = child.func
            if isinstance(fn, ast.Name):
                calls.add(fn.id)
            elif isinstance(fn, ast.Attribute):
                calls.add(fn.attr)

    return sorted(calls)


def imports_in_file(tree):
    rows = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                rows.append({
                    "kind": "import",
                    "module": alias.name,
                    "name": alias.asname or alias.name,
                    "lineno": node.lineno,
                })

        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                rows.append({
                    "kind": "from_import",
                    "module": node.module or "",
                    "name": alias.name,
                    "asname": alias.asname,
                    "lineno": node.lineno,
                })

    return rows


def main():
    blockers = []
    warnings = []
    rows = []

    for target in TARGETS:
        path = Path(target["source_path"])

        if not path.exists():
            blockers.append(f"missing_source_path_{path}")
            continue

        text = read_text(path)
        lines = text.splitlines()
        tree = ast.parse(text)
        file_imports = imports_in_file(tree)

        functions_by_name = {
            node.name: node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.col_offset == 0
        }

        for function_name in target["functions"]:
            node = functions_by_name.get(function_name)

            if node is None:
                blockers.append(f"missing_function_{path}_{function_name}")
                continue

            src = function_source(lines, node)

            rows.append({
                "source_path": str(path).replace("\\", "/"),
                "function": function_name,
                "lineno": node.lineno,
                "end_lineno": getattr(node, "end_lineno", node.lineno),
                "line_count": getattr(node, "end_lineno", node.lineno) - node.lineno + 1,
                "proposed_engine_target": target["proposed_engine_target"],
                "names_used": names_used(node),
                "calls_used": calls_used(node),
                "source": src,
                "file_imports": file_imports,
            })

    warnings.append("stage36i_is_read_only_source_slice_review")
    warnings.append("do_not_move_historical_wrappers_out_of_backtesting")
    warnings.append("next_stage_should_extract_first_selection_decision_cluster_with_parity_test")

    summary = {
        "adapter_type": "decision_logic_source_slice_review_builder",
        "artifact_type": "signalforge_decision_logic_source_slice_review",
        "contract": "decision_logic_source_slice_review",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,
        "source_file_count": len(TARGETS),
        "function_slice_count": len(rows),
        "paper_order_created": False,
        "live_order_created": False,
        "live_trade_supported": False,
        "next_step": "stage36j_extract_selection_decision_cluster_with_parity_test",
    }

    summary_path = OUT_DIR / "signalforge_stage36i_decision_logic_source_slice_review_summary.json"
    rows_path = OUT_DIR / "signalforge_stage36i_decision_logic_source_slice_review_rows.jsonl"
    md_path = OUT_DIR / "signalforge_stage36i_decision_logic_source_slice_review.md"

    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    with rows_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")

    md = [
        "# Stage 36I Decision Logic Source Slice Review",
        "",
        f"- is_ready: {summary['is_ready']}",
        f"- blocker_count: {summary['blocker_count']}",
        f"- function_slice_count: {summary['function_slice_count']}",
        f"- paper_order_created: {summary['paper_order_created']}",
        f"- live_order_created: {summary['live_order_created']}",
        f"- live_trade_supported: {summary['live_trade_supported']}",
        "",
    ]

    for row in rows:
        md.extend([
            f"## `{row['function']}`",
            "",
            f"- source: `{row['source_path']}`",
            f"- lines: {row['lineno']}-{row['end_lineno']}",
            f"- proposed target: `{row['proposed_engine_target']}`",
            f"- calls: {', '.join(row['calls_used'])}",
            f"- external names: {', '.join(row['names_used'])}",
            "",
            "```python",
            row["source"],
            "```",
            "",
        ])

    if blockers:
        md.extend(["## Blockers", ""])
        for blocker in blockers:
            md.append(f"- {blocker}")

    if warnings:
        md.extend(["## Warnings", ""])
        for warning in warnings:
            md.append(f"- {warning}")

    md_path.write_text("\n".join(md), encoding="utf-8")

    print("\n--- Stage 36I decision logic source slice review compact ---")
    for key in [
        "is_ready",
        "blocker_count",
        "warning_count",
        "source_file_count",
        "function_slice_count",
        "paper_order_created",
        "live_order_created",
        "live_trade_supported",
    ]:
        print(f"{key}: {summary[key]}")

    print(f"summary_path: {summary_path}")
    print(f"rows_path: {rows_path}")
    print(f"md_path: {md_path}")

    print("\n--- Stage 36I function slices compact ---")
    print("source_path\tfunction\tlines\tproposed_engine_target\tcalls")
    for row in rows:
        print(
            f"{row['source_path']}\t{row['function']}\t"
            f"{row['lineno']}-{row['end_lineno']}\t"
            f"{row['proposed_engine_target']}\t"
            f"{','.join(row['calls_used'])}"
        )

    if blockers:
        print("\n--- Stage 36I blockers ---")
        for blocker in blockers:
            print(blocker)
        raise SystemExit(1)

    if warnings:
        print("\n--- Stage 36I warnings ---")
        for warning in warnings:
            print(warning)


if __name__ == "__main__":
    main()
