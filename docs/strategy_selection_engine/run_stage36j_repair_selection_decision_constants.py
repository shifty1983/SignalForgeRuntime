import ast
import builtins
import importlib
import importlib.machinery
import importlib.util
import json
import py_compile
import sys
from pathlib import Path
from typing import Any


SOURCE_PATH = Path("src/signalforge/backtesting/historical_strategy_selection_rows_builder.py")
ENGINE_PATH = Path("src/signalforge/engines/strategy_selection/selection_decision.py")
OUT_DIR = Path("docs/strategy_selection_engine")
BACKUP_PATH = OUT_DIR / "stage36j_backtesting_backups" / "historical_strategy_selection_rows_builder.py.before_stage36j"

FUNCTIONS_TO_EXTRACT = [
    "_as_float",
    "_as_int",
    "_candidate_id",
    "_is_selectable",
    "_selection_score",
    "_sample_confidence_multiplier",
    "_scope_confidence_multiplier",
    "_confidence_adjusted_selection_score",
    "_rank_tuple",
    "_selection_row",
]

PARITY_FUNCTIONS = [
    "_candidate_id",
    "_is_selectable",
    "_selection_score",
    "_sample_confidence_multiplier",
    "_scope_confidence_multiplier",
    "_confidence_adjusted_selection_score",
    "_rank_tuple",
    "_selection_row",
]

ALLOWED_EXTERNALS = set(dir(builtins)) | set(FUNCTIONS_TO_EXTRACT) | {
    "Any",
    "log10",
    "dict",
    "list",
    "tuple",
    "set",
    "str",
    "int",
    "float",
    "bool",
}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def parse(path: Path) -> ast.Module:
    return ast.parse(read_text(path))


def source_for_node(path: Path, node: ast.AST) -> str:
    lines = read_text(path).splitlines()
    start = getattr(node, "lineno", 1)
    end = getattr(node, "end_lineno", start)
    return "\n".join(lines[start - 1:end])


