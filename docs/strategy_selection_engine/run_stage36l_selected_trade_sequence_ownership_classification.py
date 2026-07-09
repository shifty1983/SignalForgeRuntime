import ast
import json
from pathlib import Path
from typing import Any, Dict, List


OUT_DIR = Path("docs/strategy_selection_engine")
SOURCE_PATH = Path("src/signalforge/backtesting/portfolio_selected_trade_sequence.py")

TARGET_FUNCTIONS = [
    "_extract_execution_realism_fields",
    "_execution_realism_coverage",
    "_extract_trade",
    "_count_source_fields",
    "build_portfolio_selected_trade_sequence",
    "build_from_paths",
]

BACKTESTING_ORCHESTRATION_TERMS = [
    "path",
    "output_dir",
    "rows_path",
    "summary_path",
    "json",
    "jsonl",
    "artifact",
    "summary",
    "coverage",
    "source",
    "source_row",
    "source_fields",
    "contract_outcome",
    "historical",
    "replay",
    "sequence",
    "trade_sequence",
    "rows",
    "write",
    "load",
    "count",
    "missing",
    "skip",
    "duplicate",
]

ROW_SHAPING_TERMS = [
    "extract",
    "coerce",
    "parse",
    "first_present",
    "normalize",
    "string",
    "date",
    "field",
    "row",
    "dict",
    "copy",
    "append",
    "join",
    "get",
    "isoformat",
]

ENGINE_DECISION_TERMS = [
    "rank",
    "score",
    "select",
    "choose",
    "eligible",
    "filter",
    "strategy_decision",
    "execution_decision",
    "trade_decision",
    "portfolio_decision",
    "risk_decision",
    "allocation",
    "sizing",
    "expected_value",
    "expectancy",
    "threshold",
    "rule",
    "candidate_score",
    "selection_score",
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
}

SAFE_BACKTESTING_HELPER_PREFIXES = (
    "_coerce",
    "_parse",
    "_first_present",
    "_string",
    "_has_contract_outcome",
    "_extract_execution_realism",
)


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


def assigned_names(node: ast.AST) -> list[str]:
    names = set()

    for child in ast.walk(node):
        if isinstance(child, ast.Assign):
            for target in child.targets:
                for item in ast.walk(target):
                    if isinstance(item, ast.Name):
                        names.add(item.id)

        elif isinstance(child, ast.AnnAssign):
            for item in ast.walk(child.target):
                if isinstance(item, ast.Name):
                    names.add(item.id)

    return sorted(names)


def score_terms(text: str, terms: list[str]) -> int:
    lowered = text.lower()
    return sum(1 for term in terms if term in lowered)


def classify_function(name: str, source: str, calls: list[str]) -> dict[str, Any]:
    haystack = f"{name}\n{source}".lower()

    backtesting_score = score_terms(haystack, BACKTESTING_ORCHESTRATION_TERMS)
    row_shaping_score = score_terms(haystack, ROW_SHAPING_TERMS)
    engine_decision_score = score_terms(haystack, ENGINE_DECISION_TERMS)
    io_call_hits = sorted(set(calls).intersection(IO_CALLS))
    safe_helper_call_hits = sorted(c for c in calls if c.startswith(SAFE_BACKTESTING_HELPER_PREFIXES))

    if name in {"build_portfolio_selected_trade_sequence", "build_from_paths"}:
        classification = "keep_in_backtesting_orchestration"
        recommendation = "do_not_extract_builder"
        reason = "top_level_historical_artifact_builder_or_path_entrypoint"

    elif io_call_hits:
        classification = "keep_in_backtesting_orchestration"
        recommendation = "do_not_extract"
        reason = "contains_file_or_artifact_io"

    elif engine_decision_score >= 4 and engine_decision_score > row_shaping_score:
        classification = "review_possible_engine_decision_logic"
        recommendation = "manual_review_before_extract"
        reason = "decision_terms_exceed_row_shaping_terms"

    elif row_shaping_score >= engine_decision_score:
        classification = "keep_in_backtesting_row_shaping"
        recommendation = "do_not_extract_now"
        reason = "row_shaping_terms_dominate_or_match_decision_terms"

    elif backtesting_score >= engine_decision_score:
        classification = "keep_in_backtesting_replay_helper"
        recommendation = "do_not_extract_now"
        reason = "historical_replay_terms_dominate_or_match_decision_terms"

    else:
        classification = "review_possible_engine_decision_logic"
        recommendation = "manual_review_before_extract"
        reason = "ambiguous_low_confidence"

    return {
        "classification": classification,
        "recommendation": recommendation,
        "reason": reason,
        "backtesting_score": backtesting_score,
        "row_shaping_score": row_shaping_score,
        "engine_decision_score": engine_decision_score,
        "io_call_hits": io_call_hits,
        "safe_helper_call_hits": safe_helper_call_hits,
    }


