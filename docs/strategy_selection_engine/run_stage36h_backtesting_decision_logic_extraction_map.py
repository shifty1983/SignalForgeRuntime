import ast
import json
from pathlib import Path
from typing import Any, Dict, List


OUT_DIR = Path("docs/strategy_selection_engine")

BACKTESTING_FILES = [
    "src/signalforge/backtesting/historical_strategy_candidate_rows_builder.py",
    "src/signalforge/backtesting/historical_strategy_selection_rows_builder.py",
    "src/signalforge/backtesting/historical_strategy_selection_rows_cli.py",
    "src/signalforge/backtesting/walk_forward_expectancy_builder.py",
    "src/signalforge/backtesting/walk_forward_expectancy_cli.py",
    "src/signalforge/backtesting/portfolio_selected_trade_sequence.py",
]

ENGINE_TARGET_HINTS = {
    "selector": [
        "select", "selected", "choose", "winner", "one_strategy", "dedupe",
        "group", "grouped", "sequence"
    ],
    "ranking": [
        "rank", "ranking", "sort", "priority", "score_order", "tie_break"
    ],
    "filters": [
        "filter", "skip", "block", "eligible", "eligibility", "threshold",
        "allowed", "reject", "accepted"
    ],
    "expected_value_scoring": [
        "expectancy", "expected_value", "ev", "win_rate", "profit_factor",
        "avg_return", "score"
    ],
    "contract_candidate_scoring": [
        "contract", "leg", "strike", "expiration", "quote", "spread",
        "bid", "ask", "mid"
    ],
    "portfolio_candidate_input": [
        "portfolio_candidate", "portfolio_input", "candidate_input",
        "construction_input"
    ],
    "allocation": [
        "allocation", "capital", "sizing", "risk", "max_return",
        "units", "heat"
    ],
    "candidates": [
        "candidate", "row", "normalize", "build_candidate"
    ],
}

BACKTESTING_ORCHESTRATION_TERMS = [
    "path", "open", "read", "write", "json", "jsonl", "csv",
    "output_dir", "summary", "artifact", "manifest", "date",
    "as_of", "historical", "replay", "load", "save"
]

DECISION_TERMS = [
    "rank", "ranking", "score", "filter", "select", "selected",
    "choose", "eligible", "allowed", "block", "skip", "reject",
    "expectancy", "priority", "tie", "threshold", "candidate_score",
    "strategy_score", "sort", "best", "winner"
]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def get_function_source(lines: List[str], node: ast.AST) -> str:
    start = getattr(node, "lineno", 1)
    end = getattr(node, "end_lineno", start)
    return "\n".join(lines[start - 1:end])


def imported_modules(tree: ast.AST) -> List[str]:
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
    return sorted(set(imports))


def called_names(node: ast.AST) -> List[str]:
    names = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            fn = child.func
            if isinstance(fn, ast.Name):
                names.append(fn.id)
            elif isinstance(fn, ast.Attribute):
                names.append(fn.attr)
    return sorted(set(names))


def assigned_names(node: ast.AST) -> List[str]:
    names = []
    for child in ast.walk(node):
        if isinstance(child, ast.Assign):
            for target in child.targets:
                if isinstance(target, ast.Name):
                    names.append(target.id)
                elif isinstance(target, ast.Tuple):
                    for elt in target.elts:
                        if isinstance(elt, ast.Name):
                            names.append(elt.id)
        elif isinstance(child, ast.AnnAssign):
            target = child.target
            if isinstance(target, ast.Name):
                names.append(target.id)
    return sorted(set(names))


def choose_engine_target(name: str, source: str) -> str:
    haystack = f"{name}\n{source}".lower()

    scores = {}
    for target, hints in ENGINE_TARGET_HINTS.items():
        scores[target] = sum(1 for hint in hints if hint in haystack)

    best_target, best_score = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[0]

    if best_score <= 0:
        return "none"

    return f"signalforge.engines.strategy_selection.{best_target}"


