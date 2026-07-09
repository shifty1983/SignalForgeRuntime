import ast
import importlib
import importlib.util
import json
import py_compile
import shutil
import sys
from pathlib import Path
from typing import Any


SOURCE_PATH = Path("src/signalforge/backtesting/historical_strategy_candidate_rows_builder.py")
ENGINE_PATH = Path("src/signalforge/engines/strategy_selection/candidate_filter_decision.py")
OUT_DIR = Path("docs/strategy_selection_engine")
BACKUP_DIR = OUT_DIR / "stage36o_backtesting_backups"
BACKUP_PATH = BACKUP_DIR / "historical_strategy_candidate_rows_builder.py.before_stage36o.py"

ENGINE_ALIAS_IMPORT = "from signalforge.engines.strategy_selection import candidate_filter_decision as _candidate_filter_decision_engine"

FUNCTIONS_TO_EXTRACT = [
    "_normalise_text",
    "_strategy_family_status_aliases",
    "_strategy_family_statuses",
    "_strategy_family_status",
    "_strategy_family_gate_block_reasons",
    "_as_dict",
    "_as_list",
    "_research_context_from_decision_row",
    "_eligibility",
    "_flag_is_true",
    "_nested_state",
    "_normalise_symbol",
    "_parse_option_behavior",
    "_decision_row_block_reasons",
    "_strategy_definition_block_reasons",
    "_has_term_structure_behavior",
    "_has_underlying_position",
    "_strategy_context_block_reasons",
    "_candidate_state",
]

MODULE_BINDINGS_TO_COPY = [
    "MISSING_VALUE",
]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def parse(path: Path) -> ast.Module:
    return ast.parse(read_text(path))


