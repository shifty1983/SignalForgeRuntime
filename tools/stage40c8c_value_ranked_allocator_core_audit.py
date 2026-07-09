from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any


REPO = Path(".").resolve()
OUT = REPO / "artifacts/stage40c8c_value_ranked_allocator_core_audit"

TARGETS = [
    REPO / "src/signalforge/backtesting/portfolio_value_ranked_allocator_v2.py",
    REPO / "src/signalforge/backtesting/portfolio_value_ranked_allocator_v2_1_cli.py",
]

EXPECTED_CORE = REPO / "src/signalforge/engines/portfolio_construction/value_ranked_allocator.py"

CORE_NAMESPACES = [
    "signalforge.engines.portfolio_construction",
]

RELATED_NAMESPACES = [
    "signalforge.engines.strategy_selection",
]

FOCUS_FUNCTIONS = {
    "rank_value",
    "build_rank_payload",
    "run_allocator",
    "expectancy_score_component",
    "bucket_units",
    "get_unit_risk",
    "get_selected_legs",
    "build",
    "main",
}

FOCUS_TERMS = [
    "value",
    "rank",
    "ranked",
    "allocator",
    "allocation",
    "portfolio",
    "heat",
    "risk",
    "budget",
    "capital",
    "quantity",
    "contract",
    "bucket",
    "expectancy",
    "score",
    "selected",
    "trade",
    "sizing",
    "skip",
    "priority",
    "profit_factor",
    "win_rate",
]


def rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def parse(path: Path) -> ast.Module:
    return ast.parse(read(path), filename=str(path))


def call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = call_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return None


def imports(tree: ast.Module) -> list[dict[str, Any]]:
    rows = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                rows.append({
                    "kind": "import",
                    "module": alias.name,
                    "name": None,
                    "asname": alias.asname,
                    "line": node.lineno,
                })
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                rows.append({
                    "kind": "from",
                    "module": node.module or "",
                    "name": alias.name,
                    "asname": alias.asname,
                    "line": node.lineno,
                })

    return rows


def namespace_hits(import_rows: list[dict[str, Any]], namespaces: list[str]) -> list[dict[str, Any]]:
    hits = []

    for imp in import_rows:
        module = imp["module"] or ""
        name = imp["name"]
        full = module if name is None else f"{module}.{name}"

        for ns in namespaces:
            if module == ns or module.startswith(ns + ".") or full == ns or full.startswith(ns + "."):
                hits.append({**imp, "matched_namespace": ns})

    return hits


def aliases(import_rows: list[dict[str, Any]], namespaces: list[str]) -> dict[str, str]:
    out = {}

    for imp in import_rows:
        module = imp["module"] or ""
        name = imp["name"]
        asname = imp["asname"]

        for ns in namespaces:
            if imp["kind"] == "import":
                if module == ns or module.startswith(ns + "."):
                    out[asname or module.split(".")[0]] = module

            if imp["kind"] == "from":
                full = f"{module}.{name}" if name else module
                if module == ns or module.startswith(ns + ".") or full == ns or full.startswith(ns + "."):
                    out[asname or name] = full

    return out


def call_hits(tree: ast.Module, alias_map: dict[str, str]) -> list[dict[str, Any]]:
    hits = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            cname = call_name(node.func)
            if not cname:
                continue

            first = cname.split(".")[0]
            if first in alias_map:
                hits.append({
                    "line": node.lineno,
                    "call": cname,
                    "resolved_core_target": alias_map[first],
                })

    return sorted(hits, key=lambda r: (r["line"], r["call"]))


