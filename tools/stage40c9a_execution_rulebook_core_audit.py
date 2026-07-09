from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any


REPO = Path(".").resolve()
OUT = REPO / "artifacts/stage40c9a_execution_rulebook_core_audit"

SEARCH_ROOTS = [
    REPO / "src/signalforge/backtesting",
    REPO / "tools",
]

EXPECTED_CORE = REPO / "src/signalforge/engines/execution/translation_rulebook.py"

CORE_NAMESPACES = [
    "signalforge.engines.execution",
    "signalforge.engines.portfolio_construction",
]

MARKERS = [
    "rulebook",
    "translation_rulebook",
    "execution_translation",
    "execution rulebook",
    "close_rule",
    "defense_rule",
    "open_rule",
    "broker_capability",
    "paper_trade_supported",
    "live_trade_supported",
    "execution_gap",
    "unmapped_exit",
    "execution_translation_rulebook",
    "portfolio_execution_translation",
]

NAME_HINTS = [
    "rulebook",
    "translation",
    "execution",
    "deployment_readiness",
    "live_translation",
]

FOCUS_FUNCTIONS = {
    "build_portfolio_execution_translation_rulebook",
    "build_execution_translation_rulebook",
    "build_rulebook",
    "translate_execution",
    "map_close_rules",
    "map_defense_rules",
    "map_open_rules",
    "execution_gap_audit",
    "main",
}

FOCUS_TERMS = [
    "rulebook",
    "execution",
    "translation",
    "broker",
    "capability",
    "paper",
    "live",
    "close",
    "defense",
    "open",
    "strategy",
    "mapped",
    "unmapped",
    "unsupported",
    "gap",
    "trade",
    "order",
    "instruction",
    "blocker",
    "warning",
]


def rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def should_skip(path: Path) -> bool:
    return bool(set(path.parts) & {".git", ".venv", "venv", "__pycache__", "artifacts"})


def is_stage_tool(path: Path) -> bool:
    return path.name.startswith("stage40c")


def discover_files() -> list[Path]:
    files = []

    for root in SEARCH_ROOTS:
        if not root.exists():
            continue

        for path in root.rglob("*.py"):
            if should_skip(path) or is_stage_tool(path):
                continue

            try:
                lowered = read(path).lower()
            except UnicodeDecodeError:
                continue

            marker_hit = any(m in lowered for m in MARKERS)
            name_hit = any(h in path.name.lower() for h in NAME_HINTS)

            if marker_hit and name_hit:
                files.append(path)

    seen = set()
    out = []

    for path in files:
        key = rel(path)
        if key not in seen:
            seen.add(key)
            out.append(path)

    return sorted(out, key=rel)


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


def classify(path: Path) -> str:
    name = path.name.lower()

    if "execution_translation_rulebook" in name or "translation_rulebook" in name:
        return "execution_translation_rulebook_core_candidate"

    if "deployment_readiness" in name or "live_translation" in name:
        return "deployment_review_or_translation_related"

    if "rulebook" in name:
        return "rulebook_related"

    return "execution_rulebook_related_unknown"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    files = discover_files()
    reports = []

    total_core_import_hits = 0
    total_core_call_hits = 0

    for path in files:
        tree = parse(path)
        imps = imports(tree)

        core_imports = namespace_hits(imps, CORE_NAMESPACES)
        core_aliases = aliases(imps, CORE_NAMESPACES)
        core_calls = call_hits(tree, core_aliases)

        funcs = function_rows(path)
        focus_count = sum(1 for f in funcs if f["is_focus_function"])
        focus_hit_count = sum(f["focus_hit_count"] for f in funcs)

        stage_guess = classify(path)

        total_core_import_hits += len(core_imports)
        total_core_call_hits += len(core_calls)

        if core_imports and core_calls:
            verdict = "verified_static_execution_core_backed"
        elif stage_guess == "execution_translation_rulebook_core_candidate":
            verdict = "not_verified_execution_rulebook_logic_owned_by_builder"
        elif focus_count > 0 or focus_hit_count > 80:
            verdict = "not_verified_execution_rulebook_or_review_logic_owned_by_backtesting"
        else:
            verdict = "related_file_no_focus_logic"

        reports.append({
            "path": rel(path),
            "stage_guess": stage_guess,
            "verdict": verdict,
            "function_count": len(funcs),
            "focus_function_count": focus_count,
            "focus_hit_count": focus_hit_count,
            "core_import_hit_count": len(core_imports),
            "core_call_hit_count": len(core_calls),
            "core_import_hits": core_imports,
            "core_call_hits": core_calls,
            "functions": funcs,
        })

    blocker_reports = [
        r for r in reports
        if r["verdict"].startswith("not_verified")
    ]

    production_candidates = [
        r for r in reports
        if r["stage_guess"] == "execution_translation_rulebook_core_candidate"
    ]

    summary = {
        "adapter_type": "stage40c9a_execution_rulebook_core_auditor",
        "artifact_type": "signalforge_stage40c9a_execution_rulebook_core_audit",
        "contract": "stage40c9a_execution_rulebook_core_audit",
        "is_ready": len(blocker_reports) == 0 and EXPECTED_CORE.exists() and total_core_import_hits > 0 and total_core_call_hits > 0,
        "stage": "26_execution_translation_rulebook",
        "file_count": len(files),
        "expected_core_path": rel(EXPECTED_CORE),
        "expected_core_exists": EXPECTED_CORE.exists(),
        "production_candidate_count": len(production_candidates),
        "total_core_import_hits": total_core_import_hits,
        "total_core_call_hits": total_core_call_hits,
        "blocker_report_count": len(blocker_reports),
        "reports": [
            {
                "path": r["path"],
                "stage_guess": r["stage_guess"],
                "verdict": r["verdict"],
                "function_count": r["function_count"],
                "focus_function_count": r["focus_function_count"],
                "focus_hit_count": r["focus_hit_count"],
                "core_import_hit_count": r["core_import_hit_count"],
                "core_call_hit_count": r["core_call_hit_count"],
            }
            for r in reports
        ],
        "paths": {
            "summary_path": "artifacts/stage40c9a_execution_rulebook_core_audit/signalforge_stage40c9a_execution_rulebook_core_audit_summary.json",
            "detail_path": "artifacts/stage40c9a_execution_rulebook_core_audit/signalforge_stage40c9a_execution_rulebook_core_audit_detail.json",
        },
    }

    detail = {
        **summary,
        "reports_detail": reports,
    }

    (OUT / "signalforge_stage40c9a_execution_rulebook_core_audit_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    (OUT / "signalforge_stage40c9a_execution_rulebook_core_audit_detail.json").write_text(
        json.dumps(detail, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
