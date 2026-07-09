from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any


REPO = Path(".").resolve()
OUT = REPO / "artifacts/stage40c2a_term_structure_core_call_verification"

BT_PATTERNS = [
    "src/signalforge/backtesting/*term_structure*augmented*candidate*.py",
    "src/signalforge/backtesting/*term_structure*candidate*.py",
    "src/signalforge/backtesting/*augmented*candidates*.py",
]

CORE_ROOT = REPO / "src/signalforge/engines/strategy_selection"

REQUIRED_CORE_NAMESPACES = [
    "signalforge.engines.strategy_selection",
]

FOCUS_FUNCTIONS = {
    "derived_term_structure_status",
    "should_generate_term_structure",
    "term_structure_state",
    "term_structure_shape",
    "extract_status_map",
}


FOCUS_TERMS = [
    "term",
    "structure",
    "candidate",
    "strategy",
    "calendar",
    "diagonal",
    "state",
    "status",
    "available",
    "eligible",
    "risk",
    "edge",
    "return",
    "generate",
    "augment",
]


def rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def discover_files() -> list[Path]:
    files: list[Path] = []
    for pattern in BT_PATTERNS:
        files.extend(REPO.glob(pattern))

    seen = set()
    out = []
    for path in files:
        if path.exists() and path.is_file():
            key = rel(path)
            if key not in seen:
                seen.add(key)
                out.append(path)

    return sorted(out, key=rel)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


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
                rows.append(
                    {
                        "kind": "import",
                        "module": alias.name,
                        "name": None,
                        "asname": alias.asname,
                        "line": node.lineno,
                    }
                )
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                rows.append(
                    {
                        "kind": "from",
                        "module": node.module or "",
                        "name": alias.name,
                        "asname": alias.asname,
                        "line": node.lineno,
                    }
                )
    return rows


