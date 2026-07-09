from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any


REPO = Path(".").resolve()
OUT = REPO / "artifacts/stage40c3a_leg_selection_core_call_audit"

SEARCH_ROOTS = [
    REPO / "src/signalforge/backtesting",
    REPO / "tools",
]

CORE_ROOTS = [
    REPO / "src/signalforge/engines/strategy_selection",
    REPO / "src/signalforge/options_execution",
]

CORE_NAMESPACES = [
    "signalforge.engines.strategy_selection",
    "signalforge.options_execution",
]

MARKERS = [
    "select_legs_for_candidate",
    "build_historical_strategy_leg_selection_rows",
    "build_historical_strategy_leg_selection_rows_artifact",
    "_select_single_long",
    "_select_vertical_debit",
    "_select_vertical_credit",
    "_select_iron_condor",
    "_select_iron_butterfly",
    "_select_calendar",
    "_select_diagonal",
    "_blocked_payload",
    "_selection_payload",
    "_front_back_available_for_exit",
    "_delta_score",
    "_atm_score",
    "_net_mid_debit",
    "leg_selection",
    "leg selection",
]

FOCUS_FUNCTIONS = {
    "_delta_abs",
    "_atm_score",
    "_delta_score",
    "_find_next_higher",
    "_find_next_lower",
    "_best_atm",
    "_best_delta",
    "_leg",
    "_net_mid_debit",
    "_selection_payload",
    "_blocked_payload",
    "_select_single_long",
    "_select_vertical_debit",
    "_select_vertical_credit",
    "_select_iron_condor",
    "_select_iron_butterfly",
    "_front_back_available_for_exit",
    "_select_calendar",
    "_select_diagonal",
    "select_legs_for_candidate",
    "_build_option_index",
    "build_historical_strategy_leg_selection_rows",
    "build_historical_strategy_leg_selection_rows_artifact",
}

FOCUS_TERMS = [
    "leg",
    "selection",
    "select",
    "candidate",
    "strategy",
    "option",
    "contract",
    "expiration",
    "dte",
    "delta",
    "atm",
    "strike",
    "spread",
    "mid",
    "bid",
    "ask",
    "debit",
    "credit",
    "calendar",
    "diagonal",
    "condor",
    "butterfly",
    "available",
    "blocked",
    "risk",
    "score",
    "rule",
    "state",
]


def rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def should_skip(path: Path) -> bool:
    parts = set(path.parts)
    return bool(parts & {".git", ".venv", "venv", "__pycache__", "artifacts"})


def discover_candidate_files() -> list[Path]:
    files: list[Path] = []

    for root in SEARCH_ROOTS:
        if not root.exists():
            continue

        for path in root.rglob("*.py"):
            if should_skip(path):
                continue

            try:
                text = read(path).lower()
            except UnicodeDecodeError:
                continue

            if any(marker.lower() in text for marker in MARKERS):
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

        for ns in CORE_NAMESPACES:
            if module == ns or module.startswith(ns + ".") or full == ns or full.startswith(ns + "."):
                hits.append({**imp, "matched_namespace": ns})

    return hits


