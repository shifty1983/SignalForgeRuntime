import ast
import json
from pathlib import Path
from typing import Any, Dict, List


OUT_DIR = Path("docs/expected_value_engine")

LEGACY_EXPECTED_VALUE_DIRS = [
    Path("src/paper_live_engine/legacy_domain/old_repo/src/expected_value"),
    Path("legacy/source_snapshots/v3_2_2/old_repo/src/expected_value"),
]

CURRENT_EXPECTED_VALUE_ENGINE_DIRS = [
    Path("src/signalforge/engines/expected_value"),
    Path("src/signalforge/engines/strategy_selection"),
]

BACKTESTING_WALK_FORWARD_FILES = [
    Path("src/signalforge/backtesting/walk_forward_expectancy_builder.py"),
    Path("src/signalforge/backtesting/walk_forward_expectancy_cli.py"),
]

PROMOTE_EXPECTED_VALUE_TERMS = [
    "expected_value",
    "expectancy",
    "ev",
    "win_rate",
    "loss_rate",
    "profit_factor",
    "avg_win",
    "avg_loss",
    "gross_profit",
    "gross_loss",
    "sample_count",
    "confidence",
    "multiplier",
    "edge",
    "score",
    "cohort",
    "stats",
    "estimate",
    "threshold",
]

STRATEGY_SELECTION_TERMS = [
    "rank",
    "ranking",
    "selection",
    "selector",
    "selected",
    "candidate",
    "strategy",
    "tie_break",
    "sort",
]

BACKTESTING_ORCHESTRATION_TERMS = [
    "walk_forward",
    "training",
    "window",
    "as_of",
    "historical",
    "replay",
    "date",
    "artifact",
    "json",
    "jsonl",
    "path",
    "output_dir",
    "summary",
    "rows",
    "load",
    "write",
    "main",
    "cli",
]

