import ast
import json
from pathlib import Path
from typing import Any, Dict, List


OUT_DIR = Path("docs/portfolio_construction_engine")
SRC_ROOT = Path("src")

KEYWORD_GROUPS = {
    "optimizer": [
        "optimizer",
        "optimization",
        "optimize",
        "objective",
        "constraint",
        "grid",
        "walkforward",
        "walk_forward",
    ],
    "portfolio_construction": [
        "portfolio_construction",
        "construction",
        "allocator",
        "allocation",
        "allocate",
        "risk_budget",
        "capital_allocation",
    ],
    "position_sizing": [
        "position_sizing",
        "sizing",
        "size_position",
        "capital",
        "risk_per_trade",
        "max_risk",
    ],
    "equity_reconstruction": [
        "equity_reconstruction",
        "reconstruction",
        "equity_curve",
        "portfolio_metrics",
        "drawdown",
        "sharpe",
        "sortino",
    ],
    "strategy_selection": [
        "strategy_selection",
        "selector",
        "ranked",
        "rank",
        "eligibility",
    ],
}

ENTRYPOINT_PREFIXES = (
    "build_",
    "run_",
    "select_",
    "rank_",
    "allocate_",
    "optimize_",
    "construct_",
    "size_",
    "replay_",
    "score_",
    "validate_",
)


def classify_path(path: Path, text: str) -> List[str]:
    haystack = f"{str(path).lower()} {text.lower()}"
    hits = []
    for group, terms in KEYWORD_GROUPS.items():
        if any(term in haystack for term in terms):
            hits.append(group)
    return hits


def ownership_bucket(path: Path) -> str:
    text = str(path).replace("\\", "/").lower()

    if "/backtesting/" in text or text.endswith("_cli.py"):
        return "backtesting_or_cli"
    if "/engines/" in text:
        return "engine_candidate"
    if "/strategy_selection/" in text:
        return "strategy_selection_engine_candidate"
    if "/portfolio" in text:
        return "portfolio_domain_candidate"
    if "/legacy" in text:
        return "legacy_or_research"
    return "unclassified_src"


