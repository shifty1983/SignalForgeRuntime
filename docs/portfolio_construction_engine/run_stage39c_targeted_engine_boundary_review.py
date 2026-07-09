import ast
import json
from pathlib import Path
from typing import Any, Dict, List


OUT_DIR = Path("docs/portfolio_construction_engine")

TARGETS = {
    "paper_runtime_reader": [
        Path("src/signalforge/engines/paper_trading/canonical_paper_review_bundle_reader.py"),
    ],
    "paper_runtime_engine_candidate": [
        Path("src/signalforge/engines/strategy_selection/allocation.py"),
        Path("src/signalforge/engines/strategy_selection/portfolio_candidate_input.py"),
        Path("src/signalforge/engines/strategy_selection/ranking.py"),
        Path("src/signalforge/engines/strategy_selection/selector.py"),
        Path("src/signalforge/engines/strategy_selection/selection_decision.py"),
    ],
    "research_backtesting_only": [
        Path("src/signalforge/backtesting/portfolio_value_ranked_allocator_v2.py"),
        Path("src/signalforge/backtesting/portfolio_position_sizing_replay.py"),
        Path("src/signalforge/backtesting/portfolio_equity_reconstruction.py"),
        Path("src/signalforge/backtesting/portfolio_metrics_report.py"),
        Path("src/signalforge/backtesting/portfolio_selected_trade_sequence.py"),
    ],
}

RUNTIME_BLOCKED_TOKENS = [
    "artifacts/",
    "artifacts\\",
    "argparse",
    "write_text",
    "open(",
    "subprocess",
    "sys.argv",
]

CANONICAL_ALLOWED_TOKENS = [
    "data/canonical",
    "data\\canonical",
    "signalforge_pipeline",
]


