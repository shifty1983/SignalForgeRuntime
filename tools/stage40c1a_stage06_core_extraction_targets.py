from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any


REPO = Path(".").resolve()
OUT = REPO / "artifacts" / "stage40c1a_stage06_core_extraction_targets"

BT_FILES = [
    REPO / "src/signalforge/backtesting/historical_decision_rows.py",
    REPO / "src/signalforge/backtesting/historical_decision_rows_cli.py",
]

CORE_ROOTS = [
    REPO / "src/signalforge/engines/regime",
    REPO / "src/signalforge/engines/behavior",
]

FOCUS_TERMS = [
    "regime",
    "behavior",
    "asset",
    "option",
    "market",
    "state",
    "decision",
    "eligibility",
    "eligible",
    "lookup",
    "asof",
    "index",
    "weekly",
    "price",
    "symbol",
    "date",
]


def rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse(path: Path) -> ast.Module:
    return ast.parse(read(path), filename=str(path))


def function_source(path: Path, node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    lines = read(path).splitlines()
    start = max(node.lineno - 1, 0)
    end = getattr(node, "end_lineno", None) or node.lineno
    return "\n".join(lines[start:end])


def call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = call_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return None


def imports_from_tree(tree: ast.Module) -> list[dict[str, Any]]:
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(
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
                imports.append(
                    {
                        "kind": "from",
                        "module": node.module or "",
                        "name": alias.name,
                        "asname": alias.asname,
                        "line": node.lineno,
                    }
                )
    return imports


def function_report(path: Path, node: ast.FunctionDef | ast.AsyncFunctionDef) -> dict[str, Any]:
    src = function_source(path, node)
    lowered = src.lower()
    term_hits = {term: lowered.count(term) for term in FOCUS_TERMS}
    calls = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            cname = call_name(child.func)
            if cname:
                calls.append({"line": child.lineno, "call": cname})

    return {
        "file": rel(path),
        "name": node.name,
        "line": node.lineno,
        "end_line": getattr(node, "end_lineno", None),
        "line_count": ((getattr(node, "end_lineno", None) or node.lineno) - node.lineno + 1),
        "focus_hit_count": sum(term_hits.values()),
        "focus_hits": term_hits,
        "calls": calls,
        "call_count": len(calls),
        "role_guess": role_guess(node.name, term_hits, src),
    }


def role_guess(name: str, hits: dict[str, int], src: str) -> str:
    n = name.lower()
    if "read" in n or "load" in n or "write" in n:
        return "io_helper"
    if "parse" in n or "coerce" in n or "normal" in n or "iso" == n:
        return "normalization_helper"
    if "index" in n:
        return "index_builder_candidate"
    if "lookup" in n or "asof" in n:
        return "lookup_logic_candidate"
    if "build_historical_decision_rows" in n or "decision" in n:
        return "decision_row_orchestrator"
    if hits.get("regime", 0) or hits.get("behavior", 0) or hits.get("state", 0):
        return "domain_logic_candidate"
    return "other"


def collect_functions(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    tree = parse(path)
    funcs = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs.append(function_report(path, node))
    return sorted(funcs, key=lambda r: (r["line"], r["name"]))


def public_core_functions() -> list[dict[str, Any]]:
    rows = []
    for root in CORE_ROOTS:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            if path.name == "__init__.py":
                continue

            try:
                tree = parse(path)
            except SyntaxError as exc:
                rows.append(
                    {
                        "file": rel(path),
                        "name": None,
                        "line": None,
                        "kind": "syntax_error",
                        "error": str(exc),
                        "focus_hit_count": 0,
                        "focus_hits": {},
                    }
                )
                continue

            module = "signalforge." + rel(path).replace("src/signalforge/", "").replace("/", ".").removesuffix(".py")
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    src = function_source(path, node)
                    lowered = src.lower()
                    term_hits = {term: lowered.count(term) for term in FOCUS_TERMS}
                    is_public = not node.name.startswith("_")
                    rows.append(
                        {
                            "file": rel(path),
                            "module": module,
                            "name": node.name,
                            "qualified": f"{module}.{node.name}",
                            "line": node.lineno,
                            "end_line": getattr(node, "end_lineno", None),
                            "is_public": is_public,
                            "line_count": ((getattr(node, "end_lineno", None) or node.lineno) - node.lineno + 1),
                            "focus_hit_count": sum(term_hits.values()),
                            "focus_hits": term_hits,
                        }
                    )
    return sorted(rows, key=lambda r: (-int(r.get("is_public") or False), -r.get("focus_hit_count", 0), r.get("file", ""), r.get("line") or 0))


def overlap_score(a: dict[str, int], b: dict[str, int]) -> float:
    keys = set(a) | set(b)
    if not keys:
        return 0.0
    shared = sum(min(a.get(k, 0), b.get(k, 0)) for k in keys)
    total = sum(max(a.get(k, 0), b.get(k, 0)) for k in keys)
    return round(shared / total, 4) if total else 0.0


def match_candidates(bt_funcs: list[dict[str, Any]], core_funcs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matches = []
    target_roles = {
        "index_builder_candidate",
        "lookup_logic_candidate",
        "decision_row_orchestrator",
        "domain_logic_candidate",
    }

    for bt in bt_funcs:
        if bt["role_guess"] not in target_roles:
            continue

        scored = []
        for core in core_funcs:
            if not core.get("name"):
                continue
            score = overlap_score(bt["focus_hits"], core.get("focus_hits", {}))
            if score <= 0:
                continue
            scored.append(
                {
                    "score": score,
                    "core_file": core["file"],
                    "core_function": core["name"],
                    "core_qualified": core.get("qualified"),
                    "core_line": core["line"],
                    "core_is_public": core.get("is_public"),
                }
            )

        matches.append(
            {
                "bt_file": bt["file"],
                "bt_function": bt["name"],
                "bt_line": bt["line"],
                "bt_role_guess": bt["role_guess"],
                "bt_focus_hit_count": bt["focus_hit_count"],
                "top_core_candidates": sorted(
                    scored,
                    key=lambda x: (-x["score"], not bool(x["core_is_public"]), x["core_file"], x["core_line"]),
                )[:8],
            }
        )

    return matches


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    bt_existing = [p for p in BT_FILES if p.exists()]
    bt_functions = []
    bt_imports = []
    for path in bt_existing:
        tree = parse(path)
        bt_imports.extend([{"file": rel(path), **imp} for imp in imports_from_tree(tree)])
        bt_functions.extend(collect_functions(path))

    core_functions = public_core_functions()
    matches = match_candidates(bt_functions, core_functions)

    extraction_targets = [
        m for m in matches
        if m["bt_role_guess"] in {
            "index_builder_candidate",
            "lookup_logic_candidate",
            "decision_row_orchestrator",
            "domain_logic_candidate",
        }
    ]

    summary = {
        "adapter_type": "stage40c1a_stage06_core_extraction_target_auditor",
        "artifact_type": "signalforge_stage40c1a_stage06_core_extraction_targets",
        "contract": "stage40c1a_stage06_core_extraction_targets",
        "is_ready": True,
        "bt_file_count": len(bt_existing),
        "bt_files": [rel(p) for p in bt_existing],
        "bt_function_count": len(bt_functions),
        "core_function_count": len(core_functions),
        "extraction_target_count": len(extraction_targets),
        "top_extraction_targets": [
            {
                "bt_file": m["bt_file"],
                "bt_function": m["bt_function"],
                "bt_line": m["bt_line"],
                "bt_role_guess": m["bt_role_guess"],
                "top_core_candidates": m["top_core_candidates"][:3],
            }
            for m in extraction_targets
        ],
        "paths": {
            "summary_path": "artifacts/stage40c1a_stage06_core_extraction_targets/signalforge_stage40c1a_stage06_core_extraction_targets_summary.json",
            "detail_path": "artifacts/stage40c1a_stage06_core_extraction_targets/signalforge_stage40c1a_stage06_core_extraction_targets_detail.json",
        },
    }

    detail = {
        **summary,
        "bt_imports": bt_imports,
        "bt_functions": bt_functions,
        "core_functions": core_functions,
        "match_candidates": matches,
    }

    (OUT / "signalforge_stage40c1a_stage06_core_extraction_targets_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (OUT / "signalforge_stage40c1a_stage06_core_extraction_targets_detail.json").write_text(
        json.dumps(detail, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