def aliases(import_rows: list[dict[str, Any]]) -> dict[str, str]:
    out: dict[str, str] = {}

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
                hits.append(
                    {
                        "line": node.lineno,
                        "call": cname,
                        "resolved_core_target": alias_map[first],
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

    for root in CORE_ROOTS:
        if not root.exists():
            continue

        for path in sorted(root.rglob("*.py")):
            if should_skip(path) or path.name == "__init__.py":
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
            exact_name_match = bt["name"] == core.get("name")

            if score <= 0 and not exact_name_match:
                continue

            if exact_name_match:
                score = max(score, 0.9)

            scored.append(
                {
                    "score": score,
                    "core_qualified": core["qualified"],
                    "core_file": core["file"],
                    "core_function": core["name"],
                    "core_line": core["line"],
                    "core_is_public": core["is_public"],
                    "exact_name_match": exact_name_match,
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
                    key=lambda r: (
                        not r["exact_name_match"],
                        -r["score"],
                        not r["core_is_public"],
                        r["core_file"],
                        r["core_line"],
                    ),
                )[:8],
            }
        )

    return sorted(out, key=lambda r: (r["bt_file"], r["bt_line"]))


def classify_stage_file(path: Path, funcs: list[dict[str, Any]]) -> str:
    names = {f["name"] for f in funcs}
    text = read(path).lower()

    if "build_historical_strategy_leg_selection_rows" in names or "select_legs_for_candidate" in names:
        return "16_leg_selection"

    if "leg_selection_candidate_input" in text or "candidate_input" in text:
        return "15_leg_selection_candidate_input"

    if any(name in names for name in {"_select_single_long", "_select_vertical_debit", "_select_calendar"}):
        return "16_leg_selection"

    return "leg_selection_related_unknown"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    bt_files = discover_candidate_files()
    core_funcs = core_functions()

    file_reports = []
    bt_funcs = []

    total_core_import_hits = 0
    total_core_call_hits = 0

    for path in bt_files:
        tree = parse(path)
        imps = imports(tree)
        ihits = import_hits(imps)
        alias_map = aliases(imps)
        chits = core_call_hits(tree, alias_map)
        funcs = function_rows(path)

        total_core_import_hits += len(ihits)
        total_core_call_hits += len(chits)
        bt_funcs.extend(funcs)

        stage_guess = classify_stage_file(path, funcs)

        if ihits and chits:
            verdict = "verified_static_core_or_runtime_backed"
        elif any(f["is_focus_function"] for f in funcs):
            verdict = "not_verified_leg_logic_owned_by_builder"
        else:
            verdict = "related_file_no_focus_logic"

        file_reports.append(
            {
                "path": rel(path),
                "stage_guess": stage_guess,
                "verdict": verdict,
                "function_count": len(funcs),
                "focus_function_count": sum(1 for f in funcs if f["is_focus_function"]),
                "core_import_hit_count": len(ihits),
                "core_call_hit_count": len(chits),
                "core_import_hits": ihits,
                "core_call_hits": chits,
                "functions": funcs,
            }
        )

    matches = match_candidates(bt_funcs, core_funcs)

    blocker_files = [
        r for r in file_reports
        if r["verdict"] == "not_verified_leg_logic_owned_by_builder"
    ]

    summary = {
        "adapter_type": "stage40c3a_leg_selection_core_call_auditor",
        "artifact_type": "signalforge_stage40c3a_leg_selection_core_call_audit",
        "contract": "stage40c3a_leg_selection_core_call_audit",
        "is_ready": len(blocker_files) == 0 and len(file_reports) > 0,
        "bt_file_count": len(bt_files),
        "total_core_import_hits": total_core_import_hits,
        "total_core_call_hits": total_core_call_hits,
        "blocker_file_count": len(blocker_files),
        "file_reports": [
            {
                "path": r["path"],
                "stage_guess": r["stage_guess"],
                "verdict": r["verdict"],
                "function_count": r["function_count"],
                "focus_function_count": r["focus_function_count"],
                "core_import_hit_count": r["core_import_hit_count"],
                "core_call_hit_count": r["core_call_hit_count"],
            }
            for r in file_reports
        ],
        "top_match_candidates": [
            {
                "bt_file": m["bt_file"],
                "bt_function": m["bt_function"],
                "bt_line": m["bt_line"],
                "is_focus_function": m["is_focus_function"],
                "top_core_match": m["top_core_candidates"][0] if m["top_core_candidates"] else None,
            }
            for m in matches[:40]
        ],
        "paths": {
            "summary_path": "artifacts/stage40c3a_leg_selection_core_call_audit/signalforge_stage40c3a_leg_selection_core_call_audit_summary.json",
            "detail_path": "artifacts/stage40c3a_leg_selection_core_call_audit/signalforge_stage40c3a_leg_selection_core_call_audit_detail.json",
        },
    }

    detail = {
        **summary,
        "file_reports_detail": file_reports,
        "match_candidates": matches,
    }

    (OUT / "signalforge_stage40c3a_leg_selection_core_call_audit_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    (OUT / "signalforge_stage40c3a_leg_selection_core_call_audit_detail.json").write_text(
        json.dumps(detail, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
