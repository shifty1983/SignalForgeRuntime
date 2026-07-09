from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any


REPO = Path(".").resolve()
OUT = REPO / "artifacts/stage40c3d_candidate_input_builder_core_audit"

TARGET = REPO / "tools/build_v13_v21_selector_candidate_input.py"

CORE_NAMESPACES = [
    "signalforge.engines.strategy_selection",
    "signalforge.options_execution",
]

EXPECTED_CORE_HINTS = [
    "portfolio_candidate_input",
    "research_adapter",
    "candidates",
    "evaluator",
    "leg_selection",
]


def rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


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
        full = module if imp["name"] is None else f"{module}.{imp['name']}"
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


def functions(tree: ast.Module) -> list[dict[str, Any]]:
    rows = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            rows.append({
                "name": node.name,
                "line": node.lineno,
                "end_line": getattr(node, "end_lineno", None),
            })
    return rows


def core_file_status() -> list[dict[str, Any]]:
    rows = []
    root = REPO / "src/signalforge/engines/strategy_selection"
    for hint in EXPECTED_CORE_HINTS:
        matches = sorted(root.glob(f"*{hint}*.py"))
        rows.append({
            "hint": hint,
            "matches": [rel(p) for p in matches],
            "match_count": len(matches),
        })
    return rows


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    if not TARGET.exists():
        summary = {
            "adapter_type": "stage40c3d_candidate_input_builder_core_auditor",
            "artifact_type": "signalforge_stage40c3d_candidate_input_builder_core_audit",
            "contract": "stage40c3d_candidate_input_builder_core_audit",
            "is_ready": False,
            "verdict": "target_builder_missing",
            "target": rel(TARGET),
        }
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 1

    source = read(TARGET)
    tree = ast.parse(source, filename=str(TARGET))
    import_rows = imports(tree)
    ihits = core_import_hits(import_rows)
    alias_map = aliases(import_rows)
    chits = core_call_hits(tree, alias_map)
    funcs = functions(tree)

    source_lower = source.lower()
    hint_hits = [
        hint for hint in EXPECTED_CORE_HINTS
        if hint.lower() in source_lower
    ]

    if ihits and chits:
        verdict = "verified_static_core_backed"
    elif hint_hits:
        verdict = "not_verified_mentions_core_hints_without_calls"
    else:
        verdict = "not_verified_tool_owns_candidate_input_logic"

    summary = {
        "adapter_type": "stage40c3d_candidate_input_builder_core_auditor",
        "artifact_type": "signalforge_stage40c3d_candidate_input_builder_core_audit",
        "contract": "stage40c3d_candidate_input_builder_core_audit",
        "is_ready": verdict == "verified_static_core_backed",
        "verdict": verdict,
        "target": rel(TARGET),
        "function_count": len(funcs),
        "functions": funcs,
        "core_import_hit_count": len(ihits),
        "core_call_hit_count": len(chits),
        "core_import_hits": ihits,
        "core_call_hits": chits,
        "core_hint_hits_in_source": hint_hits,
        "expected_core_file_status": core_file_status(),
        "paths": {
            "summary_path": "artifacts/stage40c3d_candidate_input_builder_core_audit/signalforge_stage40c3d_candidate_input_builder_core_audit_summary.json",
            "detail_path": "artifacts/stage40c3d_candidate_input_builder_core_audit/signalforge_stage40c3d_candidate_input_builder_core_audit_detail.json",
        },
    }

    detail = {
        **summary,
        "imports": import_rows,
    }

    (OUT / "signalforge_stage40c3d_candidate_input_builder_core_audit_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (OUT / "signalforge_stage40c3d_candidate_input_builder_core_audit_detail.json").write_text(
        json.dumps(detail, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
