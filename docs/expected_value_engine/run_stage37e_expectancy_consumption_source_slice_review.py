import ast
import builtins
import json
from pathlib import Path
from typing import Any, Dict, List, Set


OUT_DIR = Path("docs/expected_value_engine")

TARGETS_BY_FILE = {
    Path("src/signalforge/backtesting/walk_forward_expectancy_builder.py"): [
        "_state_for_stats",
    ],
    Path("src/signalforge/engines/strategy_selection/expected_value_scoring.py"): [
        "build_signalforge_expected_value_scoring",
        "_build_ev_item",
        "_candidate_families",
        "_score_family_candidate",
        "_candidate_ev_state",
        "_item_ev_state",
        "_candidate_handoff_status",
        "_summary",
        "_blocked_result",
    ],
}

BUILTINS = set(dir(builtins)) | {"True", "False", "None"}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def source_for_node(lines: list[str], node: ast.AST) -> str:
    start = getattr(node, "lineno", 1)
    end = getattr(node, "end_lineno", start)
    return "\n".join(lines[start - 1:end])


def top_level_functions(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    }


def top_level_classes(tree: ast.Module) -> dict[str, ast.ClassDef]:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
    }


def import_rows(tree: ast.Module) -> list[dict[str, Any]]:
    rows = []

    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                rows.append({
                    "module": alias.name,
                    "name": alias.asname or alias.name.split(".")[0],
                    "source": ast.unparse(node),
                })

        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                rows.append({
                    "module": node.module or "",
                    "name": alias.asname or alias.name,
                    "imported_name": alias.name,
                    "level": node.level,
                    "source": ast.unparse(node),
                })

    return rows


def module_binding_names(tree: ast.Module) -> set[str]:
    names = set()

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            names.add(node.name)

        elif isinstance(node, ast.Assign):
            for target in node.targets:
                for child in ast.walk(target):
                    if isinstance(child, ast.Name):
                        names.add(child.id)

        elif isinstance(node, ast.AnnAssign):
            for child in ast.walk(node.target):
                if isinstance(child, ast.Name):
                    names.add(child.id)

        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])

        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)

    return names


def bound_names(node: ast.AST) -> set[str]:
    names = set()

    for child in ast.walk(node):
        if isinstance(child, ast.FunctionDef):
            for arg in child.args.posonlyargs + child.args.args + child.args.kwonlyargs:
                names.add(arg.arg)
            if child.args.vararg:
                names.add(child.args.vararg.arg)
            if child.args.kwarg:
                names.add(child.args.kwarg.arg)

        elif isinstance(child, ast.Lambda):
            for arg in child.args.posonlyargs + child.args.args + child.args.kwonlyargs:
                names.add(arg.arg)
            if child.args.vararg:
                names.add(child.args.vararg.arg)
            if child.args.kwarg:
                names.add(child.args.kwarg.arg)

        elif isinstance(child, ast.Name) and isinstance(child.ctx, (ast.Store, ast.Del)):
            names.add(child.id)

        elif isinstance(child, ast.ExceptHandler) and child.name:
            names.add(child.name)

        elif isinstance(child, ast.comprehension):
            for target_child in ast.walk(child.target):
                if isinstance(target_child, ast.Name):
                    names.add(target_child.id)

    return names


def loaded_names(node: ast.AST) -> set[str]:
    names = set()

    for child in ast.walk(node):
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
            names.add(child.id)

    return names


def external_names(node: ast.AST) -> set[str]:
    return loaded_names(node) - bound_names(node) - BUILTINS


def calls_used(node: ast.AST) -> list[str]:
    calls = set()

    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            fn = child.func
            if isinstance(fn, ast.Name):
                calls.add(fn.id)
            elif isinstance(fn, ast.Attribute):
                calls.add(fn.attr)

    return sorted(calls)