def main() -> None:
    blockers: List[str] = []
    warnings: List[str] = []
    rows: List[Dict[str, Any]] = []

    if not SOURCE_PATH.exists():
        blockers.append(f"missing_source_path_{SOURCE_PATH}")
    else:
        text = read_text(SOURCE_PATH)
        lines = text.splitlines()
        tree = ast.parse(text)
        functions = top_level_functions(tree)

        for function_name in TARGET_FUNCTIONS:
            node = functions.get(function_name)

            if node is None:
                blockers.append(f"missing_function_{function_name}")
                continue

            source = source_for_node(lines, node)
            calls = calls_used(node)
            classification = classify_function(function_name, source, calls)

            rows.append({
                "source_path": str(SOURCE_PATH).replace("\\", "/"),
                "function": function_name,
                "lineno": node.lineno,
                "end_lineno": getattr(node, "end_lineno", node.lineno),
                "line_count": getattr(node, "end_lineno", node.lineno) - node.lineno + 1,
                "calls": calls,
                "assigned_names": assigned_names(node),
                **classification,
            })

    extract_now_rows = [
        row for row in rows
        if row["recommendation"] in {"extract_to_engine", "manual_review_before_extract"}
        and row["classification"] == "review_possible_engine_decision_logic"
    ]

    keep_in_backtesting_rows = [
        row for row in rows
        if row["recommendation"] in {
            "do_not_extract",
            "do_not_extract_now",
            "do_not_extract_builder",
        }
    ]

    warnings.append("stage36l_is_read_only_no_logic_moved")
    warnings.append("portfolio_selected_trade_sequence_remains_backtesting_owned_unless_manual_review_finds_core_decision_logic")
    warnings.append("do_not_extract_row_shaping_or_artifact_contract_logic_to_core_engines")

    summary = {
        "adapter_type": "selected_trade_sequence_ownership_classification_builder",
        "artifact_type": "signalforge_selected_trade_sequence_ownership_classification",
        "contract": "selected_trade_sequence_ownership_classification",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,
        "source_path": str(SOURCE_PATH),
        "target_function_count": len(TARGET_FUNCTIONS),
        "classified_function_count": len(rows),
        "keep_in_backtesting_count": len(keep_in_backtesting_rows),
        "manual_review_before_extract_count": len(extract_now_rows),
        "recommendation": (
            "keep_portfolio_selected_trade_sequence_in_backtesting"
            if len(extract_now_rows) == 0
            else "manual_review_required_before_any_extraction"
        ),
        "paper_order_created": False,
        "live_order_created": False,
        "live_trade_supported": False,
        "next_step": (
            "stage36m_classify_candidate_rows_builder_decision_logic"
            if len(extract_now_rows) == 0
            else "stage36m_manual_review_selected_trade_sequence_ambiguous_functions"
        ),
    }

    summary_path = OUT_DIR / "signalforge_stage36l_selected_trade_sequence_ownership_classification_summary.json"
    rows_path = OUT_DIR / "signalforge_stage36l_selected_trade_sequence_ownership_classification_rows.jsonl"
    md_path = OUT_DIR / "signalforge_stage36l_selected_trade_sequence_ownership_classification.md"

    summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    with rows_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, default=str) + "\n")

    md = [
        "# Stage 36L Selected Trade Sequence Ownership Classification",
        "",
        f"- is_ready: {summary['is_ready']}",
        f"- blocker_count: {summary['blocker_count']}",
        f"- recommendation: `{summary['recommendation']}`",
        f"- classified_function_count: {summary['classified_function_count']}",
        f"- keep_in_backtesting_count: {summary['keep_in_backtesting_count']}",
        f"- manual_review_before_extract_count: {summary['manual_review_before_extract_count']}",
        f"- paper_order_created: {summary['paper_order_created']}",
        f"- live_order_created: {summary['live_order_created']}",
        f"- live_trade_supported: {summary['live_trade_supported']}",
        "",
        "## Function Classifications",
        "",
        "| function | classification | recommendation | reason | backtesting score | row shaping score | engine decision score |",
        "|---|---|---|---|---:|---:|---:|",
    ]

    for row in rows:
        md.append(
            f"| `{row['function']}` | {row['classification']} | {row['recommendation']} | "
            f"{row['reason']} | {row['backtesting_score']} | {row['row_shaping_score']} | "
            f"{row['engine_decision_score']} |"
        )

    if blockers:
        md.extend(["", "## Blockers", ""])
        for blocker in blockers:
            md.append(f"- {blocker}")

    if warnings:
        md.extend(["", "## Warnings", ""])
        for warning in warnings:
            md.append(f"- {warning}")

    summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    md_path.write_text("\n".join(md), encoding="utf-8")

    print("\n--- Stage 36L selected trade sequence ownership classification compact ---")
    for key in [
        "is_ready",
        "blocker_count",
        "warning_count",
        "classified_function_count",
        "keep_in_backtesting_count",
        "manual_review_before_extract_count",
        "recommendation",
        "paper_order_created",
        "live_order_created",
        "live_trade_supported",
    ]:
        print(f"{key}: {summary[key]}")

    print(f"summary_path: {summary_path}")
    print(f"rows_path: {rows_path}")
    print(f"md_path: {md_path}")

    print("\n--- Stage 36L function classifications compact ---")
    print("function\tclassification\trecommendation\treason\tbacktesting_score\trow_shaping_score\tengine_decision_score")
    for row in rows:
        print(
            f"{row['function']}\t{row['classification']}\t{row['recommendation']}\t"
            f"{row['reason']}\t{row['backtesting_score']}\t{row['row_shaping_score']}\t"
            f"{row['engine_decision_score']}"
        )

    if blockers:
        print("\n--- Stage 36L blockers ---")
        for blocker in blockers:
            print(blocker)
        raise SystemExit(1)

    if warnings:
        print("\n--- Stage 36L warnings ---")
        for warning in warnings:
            print(warning)


if __name__ == "__main__":
    main()