def classify_function(name: str, source: str, calls: List[str]) -> Dict[str, Any]:
    haystack = f"{name}\n{source}".lower()

    decision_score = sum(1 for term in DECISION_TERMS if term in haystack)
    orchestration_score = sum(1 for term in BACKTESTING_ORCHESTRATION_TERMS if term in haystack)

    io_call_hits = sorted(set(c for c in calls if c in {
        "open", "read_text", "write_text", "mkdir", "loads", "dumps",
        "json", "print", "parse_args", "exists", "glob", "rglob"
    }))

    # Strong backtesting orchestration signals.
    if name.startswith("main") or "parse_args" in calls:
        classification = "keep_in_backtesting_cli_or_entrypoint"
    elif io_call_hits and orchestration_score >= decision_score:
        classification = "keep_in_backtesting_orchestration"
    elif decision_score >= 3 and orchestration_score <= 2:
        classification = "extract_decision_logic_to_engine"
    elif decision_score >= 3 and orchestration_score > 2:
        classification = "mixed_extract_core_keep_wrapper"
    elif decision_score > 0:
        classification = "review_possible_embedded_decision_logic"
    else:
        classification = "keep_in_backtesting_helper_or_io"

    target = choose_engine_target(name, source)

    if classification in {
        "extract_decision_logic_to_engine",
        "mixed_extract_core_keep_wrapper",
        "review_possible_embedded_decision_logic",
    } and target == "none":
        target = "signalforge.engines.strategy_selection.review_required"

    return {
        "classification": classification,
        "decision_score": decision_score,
        "orchestration_score": orchestration_score,
        "io_call_hits": io_call_hits,
        "recommended_engine_target": target,
    }


