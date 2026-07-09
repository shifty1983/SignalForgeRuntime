from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any


REPO = Path(".").resolve()
OUT = REPO / "artifacts/stage40c5a_strategy_selection_pipeline_audit"

TARGETS = [
    REPO / "src/signalforge/backtesting/historical_strategy_selection_rows_builder.py",
    REPO / "src/signalforge/backtesting/historical_strategy_selection_rows_cli.py",
]

CORE_ROOT = REPO / "src/signalforge/engines/strategy_selection"

CORE_NAMESPACES = [
    "signalforge.engines.strategy_selection",
]

PIPELINE_CANDIDATES = [
    "selection_pipeline.py",
    "selection_decision.py",
    "selection_report.py",
    "selector.py",
    "rules.py",
    "allocation.py",
    "portfolio_candidate_input.py",
]

FOCUS_TERMS = [
    "selection",
    "selected",
    "strategy",
    "candidate",
    "rank",
    "score",
    "expectancy",
    "expected",
    "return",
    "win",
    "sample",
    "rule",
    "allocation",
    "portfolio",
    "group",
    "baseline",
    "pruned",
]

FOCUS_FUNCTIONS = {
    "build_historical_strategy_selection_rows",
    "build_historical_strategy_selection_rows_artifact",
    "select_strategy",
    "select_strategies",
    "apply_selection_rules",
    "rank_candidates",
    "score_candidate",
    "selection_breakdown",
}


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


def core_import_hits(import_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    hits = []

    for imp in import_rows:
        module = imp["module"] or ""
        name = imp["name"]
        full = module if name is None else f"{module}.{name}"

        for ns in CORE_NAMESPACES:
            if module == ns or module.startswith(ns + ".") or full == ns or full.startswith(ns + "."):
                hits.append({**imp, "matched_namespace": ns})

    return hits


def aliases(import_rows: list[dict[str, Any]]) -> dict[str, str]:
    out = {}

    for imp in import_rows:
        module = imp["module"] or ""
        name = imp["name"]
        asname = imp["asname"]

        for ns in CORE_NAMESPACES:
            if imp["kind"] == "import":
                if module == ns or module.startswith(ns + "."):
                    out[asname or module.split(".")[0]] = module

            if imp["kind"] == "from":
                full = f"{module}.{name}" if name else module
                if module == ns or module.startswith(ns + ".") or full == ns or full.startswith(ns + "."):
                    out[asname or name] = full

    return out


def core_call_hits(tree: ast.Module, alias_map: dict[str, str]) -> list[dict[str, Any]]:
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


def core_pipeline_file_status() -> list[dict[str, Any]]:
    rows = []
    for name in PIPELINE_CANDIDATES:
        path = CORE_ROOT / name
        rows.append({
            "path": rel(path),
            "exists": path.exists(),
            "is_file": path.is_file(),
        })
    return rows


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    reports = []

    total_core_import_hits = 0
    total_core_call_hits = 0

    for path in TARGETS:
        if not path.exists():
            reports.append({
                "path": rel(path),
                "exists": False,
                "verdict": "missing_target",
                "function_count": 0,
                "focus_function_count": 0,
                "core_import_hit_count": 0,
                "core_call_hit_count": 0,
            })
            continue

        tree = parse(path)
        imps = imports(tree)
        ihits = core_import_hits(imps)
        amap = aliases(imps)
        chits = core_call_hits(tree, amap)
        funcs = function_rows(path)

        total_core_import_hits += len(ihits)
        total_core_call_hits += len(chits)

        if ihits and chits:
            verdict = "verified_static_core_backed"
        elif any(f["is_focus_function"] for f in funcs):
            verdict = "not_verified_selection_logic_owned_by_builder"
        else:
            verdict = "related_file_no_focus_logic"

        reports.append({
            "path": rel(path),
            "exists": True,
            "verdict": verdict,
            "function_count": len(funcs),
            "focus_function_count": sum(1 for f in funcs if f["is_focus_function"]),
            "core_import_hit_count": len(ihits),
            "core_call_hit_count": len(chits),
            "core_import_hits": ihits,
            "core_call_hits": chits,
            "functions": funcs,
        })

    blocker_reports = [
        r for r in reports
        if r["verdict"] == "not_verified_selection_logic_owned_by_builder"
    ]

    selection_pipeline_path = CORE_ROOT / "selection_pipeline.py"

    summary = {
        "adapter_type": "stage40c5a_strategy_selection_pipeline_auditor",
        "artifact_type": "signalforge_stage40c5a_strategy_selection_pipeline_audit",
        "contract": "stage40c5a_strategy_selection_pipeline_audit",
        "is_ready": len(blocker_reports) == 0 and total_core_import_hits > 0 and total_core_call_hits > 0,
        "stage": "19_strategy_selection_full_baseline",
        "target_count": len(TARGETS),
        "total_core_import_hits": total_core_import_hits,
        "total_core_call_hits": total_core_call_hits,
        "blocker_report_count": len(blocker_reports),
        "selection_pipeline_exists": selection_pipeline_path.exists(),
        "core_pipeline_file_status": core_pipeline_file_status(),
        "reports": [
            {
                "path": r["path"],
                "exists": r["exists"],
                "verdict": r["verdict"],
                "function_count": r["function_count"],
                "focus_function_count": r["focus_function_count"],
                "core_import_hit_count": r["core_import_hit_count"],
                "core_call_hit_count": r["core_call_hit_count"],
            }
            for r in reports
        ],
        "paths": {
            "summary_path": "artifacts/stage40c5a_strategy_selection_pipeline_audit/signalforge_stage40c5a_strategy_selection_pipeline_audit_summary.json",
            "detail_path": "artifacts/stage40c5a_strategy_selection_pipeline_audit/signalforge_stage40c5a_strategy_selection_pipeline_audit_detail.json",
        },
    }

    detail = {
        **summary,
        "reports_detail": reports,
    }

    (OUT / "signalforge_stage40c5a_strategy_selection_pipeline_audit_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    (OUT / "signalforge_stage40c5a_strategy_selection_pipeline_audit_detail.json").write_text(
        json.dumps(detail, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
