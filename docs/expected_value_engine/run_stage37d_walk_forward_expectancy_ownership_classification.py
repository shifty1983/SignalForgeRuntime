import ast
import json
from pathlib import Path
from typing import Any, Dict, List


OUT_DIR = Path("docs/expected_value_engine")

SOURCE_FILES = [
    Path("src/signalforge/backtesting/walk_forward_expectancy_builder.py"),
    Path("src/signalforge/backtesting/walk_forward_expectancy_cli.py"),
    Path("src/signalforge/engines/strategy_selection/expected_value_scoring.py"),
]

BACKTESTING_TERMS = [
    "walk_forward",
    "training",
    "window",
    "train",
    "historical",
    "replay",
    "as_of",
    "date",
    "lookback",
    "artifact",
    "json",
    "jsonl",
    "path",
    "output_dir",
    "summary",
    "manifest",
    "rows",
    "load",
    "write",
    "main",
    "cli",
    "argparse",
    "glob",
]

EXPECTANCY_POLICY_TERMS = [
    "expectancy",
    "expected_value",
    "ev",
    "avg_return",
    "average_return",
    "win_rate",
    "loss_rate",
    "sample_count",
    "sample",
    "confidence",
    "score",
    "rank",
    "selection",
    "threshold",
    "positive",
    "negative",
    "edge",
    "cohort",
    "fallback",
    "missing",
    "insufficient",
]

PAPER_ENGINE_TERMS = [
    "consume",
    "snapshot",
    "lookup",
    "candidate",
    "family",
    "strategy",
    "eligibility",
    "filter",
    "state",
    "handoff",
    "rule",
    "policy",
    "blocked",
    "allowed",
    "reason",
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


def source_for_node(lines: list[str], node: ast.AST) -> str:
    start = getattr(node, "lineno", 1)
    end = getattr(node, "end_lineno", start)
    return "\n".join(lines[start - 1:end])


def top_level_symbols(tree: ast.Module) -> list[ast.AST]:
    return [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.ClassDef))
    ]


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

    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")

    return sorted(imports)


def score_terms(text: str, terms: list[str]) -> int:
    lowered = text.lower()
    return sum(1 for term in terms if term in lowered)


def signature(node: ast.AST) -> str:
    if isinstance(node, ast.FunctionDef):
        return f"def {node.name}({ast.unparse(node.args)}):"
    if isinstance(node, ast.ClassDef):
        return f"class {node.name}"
    return ""


def classify_symbol(path: Path, name: str, kind: str, source: str, calls: list[str]) -> Dict[str, Any]:
    haystack = f"{path}\n{name}\n{source}".lower()

    backtesting_score = score_terms(haystack, BACKTESTING_TERMS)
    expectancy_score = score_terms(haystack, EXPECTANCY_POLICY_TERMS)
    paper_engine_score = score_terms(haystack, PAPER_ENGINE_TERMS)
    io_hits = sorted(set(calls).intersection(IO_CALLS))

    path_text = str(path).replace("\\", "/")

    if path_text.endswith("walk_forward_expectancy_cli.py"):
        classification = "keep_in_backtesting_cli"
        recommendation = "do_not_extract"
        target = "none"
        reason = "cli_entrypoint"

    elif io_hits:
        classification = "keep_in_backtesting_artifact_io"
        recommendation = "do_not_extract"
        target = "none"
        reason = "contains_file_or_artifact_io"

    elif "walk_forward_expectancy_builder.py" in path_text and backtesting_score >= expectancy_score:
        classification = "keep_in_backtesting_walk_forward_orchestration"
        recommendation = "do_not_extract_builder_or_training_window_logic"
        target = "none"
        reason = "walk_forward_training_or_historical_replay_terms_dominate"

    elif expectancy_score >= 4 and paper_engine_score >= 2:
        classification = "review_extract_expectancy_consumption_policy"
        recommendation = "source_slice_review_before_extract"
        target = "src/signalforge/engines/strategy_selection/expectancy_decision.py"
        reason = "expectancy_policy_plus_candidate_consumption_terms"

    elif expectancy_score >= 4:
        classification = "review_extract_expectancy_metric_helper"
        recommendation = "source_slice_review_before_extract"
        target = "src/signalforge/engines/strategy_selection/expectancy_decision.py"
        reason = "expectancy_metric_or_confidence_terms"

    elif paper_engine_score >= 4:
        classification = "review_extract_strategy_candidate_policy"
        recommendation = "source_slice_review_before_extract"
        target = "src/signalforge/engines/strategy_selection/expectancy_decision.py"
        reason = "candidate_policy_terms_without_strong_backtesting_io"

    else:
        classification = "keep_or_review_low_confidence"
        recommendation = "manual_review"
        target = "manual_review"
        reason = "low_signal_or_mixed_terms"

    return {
        "classification": classification,
        "recommendation": recommendation,
        "recommended_target": target,
        "reason": reason,
        "backtesting_score": backtesting_score,
        "expectancy_score": expectancy_score,
        "paper_engine_score": paper_engine_score,
        "io_call_hits": io_hits,
    }