def main() -> None:
    blockers: List[str] = []
    warnings: List[str] = []
    function_rows: List[Dict[str, Any]] = []

    for file_name in BACKTESTING_FILES:
        path = Path(file_name)

        if not path.exists():
            blockers.append(f"missing_backtesting_file_{file_name}")
            continue

        text = read_text(path)
        lines = text.splitlines()
        tree = ast.parse(text)
        imports = imported_modules(tree)

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.col_offset == 0:
                source = get_function_source(lines, node)
                calls = called_names(node)
                assigned = assigned_names(node)
                classification = classify_function(node.name, source, calls)

                function_rows.append({
                    "path": str(path).replace("\\", "/"),
                    "function": node.name,
                    "lineno": node.lineno,
                    "end_lineno": getattr(node, "end_lineno", node.lineno),
                    "line_count": getattr(node, "end_lineno", node.lineno) - node.lineno + 1,
                    "imports": imports,
                    "calls": calls,
                    "assigned_names": assigned,
                    **classification,
                })

    classification_counts: Dict[str, int] = {}
    target_counts: Dict[str, int] = {}

    for row in function_rows:
        classification_counts[row["classification"]] = classification_counts.get(row["classification"], 0) + 1
        target_counts[row["recommended_engine_target"]] = target_counts.get(row["recommended_engine_target"], 0) + 1

    extraction_rows = [
        row for row in function_rows
        if row["classification"] in {
            "extract_decision_logic_to_engine",
            "mixed_extract_core_keep_wrapper",
            "review_possible_embedded_decision_logic",
        }
    ]

    high_confidence_extract_rows = [
        row for row in function_rows
        if row["classification"] == "extract_decision_logic_to_engine"
    ]

    mixed_rows = [
        row for row in function_rows
        if row["classification"] == "mixed_extract_core_keep_wrapper"
    ]

    warnings.append("stage36h_is_read_only_no_logic_moved")
    warnings.append("historical_wrappers_should_stay_in_backtesting")
    warnings.append("extract_only_reusable_decision_logic_into_engines")

    summary = {
        "adapter_type": "backtesting_decision_logic_extraction_map_builder",
        "artifact_type": "signalforge_backtesting_decision_logic_extraction_map",
        "contract": "backtesting_decision_logic_extraction_map",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,
        "backtesting_file_count": len(BACKTESTING_FILES),
        "function_count": len(function_rows),
        "extraction_candidate_count": len(extraction_rows),
        "high_confidence_extract_count": len(high_confidence_extract_rows),
        "mixed_extract_core_keep_wrapper_count": len(mixed_rows),
        "classification_counts": dict(sorted(classification_counts.items())),
        "target_counts": dict(sorted(target_counts.items())),
        "paper_order_created": False,
        "live_order_created": False,
        "live_trade_supported": False,
        "next_step": "stage36i_extract_one_high_confidence_decision_function_to_engine_with_parity_test",
    }

    summary_path = OUT_DIR / "signalforge_stage36h_backtesting_decision_logic_extraction_map_summary.json"
    rows_path = OUT_DIR / "signalforge_stage36h_backtesting_decision_logic_extraction_map_rows.jsonl"
    md_path = OUT_DIR / "signalforge_stage36h_backtesting_decision_logic_extraction_map.md"

    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    with rows_path.open("w", encoding="utf-8") as f:
        for row in function_rows:
            f.write(json.dumps(row) + "\n")

    md = [
        "# Stage 36H Backtesting Decision Logic Extraction Map",
        "",
        f"- is_ready: {summary['is_ready']}",
        f"- blocker_count: {summary['blocker_count']}",
        f"- function_count: {summary['function_count']}",
        f"- extraction_candidate_count: {summary['extraction_candidate_count']}",
        f"- high_confidence_extract_count: {summary['high_confidence_extract_count']}",
        f"- mixed_extract_core_keep_wrapper_count: {summary['mixed_extract_core_keep_wrapper_count']}",
        f"- paper_order_created: {summary['paper_order_created']}",
        f"- live_order_created: {summary['live_order_created']}",
        f"- live_trade_supported: {summary['live_trade_supported']}",
        "",
        "## Classification Counts",
        "",
    ]

    for key, value in summary["classification_counts"].items():
        md.append(f"- {key}: {value}")

    md.extend(["", "## Target Counts", ""])
    for key, value in summary["target_counts"].items():
        md.append(f"- {key}: {value}")

    md.extend([
        "",
        "## Extraction Candidates",
        "",
        "| classification | target | file | function | lines | decision score | orchestration score |",
        "|---|---|---|---|---:|---:|---:|",
    ])

    for row in extraction_rows:
        md.append(
            f"| {row['classification']} | `{row['recommended_engine_target']}` | "
            f"`{row['path']}` | `{row['function']}` | {row['lineno']}-{row['end_lineno']} | "
            f"{row['decision_score']} | {row['orchestration_score']} |"
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

    print("\n--- Stage 36H backtesting decision logic extraction map compact ---")
    for key in [
        "is_ready",
        "blocker_count",
        "warning_count",
        "backtesting_file_count",
        "function_count",
        "extraction_candidate_count",
        "high_confidence_extract_count",
        "mixed_extract_core_keep_wrapper_count",
        "paper_order_created",
        "live_order_created",
        "live_trade_supported",
    ]:
        print(f"{key}: {summary[key]}")

    print(f"summary_path: {summary_path}")
    print(f"rows_path: {rows_path}")
    print(f"md_path: {md_path}")

    print("\n--- Stage 36H classification counts ---")
    for key, value in summary["classification_counts"].items():
        print(f"{key}: {value}")

    print("\n--- Stage 36H target counts ---")
    for key, value in summary["target_counts"].items():
        print(f"{key}: {value}")

    print("\n--- Stage 36H extraction candidates compact ---")
    print("classification\ttarget\tpath\tfunction\tlines\tdecision_score\torchestration_score")
    for row in extraction_rows:
        print(
            f"{row['classification']}\t{row['recommended_engine_target']}\t"
            f"{row['path']}\t{row['function']}\t{row['lineno']}-{row['end_lineno']}\t"
            f"{row['decision_score']}\t{row['orchestration_score']}"
        )

    if blockers:
        print("\n--- Stage 36H blockers ---")
        for blocker in blockers:
            print(blocker)
        raise SystemExit(1)

    if warnings:
        print("\n--- Stage 36H warnings ---")
        for warning in warnings:
            print(warning)


if __name__ == "__main__":
    main()
