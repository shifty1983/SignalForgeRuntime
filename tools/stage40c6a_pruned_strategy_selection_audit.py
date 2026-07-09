from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any


REPO = Path(".").resolve()
OUT = REPO / "artifacts/stage40c6a_pruned_strategy_selection_audit"

SEARCH_ROOTS = [
    REPO / "src/signalforge/backtesting",
    REPO / "tools",
]

CORE_NAMESPACES = [
    "signalforge.engines.strategy_selection",
]

MARKERS = [
    "strategy_selection_pruned",
    "selection_pruned",
    "pruned_strategy_selection",
    "pruned selection",
    "walkforward_prune",
    "walk_forward_prune",
    "prune",
    "pruned",
    "selected_strategy",
    "selected strategy",
    "selection_state",
    "selection_status",
]

REQUIRED_STAGE21_CONTEXT_MARKERS = [
    "strategy",
    "selection",
    "prune",
]

FOCUS_TERMS = [
    "strategy",
    "selection",
    "selected",
    "prune",
    "pruned",
    "candidate",
    "rank",
    "score",
    "expectancy",
    "sample",
    "return",
    "win",
    "cohort",
    "risk",
    "rule",
    "threshold",
    "skip",
    "blocked",
    "portfolio",
]

FOCUS_FUNCTIONS = {
    "build_pruned_strategy_selection_rows",
    "build_strategy_selection_pruned_rows",
    "build_historical_strategy_selection_pruned_rows",
    "build_pruned_selection_rows",
    "prune_strategy_selection_rows",
    "prune_selection_rows",
    "apply_pruning",
    "should_prune",
    "select_pruned_strategy",
    "build_pruned_strategy_selection_artifact",
    "main",
}


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

            marker_hits = [m for m in MARKERS if m.lower() in lowered]
            context_hits = [m for m in REQUIRED_STAGE21_CONTEXT_MARKERS if m.lower() in lowered]

            # Avoid catching every later portfolio file that merely says "pruned".
            name_hit = any(token in path.name.lower() for token in ["prun", "selection", "selected"])
            strong_context = len(context_hits) >= 2

            if marker_hits and (name_hit or strong_context):
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


def marker_hits_for(path: Path) -> list[str]:
    lowered = read(path).lower()
    return [m for m in MARKERS if m.lower() in lowered]


def classify(path: Path, funcs: list[dict[str, Any]], marker_hits: list[str]) -> str:
    lowered_name = path.name.lower()
    names = {f["name"] for f in funcs}

    if "prun" in lowered_name and "selection" in lowered_name:
        return "21_strategy_selection_pruned"

    if any(name in names for name in {
        "build_pruned_strategy_selection_rows",
        "build_strategy_selection_pruned_rows",
        "build_historical_strategy_selection_pruned_rows",
        "prune_strategy_selection_rows",
        "prune_selection_rows",
    }):
        return "21_strategy_selection_pruned"

    if "walkforward_prune" in " ".join(marker_hits) or "walk_forward_prune" in " ".join(marker_hits):
        return "21_strategy_selection_pruned_or_validation"

    return "pruned_selection_related_unknown"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    files = discover_files()
    reports = []

    total_core_import_hits = 0
    total_core_call_hits = 0

    for path in files:
        tree = parse(path)
        imps = imports(tree)
        ihits = core_import_hits(imps)
        amap = aliases(imps)
        chits = core_call_hits(tree, amap)
        funcs = function_rows(path)
        markers = marker_hits_for(path)

        total_core_import_hits += len(ihits)
        total_core_call_hits += len(chits)

        stage_guess = classify(path, funcs, markers)

        focus_count = sum(1 for f in funcs if f["is_focus_function"])
        focus_hit_count = sum(f["focus_hit_count"] for f in funcs)

        if ihits and chits:
            verdict = "verified_static_core_backed"
        elif stage_guess.startswith("21_") and (focus_count > 0 or focus_hit_count > 20):
            verdict = "not_verified_pruned_selection_logic_owned_by_builder"
        elif "prun" in path.name.lower() and focus_hit_count > 20:
            verdict = "not_verified_pruned_selection_or_validation_logic_owned_by_builder"
        else:
            verdict = "related_file_no_focus_logic"

        reports.append({
            "path": rel(path),
            "stage_guess": stage_guess,
            "verdict": verdict,
            "marker_hits": markers,
            "function_count": len(funcs),
            "focus_function_count": focus_count,
            "focus_hit_count": focus_hit_count,
            "core_import_hit_count": len(ihits),
            "core_call_hit_count": len(chits),
            "core_import_hits": ihits,
            "core_call_hits": chits,
            "functions": funcs,
        })

    blocker_reports = [
        r for r in reports
        if r["verdict"].startswith("not_verified")
    ]

    likely_stage21 = [
        r for r in reports
        if r["stage_guess"].startswith("21_")
    ]

    summary = {
        "adapter_type": "stage40c6a_pruned_strategy_selection_auditor",
        "artifact_type": "signalforge_stage40c6a_pruned_strategy_selection_audit",
        "contract": "stage40c6a_pruned_strategy_selection_audit",
        "is_ready": len(blocker_reports) == 0 and len(likely_stage21) > 0,
        "stage": "21_strategy_selection_pruned",
        "file_count": len(files),
        "likely_stage21_file_count": len(likely_stage21),
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
                "marker_hits": r["marker_hits"],
            }
            for r in reports
        ],
        "paths": {
            "summary_path": "artifacts/stage40c6a_pruned_strategy_selection_audit/signalforge_stage40c6a_pruned_strategy_selection_audit_summary.json",
            "detail_path": "artifacts/stage40c6a_pruned_strategy_selection_audit/signalforge_stage40c6a_pruned_strategy_selection_audit_detail.json",
        },
    }

    detail = {
        **summary,
        "reports_detail": reports,
    }

    (OUT / "signalforge_stage40c6a_pruned_strategy_selection_audit_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    (OUT / "signalforge_stage40c6a_pruned_strategy_selection_audit_detail.json").write_text(
        json.dumps(detail, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