IO_CALLS = {
    "open",
    "read_text",
    "write_text",
    "mkdir",
    "loads",
    "dumps",
    "exists",
    "glob",
    "rglob",
    "parse_args",
    "print",
}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def py_files(root: Path) -> List[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*.py") if path.is_file())


def source_for_node(lines: list[str], node: ast.AST) -> str:
    start = getattr(node, "lineno", 1)
    end = getattr(node, "end_lineno", start)
    return "\n".join(lines[start - 1:end])


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


def imports_used(tree: ast.Module) -> list[str]:
    imports = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")

    return sorted(imports)


def score_terms(text: str, terms: list[str]) -> int:
    lowered = text.lower()
    return sum(1 for term in terms if term in lowered)


def classify_symbol(file_path: Path, name: str, kind: str, source: str, calls: list[str]) -> Dict[str, Any]:
    haystack = f"{file_path}\n{name}\n{source}".lower()

    expected_value_score = score_terms(haystack, PROMOTE_EXPECTED_VALUE_TERMS)
    strategy_selection_score = score_terms(haystack, STRATEGY_SELECTION_TERMS)
    backtesting_score = score_terms(haystack, BACKTESTING_ORCHESTRATION_TERMS)
    io_hits = sorted(set(calls).intersection(IO_CALLS))

    if kind == "class":
        callable_state = "class_review_required"
    else:
        callable_state = "function_review"

    if io_hits or backtesting_score >= expected_value_score + strategy_selection_score:
        classification = "keep_in_backtesting_or_legacy_artifact_orchestration"
        recommended_target = "none"
        reason = "io_or_walk_forward_artifact_terms_dominate"

    elif expected_value_score >= 3 and strategy_selection_score >= 2:
        classification = "review_for_strategy_selection_expected_value_scoring"
        recommended_target = "src/signalforge/engines/strategy_selection/expected_value_scoring.py"
        reason = "expected_value_logic_plus_strategy_selection_terms"

    elif expected_value_score >= 3:
        classification = "promote_candidate_expected_value_engine"
        recommended_target = "src/signalforge/engines/expected_value"
        reason = "pure_or_reusable_expected_value_terms"

    elif strategy_selection_score >= 3:
        classification = "review_for_strategy_selection_engine"
        recommended_target = "src/signalforge/engines/strategy_selection"
        reason = "strategy_selection_terms_without_strong_ev_terms"

    else:
        classification = "keep_or_review_low_confidence"
        recommended_target = "manual_review"
        reason = "low_signal"

    return {
        "classification": classification,
        "recommended_target": recommended_target,
        "reason": reason,
        "callable_state": callable_state,
        "expected_value_score": expected_value_score,
        "strategy_selection_score": strategy_selection_score,
        "backtesting_score": backtesting_score,
        "io_call_hits": io_hits,
    }


def inspect_file(path: Path, source_group: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    text = read_text(path)
    lines = text.splitlines()
    tree = ast.parse(text)

    symbols = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.col_offset == 0:
            source = source_for_node(lines, node)
            calls = calls_used(node)

            symbols.append({
                "source_group": source_group,
                "path": str(path).replace("\\", "/"),
                "name": node.name,
                "kind": "function",
                "lineno": node.lineno,
                "end_lineno": getattr(node, "end_lineno", node.lineno),
                "line_count": getattr(node, "end_lineno", node.lineno) - node.lineno + 1,
                "calls": calls,
                **classify_symbol(path, node.name, "function", source, calls),
            })

        elif isinstance(node, ast.ClassDef) and node.col_offset == 0:
            source = source_for_node(lines, node)
            calls = calls_used(node)

            symbols.append({
                "source_group": source_group,
                "path": str(path).replace("\\", "/"),
                "name": node.name,
                "kind": "class",
                "lineno": node.lineno,
                "end_lineno": getattr(node, "end_lineno", node.lineno),
                "line_count": getattr(node, "end_lineno", node.lineno) - node.lineno + 1,
                "calls": calls,
                **classify_symbol(path, node.name, "class", source, calls),
            })

    file_row = {
        "source_group": source_group,
        "path": str(path).replace("\\", "/"),
        "line_count": len(lines),
        "imports": imports_used(tree),
        "symbol_count": len(symbols),
        "expected_value_term_score": score_terms(text, PROMOTE_EXPECTED_VALUE_TERMS),
        "strategy_selection_term_score": score_terms(text, STRATEGY_SELECTION_TERMS),
        "backtesting_orchestration_term_score": score_terms(text, BACKTESTING_ORCHESTRATION_TERMS),
    }

    return file_row, symbols


def main() -> None:
    blockers: List[str] = []
    warnings: List[str] = []
    file_rows: List[Dict[str, Any]] = []
    symbol_rows: List[Dict[str, Any]] = []

    legacy_dirs_found = [root for root in LEGACY_EXPECTED_VALUE_DIRS if root.exists()]

    if not legacy_dirs_found:
        blockers.append("missing_legacy_expected_value_domain_dir")

    inspected_paths = set()

    for root in LEGACY_EXPECTED_VALUE_DIRS:
        for path in py_files(root):
            key = str(path.resolve())
            if key in inspected_paths:
                continue
            inspected_paths.add(key)

            file_row, symbols = inspect_file(path, "legacy_expected_value")
            file_rows.append(file_row)
            symbol_rows.extend(symbols)

    for root in CURRENT_EXPECTED_VALUE_ENGINE_DIRS:
        if root.exists():
            for path in py_files(root):
                if "expected_value" not in str(path).lower() and "selection" not in str(path).lower():
                    continue

                key = str(path.resolve())
                if key in inspected_paths:
                    continue
                inspected_paths.add(key)

                file_row, symbols = inspect_file(path, "current_engine")
                file_rows.append(file_row)
                symbol_rows.extend(symbols)

    for path in BACKTESTING_WALK_FORWARD_FILES:
        if path.exists():
            key = str(path.resolve())
            if key in inspected_paths:
                continue
            inspected_paths.add(key)

            file_row, symbols = inspect_file(path, "backtesting_walk_forward")
            file_rows.append(file_row)
            symbol_rows.extend(symbols)

    promote_rows = [
        row for row in symbol_rows
        if row["source_group"] == "legacy_expected_value"
        and row["classification"] in {
            "promote_candidate_expected_value_engine",
            "review_for_strategy_selection_expected_value_scoring",
            "review_for_strategy_selection_engine",
        }
    ]

    keep_rows = [
        row for row in symbol_rows
        if row["source_group"] == "legacy_expected_value"
        and row["classification"] == "keep_in_backtesting_or_legacy_artifact_orchestration"
    ]

    current_engine_names = {
        row["name"]
        for row in symbol_rows
        if row["source_group"] == "current_engine"
    }

    already_present_rows = [
        row for row in promote_rows
        if row["name"] in current_engine_names
    ]

    missing_engine_candidate_rows = [
        row for row in promote_rows
        if row["name"] not in current_engine_names
    ]

    warnings.append("stage37a_is_read_only_no_logic_moved")
    warnings.append("walk_forward_expectancy_builder_should_remain_backtesting_orchestration")
    warnings.append("promote_only_pure_expected_value_or_strategy_scoring_helpers_after_source_slice_parity_review")

    summary = {
        "adapter_type": "legacy_expected_value_domain_inspection_builder",
        "artifact_type": "signalforge_legacy_expected_value_domain_inspection",
        "contract": "legacy_expected_value_domain_inspection",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,
        "legacy_dir_count": len(legacy_dirs_found),
        "file_count": len(file_rows),
        "symbol_count": len(symbol_rows),
        "legacy_promote_candidate_count": len(promote_rows),
        "legacy_keep_orchestration_count": len(keep_rows),
        "already_present_candidate_name_count": len(already_present_rows),
        "missing_engine_candidate_name_count": len(missing_engine_candidate_rows),
        "walk_forward_owner": "src/signalforge/backtesting/walk_forward_expectancy_builder.py",
        "expected_value_engine_target": "src/signalforge/engines/expected_value",
        "strategy_selection_ev_scoring_target": "src/signalforge/engines/strategy_selection/expected_value_scoring.py",
        "paper_order_created": False,
        "live_order_created": False,
        "live_trade_supported": False,
        "next_step": "stage37b_source_slice_promote_candidate_expected_value_helpers",
    }

    summary_path = OUT_DIR / "signalforge_stage37a_legacy_expected_value_domain_inspection_summary.json"
    file_rows_path = OUT_DIR / "signalforge_stage37a_legacy_expected_value_file_rows.jsonl"
    symbol_rows_path = OUT_DIR / "signalforge_stage37a_legacy_expected_value_symbol_rows.jsonl"
    md_path = OUT_DIR / "signalforge_stage37a_legacy_expected_value_domain_inspection.md"

    summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    with file_rows_path.open("w", encoding="utf-8") as f:
        for row in file_rows:
            f.write(json.dumps(row, default=str) + "\n")

    with symbol_rows_path.open("w", encoding="utf-8") as f:
        for row in symbol_rows:
            f.write(json.dumps(row, default=str) + "\n")

    md = [
        "# Stage 37A Legacy Expected-Value Domain Inspection",
        "",
        f"- is_ready: {summary['is_ready']}",
        f"- blocker_count: {summary['blocker_count']}",
        f"- legacy_dir_count: {summary['legacy_dir_count']}",
        f"- file_count: {summary['file_count']}",
        f"- symbol_count: {summary['symbol_count']}",
        f"- legacy_promote_candidate_count: {summary['legacy_promote_candidate_count']}",
        f"- legacy_keep_orchestration_count: {summary['legacy_keep_orchestration_count']}",
        f"- already_present_candidate_name_count: {summary['already_present_candidate_name_count']}",
        f"- missing_engine_candidate_name_count: {summary['missing_engine_candidate_name_count']}",
        f"- walk_forward_owner: `{summary['walk_forward_owner']}`",
        f"- expected_value_engine_target: `{summary['expected_value_engine_target']}`",
        f"- strategy_selection_ev_scoring_target: `{summary['strategy_selection_ev_scoring_target']}`",
        f"- paper_order_created: {summary['paper_order_created']}",
        f"- live_order_created: {summary['live_order_created']}",
        f"- live_trade_supported: {summary['live_trade_supported']}",
        "",
        "## File Inventory",
        "",
        "| source | file | symbols | EV score | selection score | orchestration score |",
        "|---|---|---:|---:|---:|---:|",
    ]

    for row in file_rows:
        md.append(
            f"| {row['source_group']} | `{row['path']}` | {row['symbol_count']} | "
            f"{row['expected_value_term_score']} | {row['strategy_selection_term_score']} | "
            f"{row['backtesting_orchestration_term_score']} |"
        )

    md.extend([
        "",
        "## Legacy Promote Candidates",
        "",
        "| classification | target | file | symbol | kind | reason | EV score | selection score | orchestration score |",
        "|---|---|---|---|---|---|---:|---:|---:|",
    ])

    for row in promote_rows:
        md.append(
            f"| {row['classification']} | `{row['recommended_target']}` | `{row['path']}` | "
            f"`{row['name']}` | {row['kind']} | {row['reason']} | "
            f"{row['expected_value_score']} | {row['strategy_selection_score']} | {row['backtesting_score']} |"
        )

    md.extend([
        "",
        "## Legacy Keep-Orchestration Rows",
        "",
        "| file | symbol | reason | IO calls |",
        "|---|---|---|---|",
    ])

    for row in keep_rows:
        md.append(
            f"| `{row['path']}` | `{row['name']}` | {row['reason']} | {', '.join(row['io_call_hits'])} |"
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

    print("\n--- Stage 37A legacy expected-value domain inspection compact ---")
    for key in [
        "is_ready",
        "blocker_count",
        "warning_count",
        "legacy_dir_count",
        "file_count",
        "symbol_count",
        "legacy_promote_candidate_count",
        "legacy_keep_orchestration_count",
        "already_present_candidate_name_count",
        "missing_engine_candidate_name_count",
        "paper_order_created",
        "live_order_created",
        "live_trade_supported",
    ]:
        print(f"{key}: {summary[key]}")

    print(f"summary_path: {summary_path}")
    print(f"file_rows_path: {file_rows_path}")
    print(f"symbol_rows_path: {symbol_rows_path}")
    print(f"md_path: {md_path}")

    print("\n--- Stage 37A file inventory compact ---")
    print("source\tfile\tsymbols\tev_score\tselection_score\torchestration_score")
    for row in file_rows:
        print(
            f"{row['source_group']}\t{row['path']}\t{row['symbol_count']}\t"
            f"{row['expected_value_term_score']}\t{row['strategy_selection_term_score']}\t"
            f"{row['backtesting_orchestration_term_score']}"
        )

    print("\n--- Stage 37A legacy promote candidates compact ---")
    print("classification\ttarget\tfile\tsymbol\tkind\tev_score\tselection_score\torchestration_score\treason")
    for row in promote_rows:
        print(
            f"{row['classification']}\t{row['recommended_target']}\t{row['path']}\t"
            f"{row['name']}\t{row['kind']}\t{row['expected_value_score']}\t"
            f"{row['strategy_selection_score']}\t{row['backtesting_score']}\t{row['reason']}"
        )

    print("\n--- Stage 37A legacy keep-orchestration compact ---")
    print("file\tsymbol\tio_calls\treason")
    for row in keep_rows:
        print(
            f"{row['path']}\t{row['name']}\t{','.join(row['io_call_hits'])}\t{row['reason']}"
        )

    if blockers:
        print("\n--- Stage 37A blockers ---")
        for blocker in blockers:
            print(blocker)
        raise SystemExit(1)

    if warnings:
        print("\n--- Stage 37A warnings ---")
        for warning in warnings:
            print(warning)


if __name__ == "__main__":
    main()
