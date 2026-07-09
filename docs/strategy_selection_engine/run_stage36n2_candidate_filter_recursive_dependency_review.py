import ast
import builtins
import json
from pathlib import Path
from typing import Any, Dict, List, Set


OUT_DIR = Path("docs/strategy_selection_engine")
SOURCE_PATH = Path("src/signalforge/backtesting/historical_strategy_candidate_rows_builder.py")
PROPOSED_ENGINE_TARGET = "src/signalforge/engines/strategy_selection/candidate_filter_decision.py"

ROOT_TARGET_FUNCTIONS = [
    "_strategy_family_gate_block_reasons",
    "_research_context_from_decision_row",
    "_decision_row_block_reasons",
    "_strategy_definition_block_reasons",
    "_strategy_context_block_reasons",
    "_candidate_state",
]

OPTIONAL_REVIEW_FUNCTIONS = [
    "_alignment_research_fields",
]

BUILTIN_NAMES = set(dir(builtins)) | {"True", "False", "None"}


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


def imports_in_file(tree: ast.Module) -> list[dict[str, Any]]:
    rows = []

    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                rows.append({
                    "kind": "import",
                    "module": alias.name,
                    "name": alias.asname or alias.name.split(".")[0],
                    "source": ast.unparse(node),
                })

        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                rows.append({
                    "kind": "from_import",
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
        if isinstance(node, ast.FunctionDef):
            names.add(node.name)

        elif isinstance(node, ast.ClassDef):
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


def module_binding_sources(tree: ast.Module, lines: list[str]) -> dict[str, str]:
    sources: dict[str, str] = {}

    for node in tree.body:
        names = set()

        if isinstance(node, ast.Assign):
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

        if names:
            src = source_for_node(lines, node)
            for name in names:
                sources[name] = src

    return sources


def names_bound_in_function(node: ast.FunctionDef) -> set[str]:
    names = set()

    for arg in node.args.posonlyargs + node.args.args + node.args.kwonlyargs:
        names.add(arg.arg)

    if node.args.vararg:
        names.add(node.args.vararg.arg)

    if node.args.kwarg:
        names.add(node.args.kwarg.arg)

    for child in ast.walk(node):
        if isinstance(child, ast.Name) and isinstance(child.ctx, (ast.Store, ast.Del)):
            names.add(child.id)

        elif isinstance(child, ast.ExceptHandler) and child.name:
            names.add(child.name)

        elif isinstance(child, ast.comprehension):
            for target_child in ast.walk(child.target):
                if isinstance(target_child, ast.Name):
                    names.add(target_child.id)

    return names


def names_loaded_in_function(node: ast.FunctionDef) -> set[str]:
    names = set()

    for child in ast.walk(node):
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
            names.add(child.id)

    return names


def external_names(node: ast.FunctionDef) -> set[str]:
    return names_loaded_in_function(node) - names_bound_in_function(node) - BUILTIN_NAMES


def calls_used(node: ast.FunctionDef) -> list[str]:
    calls = set()

    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            fn = child.func
            if isinstance(fn, ast.Name):
                calls.add(fn.id)
            elif isinstance(fn, ast.Attribute):
                calls.add(fn.attr)

    return sorted(calls)


def function_signature(node: ast.FunctionDef) -> str:
    return f"def {node.name}({ast.unparse(node.args)}):"


def dependency_closure(root_names: list[str], functions: dict[str, ast.FunctionDef]) -> list[str]:
    seen: Set[str] = set()
    ordered: list[str] = []

    def visit(name: str) -> None:
        if name in seen:
            return
        seen.add(name)

        node = functions.get(name)
        if node is None:
            return

        deps = sorted(dep for dep in external_names(node) if dep in functions)

        for dep in deps:
            visit(dep)

        ordered.append(name)

    for root in root_names:
        visit(root)

    return ordered


def classify_action(name: str, root_targets: set[str], optional_review: set[str]) -> str:
    if name in root_targets and name == "_candidate_state":
        return "manual_review_include_if_candidate_state_is_reusable_decision"

    if name in root_targets:
        return "extract_root_candidate_filter_decision"

    if name in optional_review:
        return "optional_review_helper_not_required_by_root_closure"

    return "extract_required_candidate_filter_helper"


def main() -> None:
    blockers: List[str] = []
    warnings: List[str] = []
    rows: List[Dict[str, Any]] = []

    if not SOURCE_PATH.exists():
        blockers.append(f"missing_source_path_{SOURCE_PATH}")
        tree = ast.Module(body=[], type_ignores=[])
        lines = []
    else:
        text = read_text(SOURCE_PATH)
        lines = text.splitlines()
        tree = ast.parse(text)

    functions = top_level_functions(tree)
    import_rows = imports_in_file(tree)
    import_names = {row["name"] for row in import_rows}
    binding_names = module_binding_names(tree)
    binding_sources = module_binding_sources(tree, lines)

    missing_roots = [name for name in ROOT_TARGET_FUNCTIONS if name not in functions]
    if missing_roots:
        blockers.append(f"missing_root_target_functions_{missing_roots}")

    closure_names = dependency_closure(ROOT_TARGET_FUNCTIONS, functions)

    review_names = list(dict.fromkeys(closure_names + OPTIONAL_REVIEW_FUNCTIONS))

    for name in review_names:
        node = functions.get(name)

        if node is None:
            blockers.append(f"missing_review_function_{name}")
            continue

        ext = sorted(external_names(node))

        internal_function_dependencies = sorted(
            value for value in ext
            if value in functions
        )

        imported_dependencies = sorted(
            value for value in ext
            if value in import_names
        )

        module_binding_dependencies = sorted(
            value for value in ext
            if value in binding_names
            and value not in functions
            and value not in import_names
        )

        unresolved_external_names = sorted(
            set(ext)
            - set(internal_function_dependencies)
            - set(imported_dependencies)
            - set(module_binding_dependencies)
        )

        if unresolved_external_names:
            blockers.append(f"{name}_has_unresolved_external_names_{unresolved_external_names}")

        action = classify_action(
            name=name,
            root_targets=set(ROOT_TARGET_FUNCTIONS),
            optional_review=set(OPTIONAL_REVIEW_FUNCTIONS),
        )

        rows.append({
            "source_path": str(SOURCE_PATH).replace("\\", "/"),
            "function": name,
            "signature": function_signature(node),
            "lineno": node.lineno,
            "end_lineno": getattr(node, "end_lineno", node.lineno),
            "line_count": getattr(node, "end_lineno", node.lineno) - node.lineno + 1,
            "proposed_engine_target": PROPOSED_ENGINE_TARGET,
            "proposed_action": action,
            "is_root_target": name in ROOT_TARGET_FUNCTIONS,
            "is_optional_review": name in OPTIONAL_REVIEW_FUNCTIONS,
            "calls": calls_used(node),
            "external_names": ext,
            "internal_function_dependencies": internal_function_dependencies,
            "imported_dependencies": imported_dependencies,
            "module_binding_dependencies": module_binding_dependencies,
            "unresolved_external_names": unresolved_external_names,
            "source": source_for_node(lines, node),
        })

    all_module_binding_dependencies = sorted({
        dep
        for row in rows
        for dep in row["module_binding_dependencies"]
    })

    required_imports = sorted({
        dep
        for row in rows
        for dep in row["imported_dependencies"]
    })

    required_function_names = [
        row["function"]
        for row in rows
        if row["proposed_action"] in {
            "extract_root_candidate_filter_decision",
            "extract_required_candidate_filter_helper",
            "manual_review_include_if_candidate_state_is_reusable_decision",
        }
    ]

    optional_function_names = [
        row["function"]
        for row in rows
        if row["proposed_action"] == "optional_review_helper_not_required_by_root_closure"
    ]

    warnings.append("stage36n2_is_read_only_no_logic_moved")
    warnings.append("historical_candidate_row_builder_remains_in_backtesting")
    warnings.append("candidate_filter_extraction_must_include_full_dependency_closure")

    summary = {
        "adapter_type": "candidate_filter_recursive_dependency_review_builder",
        "artifact_type": "signalforge_candidate_filter_recursive_dependency_review",
        "contract": "candidate_filter_recursive_dependency_review",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,
        "source_path": str(SOURCE_PATH),
        "proposed_engine_target": PROPOSED_ENGINE_TARGET,
        "root_target_count": len(ROOT_TARGET_FUNCTIONS),
        "dependency_closure_count": len(closure_names),
        "reviewed_function_count": len(rows),
        "required_function_count": len(required_function_names),
        "optional_function_count": len(optional_function_names),
        "required_function_names": required_function_names,
        "optional_function_names": optional_function_names,
        "required_import_names": required_imports,
        "module_binding_dependencies": all_module_binding_dependencies,
        "module_binding_sources": {
            name: binding_sources.get(name)
            for name in all_module_binding_dependencies
        },
        "paper_order_created": False,
        "live_order_created": False,
        "live_trade_supported": False,
        "next_step": "stage36o_extract_candidate_filter_decision_cluster_with_parity_test",
    }

    summary_path = OUT_DIR / "signalforge_stage36n2_candidate_filter_recursive_dependency_review_summary.json"
    rows_path = OUT_DIR / "signalforge_stage36n2_candidate_filter_recursive_dependency_review_rows.jsonl"
    md_path = OUT_DIR / "signalforge_stage36n2_candidate_filter_recursive_dependency_review.md"

    summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    with rows_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, default=str) + "\n")

    md = [
        "# Stage 36N2 Candidate Filter Recursive Dependency Review",
        "",
        f"- is_ready: {summary['is_ready']}",
        f"- blocker_count: {summary['blocker_count']}",
        f"- source_path: `{summary['source_path']}`",
        f"- proposed_engine_target: `{summary['proposed_engine_target']}`",
        f"- root_target_count: {summary['root_target_count']}",
        f"- dependency_closure_count: {summary['dependency_closure_count']}",
        f"- required_function_count: {summary['required_function_count']}",
        f"- optional_function_count: {summary['optional_function_count']}",
        f"- required_import_names: {', '.join(summary['required_import_names'])}",
        f"- module_binding_dependencies: {', '.join(summary['module_binding_dependencies'])}",
        f"- paper_order_created: {summary['paper_order_created']}",
        f"- live_order_created: {summary['live_order_created']}",
        f"- live_trade_supported: {summary['live_trade_supported']}",
        "",
        "## Required Function Closure",
        "",
    ]

    for name in required_function_names:
        md.append(f"- `{name}`")

    if optional_function_names:
        md.extend(["", "## Optional Review Functions", ""])
        for name in optional_function_names:
            md.append(f"- `{name}`")

    md.extend([
        "",
        "## Function Dependency Review",
        "",
        "| function | action | internal deps | imported deps | module bindings | unresolved |",
        "|---|---|---|---|---|---|",
    ])

    for row in rows:
        md.append(
            f"| `{row['function']}` | {row['proposed_action']} | "
            f"{', '.join(row['internal_function_dependencies'])} | "
            f"{', '.join(row['imported_dependencies'])} | "
            f"{', '.join(row['module_binding_dependencies'])} | "
            f"{', '.join(row['unresolved_external_names'])} |"
        )

    md.extend(["", "## Source Slices", ""])

    for row in rows:
        md.extend([
            f"### `{row['function']}`",
            "",
            f"- action: {row['proposed_action']}",
            f"- lines: {row['lineno']}-{row['end_lineno']}",
            f"- signature: `{row['signature']}`",
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

    print("\n--- Stage 36N2 candidate filter recursive dependency review compact ---")
    for key in [
        "is_ready",
        "blocker_count",
        "warning_count",
        "root_target_count",
        "dependency_closure_count",
        "reviewed_function_count",
        "required_function_count",
        "optional_function_count",
        "paper_order_created",
        "live_order_created",
        "live_trade_supported",
    ]:
        print(f"{key}: {summary[key]}")

    print(f"summary_path: {summary_path}")
    print(f"rows_path: {rows_path}")
    print(f"md_path: {md_path}")

    print("\n--- Stage 36N2 required function names ---")
    for name in required_function_names:
        print(name)

    print("\n--- Stage 36N2 optional function names ---")
    for name in optional_function_names:
        print(name)

    print("\n--- Stage 36N2 imports and module bindings ---")
    print(f"required_import_names: {','.join(required_imports)}")
    print(f"module_binding_dependencies: {','.join(all_module_binding_dependencies)}")

    print("\n--- Stage 36N2 function dependency compact ---")
    print("function\taction\tinternal_deps\timported_deps\tmodule_bindings\tunresolved")
    for row in rows:
        print(
            f"{row['function']}\t{row['proposed_action']}\t"
            f"{','.join(row['internal_function_dependencies'])}\t"
            f"{','.join(row['imported_dependencies'])}\t"
            f"{','.join(row['module_binding_dependencies'])}\t"
            f"{','.join(row['unresolved_external_names'])}"
        )

    if blockers:
        print("\n--- Stage 36N2 blockers ---")
        for blocker in blockers:
            print(blocker)
        raise SystemExit(1)

    if warnings:
        print("\n--- Stage 36N2 warnings ---")
        for warning in warnings:
            print(warning)


if __name__ == "__main__":
    main()