def signature(node: ast.AST) -> str:
    if isinstance(node, ast.FunctionDef):
        return f"def {node.name}({ast.unparse(node.args)}):"
    if isinstance(node, ast.ClassDef):
        return f"class {node.name}"
    return ""


def dependency_closure(root_names: list[str], functions: dict[str, ast.FunctionDef], classes: dict[str, ast.ClassDef]) -> list[str]:
    seen: Set[str] = set()
    ordered: list[str] = []

    def visit(name: str) -> None:
        if name in seen:
            return

        seen.add(name)

        node = functions.get(name) or classes.get(name)
        if node is None:
            return

        deps = sorted(
            dep for dep in external_names(node)
            if dep in functions or dep in classes
        )

        for dep in deps:
            visit(dep)

        ordered.append(name)

    for root in root_names:
        visit(root)

    return ordered


def classify_action(path: Path, name: str, is_root: bool) -> dict[str, str]:
    path_text = str(path).replace("\\", "/")

    if path_text.endswith("walk_forward_expectancy_builder.py"):
        return {
            "ownership": "backtesting_generation_policy_candidate",
            "recommended_action": "review_for_contract_alignment_do_not_extract_now",
            "recommended_target": "none",
            "reason": "state mapping is part of tested walk-forward output semantics",
        }

    if name == "build_signalforge_expected_value_scoring":
        return {
            "ownership": "engine_expectancy_consumption_entrypoint",
            "recommended_action": "keep_in_engine_as_paper_consumption_candidate",
            "recommended_target": str(path).replace("\\", "/"),
            "reason": "current engine entrypoint for consuming expectancy-like strategy selection inputs",
        }

    if path_text.endswith("expected_value_scoring.py"):
        return {
            "ownership": "engine_expectancy_consumption_helper",
            "recommended_action": "keep_in_engine_verify_snapshot_contract",
            "recommended_target": str(path).replace("\\", "/"),
            "reason": "existing engine-owned scoring helper, should be validated against locked expectancy snapshot contract",
        }

    return {
        "ownership": "manual_review",
        "recommended_action": "manual_review",
        "recommended_target": "manual_review",
        "reason": "unclassified",
    }