def ast_info(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    tree = ast.parse(text)

    functions = []
    classes = []
    imports = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = [arg.arg for arg in node.args.args]
            functions.append({
                "name": node.name,
                "args": args,
                "lineno": node.lineno,
            })
        elif isinstance(node, ast.ClassDef):
            classes.append({
                "name": node.name,
                "lineno": node.lineno,
            })
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")

    return {
        "text": text,
        "functions": functions,
        "classes": classes,
        "imports": sorted(set(imports)),
    }


def decision_for(role: str, text: str) -> str:
    lower = text.lower()

    if role == "paper_runtime_reader":
        return "paper_runtime_allowed_reader"

    if role == "research_backtesting_only":
        return "research_only_do_not_import_into_paper_runtime"

    blocked_hits = [token for token in RUNTIME_BLOCKED_TOKENS if token.lower() in lower]
    if blocked_hits:
        return "needs_wrapper_or_contract_review_before_paper_runtime"

    return "paper_runtime_engine_candidate"


def main() -> None:
    blockers: List[str] = []
    warnings: List[str] = [
        "stage39c_targeted_boundary_review_only",
        "paper_runtime_must_read_canonical_outputs_not_run_optimizer",
        "backtesting_allocator_is_research_only_until_ab_promoted",
    ]

    module_rows: List[Dict[str, Any]] = []
    function_rows: List[Dict[str, Any]] = []

    for role, paths in TARGETS.items():
        for path in paths:
            exists = path.exists()

            row: Dict[str, Any] = {
                "role": role,
                "path": str(path),
                "exists": exists,
                "size_bytes": path.stat().st_size if exists else None,
                "parse_ok": None,
                "parse_error": None,
                "function_count": 0,
                "class_count": 0,
                "import_count": 0,
                "runtime_blocked_token_hits": [],
                "canonical_allowed_token_hits": [],
                "boundary_decision": "missing",
            }

            if not exists:
                if role in {"paper_runtime_reader", "paper_runtime_engine_candidate"}:
                    blockers.append(f"missing_required_runtime_target_{path}")
                module_rows.append(row)
                continue

            try:
                info = ast_info(path)
                text = info["text"]
                lower = text.lower()

                blocked_hits = [
                    token for token in RUNTIME_BLOCKED_TOKENS
                    if token.lower() in lower
                ]

                canonical_hits = [
                    token for token in CANONICAL_ALLOWED_TOKENS
                    if token.lower() in lower
                ]

                row.update({
                    "parse_ok": True,
                    "parse_error": None,
                    "function_count": len(info["functions"]),
                    "class_count": len(info["classes"]),
                    "import_count": len(info["imports"]),
                    "imports": info["imports"],
                    "runtime_blocked_token_hits": blocked_hits,
                    "canonical_allowed_token_hits": canonical_hits,
                    "boundary_decision": decision_for(role, text),
                })

                for fn in info["functions"]:
                    function_rows.append({
                        "role": role,
                        "path": str(path),
                        "function": fn["name"],
                        "args": fn["args"],
                        "lineno": fn["lineno"],
                        "boundary_decision": row["boundary_decision"],
                    })

            except Exception as exc:
                row.update({
                    "parse_ok": False,
                    "parse_error": str(exc),
                    "boundary_decision": "parse_failed",
                })
                blockers.append(f"parse_failed_{path}_{exc}")

            module_rows.append(row)

    runtime_allowed = [
        row for row in module_rows
        if row["boundary_decision"] in {
            "paper_runtime_allowed_reader",
            "paper_runtime_engine_candidate",
        }
    ]

    needs_wrapper = [
        row for row in module_rows
        if row["boundary_decision"] == "needs_wrapper_or_contract_review_before_paper_runtime"
    ]

    research_only = [
        row for row in module_rows
        if row["boundary_decision"] == "research_only_do_not_import_into_paper_runtime"
    ]

    recommendation = {
        "paper_runtime_reader": "use canonical_paper_review_bundle_reader as the paper-runtime entrypoint",
        "portfolio_construction_runtime": "build a canonical portfolio construction reader/wrapper that consumes Stage 24/25/25A canonical outputs",
        "optimizer_runtime": "do_not_run_optimizer_in_paper_runtime",
        "optimizer_research": "A/B test portfolio_value_ranked_allocator_v2 or successors upstream before canonical promotion",
        "next_step": "stage39d_promote_canonical_portfolio_construction_reader",
    }

    summary = {
        "adapter_type": "targeted_engine_boundary_review_builder",
        "artifact_type": "signalforge_targeted_engine_boundary_review",
        "contract": "targeted_engine_boundary_review",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,
        "target_module_count": len(module_rows),
        "function_count": len(function_rows),
        "runtime_allowed_count": len(runtime_allowed),
        "needs_wrapper_count": len(needs_wrapper),
        "research_only_count": len(research_only),
        "recommendation": recommendation,
        "paper_order_created": False,
        "live_order_created": False,
        "live_trade_supported": False,
    }

    summary_path = OUT_DIR / "signalforge_stage39c_targeted_engine_boundary_review_summary.json"
    module_rows_path = OUT_DIR / "signalforge_stage39c_targeted_engine_boundary_review_module_rows.jsonl"
    function_rows_path = OUT_DIR / "signalforge_stage39c_targeted_engine_boundary_review_function_rows.jsonl"

    summary_path.write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")

    with module_rows_path.open("w", encoding="utf-8") as f:
        for row in module_rows:
            f.write(json.dumps(row, default=str) + "\n")

    with function_rows_path.open("w", encoding="utf-8") as f:
        for row in function_rows:
            f.write(json.dumps(row, default=str) + "\n")

    print("\n--- Stage 39C targeted engine boundary review compact ---")
    for key in [
        "is_ready",
        "blocker_count",
        "warning_count",
        "target_module_count",
        "function_count",
        "runtime_allowed_count",
        "needs_wrapper_count",
        "research_only_count",
        "paper_order_created",
        "live_order_created",
        "live_trade_supported",
    ]:
        print(f"{key}: {summary[key]}")

    print("\n--- Stage 39C module rows compact ---")
    print("role\tdecision\tblocked_tokens\tcanonical_tokens\tfunctions\tpath")
    for row in module_rows:
        print(
            f"{row['role']}\t{row['boundary_decision']}\t"
            f"{row.get('runtime_blocked_token_hits')}\t"
            f"{row.get('canonical_allowed_token_hits')}\t"
            f"{row['function_count']}\t{row['path']}"
        )

    print("\n--- Stage 39C recommendation ---")
    print(json.dumps(recommendation, indent=2, default=str))

    print(f"\nsummary_path: {summary_path}")
    print(f"module_rows_path: {module_rows_path}")
    print(f"function_rows_path: {function_rows_path}")

    if blockers:
        print("\n--- Stage 39C blockers ---")
        for blocker in blockers:
            print(blocker)
        raise SystemExit(1)

    print("\n--- Stage 39C warnings ---")
    for warning in warnings:
        print(warning)


if __name__ == "__main__":
    main()