def inspect_file(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    text = read_text(path)
    lines = text.splitlines()
    tree = ast.parse(text)

    symbol_rows = []

    for node in top_level_symbols(tree):
        name = node.name
        kind = "class" if isinstance(node, ast.ClassDef) else "function"
        source = source_for_node(lines, node)
        calls = calls_used(node)

        symbol_rows.append({
            "path": str(path).replace("\\", "/"),
            "symbol": name,
            "kind": kind,
            "signature": signature(node),
            "lineno": node.lineno,
            "end_lineno": getattr(node, "end_lineno", node.lineno),
            "line_count": getattr(node, "end_lineno", node.lineno) - node.lineno + 1,
            "calls": calls,
            **classify_symbol(path, name, kind, source, calls),
        })

    file_row = {
        "path": str(path).replace("\\", "/"),
        "exists": path.exists(),
        "line_count": len(lines),
        "imports": imports_used(tree),
        "symbol_count": len(symbol_rows),
        "backtesting_score": score_terms(text, BACKTESTING_TERMS),
        "expectancy_score": score_terms(text, EXPECTANCY_POLICY_TERMS),
        "paper_engine_score": score_terms(text, PAPER_ENGINE_TERMS),
    }

    return file_row, symbol_rows


def main() -> None:
    blockers: List[str] = []
    warnings: List[str] = []
    file_rows: List[Dict[str, Any]] = []
    symbol_rows: List[Dict[str, Any]] = []

    for path in SOURCE_FILES:
        if not path.exists():
            blockers.append(f"missing_source_file_{path}")
            continue

        file_row, rows = inspect_file(path)
        file_rows.append(file_row)
        symbol_rows.extend(rows)

    extraction_review_rows = [
        row for row in symbol_rows
        if row["recommendation"] == "source_slice_review_before_extract"
    ]

    backtesting_keep_rows = [
        row for row in symbol_rows
        if row["recommendation"] in {
            "do_not_extract",
            "do_not_extract_builder_or_training_window_logic",
        }
    ]

    warnings.append("stage37d_is_read_only_no_logic_moved")
    warnings.append("walk_forward_expectancy_generation_remains_backtesting_owned")
    warnings.append("paper_engine_should_consume_locked_expectancy_snapshot_not_recompute_walk_forward")

    summary = {
        "adapter_type": "walk_forward_expectancy_ownership_classification_builder",
        "artifact_type": "signalforge_walk_forward_expectancy_ownership_classification",
        "contract": "walk_forward_expectancy_ownership_classification",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,
        "file_count": len(file_rows),
        "symbol_count": len(symbol_rows),
        "extraction_review_count": len(extraction_review_rows),
        "backtesting_keep_count": len(backtesting_keep_rows),
        "walk_forward_owner": "src/signalforge/backtesting/walk_forward_expectancy_builder.py",
        "paper_expectancy_consumption_target": "src/signalforge/engines/strategy_selection/expectancy_decision.py",
        "current_strategy_ev_scoring_path": "src/signalforge/engines/strategy_selection/expected_value_scoring.py",
        "legacy_expected_value_status": "research_candidate_only_until_ab_backtested",
        "paper_order_created": False,
        "live_order_created": False,
        "live_trade_supported": False,
        "next_step": (
            "stage37e_source_slice_review_expectancy_consumption_policy"
            if extraction_review_rows
            else "stage37e_design_paper_expectancy_snapshot_contract"
        ),
    }

    summary_path = OUT_DIR / "signalforge_stage37d_walk_forward_expectancy_ownership_classification_summary.json"
    file_rows_path = OUT_DIR / "signalforge_stage37d_walk_forward_expectancy_file_rows.jsonl"
    symbol_rows_path = OUT_DIR / "signalforge_stage37d_walk_forward_expectancy_symbol_rows.jsonl"
    md_path = OUT_DIR / "signalforge_stage37d_walk_forward_expectancy_ownership_classification.md"

    summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    with file_rows_path.open("w", encoding="utf-8") as f:
        for row in file_rows:
            f.write(json.dumps(row, default=str) + "\n")

    with symbol_rows_path.open("w", encoding="utf-8") as f:
        for row in symbol_rows:
            f.write(json.dumps(row, default=str) + "\n")

    md = [
        "# Stage 37D Walk-Forward Expectancy Ownership Classification",
        "",
        f"- is_ready: {summary['is_ready']}",
        f"- blocker_count: {summary['blocker_count']}",
        f"- file_count: {summary['file_count']}",
        f"- symbol_count: {summary['symbol_count']}",
        f"- extraction_review_count: {summary['extraction_review_count']}",
        f"- backtesting_keep_count: {summary['backtesting_keep_count']}",
        f"- walk_forward_owner: `{summary['walk_forward_owner']}`",
        f"- paper_expectancy_consumption_target: `{summary['paper_expectancy_consumption_target']}`",
        f"- legacy_expected_value_status: `{summary['legacy_expected_value_status']}`",
        f"- paper_order_created: {summary['paper_order_created']}",
        f"- live_order_created: {summary['live_order_created']}",
        f"- live_trade_supported: {summary['live_trade_supported']}",
        "",
        "## Ownership Decision",
        "",
        "Walk-forward expectancy generation remains backtesting-owned.",
        "Paper trading should consume a locked expectancy snapshot produced by the validated backtest workflow.",
        "Only reusable expectancy lookup, confidence handling, and candidate consumption policy should be considered for engine extraction after source-slice review and parity tests.",
        "",
        "## File Inventory",
        "",
        "| file | symbols | backtesting score | expectancy score | paper engine score |",
        "|---|---:|---:|---:|---:|",
    ]

    for row in file_rows:
        md.append(
            f"| `{row['path']}` | {row['symbol_count']} | "
            f"{row['backtesting_score']} | {row['expectancy_score']} | {row['paper_engine_score']} |"
        )

    md.extend([
        "",
        "## Symbol Classification",
        "",
        "| symbol | file | classification | recommendation | target | reason | backtesting | expectancy | paper engine | IO calls |",
        "|---|---|---|---|---|---|---:|---:|---:|---|",
    ])

    for row in symbol_rows:
        md.append(
            f"| `{row['symbol']}` | `{row['path']}` | {row['classification']} | "
            f"{row['recommendation']} | `{row['recommended_target']}` | {row['reason']} | "
            f"{row['backtesting_score']} | {row['expectancy_score']} | {row['paper_engine_score']} | "
            f"{', '.join(row['io_call_hits'])} |"
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

    print("\n--- Stage 37D walk-forward expectancy ownership classification compact ---")
    for key in [
        "is_ready",
        "blocker_count",
        "warning_count",
        "file_count",
        "symbol_count",
        "extraction_review_count",
        "backtesting_keep_count",
        "paper_order_created",
        "live_order_created",
        "live_trade_supported",
    ]:
        print(f"{key}: {summary[key]}")

    print(f"summary_path: {summary_path}")
    print(f"file_rows_path: {file_rows_path}")
    print(f"symbol_rows_path: {symbol_rows_path}")
    print(f"md_path: {md_path}")

    print("\n--- Stage 37D file inventory compact ---")
    print("file\tsymbols\tbacktesting_score\texpectancy_score\tpaper_engine_score")
    for row in file_rows:
        print(
            f"{row['path']}\t{row['symbol_count']}\t"
            f"{row['backtesting_score']}\t{row['expectancy_score']}\t{row['paper_engine_score']}"
        )

    print("\n--- Stage 37D symbol classification compact ---")
    print("symbol\tfile\tclassification\trecommendation\ttarget\treason\tbacktesting_score\texpectancy_score\tpaper_engine_score\tio_calls")
    for row in symbol_rows:
        print(
            f"{row['symbol']}\t{row['path']}\t{row['classification']}\t"
            f"{row['recommendation']}\t{row['recommended_target']}\t{row['reason']}\t"
            f"{row['backtesting_score']}\t{row['expectancy_score']}\t"
            f"{row['paper_engine_score']}\t{','.join(row['io_call_hits'])}"
        )

    if blockers:
        print("\n--- Stage 37D blockers ---")
        for blocker in blockers:
            print(blocker)
        raise SystemExit(1)

    if warnings:
        print("\n--- Stage 37D warnings ---")
        for warning in warnings:
            print(warning)


if __name__ == "__main__":
    main()