def get_function_nodes(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    return {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.col_offset == 0
    }


def source_for_node(lines: list[str], node: ast.AST) -> str:
    start = getattr(node, "lineno", 1)
    end = getattr(node, "end_lineno", start)
    return "\n".join(lines[start - 1:end])


def binding_names(node: ast.AST) -> set[str]:
    names: set[str] = set()

    if isinstance(node, ast.Assign):
        targets = node.targets
    elif isinstance(node, ast.AnnAssign):
        targets = [node.target]
    else:
        targets = []

    for target in targets:
        for child in ast.walk(target):
            if isinstance(child, ast.Name):
                names.add(child.id)

    return names


def binding_sources(tree: ast.Module, lines: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}

    for node in tree.body:
        names = binding_names(node)

        if not names:
            continue

        src = source_for_node(lines, node)

        for name in names:
            result[name] = src

    return result


def call_argument_string(args: ast.arguments) -> str:
    pieces: list[str] = []

    for arg in list(args.posonlyargs) + list(args.args):
        pieces.append(arg.arg)

    if args.vararg:
        pieces.append("*" + args.vararg.arg)

    for arg in args.kwonlyargs:
        pieces.append(f"{arg.arg}={arg.arg}")

    if args.kwarg:
        pieces.append("**" + args.kwarg.arg)

    return ", ".join(pieces)


def wrapper_source(node: ast.FunctionDef) -> str:
    signature = ast.unparse(node.args)
    call_args = call_argument_string(node.args)

    return (
        f"def {node.name}({signature}):\n"
        f"    return _candidate_filter_decision_engine.{node.name}({call_args})\n"
    )


def find_import_insert_line(tree: ast.Module) -> int:
    body = list(tree.body)

    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
        start_index = 1
        insert_after = getattr(body[0], "end_lineno", body[0].lineno)
    else:
        start_index = 0
        insert_after = 0

    for node in body[start_index:]:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            insert_after = getattr(node, "end_lineno", node.lineno)
            continue
        break

    return insert_after


def patch_backtesting_file(original_text: str, tree: ast.Module, nodes: dict[str, ast.FunctionDef]) -> str:
    lines = original_text.splitlines()

    replacements = []

    for name in FUNCTIONS_TO_EXTRACT:
        node = nodes[name]
        start = node.lineno
        end = getattr(node, "end_lineno", node.lineno)
        replacements.append((start, end, wrapper_source(node).splitlines()))

    for start, end, new_lines in sorted(replacements, key=lambda item: item[0], reverse=True):
        lines[start - 1:end] = new_lines

    patched = "\n".join(lines) + "\n"

    if ENGINE_ALIAS_IMPORT not in patched:
        patched_tree = ast.parse(patched)
        insert_after = find_import_insert_line(patched_tree)
        patched_lines = patched.splitlines()
        patched_lines.insert(insert_after, ENGINE_ALIAS_IMPORT)
        patched = "\n".join(patched_lines) + "\n"

    return patched


def build_engine_source(original_tree: ast.Module, original_lines: list[str], nodes: dict[str, ast.FunctionDef]) -> str:
    bindings = binding_sources(original_tree, original_lines)

    missing_bindings = [
        name for name in MODULE_BINDINGS_TO_COPY
        if name not in bindings
    ]

    if missing_bindings:
        raise RuntimeError(f"Missing module bindings to copy: {missing_bindings}")

    binding_text = "\n".join(bindings[name] for name in MODULE_BINDINGS_TO_COPY)

    function_text = "\n\n".join(
        source_for_node(original_lines, nodes[name])
        for name in FUNCTIONS_TO_EXTRACT
    )

    return "\n".join([
        '"""Reusable candidate-filter and block-reason decision helpers.',
        "",
        "Backtesting owns historical replay orchestration.",
        "This module owns reusable candidate filter/block-reason logic used by",
        "historical replay, paper candidate evaluation, and future live evaluation.",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "import json",
        "from typing import Any, Dict, List, Mapping, Sequence",
        "",
        binding_text,
        "",
        function_text,
        "",
    ])


def load_module_from_path(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)

    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module spec for {path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def fixture_decision_row() -> dict[str, Any]:
    return {
        "as_of_date": "2024-01-02",
        "symbol": "SPY",
        "underlying_symbol": "SPY",
        "strategy_family": "long_call",
        "strategy_name": "long_call",
        "data_state": "complete",
        "decision_state": "candidate",
        "regime": "bullish",
        "asset_behavior_state": "trend_up",
        "option_behavior_state": "complete",
        "strategy_family_eligibility": {
            "long_call": {
                "is_eligible": True,
                "eligible": True,
                "state": "eligible",
                "status": "eligible",
                "block_reasons": [],
            }
        },
        "strategy_family_statuses": {
            "long_call": "eligible",
        },
        "strategy_family_status": "eligible",
        "eligibility": {
            "has_option_behavior": True,
            "has_contract_outcome": True,
            "is_tradable": True,
            "tradable": True,
            "has_underlying_position": False,
            "has_term_structure_behavior": True,
        },
        "option_behavior": {
            "state": "complete",
            "term_structure": {
                "state": "available",
            },
            "underlying_position": None,
        },
        "research": {
            "regime": "bullish",
            "asset_behavior": "trend_up",
            "option_behavior": "complete",
        },
    }


def fixture_strategy_definition() -> dict[str, Any]:
    return {
        "strategy_name": "long_call",
        "strategy_family": "long_call",
        "enabled": True,
        "is_enabled": True,
        "tradable": True,
        "requires_option_behavior": True,
        "requires_contract_outcome": True,
        "block_reasons": [],
    }


def fixture_strategy_context() -> dict[str, Any]:
    return {
        "strategy_name": "long_call",
        "strategy_family": "long_call",
        "symbol": "SPY",
        "decision_row": fixture_decision_row(),
        "research_context": {
            "regime": "bullish",
            "asset_behavior": "trend_up",
            "option_behavior": "complete",
        },
        "eligibility": {
            "has_option_behavior": True,
            "has_contract_outcome": True,
            "is_tradable": True,
            "tradable": True,
            "has_underlying_position": False,
            "has_term_structure_behavior": True,
        },
    }


def sample_value_for_param(param_name: str) -> Any:
    lowered = param_name.lower()

    if "strategy_definition" in lowered or "definition" in lowered:
        return fixture_strategy_definition()

    if "strategy_context" in lowered or "context" in lowered:
        return fixture_strategy_context()

    if "decision_row" in lowered or lowered == "row":
        return fixture_decision_row()

    if "strategy_family" in lowered or "family" in lowered:
        return "long_call"

    if "symbol" in lowered:
        return "SPY"

    if "option_behavior" in lowered:
        return fixture_decision_row()["option_behavior"]

    if "eligibility" in lowered:
        return fixture_decision_row()["eligibility"]

    if "status" in lowered:
        return "eligible"

    if "statuses" in lowered:
        return {"long_call": "eligible"}

    if "value" in lowered or "text" in lowered or "raw" in lowered:
        return "eligible"

    if "reasons" in lowered:
        return []

    return fixture_decision_row()


def build_args(func) -> tuple[list[Any], dict[str, Any]]:
    import inspect

    sig = inspect.signature(func)
    args: list[Any] = []
    kwargs: dict[str, Any] = {}

    for name, param in sig.parameters.items():
        if param.kind in {param.VAR_POSITIONAL, param.VAR_KEYWORD}:
            continue

        if param.default is not param.empty:
            continue

        value = sample_value_for_param(name)

        if param.kind == param.KEYWORD_ONLY:
            kwargs[name] = value
        else:
            args.append(value)

    return args, kwargs


def call_safely(func) -> dict[str, Any]:
    args, kwargs = build_args(func)

    try:
        value = func(*args, **kwargs)
        return {
            "ok": True,
            "value": value,
            "error_type": None,
            "error": None,
            "args_repr": repr(args),
            "kwargs_repr": repr(kwargs),
        }
    except Exception as exc:
        return {
            "ok": False,
            "value": None,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "args_repr": repr(args),
            "kwargs_repr": repr(kwargs),
        }


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def main() -> None:
    blockers: list[str] = []
    warnings: list[str] = []

    if not SOURCE_PATH.exists():
        raise SystemExit(f"Missing source file: {SOURCE_PATH}")

    original_text = read_text(SOURCE_PATH)
    original_tree = ast.parse(original_text)
    original_lines = original_text.splitlines()
    function_nodes = get_function_nodes(original_tree)

    missing = [name for name in FUNCTIONS_TO_EXTRACT if name not in function_nodes]

    if missing:
        raise SystemExit(f"Missing functions to extract: {missing}")

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    write_text(BACKUP_PATH, original_text)

    engine_source = build_engine_source(original_tree, original_lines, function_nodes)
    write_text(ENGINE_PATH, engine_source)

    patched_text = patch_backtesting_file(original_text, original_tree, function_nodes)
    write_text(SOURCE_PATH, patched_text)

    compile_rows = []

    for path in [ENGINE_PATH, SOURCE_PATH]:
        try:
            py_compile.compile(str(path), doraise=True)
            compile_rows.append({"path": str(path), "compile_ok": True, "error": None})
        except Exception as exc:
            compile_rows.append({"path": str(path), "compile_ok": False, "error": str(exc)})
            blockers.append(f"compile_failed_{path}: {exc}")

    importlib.invalidate_caches()

    backup_module = load_module_from_path(
        "stage36o_original_historical_strategy_candidate_rows_builder",
        BACKUP_PATH,
    )

    sys.modules.pop("signalforge.backtesting.historical_strategy_candidate_rows_builder", None)
    sys.modules.pop("signalforge.engines.strategy_selection.candidate_filter_decision", None)

    engine_module = importlib.import_module("signalforge.engines.strategy_selection.candidate_filter_decision")
    patched_module = importlib.import_module("signalforge.backtesting.historical_strategy_candidate_rows_builder")

    parity_rows = []

    for name in FUNCTIONS_TO_EXTRACT:
        original_func = getattr(backup_module, name)
        engine_func = getattr(engine_module, name)
        patched_func = getattr(patched_module, name)

        original_result = call_safely(original_func)
        engine_result = call_safely(engine_func)
        patched_result = call_safely(patched_func)

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

    patched_nodes = get_function_nodes(parse(SOURCE_PATH))
    wrapper_rows = []

    for name in FUNCTIONS_TO_EXTRACT:
        node = patched_nodes.get(name)

        if node is None:
            wrapper_rows.append({"function": name, "is_wrapper": False})
            blockers.append(f"{name}_backtesting_wrapper_missing")
            continue

        src = source_for_node(read_text(SOURCE_PATH).splitlines(), node)
        is_wrapper = "_candidate_filter_decision_engine" in src

        wrapper_rows.append({
            "function": name,
            "is_wrapper": is_wrapper,
        })

        if not is_wrapper:
            blockers.append(f"{name}_backtesting_function_not_wrapped_to_engine")

    warnings.append("stage36o_extracts_candidate_filter_decision_logic_only")
    warnings.append("historical_candidate_row_builder_remains_in_backtesting")
    warnings.append("stage36o_parity_uses_function_fixture_full_replay_parity_should_follow")

    summary = {
        "adapter_type": "candidate_filter_decision_cluster_extraction_builder",
        "artifact_type": "signalforge_candidate_filter_decision_cluster_extraction",
        "contract": "candidate_filter_decision_cluster_extraction",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,
        "source_path": str(SOURCE_PATH),
        "engine_path": str(ENGINE_PATH),
        "backup_path": str(BACKUP_PATH),
        "extracted_function_count": len(FUNCTIONS_TO_EXTRACT),
        "module_bindings_copied": MODULE_BINDINGS_TO_COPY,
        "compile_rows": compile_rows,
        "wrapper_rows": wrapper_rows,
        "parity_rows": parity_rows,
        "paper_order_created": False,
        "live_order_created": False,
        "live_trade_supported": False,
        "next_step": "stage36p_historical_candidate_rows_replay_parity",
    }

    summary_path = OUT_DIR / "signalforge_stage36o_candidate_filter_decision_cluster_extraction_summary.json"
    parity_rows_path = OUT_DIR / "signalforge_stage36o_candidate_filter_decision_cluster_parity_rows.jsonl"
    wrapper_rows_path = OUT_DIR / "signalforge_stage36o_candidate_filter_decision_cluster_wrapper_rows.jsonl"
    md_path = OUT_DIR / "signalforge_stage36o_candidate_filter_decision_cluster_extraction.md"

    write_text(summary_path, json.dumps(summary, indent=2, default=str))

    with parity_rows_path.open("w", encoding="utf-8") as f:
        for item in parity_rows:
            f.write(json.dumps(item, default=str) + "\n")

    with wrapper_rows_path.open("w", encoding="utf-8") as f:
        for item in wrapper_rows:
            f.write(json.dumps(item, default=str) + "\n")

    md = [
        "# Stage 36O Candidate Filter Decision Cluster Extraction",
        "",
        f"- is_ready: {summary['is_ready']}",
        f"- blocker_count: {summary['blocker_count']}",
        f"- source_path: `{summary['source_path']}`",
        f"- engine_path: `{summary['engine_path']}`",
        f"- backup_path: `{summary['backup_path']}`",
        f"- extracted_function_count: {summary['extracted_function_count']}",
        f"- module_bindings_copied: {', '.join(summary['module_bindings_copied'])}",
        f"- paper_order_created: {summary['paper_order_created']}",
        f"- live_order_created: {summary['live_order_created']}",
        f"- live_trade_supported: {summary['live_trade_supported']}",
        "",
        "## Extracted Functions",
        "",
    ]

    for name in FUNCTIONS_TO_EXTRACT:
        md.append(f"- `{name}`")

    md.extend([
        "",
        "## Wrapper Verification",
        "",
        "| function | backtesting function is wrapper |",
        "|---|---:|",
    ])

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

    print("\n--- Stage 36O candidate filter decision cluster extraction compact ---")
    for key in [
        "is_ready",
        "blocker_count",
        "warning_count",
        "extracted_function_count",
        "paper_order_created",
        "live_order_created",
        "live_trade_supported",
    ]:
        print(f"{key}: {summary[key]}")

    print(f"source_path: {SOURCE_PATH}")
    print(f"engine_path: {ENGINE_PATH}")
    print(f"backup_path: {BACKUP_PATH}")
    print(f"summary_path: {summary_path}")
    print(f"parity_rows_path: {parity_rows_path}")
    print(f"wrapper_rows_path: {wrapper_rows_path}")
    print(f"md_path: {md_path}")

    print("\n--- Stage 36O wrapper verification compact ---")
    print("function\tis_wrapper")
    for item in wrapper_rows:
        print(f"{item['function']}\t{item['is_wrapper']}")

    print("\n--- Stage 36O parity rows compact ---")
    print("function\toriginal_vs_engine\tengine_vs_patched_backtesting_wrapper")
    for item in parity_rows:
        print(
            f"{item['function']}\t{item['original_vs_engine']}\t"
            f"{item['engine_vs_patched_backtesting_wrapper']}"
        )

    if blockers:
        print("\n--- Stage 36O blockers ---")
        for blocker in blockers:
            print(blocker)
        raise SystemExit(1)

    if warnings:
        print("\n--- Stage 36O warnings ---")
        for warning in warnings:
            print(warning)


if __name__ == "__main__":
    main()