def import_hits(import_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    hits = []
    for imp in import_rows:
        module = imp["module"] or ""
        full = module if imp["name"] is None else f"{module}.{imp['name']}"
        for ns in REQUIRED_CORE_NAMESPACES:
            if module == ns or module.startswith(ns + ".") or full == ns or full.startswith(ns + "."):
                hits.append({**imp, "matched_namespace": ns})
    return hits


def import_aliases(import_rows: list[dict[str, Any]]) -> dict[str, str]:
    aliases: dict[str, str] = {}

    for imp in import_rows:
        module = imp["module"] or ""
        name = imp["name"]
        asname = imp["asname"]

        for ns in REQUIRED_CORE_NAMESPACES:
            if imp["kind"] == "import":
                if module == ns or module.startswith(ns + "."):
                    aliases[asname or module.split(".")[0]] = module

            if imp["kind"] == "from":
                full = f"{module}.{name}" if name else module
                if module == ns or module.startswith(ns + ".") or full == ns or full.startswith(ns + "."):
                    aliases[asname or name] = full

    return aliases


def core_call_hits(tree: ast.Module, aliases: dict[str, str]) -> list[dict[str, Any]]:
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            cname = call_name(node.func)
            if not cname:
                continue

            first = cname.split(".")[0]
            if first in aliases:
                hits.append(
                    {
                        "line": node.lineno,
                        "call": cname,
                        "resolved_core_target": aliases[first],
                    }
                )

    return sorted(hits, key=lambda r: (r["line"], r["call"]))


def function_rows(path: Path) -> list[dict[str, Any]]:
    source = read(path)
    tree = ast.parse(source, filename=str(path))
    rows = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            segment = ast.get_source_segment(source, node) or ""
            lowered = segment.lower()
            hits = {term: lowered.count(term) for term in FOCUS_TERMS}

            rows.append(
                {
                    "file": rel(path),
                    "name": node.name,
                    "line": node.lineno,
                    "end_line": getattr(node, "end_lineno", None),
                    "is_focus_function": node.name in FOCUS_FUNCTIONS,
                    "focus_hit_count": sum(hits.values()),
                    "focus_hits": hits,
                }
            )

    return sorted(rows, key=lambda r: (r["line"], r["name"]))


def core_functions() -> list[dict[str, Any]]:
    rows = []

    if not CORE_ROOT.exists():
        return rows

    for path in sorted(CORE_ROOT.rglob("*.py")):
        if path.name == "__init__.py":
            continue

        try:
            source = read(path)
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            rows.append(
                {
                    "file": rel(path),
                    "name": None,
                    "qualified": None,
                    "line": None,
                    "syntax_error": str(exc),
                    "focus_hit_count": 0,
                    "focus_hits": {},
                    "is_public": False,
                }
            )
            continue

        module = "signalforge." + rel(path).replace("src/signalforge/", "").replace("/", ".").removesuffix(".py")

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                segment = ast.get_source_segment(source, node) or ""
                lowered = segment.lower()
                hits = {term: lowered.count(term) for term in FOCUS_TERMS}

                rows.append(
                    {
                        "file": rel(path),
                        "name": node.name,
                        "qualified": f"{module}.{node.name}",
                        "line": node.lineno,
                        "is_public": not node.name.startswith("_"),
                        "focus_hit_count": sum(hits.values()),
                        "focus_hits": hits,
                    }
                )

    return rows


def overlap(a: dict[str, int], b: dict[str, int]) -> float:
    keys = set(a) | set(b)
    if not keys:
        return 0.0
    shared = sum(min(a.get(k, 0), b.get(k, 0)) for k in keys)
    total = sum(max(a.get(k, 0), b.get(k, 0)) for k in keys)
    return round(shared / total, 4) if total else 0.0


def match_candidates(bt_funcs: list[dict[str, Any]], core_funcs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []

    for bt in bt_funcs:
        if bt["focus_hit_count"] <= 0 and not bt["is_focus_function"]:
            continue

        scored = []
        for core in core_funcs:
            if not core.get("qualified"):
                continue

            score = overlap(bt["focus_hits"], core["focus_hits"])
            if score <= 0:
                continue

            scored.append(
                {
                    "score": score,
                    "core_qualified": core["qualified"],
                    "core_file": core["file"],
                    "core_function": core["name"],
                    "core_line": core["line"],
                    "core_is_public": core["is_public"],
                }
            )

        out.append(
            {
                "bt_file": bt["file"],
                "bt_function": bt["name"],
                "bt_line": bt["line"],
                "is_focus_function": bt["is_focus_function"],
                "bt_focus_hit_count": bt["focus_hit_count"],
                "top_core_candidates": sorted(
                    scored,
                    key=lambda r: (-r["score"], not r["core_is_public"], r["core_file"], r["core_line"]),
                )[:8],
            }
        )

    return sorted(out, key=lambda r: (not r["is_focus_function"], r["bt_file"], r["bt_line"]))


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    bt_files = discover_files()
    file_reports = []
    bt_funcs = []

    total_core_import_hits = 0
    total_core_call_hits = 0

    for path in bt_files:
        tree = parse(path)
        imps = imports(tree)
        hits = import_hits(imps)
        aliases = import_aliases(imps)
        calls = core_call_hits(tree, aliases)
        funcs = function_rows(path)

        total_core_import_hits += len(hits)
        total_core_call_hits += len(calls)
        bt_funcs.extend(funcs)

        file_reports.append(
            {
                "path": rel(path),
                "function_count": len(funcs),
                "focus_function_count": sum(1 for f in funcs if f["is_focus_function"]),
                "core_import_hit_count": len(hits),
                "core_import_hits": hits,
                "core_aliases": aliases,
                "core_call_hit_count": len(calls),
                "core_call_hits": calls,
                "functions": funcs,
            }
        )

    core_funcs = core_functions()
    matches = match_candidates(bt_funcs, core_funcs)

    if not bt_files:
        verdict = "blocked_no_stage12_backtesting_file_found"
    elif total_core_import_hits > 0 and total_core_call_hits > 0:
        verdict = "verified_static_core_backed"
    elif matches:
        verdict = "not_verified_core_candidates_exist_patch_or_extract"
    else:
        verdict = "not_verified_no_core_match_create_engine"

    is_ready = verdict == "verified_static_core_backed"

    summary = {
        "adapter_type": "stage40c2a_term_structure_core_call_verification_auditor",
        "artifact_type": "signalforge_stage40c2a_term_structure_core_call_verification",
        "contract": "stage40c2a_term_structure_core_call_verification",
        "is_ready": is_ready,
        "verdict": verdict,
        "bt_file_count": len(bt_files),
        "bt_files": [rel(p) for p in bt_files],
        "total_core_import_hits": total_core_import_hits,
        "total_core_call_hits": total_core_call_hits,
        "focus_function_count": sum(1 for f in bt_funcs if f["is_focus_function"]),
        "match_candidate_count": len(matches),
        "top_match_candidates": [
            {
                "bt_file": m["bt_file"],
                "bt_function": m["bt_function"],
                "bt_line": m["bt_line"],
                "is_focus_function": m["is_focus_function"],
                "top_core_match": m["top_core_candidates"][0] if m["top_core_candidates"] else None,
            }
            for m in matches[:20]
        ],
        "paths": {
            "summary_path": "artifacts/stage40c2a_term_structure_core_call_verification/signalforge_stage40c2a_term_structure_core_call_verification_summary.json",
            "detail_path": "artifacts/stage40c2a_term_structure_core_call_verification/signalforge_stage40c2a_term_structure_core_call_verification_detail.json",
        },
    }

    detail = {
        **summary,
        "file_reports": file_reports,
        "match_candidates": matches,
    }

    (OUT / "signalforge_stage40c2a_term_structure_core_call_verification_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (OUT / "signalforge_stage40c2a_term_structure_core_call_verification_detail.json").write_text(
        json.dumps(detail, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if is_ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