def function_nodes(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    return {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.col_offset == 0
    }


def binding_names(node: ast.AST) -> set[str]:
    names: set[str] = set()

    if isinstance(node, ast.Assign):
        targets = node.targets
    elif isinstance(node, ast.AnnAssign):
        targets = [node.target]
    elif isinstance(node, ast.AugAssign):
        targets = [node.target]
    else:
        targets = []

    for target in targets:
        for child in ast.walk(target):
            if isinstance(child, ast.Name):
                names.add(child.id)

    if isinstance(node, ast.Import):
        for alias in node.names:
            names.add(alias.asname or alias.name.split(".")[0])

    if isinstance(node, ast.ImportFrom):
        for alias in node.names:
            names.add(alias.asname or alias.name)

    return names


def top_level_bindings(tree: ast.Module) -> set[str]:
    names: set[str] = set()

    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            names.add(node.name)
        else:
            names.update(binding_names(node))

    return names


def function_external_names(node: ast.FunctionDef) -> set[str]:
    used: set[str] = set()
    bound: set[str] = set()

    for arg in node.args.posonlyargs + node.args.args + node.args.kwonlyargs:
        bound.add(arg.arg)

    if node.args.vararg:
        bound.add(node.args.vararg.arg)

    if node.args.kwarg:
        bound.add(node.args.kwarg.arg)

    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            if isinstance(child.ctx, ast.Load):
                used.add(child.id)
            elif isinstance(child.ctx, (ast.Store, ast.Del)):
                bound.add(child.id)

    return used - bound - ALLOWED_EXTERNALS


def first_function_line(path: Path) -> int:
    tree = parse(path)

    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            return node.lineno

    return len(read_text(path).splitlines()) + 1


def load_module_from_any_suffix(module_name: str, path: Path):
    loader = importlib.machinery.SourceFileLoader(module_name, str(path))
    spec = importlib.util.spec_from_loader(module_name, loader)

    if spec is None:
        raise RuntimeError(f"Could not create loader spec for {path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    loader.exec_module(module)
    return module


def fixture_row() -> dict[str, Any]:
    return {
        "candidate_id": "stage36j_candidate_001",
        "as_of_date": "2024-01-02",
        "symbol": "SPY",
        "strategy_name": "long_call",
        "strategy_family": "long_call",
        "final_execution_state": "allowed",
        "execution_state": "allowed",
        "candidate_state": "qualified",
        "is_selectable": True,
        "expectancy_state": "accepted",
        "walk_forward_expectancy_state": "accepted",
        "sample_count": 25,
        "training_sample_count": 25,
        "scope": "symbol_regime_strategy",
        "sample_scope": "symbol_regime_strategy",
        "expectancy_scope": "symbol_regime_strategy",
        "avg_unit_pnl": 2.5,
        "avg_strategy_return": 0.18,
        "expected_value": 0.18,
        "expectancy_score": 0.18,
        "selection_score": 0.18,
        "win_rate": 0.61,
        "profit_factor": 2.4,
        "max_loss": -1.0,
        "max_profit": 3.0,
        "observed_relative_spread": 0.08,
        "max_allowed_relative_spread": 0.10,
    }


def build_args(func, row: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    import inspect

    sig = inspect.signature(func)
    args: list[Any] = []
    kwargs: dict[str, Any] = {}

    for name, param in sig.parameters.items():
        if param.kind in {param.VAR_POSITIONAL, param.VAR_KEYWORD}:
            continue

        if param.default is not param.empty:
            continue

        lowered = name.lower()

        if "row" in lowered or "candidate" in lowered:
            value = row
        elif "rank" in lowered or "index" in lowered or "position" in lowered:
            value = 1
        elif "selected" in lowered:
            value = True
        elif "key" in lowered:
            value = "expected_value"
        elif "default" in lowered:
            value = 0
        else:
            value = row

        if param.kind == param.KEYWORD_ONLY:
            kwargs[name] = value
        else:
            args.append(value)

    return args, kwargs


def call_safely(func, row: dict[str, Any]) -> dict[str, Any]:
    args, kwargs = build_args(func, row)

    try:
        value = func(*args, **kwargs)
        return {
            "ok": True,
            "value": value,
            "error_type": None,
            "error": None,
        }
    except Exception as exc:
        return {
            "ok": False,
            "value": None,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def main() -> None:
    blockers: list[str] = []
    warnings: list[str] = []

    for path in [SOURCE_PATH, ENGINE_PATH, BACKUP_PATH]:
        if not path.exists():
            blockers.append(f"missing_required_path_{path}")

    if blockers:
        raise SystemExit("\n".join(blockers))

    backup_tree = parse(BACKUP_PATH)
    engine_tree = parse(ENGINE_PATH)
    source_tree = parse(SOURCE_PATH)

    backup_functions = function_nodes(backup_tree)
    source_functions = function_nodes(source_tree)

    needed_external_names: set[str] = set()

    for name in FUNCTIONS_TO_EXTRACT:
        node = backup_functions.get(name)

        if node is None:
            blockers.append(f"backup_missing_original_function_{name}")
            continue

        needed_external_names.update(function_external_names(node))

    engine_bound_names = top_level_bindings(engine_tree)
    missing_engine_bindings = sorted(needed_external_names - engine_bound_names)

    backup_binding_sources: list[tuple[set[str], str]] = []

    for node in backup_tree.body:
        names = binding_names(node)
        if names and names.intersection(missing_engine_bindings):
            backup_binding_sources.append((names, source_for_node(BACKUP_PATH, node)))

    copied_binding_names = sorted(set().union(*(names for names, _ in backup_binding_sources)) if backup_binding_sources else set())
    unresolved_bindings = sorted(set(missing_engine_bindings) - set(copied_binding_names))

    if unresolved_bindings:
        blockers.append(f"unresolved_missing_engine_bindings_{unresolved_bindings}")

    if backup_binding_sources:
        engine_text = read_text(ENGINE_PATH)
        insert_before_line = first_function_line(ENGINE_PATH)
        lines = engine_text.splitlines()

        insertion_lines = [
            "",
            "# Extracted module-level bindings required by selection decision helpers.",
        ]

        for _, source in backup_binding_sources:
            insertion_lines.extend(source.splitlines())
            insertion_lines.append("")

        lines[insert_before_line - 1:insert_before_line - 1] = insertion_lines
        write_text(ENGINE_PATH, "\n".join(lines) + "\n")

    compile_rows = []

    for path in [ENGINE_PATH, SOURCE_PATH]:
        try:
            py_compile.compile(str(path), doraise=True)
            compile_rows.append({"path": str(path), "compile_ok": True, "error": None})
        except Exception as exc:
            compile_rows.append({"path": str(path), "compile_ok": False, "error": str(exc)})
            blockers.append(f"compile_failed_{path}: {exc}")

    importlib.invalidate_caches()

    backup_module = load_module_from_any_suffix(
        "stage36j_original_historical_strategy_selection_rows_builder",
        BACKUP_PATH,
    )

    sys.modules.pop("signalforge.backtesting.historical_strategy_selection_rows_builder", None)
    sys.modules.pop("signalforge.engines.strategy_selection.selection_decision", None)

    engine_module = importlib.import_module("signalforge.engines.strategy_selection.selection_decision")
    patched_module = importlib.import_module("signalforge.backtesting.historical_strategy_selection_rows_builder")

    row = fixture_row()
    parity_rows = []

    for name in PARITY_FUNCTIONS:
        original_func = getattr(backup_module, name)
        engine_func = getattr(engine_module, name)
        patched_func = getattr(patched_module, name)

        original_result = call_safely(original_func, row)
        engine_result = call_safely(engine_func, row)
        patched_result = call_safely(patched_func, row)

        original_vs_engine = canonical(original_result) == canonical(engine_result)
        engine_vs_patched = canonical(engine_result) == canonical(patched_result)

        parity_rows.append({
            "function": name,
            "original_vs_engine": original_vs_engine,
            "engine_vs_patched_backtesting_wrapper": engine_vs_patched,
            "original_result": original_result,
            "engine_result": engine_result,
            "patched_result": patched_result,
        })

        if not original_vs_engine:
            blockers.append(f"{name}_original_vs_engine_parity_failed")

        if not engine_vs_patched:
            blockers.append(f"{name}_engine_vs_patched_backtesting_wrapper_parity_failed")

    patched_source_nodes = function_nodes(parse(SOURCE_PATH))
    wrapper_rows = []

    for name in FUNCTIONS_TO_EXTRACT:
        node = patched_source_nodes.get(name)

        if node is None:
            wrapper_rows.append({"function": name, "is_wrapper": False})
            blockers.append(f"backtesting_missing_wrapper_function_{name}")
            continue

        src = source_for_node(SOURCE_PATH, node)
        is_wrapper = "_selection_decision_engine" in src

        wrapper_rows.append({
            "function": name,
            "is_wrapper": is_wrapper,
        })

        if not is_wrapper:
            blockers.append(f"backtesting_function_not_wrapped_to_engine_{name}")

    warnings.append("stage36j_repaired_missing_engine_constants_after_initial_extraction")
    warnings.append("historical_backtesting_wrapper_remains_in_backtesting")
    warnings.append("selection_decision_logic_now_owned_by_engine")
    warnings.append("parity_uses_small_fixture_not_full_historical_replay")

    summary = {
        "adapter_type": "selection_decision_cluster_extraction_repair_builder",
        "artifact_type": "signalforge_selection_decision_cluster_extraction_repair",
        "contract": "selection_decision_cluster_extraction",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,
        "source_path": str(SOURCE_PATH),
        "engine_path": str(ENGINE_PATH),
        "backup_path": str(BACKUP_PATH),
        "needed_external_names": sorted(needed_external_names),
        "missing_engine_bindings_before_repair": missing_engine_bindings,
        "copied_binding_names": copied_binding_names,
        "unresolved_bindings": unresolved_bindings,
        "extracted_function_count": len(FUNCTIONS_TO_EXTRACT),
        "parity_function_count": len(PARITY_FUNCTIONS),
        "compile_rows": compile_rows,
        "wrapper_rows": wrapper_rows,
        "parity_rows": parity_rows,
        "paper_order_created": False,
        "live_order_created": False,
        "live_trade_supported": False,
        "next_step": "stage36k_historical_strategy_selection_replay_parity",
    }

    summary_path = OUT_DIR / "signalforge_stage36j_selection_decision_cluster_extraction_summary.json"
    rows_path = OUT_DIR / "signalforge_stage36j_selection_decision_cluster_extraction_parity_rows.jsonl"
    wrapper_rows_path = OUT_DIR / "signalforge_stage36j_selection_decision_cluster_wrapper_rows.jsonl"
    md_path = OUT_DIR / "signalforge_stage36j_selection_decision_cluster_extraction.md"

    write_text(summary_path, json.dumps(summary, indent=2, default=str))

    with rows_path.open("w", encoding="utf-8") as f:
        for item in parity_rows:
            f.write(json.dumps(item, default=str) + "\n")

    with wrapper_rows_path.open("w", encoding="utf-8") as f:
        for item in wrapper_rows:
            f.write(json.dumps(item, default=str) + "\n")

    md = [
        "# Stage 36J Selection Decision Cluster Extraction",
        "",
        f"- is_ready: {summary['is_ready']}",
        f"- blocker_count: {summary['blocker_count']}",
        f"- source_path: `{summary['source_path']}`",
        f"- engine_path: `{summary['engine_path']}`",
        f"- backup_path: `{summary['backup_path']}`",
        f"- extracted_function_count: {summary['extracted_function_count']}",
        f"- parity_function_count: {summary['parity_function_count']}",
        f"- copied_binding_names: {', '.join(summary['copied_binding_names'])}",
        f"- paper_order_created: {summary['paper_order_created']}",
        f"- live_order_created: {summary['live_order_created']}",
        f"- live_trade_supported: {summary['live_trade_supported']}",
        "",
        "## Wrapper Verification",
        "",
        "| function | backtesting function is wrapper |",
        "|---|---:|",
    ]

    for item in wrapper_rows:
        md.append(f"| `{item['function']}` | {item['is_wrapper']} |")

    md.extend([
        "",
        "## Parity Rows",
        "",
        "| function | original vs engine | engine vs patched wrapper |",
        "|---|---:|---:|",
    ])

    for item in parity_rows:
        md.append(
            f"| `{item['function']}` | {item['original_vs_engine']} | "
            f"{item['engine_vs_patched_backtesting_wrapper']} |"
        )

    if blockers:
        md.extend(["", "## Blockers", ""])
        for blocker in blockers:
            md.append(f"- {blocker}")

    if warnings:
        md.extend(["", "## Warnings", ""])
        for warning in warnings:
            md.append(f"- {warning}")

    write_text(md_path, "\n".join(md))

    print("\n--- Stage 36J repaired selection decision extraction compact ---")
    for key in [
        "is_ready",
        "blocker_count",
        "warning_count",
        "extracted_function_count",
        "parity_function_count",
        "paper_order_created",
        "live_order_created",
        "live_trade_supported",
    ]:
        print(f"{key}: {summary[key]}")

    print(f"source_path: {SOURCE_PATH}")
    print(f"engine_path: {ENGINE_PATH}")
    print(f"backup_path: {BACKUP_PATH}")
    print(f"summary_path: {summary_path}")
    print(f"rows_path: {rows_path}")
    print(f"wrapper_rows_path: {wrapper_rows_path}")
    print(f"md_path: {md_path}")

    print("\n--- Stage 36J binding repair compact ---")
    print(f"needed_external_names: {','.join(summary['needed_external_names'])}")
    print(f"missing_engine_bindings_before_repair: {','.join(summary['missing_engine_bindings_before_repair'])}")
    print(f"copied_binding_names: {','.join(summary['copied_binding_names'])}")
    print(f"unresolved_bindings: {','.join(summary['unresolved_bindings'])}")

    print("\n--- Stage 36J wrapper verification compact ---")
    print("function\tis_wrapper")
    for item in wrapper_rows:
        print(f"{item['function']}\t{item['is_wrapper']}")

    print("\n--- Stage 36J parity rows compact ---")
    print("function\toriginal_vs_engine\tengine_vs_patched_backtesting_wrapper")
    for item in parity_rows:
        print(
            f"{item['function']}\t{item['original_vs_engine']}\t"
            f"{item['engine_vs_patched_backtesting_wrapper']}"
        )

    if blockers:
        print("\n--- Stage 36J blockers ---")
        for blocker in blockers:
            print(blocker)
        raise SystemExit(1)

    if warnings:
        print("\n--- Stage 36J warnings ---")
        for warning in warnings:
            print(warning)


if __name__ == "__main__":
    main()