def ast_summary(path: Path) -> Dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        tree = ast.parse(text)
    except Exception as exc:
        return {
            "parse_ok": False,
            "parse_error": str(exc),
            "functions": [],
            "classes": [],
            "entrypoints": [],
            "imports": [],
        }

    functions = []
    classes = []
    imports = []

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            functions.append(node.name)
        elif isinstance(node, ast.AsyncFunctionDef):
            functions.append(node.name)
        elif isinstance(node, ast.ClassDef):
            classes.append(node.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imports.append(module)

    entrypoints = [
        name for name in functions
        if name.startswith(ENTRYPOINT_PREFIXES)
    ]

    return {
        "parse_ok": True,
        "parse_error": None,
        "functions": sorted(functions),
        "classes": sorted(classes),
        "entrypoints": sorted(entrypoints),
        "imports": sorted(set(imports)),
    }


blockers: List[str] = []
warnings: List[str] = [
    "stage39b_src_inventory_only_no_runtime_changes",
    "paper_trading_should_consume_canonical_outputs_not_run_optimization",
    "optimizer_logic_requires_ab_test_before_paper_promotion",
]

if not SRC_ROOT.exists():
    blockers.append(f"missing_src_root_{SRC_ROOT}")

module_rows: List[Dict[str, Any]] = []
entrypoint_rows: List[Dict[str, Any]] = []

if not blockers:
    for path in sorted(SRC_ROOT.rglob("*.py"), key=lambda p: str(p).lower()):
        if "__pycache__" in path.parts:
            continue

        try:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
        except Exception as exc:
            module_rows.append({
                "path": str(path),
                "read_ok": False,
                "read_error": str(exc),
                "category_hits": [],
                "ownership_bucket": ownership_bucket(path),
            })
            continue

        category_hits = classify_path(path, text)
        if not category_hits:
            continue

        ast_info = ast_summary(path)
        row = {
            "path": str(path),
            "read_ok": True,
            "read_error": None,
            "category_hits": category_hits,
            "ownership_bucket": ownership_bucket(path),
            "parse_ok": ast_info["parse_ok"],
            "parse_error": ast_info["parse_error"],
            "function_count": len(ast_info["functions"]),
            "class_count": len(ast_info["classes"]),
            "entrypoint_count": len(ast_info["entrypoints"]),
            "entrypoints": ast_info["entrypoints"],
            "classes": ast_info["classes"],
            "size_bytes": path.stat().st_size,
        }
        module_rows.append(row)

        for entrypoint in ast_info["entrypoints"]:
            entrypoint_rows.append({
                "path": str(path),
                "entrypoint": entrypoint,
                "category_hits": category_hits,
                "ownership_bucket": ownership_bucket(path),
            })

category_counts: Dict[str, int] = {}
ownership_counts: Dict[str, int] = {}

for row in module_rows:
    ownership_counts[row["ownership_bucket"]] = ownership_counts.get(row["ownership_bucket"], 0) + 1
    for category in row["category_hits"]:
        category_counts[category] = category_counts.get(category, 0) + 1

engine_candidate_rows = [
    row for row in module_rows
    if row["ownership_bucket"] in {
        "engine_candidate",
        "strategy_selection_engine_candidate",
        "portfolio_domain_candidate",
    }
]

backtesting_rows = [
    row for row in module_rows
    if row["ownership_bucket"] == "backtesting_or_cli"
]

recommendation = {
    "paper_runtime_policy": "consume_canonical_outputs_only",
    "optimization_policy": "research_backtesting_only_until_ab_promoted",
    "portfolio_construction_policy": "wrap_or_read_promoted_canonical_stage_24_25_25A_outputs_before_importing_optimizers",
    "next_step": "inspect_engine_candidate_modules_and_choose_reader_or_adapter_boundary",
}

summary = {
    "adapter_type": "src_optimizer_portfolio_construction_inventory_builder",
    "artifact_type": "signalforge_src_optimizer_portfolio_construction_inventory",
    "contract": "src_optimizer_portfolio_construction_inventory",
    "is_ready": len(blockers) == 0,
    "blocker_count": len(blockers),
    "blockers": blockers,
    "warning_count": len(warnings),
    "warnings": warnings,
    "src_root": str(SRC_ROOT),
    "matched_module_count": len(module_rows),
    "entrypoint_count": len(entrypoint_rows),
    "engine_candidate_module_count": len(engine_candidate_rows),
    "backtesting_or_cli_module_count": len(backtesting_rows),
    "category_counts": category_counts,
    "ownership_counts": ownership_counts,
    "recommendation": recommendation,
    "paper_order_created": False,
    "live_order_created": False,
    "live_trade_supported": False,
}

summary_path = OUT_DIR / "signalforge_stage39b_src_optimizer_portfolio_construction_inventory_summary.json"
module_rows_path = OUT_DIR / "signalforge_stage39b_src_optimizer_portfolio_construction_module_rows.jsonl"
entrypoint_rows_path = OUT_DIR / "signalforge_stage39b_src_optimizer_portfolio_construction_entrypoint_rows.jsonl"

summary_path.write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")

with module_rows_path.open("w", encoding="utf-8") as f:
    for row in module_rows:
        f.write(json.dumps(row, default=str) + "\n")

with entrypoint_rows_path.open("w", encoding="utf-8") as f:
    for row in entrypoint_rows:
        f.write(json.dumps(row, default=str) + "\n")

print("\n--- Stage 39B src optimizer / portfolio construction inventory compact ---")
for key in [
    "is_ready",
    "blocker_count",
    "warning_count",
    "matched_module_count",
    "entrypoint_count",
    "engine_candidate_module_count",
    "backtesting_or_cli_module_count",
    "paper_order_created",
    "live_order_created",
    "live_trade_supported",
]:
    print(f"{key}: {summary[key]}")

print("\n--- Stage 39B category counts ---")
print(json.dumps(category_counts, indent=2, default=str))

print("\n--- Stage 39B ownership counts ---")
print(json.dumps(ownership_counts, indent=2, default=str))

print("\n--- Stage 39B engine candidate modules compact ---")
print("ownership\tcategories\tentrypoints\tpath")
for row in engine_candidate_rows[:80]:
    print(
        f"{row['ownership_bucket']}\t{','.join(row['category_hits'])}\t"
        f"{','.join(row['entrypoints'][:8])}\t{row['path']}"
    )

print("\n--- Stage 39B backtesting / cli modules compact ---")
print("ownership\tcategories\tentrypoints\tpath")
for row in backtesting_rows[:80]:
    print(
        f"{row['ownership_bucket']}\t{','.join(row['category_hits'])}\t"
        f"{','.join(row['entrypoints'][:8])}\t{row['path']}"
    )

print(f"\nsummary_path: {summary_path}")
print(f"module_rows_path: {module_rows_path}")
print(f"entrypoint_rows_path: {entrypoint_rows_path}")

if blockers:
    print("\n--- Stage 39B blockers ---")
    for blocker in blockers:
        print(blocker)
    raise SystemExit(1)

print("\n--- Stage 39B warnings ---")
for warning in warnings:
    print(warning)