def main() -> None:
    blockers: List[str] = []
    warnings: List[str] = []
    rows: List[Dict[str, Any]] = []
    closure_rows: List[Dict[str, Any]] = []

    for source_path, roots in TARGETS_BY_FILE.items():
        if not source_path.exists():
            blockers.append(f"missing_source_path_{source_path}")
            continue

        text = read_text(source_path)
        lines = text.splitlines()
        tree = ast.parse(text)

        functions = top_level_functions(tree)
        classes = top_level_classes(tree)
        imports = import_rows(tree)
        import_names = {row["name"] for row in imports}
        module_bindings = module_binding_names(tree)

        missing_roots = [name for name in roots if name not in functions and name not in classes]
        if missing_roots:
            blockers.append(f"missing_roots_{source_path}_{missing_roots}")

        closure = dependency_closure(roots, functions, classes)

        closure_rows.append({
            "source_path": str(source_path).replace("\\", "/"),
            "root_names": roots,
            "closure_names": closure,
            "closure_count": len(closure),
        })

        for name in closure:
            node = functions.get(name) or classes.get(name)

            if node is None:
                blockers.append(f"missing_closure_symbol_{source_path}_{name}")
                continue

            ext = sorted(external_names(node))

            internal_function_dependencies = sorted(dep for dep in ext if dep in functions)
            internal_class_dependencies = sorted(dep for dep in ext if dep in classes)
            imported_dependencies = sorted(dep for dep in ext if dep in import_names)
            module_binding_dependencies = sorted(
                dep for dep in ext
                if dep in module_bindings
                and dep not in functions
                and dep not in classes
                and dep not in import_names
            )
            unresolved_external_names = sorted(
                set(ext)
                - set(internal_function_dependencies)
                - set(internal_class_dependencies)
                - set(imported_dependencies)
                - set(module_binding_dependencies)
            )

            if unresolved_external_names:
                blockers.append(f"{name}_has_unresolved_external_names_{unresolved_external_names}")

            rows.append({
                "source_path": str(source_path).replace("\\", "/"),
                "symbol": name,
                "kind": "function" if name in functions else "class",
                "is_root": name in roots,
                "signature": signature(node),
                "lineno": node.lineno,
                "end_lineno": getattr(node, "end_lineno", node.lineno),
                "line_count": getattr(node, "end_lineno", node.lineno) - node.lineno + 1,
                "calls": calls_used(node),
                "internal_function_dependencies": internal_function_dependencies,
                "internal_class_dependencies": internal_class_dependencies,
                "imported_dependencies": imported_dependencies,
                "module_binding_dependencies": module_binding_dependencies,
                "unresolved_external_names": unresolved_external_names,
                "source": source_for_node(lines, node),
                **classify_action(source_path, name, name in roots),
            })

    engine_rows = [
        row for row in rows
        if row["source_path"].endswith("expected_value_scoring.py")
    ]

    backtesting_rows = [
        row for row in rows
        if row["source_path"].endswith("walk_forward_expectancy_builder.py")
    ]

    warnings.append("stage37e_is_read_only_no_logic_moved")
    warnings.append("do_not_recompute_walk_forward_expectancy_inside_paper_engine")
    warnings.append("next_stage_should_define_locked_expectancy_snapshot_contract_for_paper_consumption")

    summary = {
        "adapter_type": "expectancy_consumption_source_slice_review_builder",
        "artifact_type": "signalforge_expectancy_consumption_source_slice_review",
        "contract": "expectancy_consumption_source_slice_review",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,
        "closure_group_count": len(closure_rows),
        "reviewed_symbol_count": len(rows),
        "engine_expectancy_consumption_symbol_count": len(engine_rows),
        "backtesting_expectancy_generation_symbol_count": len(backtesting_rows),
        "paper_expectancy_consumption_entrypoint": "signalforge.engines.strategy_selection.expected_value_scoring.build_signalforge_expected_value_scoring",
        "walk_forward_generation_owner": "src/signalforge/backtesting/walk_forward_expectancy_builder.py",
        "paper_order_created": False,
        "live_order_created": False,
        "live_trade_supported": False,
        "next_step": "stage37f_define_locked_expectancy_snapshot_contract",
    }

    summary_path = OUT_DIR / "signalforge_stage37e_expectancy_consumption_source_slice_review_summary.json"
    rows_path = OUT_DIR / "signalforge_stage37e_expectancy_consumption_source_slice_review_rows.jsonl"
    closure_rows_path = OUT_DIR / "signalforge_stage37e_expectancy_consumption_source_slice_review_closure_rows.jsonl"
    md_path = OUT_DIR / "signalforge_stage37e_expectancy_consumption_source_slice_review.md"

    summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    with rows_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, default=str) + "\n")

    with closure_rows_path.open("w", encoding="utf-8") as f:
        for row in closure_rows:
            f.write(json.dumps(row, default=str) + "\n")

    md = [
        "# Stage 37E Expectancy Consumption Source Slice Review",
        "",
        f"- is_ready: {summary['is_ready']}",
        f"- blocker_count: {summary['blocker_count']}",
        f"- closure_group_count: {summary['closure_group_count']}",
        f"- reviewed_symbol_count: {summary['reviewed_symbol_count']}",
        f"- engine_expectancy_consumption_symbol_count: {summary['engine_expectancy_consumption_symbol_count']}",
        f"- backtesting_expectancy_generation_symbol_count: {summary['backtesting_expectancy_generation_symbol_count']}",
        f"- paper_expectancy_consumption_entrypoint: `{summary['paper_expectancy_consumption_entrypoint']}`",
        f"- walk_forward_generation_owner: `{summary['walk_forward_generation_owner']}`",
        f"- paper_order_created: {summary['paper_order_created']}",
        f"- live_order_created: {summary['live_order_created']}",
        f"- live_trade_supported: {summary['live_trade_supported']}",
        "",
        "## Closure Groups",
        "",
        "| source | roots | closure count | closure |",
        "|---|---|---:|---|",
    ]

    for row in closure_rows:
        md.append(
            f"| `{row['source_path']}` | {', '.join(row['root_names'])} | "
            f"{row['closure_count']} | {', '.join(row['closure_names'])} |"
        )

    md.extend([
        "",
        "## Symbol Review",
        "",
        "| symbol | source | ownership | action | target | internal funcs | imports | module bindings | unresolved |",
        "|---|---|---|---|---|---|---|---|---|",
    ])

    for row in rows:
        md.append(
            f"| `{row['symbol']}` | `{row['source_path']}` | {row['ownership']} | "
            f"{row['recommended_action']} | `{row['recommended_target']}` | "
            f"{', '.join(row['internal_function_dependencies'])} | "
            f"{', '.join(row['imported_dependencies'])} | "
            f"{', '.join(row['module_binding_dependencies'])} | "
            f"{', '.join(row['unresolved_external_names'])} |"
        )

    md.extend(["", "## Source Slices", ""])

    for row in rows:
        md.extend([
            f"### `{row['symbol']}`",
            "",
            f"- source: `{row['source_path']}`",
            f"- ownership: {row['ownership']}",
            f"- action: {row['recommended_action']}",
            f"- signature: `{row['signature']}`",
            f"- reason: {row['reason']}",
            "",
            "```python",
            row["source"],
            "```",
            "",
        ])

    if blockers:
        md.extend(["", "## Blockers", ""])
        for blocker in blockers:
            md.append(f"- {blocker}")

    if warnings:
        md.extend(["", "## Warnings", ""])
        for warning in warnings:
            md.append(f"- {warning}")

    md_path.write_text("\n".join(md), encoding="utf-8")

    print("\n--- Stage 37E expectancy consumption source slice review compact ---")
    for key in [
        "is_ready",
        "blocker_count",
        "warning_count",
        "closure_group_count",
        "reviewed_symbol_count",
        "engine_expectancy_consumption_symbol_count",
        "backtesting_expectancy_generation_symbol_count",
        "paper_order_created",
        "live_order_created",
        "live_trade_supported",
    ]:
        print(f"{key}: {summary[key]}")

    print(f"summary_path: {summary_path}")
    print(f"rows_path: {rows_path}")
    print(f"closure_rows_path: {closure_rows_path}")
    print(f"md_path: {md_path}")

    print("\n--- Stage 37E closure groups compact ---")
    print("source\troots\tclosure_count\tclosure")
    for row in closure_rows:
        print(
            f"{row['source_path']}\t{','.join(row['root_names'])}\t"
            f"{row['closure_count']}\t{','.join(row['closure_names'])}"
        )

    print("\n--- Stage 37E symbol review compact ---")
    print("symbol\tsource\townership\taction\ttarget\tinternal_funcs\timports\tmodule_bindings\tunresolved")
    for row in rows:
        print(
            f"{row['symbol']}\t{row['source_path']}\t{row['ownership']}\t"
            f"{row['recommended_action']}\t{row['recommended_target']}\t"
            f"{','.join(row['internal_function_dependencies'])}\t"
            f"{','.join(row['imported_dependencies'])}\t"
            f"{','.join(row['module_binding_dependencies'])}\t"
            f"{','.join(row['unresolved_external_names'])}"
        )

    if blockers:
        print("\n--- Stage 37E blockers ---")
        for blocker in blockers:
            print(blocker)
        raise SystemExit(1)

    if warnings:
        print("\n--- Stage 37E warnings ---")
        for warning in warnings:
            print(warning)


if __name__ == "__main__":
    main()