def function_rows(path: Path) -> list[dict[str, Any]]:
    source = read(path)
    tree = ast.parse(source, filename=str(path))
    rows = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            segment = ast.get_source_segment(source, node) or ""
            lowered = segment.lower()
            focus_hits = {term: lowered.count(term) for term in FOCUS_TERMS}

            rows.append({
                "name": node.name,
                "line": node.lineno,
                "end_line": getattr(node, "end_lineno", None),
                "is_focus_function": node.name in FOCUS_FUNCTIONS,
                "focus_hit_count": sum(focus_hits.values()),
                "focus_hits": focus_hits,
            })

    return sorted(rows, key=lambda r: (r["line"], r["name"]))


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    reports = []
    total_core_import_hits = 0
    total_core_call_hits = 0
    total_related_import_hits = 0
    total_related_call_hits = 0

    for path in TARGETS:
        if not path.exists():
            reports.append({
                "path": rel(path),
                "exists": False,
                "verdict": "missing_target",
                "function_count": 0,
                "focus_function_count": 0,
                "focus_hit_count": 0,
                "core_import_hit_count": 0,
                "core_call_hit_count": 0,
                "related_import_hit_count": 0,
                "related_call_hit_count": 0,
            })
            continue

        tree = parse(path)
        imps = imports(tree)

        core_imports = namespace_hits(imps, CORE_NAMESPACES)
        core_aliases = aliases(imps, CORE_NAMESPACES)
        core_calls = call_hits(tree, core_aliases)

        related_imports = namespace_hits(imps, RELATED_NAMESPACES)
        related_aliases = aliases(imps, RELATED_NAMESPACES)
        related_calls = call_hits(tree, related_aliases)

        funcs = function_rows(path)
        focus_count = sum(1 for f in funcs if f["is_focus_function"])
        focus_hit_count = sum(f["focus_hit_count"] for f in funcs)

        total_core_import_hits += len(core_imports)
        total_core_call_hits += len(core_calls)
        total_related_import_hits += len(related_imports)
        total_related_call_hits += len(related_calls)

        if core_imports and core_calls:
            verdict = "verified_static_portfolio_construction_core_backed"
        elif focus_count > 0 or focus_hit_count > 50:
            verdict = "not_verified_value_ranked_allocator_logic_owned_by_backtesting"
        else:
            verdict = "related_file_no_focus_logic"

        reports.append({
            "path": rel(path),
            "exists": True,
            "verdict": verdict,
            "function_count": len(funcs),
            "focus_function_count": focus_count,
            "focus_hit_count": focus_hit_count,
            "core_import_hit_count": len(core_imports),
            "core_call_hit_count": len(core_calls),
            "related_import_hit_count": len(related_imports),
            "related_call_hit_count": len(related_calls),
            "core_import_hits": core_imports,
            "core_call_hits": core_calls,
            "related_import_hits": related_imports,
            "related_call_hits": related_calls,
            "functions": funcs,
        })

    blocker_reports = [
        r for r in reports
        if r["verdict"] == "not_verified_value_ranked_allocator_logic_owned_by_backtesting"
    ]

    summary = {
        "adapter_type": "stage40c8c_value_ranked_allocator_core_auditor",
        "artifact_type": "signalforge_stage40c8c_value_ranked_allocator_core_audit",
        "contract": "stage40c8c_value_ranked_allocator_core_audit",
        "is_ready": len(blocker_reports) == 0 and EXPECTED_CORE.exists() and total_core_import_hits > 0 and total_core_call_hits > 0,
        "stage": "24A_value_ranked_allocator",
        "target_count": len(TARGETS),
        "expected_core_path": rel(EXPECTED_CORE),
        "expected_core_exists": EXPECTED_CORE.exists(),
        "total_core_import_hits": total_core_import_hits,
        "total_core_call_hits": total_core_call_hits,
        "total_related_import_hits": total_related_import_hits,
        "total_related_call_hits": total_related_call_hits,
        "blocker_report_count": len(blocker_reports),
        "reports": [
            {
                "path": r["path"],
                "exists": r["exists"],
                "verdict": r["verdict"],
                "function_count": r["function_count"],
                "focus_function_count": r["focus_function_count"],
                "focus_hit_count": r["focus_hit_count"],
                "core_import_hit_count": r["core_import_hit_count"],
                "core_call_hit_count": r["core_call_hit_count"],
                "related_import_hit_count": r["related_import_hit_count"],
                "related_call_hit_count": r["related_call_hit_count"],
            }
            for r in reports
        ],
        "paths": {
            "summary_path": "artifacts/stage40c8c_value_ranked_allocator_core_audit/signalforge_stage40c8c_value_ranked_allocator_core_audit_summary.json",
            "detail_path": "artifacts/stage40c8c_value_ranked_allocator_core_audit/signalforge_stage40c8c_value_ranked_allocator_core_audit_detail.json",
        },
    }

    detail = {
        **summary,
        "reports_detail": reports,
    }

    (OUT / "signalforge_stage40c8c_value_ranked_allocator_core_audit_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    (OUT / "signalforge_stage40c8c_value_ranked_allocator_core_audit_detail.json").write_text(
        json.dumps(detail, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
