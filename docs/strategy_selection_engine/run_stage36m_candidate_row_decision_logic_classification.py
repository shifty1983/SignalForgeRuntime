import ast
import json
from pathlib import Path
from typing import Any, Dict, List


OUT_DIR = Path("docs/strategy_selection_engine")
SOURCE_PATH = Path("src/signalforge/backtesting/historical_strategy_candidate_rows_builder.py")

TARGET_FUNCTIONS = [
    "_strategy_family_gate_block_reasons",
    "_as_list",
    "_research_context_from_decision_row",
    "_alignment_research_fields",
    "_decision_row_block_reasons",
    "_strategy_definition_block_reasons",
    "_strategy_context_block_reasons",
    "_candidate_state",
    "build_historical_strategy_candidate_rows",
    "build_historical_strategy_candidate_rows_artifact",
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
    "historical",
    "replay",
    "rows",
    "write",
    "load",
    "count",
    "manifest",
    "source",
    "as_of",
    "date",
]

ROW_SHAPING_TERMS = [
    "extract",
    "coerce",
    "parse",
    "normalize",
    "string",
    "field",
    "row",
    "dict",
    "copy",
    "append",
    "join",
    "get",
    "items",
    "update",
    "context",
]

ENGINE_DECISION_TERMS = [
    "block",
    "block_reason",
    "gate",
    "eligible",
    "eligibility",
    "allowed",
    "reject",
    "skip",
    "candidate_state",
    "tradable",
    "strategy_family",
    "strategy_definition",
    "strategy_context",
    "asset_behavior",
    "option_behavior",
    "regime",
    "rule",
    "filter",
    "required",
    "missing",
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


def score_terms(text: str, terms: list[str]) -> int:
    lowered = text.lower()
    return sum(1 for term in terms if term in lowered)


def classify_function(name: str, source: str, calls: list[str]) -> dict[str, Any]:
    haystack = f"{name}\n{source}".lower()

    backtesting_score = score_terms(haystack, BACKTESTING_ORCHESTRATION_TERMS)
    row_shaping_score = score_terms(haystack, ROW_SHAPING_TERMS)
    engine_decision_score = score_terms(haystack, ENGINE_DECISION_TERMS)
    io_call_hits = sorted(set(calls).intersection(IO_CALLS))

    if name.endswith("_artifact") or name.startswith("build_historical_"):
        if engine_decision_score >= 5:
            classification = "mixed_keep_wrapper_extract_core_decision_logic"
            recommendation = "manual_review_extract_inner_decisions_only"
            target = "signalforge.engines.strategy_selection.filters"
            reason = "historical_builder_contains_decision_terms_but_must_remain_backtesting_orchestration"
        else:
            classification = "keep_in_backtesting_orchestration"
            recommendation = "do_not_extract_builder"
            target = "none"
            reason = "historical_artifact_builder_or_replay_entrypoint"

    elif io_call_hits:
        classification = "keep_in_backtesting_orchestration"
        recommendation = "do_not_extract"
        target = "none"
        reason = "contains_file_or_artifact_io"

    elif engine_decision_score >= 4 and engine_decision_score > row_shaping_score:
        classification = "extract_decision_logic_to_engine_candidate_filter"
        recommendation = "extract_with_parity_test"
        target = "signalforge.engines.strategy_selection.candidate_filter_decision"
        reason = "candidate_filter_or_block_reason_logic"

    elif engine_decision_score >= 2 and engine_decision_score >= row_shaping_score:
        classification = "review_possible_candidate_decision_logic"
        recommendation = "manual_review_before_extract"
        target = "signalforge.engines.strategy_selection.candidate_filter_decision"
        reason = "possible_reusable_candidate_filter_logic"

    elif row_shaping_score >= engine_decision_score:
        classification = "keep_in_backtesting_row_shaping"
        recommendation = "do_not_extract_now"
        target = "none"
        reason = "row_shaping_terms_dominate_or_match_decision_terms"

    elif backtesting_score >= engine_decision_score:
        classification = "keep_in_backtesting_replay_helper"
        recommendation = "do_not_extract_now"
        target = "none"
        reason = "historical_replay_terms_dominate_or_match_decision_terms"

    else:
        classification = "review_low_confidence"
        recommendation = "manual_review_before_extract"
        target = "signalforge.engines.strategy_selection.review_required"
        reason = "ambiguous_low_confidence"

    return {
        "classification": classification,
        "recommendation": recommendation,
        "recommended_engine_target": target,
        "reason": reason,
        "backtesting_score": backtesting_score,
        "row_shaping_score": row_shaping_score,
        "engine_decision_score": engine_decision_score,
        "io_call_hits": io_call_hits,
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
                **classification,
            })

    extract_rows = [
        row for row in rows
        if row["recommendation"] in {
            "extract_with_parity_test",
            "manual_review_extract_inner_decisions_only",
        }
    ]

    review_rows = [
        row for row in rows
        if row["recommendation"] == "manual_review_before_extract"
    ]

    keep_rows = [
        row for row in rows
        if row["recommendation"] in {
            "do_not_extract",
            "do_not_extract_now",
            "do_not_extract_builder",
        }
    ]

    warnings.append("stage36m_is_read_only_no_logic_moved")
    warnings.append("historical_candidate_row_builder_remains_in_backtesting")
    warnings.append("extract_only_reusable_candidate_filter_or_block_reason_logic")

    summary = {
        "adapter_type": "candidate_row_decision_logic_classification_builder",
        "artifact_type": "signalforge_candidate_row_decision_logic_classification",
        "contract": "candidate_row_decision_logic_classification",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,
        "source_path": str(SOURCE_PATH),
        "target_function_count": len(TARGET_FUNCTIONS),
        "classified_function_count": len(rows),
        "extract_with_parity_test_count": len(extract_rows),
        "manual_review_before_extract_count": len(review_rows),
        "keep_in_backtesting_count": len(keep_rows),
        "recommendation": (
            "extract_candidate_filter_decision_cluster_with_parity_test"
            if extract_rows
            else "keep_candidate_row_builder_in_backtesting_no_extraction_now"
        ),
        "paper_order_created": False,
        "live_order_created": False,
        "live_trade_supported": False,
        "next_step": (
            "stage36n_extract_candidate_filter_decision_cluster_with_parity_test"
            if extract_rows
            else "stage36n_classify_walk_forward_expectancy_decision_logic"
        ),
    }

    summary_path = OUT_DIR / "signalforge_stage36m_candidate_row_decision_logic_classification_summary.json"
    rows_path = OUT_DIR / "signalforge_stage36m_candidate_row_decision_logic_classification_rows.jsonl"
    md_path = OUT_DIR / "signalforge_stage36m_candidate_row_decision_logic_classification.md"

    summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    with rows_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, default=str) + "\n")

    md = [
        "# Stage 36M Candidate Row Decision Logic Classification",
        "",
        f"- is_ready: {summary['is_ready']}",
        f"- blocker_count: {summary['blocker_count']}",
        f"- recommendation: `{summary['recommendation']}`",
        f"- classified_function_count: {summary['classified_function_count']}",
        f"- extract_with_parity_test_count: {summary['extract_with_parity_test_count']}",
        f"- manual_review_before_extract_count: {summary['manual_review_before_extract_count']}",
        f"- keep_in_backtesting_count: {summary['keep_in_backtesting_count']}",
        f"- paper_order_created: {summary['paper_order_created']}",
        f"- live_order_created: {summary['live_order_created']}",
        f"- live_trade_supported: {summary['live_trade_supported']}",
        "",
        "## Function Classifications",
        "",
        "| function | classification | recommendation | target | reason | backtesting score | row shaping score | engine decision score |",
        "|---|---|---|---|---|---:|---:|---:|",
    ]

    for row in rows:
        md.append(
            f"| `{row['function']}` | {row['classification']} | {row['recommendation']} | "
            f"`{row['recommended_engine_target']}` | {row['reason']} | "
            f"{row['backtesting_score']} | {row['row_shaping_score']} | {row['engine_decision_score']} |"
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

    print("\n--- Stage 36M candidate row decision logic classification compact ---")
    for key in [
        "is_ready",
        "blocker_count",
        "warning_count",
        "classified_function_count",
        "extract_with_parity_test_count",
        "manual_review_before_extract_count",
        "keep_in_backtesting_count",
        "recommendation",
        "paper_order_created",
        "live_order_created",
        "live_trade_supported",
    ]:
        print(f"{key}: {summary[key]}")

    print(f"summary_path: {summary_path}")
    print(f"rows_path: {rows_path}")
    print(f"md_path: {md_path}")

    print("\n--- Stage 36M function classifications compact ---")
    print("function\tclassification\trecommendation\ttarget\treason\tbacktesting_score\trow_shaping_score\tengine_decision_score")
    for row in rows:
        print(
            f"{row['function']}\t{row['classification']}\t{row['recommendation']}\t"
            f"{row['recommended_engine_target']}\t{row['reason']}\t"
            f"{row['backtesting_score']}\t{row['row_shaping_score']}\t{row['engine_decision_score']}"
        )

    if blockers:
        print("\n--- Stage 36M blockers ---")
        for blocker in blockers:
            print(blocker)
        raise SystemExit(1)

    if warnings:
        print("\n--- Stage 36M warnings ---")
        for warning in warnings:
            print(warning)


if __name__ == "__main__":
    main()
