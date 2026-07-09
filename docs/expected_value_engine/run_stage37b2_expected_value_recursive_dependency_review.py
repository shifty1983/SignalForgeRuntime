import ast
import builtins
import json
from pathlib import Path
from typing import Any, Dict, List, Set


OUT_DIR = Path("docs/expected_value_engine")
SOURCE_ROOT = Path("src/paper_live_engine/legacy_domain/old_repo/src/expected_value")

ROOTS_BY_FILE = {
    SOURCE_ROOT / "opportunity_score.py": [
        "score_vega",
        "rank_opportunities",
        "passes_minimum_thresholds",
        "filter_opportunities",
    ],
    SOURCE_ROOT / "risk_reward.py": [
        "profit_factor",
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
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.col_offset == 0
    }


def top_level_classes(tree: ast.Module) -> dict[str, ast.ClassDef]:
    return {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.col_offset == 0
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


def classify_target(path: Path, name: str, is_root: bool) -> dict[str, str]:
    file_name = path.name

    if file_name == "risk_reward.py":
        return {
            "recommended_target": "src/signalforge/engines/expected_value/risk_reward.py",
            "promotion_class": "pure_expected_value_metric_cluster",
            "reason": "risk/reward metric helper",
        }

    if name in {"rank_opportunities", "passes_minimum_thresholds"}:
        return {
            "recommended_target": "src/signalforge/engines/strategy_selection/expected_value_scoring.py",
            "promotion_class": "strategy_selection_expected_value_scoring_root",
            "reason": "post-expectancy opportunity ranking/filter helper",
        }

    if file_name == "opportunity_score.py":
        return {
            "recommended_target": "src/signalforge/engines/expected_value/opportunity_score.py",
            "promotion_class": "expected_value_opportunity_scoring_cluster",
            "reason": "shared opportunity scoring dependency",
        }

    return {
        "recommended_target": "manual_review",
        "promotion_class": "manual_review",
        "reason": "unclassified",
    }


def main() -> None:
    blockers: List[str] = []
    warnings: List[str] = []
    rows: List[Dict[str, Any]] = []
    closure_rows: List[Dict[str, Any]] = []

    for source_path, root_names in ROOTS_BY_FILE.items():
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

        missing_roots = [name for name in root_names if name not in functions and name not in classes]
        if missing_roots:
            blockers.append(f"missing_roots_{source_path}_{missing_roots}")

        closure_names = dependency_closure(root_names, functions, classes)

        closure_rows.append({
            "source_path": str(source_path).replace("\\", "/"),
            "root_names": root_names,
            "closure_names": closure_names,
            "closure_count": len(closure_names),
        })

        for name in closure_names:
            node = functions.get(name) or classes.get(name)

            if node is None:
                blockers.append(f"missing_closure_node_{source_path}_{name}")
                continue

            ext = sorted(external_names(node))

            internal_function_dependencies = sorted(
                dep for dep in ext
                if dep in functions
            )

            internal_class_dependencies = sorted(
                dep for dep in ext
                if dep in classes
            )

            imported_dependencies = sorted(
                dep for dep in ext
                if dep in import_names
            )

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

            row = {
                "source_path": str(source_path).replace("\\", "/"),
                "name": name,
                "kind": "function" if name in functions else "class",
                "is_root": name in root_names,
                "signature": signature(node),
                "lineno": node.lineno,
                "end_lineno": getattr(node, "end_lineno", node.lineno),
                "line_count": getattr(node, "end_lineno", node.lineno) - node.lineno + 1,
                "calls": calls_used(node),
                "external_names": ext,
                "internal_function_dependencies": internal_function_dependencies,
                "internal_class_dependencies": internal_class_dependencies,
                "imported_dependencies": imported_dependencies,
                "module_binding_dependencies": module_binding_dependencies,
                "unresolved_external_names": unresolved_external_names,
                "source": source_for_node(lines, node),
                **classify_target(source_path, name, name in root_names),
            }

            rows.append(row)

    opportunity_rows = [
        row for row in rows
        if row["source_path"].endswith("opportunity_score.py")
    ]

    risk_reward_rows = [
        row for row in rows
        if row["source_path"].endswith("risk_reward.py")
    ]

    strategy_selection_roots = [
        row for row in rows
        if row["name"] in {"rank_opportunities", "passes_minimum_thresholds"}
    ]

    warnings.append("stage37b2_is_read_only_no_logic_moved")
    warnings.append("walk_forward_expectancy_builder_remains_backtesting_owned")
    warnings.append("next_stage_should_extract_verified_dependency_clusters_with_parity_tests")

    summary = {
        "adapter_type": "expected_value_recursive_dependency_review_builder",
        "artifact_type": "signalforge_expected_value_recursive_dependency_review",
        "contract": "expected_value_recursive_dependency_review",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,
        "closure_group_count": len(closure_rows),
        "reviewed_symbol_count": len(rows),
        "opportunity_score_closure_count": len(opportunity_rows),
        "risk_reward_closure_count": len(risk_reward_rows),
        "strategy_selection_root_count": len(strategy_selection_roots),
        "walk_forward_owner": "src/signalforge/backtesting/walk_forward_expectancy_builder.py",
        "expected_value_targets": [
            "src/signalforge/engines/expected_value/opportunity_score.py",
            "src/signalforge/engines/expected_value/risk_reward.py",
        ],
        "strategy_selection_target": "src/signalforge/engines/strategy_selection/expected_value_scoring.py",
        "paper_order_created": False,
        "live_order_created": False,
        "live_trade_supported": False,
        "next_step": "stage37c_extract_expected_value_dependency_clusters_with_parity_tests",
    }

    summary_path = OUT_DIR / "signalforge_stage37b2_expected_value_recursive_dependency_review_summary.json"
    rows_path = OUT_DIR / "signalforge_stage37b2_expected_value_recursive_dependency_review_rows.jsonl"
    closure_rows_path = OUT_DIR / "signalforge_stage37b2_expected_value_recursive_dependency_review_closure_rows.jsonl"
    md_path = OUT_DIR / "signalforge_stage37b2_expected_value_recursive_dependency_review.md"

    summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    with rows_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, default=str) + "\n")

    with closure_rows_path.open("w", encoding="utf-8") as f:
        for row in closure_rows:
            f.write(json.dumps(row, default=str) + "\n")

    md = [
        "# Stage 37B2 Expected-Value Recursive Dependency Review",
        "",
        f"- is_ready: {summary['is_ready']}",
        f"- blocker_count: {summary['blocker_count']}",
        f"- closure_group_count: {summary['closure_group_count']}",
        f"- reviewed_symbol_count: {summary['reviewed_symbol_count']}",
        f"- opportunity_score_closure_count: {summary['opportunity_score_closure_count']}",
        f"- risk_reward_closure_count: {summary['risk_reward_closure_count']}",
        f"- strategy_selection_root_count: {summary['strategy_selection_root_count']}",
        f"- walk_forward_owner: `{summary['walk_forward_owner']}`",
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
        "## Symbol Dependency Review",
        "",
        "| symbol | kind | root | target | internal funcs | internal classes | imports | module bindings | unresolved |",
        "|---|---|---:|---|---|---|---|---|---|",
    ])

    for row in rows:
        md.append(
            f"| `{row['name']}` | {row['kind']} | {row['is_root']} | `{row['recommended_target']}` | "
            f"{', '.join(row['internal_function_dependencies'])} | "
            f"{', '.join(row['internal_class_dependencies'])} | "
            f"{', '.join(row['imported_dependencies'])} | "
            f"{', '.join(row['module_binding_dependencies'])} | "
            f"{', '.join(row['unresolved_external_names'])} |"
        )

    md.extend(["", "## Source Slices", ""])

    for row in rows:
        md.extend([
            f"### `{row['name']}`",
            "",
            f"- source: `{row['source_path']}`",
            f"- kind: {row['kind']}",
            f"- target: `{row['recommended_target']}`",
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

    print("\n--- Stage 37B2 expected-value recursive dependency review compact ---")
    for key in [
        "is_ready",
        "blocker_count",
        "warning_count",
        "closure_group_count",
        "reviewed_symbol_count",
        "opportunity_score_closure_count",
        "risk_reward_closure_count",
        "strategy_selection_root_count",
        "paper_order_created",
        "live_order_created",
        "live_trade_supported",
    ]:
        print(f"{key}: {summary[key]}")

    print(f"summary_path: {summary_path}")
    print(f"rows_path: {rows_path}")
    print(f"closure_rows_path: {closure_rows_path}")
    print(f"md_path: {md_path}")

    print("\n--- Stage 37B2 closure groups compact ---")
    print("source\troots\tclosure_count\tclosure")
    for row in closure_rows:
        print(
            f"{row['source_path']}\t{','.join(row['root_names'])}\t"
            f"{row['closure_count']}\t{','.join(row['closure_names'])}"
        )

    print("\n--- Stage 37B2 symbol dependency compact ---")
    print("symbol\tkind\troot\ttarget\tinternal_funcs\tinternal_classes\timports\tmodule_bindings\tunresolved")
    for row in rows:
        print(
            f"{row['name']}\t{row['kind']}\t{row['is_root']}\t{row['recommended_target']}\t"
            f"{','.join(row['internal_function_dependencies'])}\t"
            f"{','.join(row['internal_class_dependencies'])}\t"
            f"{','.join(row['imported_dependencies'])}\t"
            f"{','.join(row['module_binding_dependencies'])}\t"
            f"{','.join(row['unresolved_external_names'])}"
        )

    if blockers:
        print("\n--- Stage 37B2 blockers ---")
        for blocker in blockers:
            print(blocker)
        raise SystemExit(1)

    if warnings:
        print("\n--- Stage 37B2 warnings ---")
        for warning in warnings:
            print(warning)


if __name__ == "__main__":
    main()
