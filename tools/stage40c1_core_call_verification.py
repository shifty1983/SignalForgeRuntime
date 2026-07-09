from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any


REPO = Path(".").resolve()
SRC = REPO / "src"
OUT = REPO / "artifacts" / "stage40c1_core_call_verification"

STAGES = {
    "06_historical_decision_rows": {
        "bt_patterns": [
            "src/signalforge/backtesting/*historical_decision*row*.py",
            "src/signalforge/backtesting/*decision_rows*.py",
        ],
        "required_core_namespaces": [
            "signalforge.engines.regime",
            "signalforge.engines.behavior",
        ],
        "expected_core_files": [
            "src/signalforge/engines/regime",
            "src/signalforge/engines/behavior",
        ],
    },
    "07_strategy_family_eligibility": {
        "bt_patterns": [
            "src/signalforge/backtesting/*strategy_family*eligibility*.py",
            "src/signalforge/backtesting/*family*eligibility*.py",
        ],
        "required_core_namespaces": [
            "signalforge.engines.strategy_selection.strategy_family_eligibility",
        ],
        "expected_core_files": [
            "src/signalforge/engines/strategy_selection/strategy_family_eligibility.py",
        ],
    },
}


def norm_path(path: Path) -> str:
    return str(path.as_posix())


def unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    out: list[Path] = []
    for path in paths:
        key = norm_path(path)
        if key not in seen and path.exists() and path.is_file():
            seen.add(key)
            out.append(path)
    return sorted(out, key=lambda p: norm_path(p))


def discover_files(patterns: list[str]) -> list[Path]:
    files: list[Path] = []
    for pattern in patterns:
        files.extend(REPO.glob(pattern))
    return unique_paths(files)


def parse_file(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = call_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return None


def imported_modules(tree: ast.Module) -> list[dict[str, Any]]:
    imports: list[dict[str, Any]] = []

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
            module = node.module or ""
            for alias in node.names:
                imports.append(
                    {
                        "kind": "from",
                        "module": module,
                        "name": alias.name,
                        "asname": alias.asname,
                        "line": node.lineno,
                    }
                )

    return imports


def function_defs(tree: ast.Module) -> list[dict[str, Any]]:
    funcs: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs.append(
                {
                    "name": node.name,
                    "line": node.lineno,
                    "end_line": getattr(node, "end_lineno", None),
                }
            )
    return sorted(funcs, key=lambda x: (x["line"], x["name"]))


def core_import_hits(imports: list[dict[str, Any]], required_namespaces: list[str]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []

    for imp in imports:
        module = imp["module"] or ""
        full = module if imp["name"] is None else f"{module}.{imp['name']}"
        for ns in required_namespaces:
            if module == ns or module.startswith(ns + ".") or full == ns or full.startswith(ns + "."):
                hits.append({**imp, "matched_namespace": ns})

    return hits


def import_aliases(imports: list[dict[str, Any]], required_namespaces: list[str]) -> dict[str, str]:
    aliases: dict[str, str] = {}

    for imp in imports:
        module = imp["module"] or ""
        name = imp["name"]
        asname = imp["asname"]

        if imp["kind"] == "import":
            for ns in required_namespaces:
                if module == ns or module.startswith(ns + "."):
                    alias = asname or module.split(".")[0]
                    aliases[alias] = module

        if imp["kind"] == "from":
            full = f"{module}.{name}" if name else module
            for ns in required_namespaces:
                if module == ns or module.startswith(ns + ".") or full == ns or full.startswith(ns + "."):
                    alias = asname or name
                    aliases[alias] = full

    return aliases


def core_call_hits(tree: ast.Module, aliases: dict[str, str]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []

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

    return sorted(hits, key=lambda x: (x["line"], x["call"]))


def source_decision_density(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    keywords = [
        "eligible",
        "eligibility",
        "state",
        "regime",
        "behavior",
        "strategy",
        "selection",
        "candidate",
        "risk",
        "rule",
        "score",
        "rank",
        "return",
        "outcome",
    ]
    counts = {k: text.count(k) for k in keywords}
    return {
        "line_count": len(text.splitlines()),
        "decision_keyword_hits": sum(counts.values()),
        "decision_keyword_counts": counts,
    }


def audit_stage(stage: str, config: dict[str, Any]) -> dict[str, Any]:
    bt_files = discover_files(config["bt_patterns"])
    required = config["required_core_namespaces"]

    file_reports = []
    total_core_import_hits = 0
    total_core_call_hits = 0

    for path in bt_files:
        tree = parse_file(path)
        imports = imported_modules(tree)
        funcs = function_defs(tree)
        import_hits = core_import_hits(imports, required)
        aliases = import_aliases(imports, required)
        call_hits = core_call_hits(tree, aliases)

        total_core_import_hits += len(import_hits)
        total_core_call_hits += len(call_hits)

        file_reports.append(
            {
                "path": norm_path(path.relative_to(REPO)),
                "function_count": len(funcs),
                "functions": funcs,
                "core_import_hit_count": len(import_hits),
                "core_import_hits": import_hits,
                "core_aliases": aliases,
                "core_call_hit_count": len(call_hits),
                "core_call_hits": call_hits,
                "source_density": source_decision_density(path),
            }
        )

    expected_core_file_status = []
    for expected in config["expected_core_files"]:
        p = REPO / expected
        expected_core_file_status.append(
            {
                "path": expected,
                "exists": p.exists(),
                "is_file": p.is_file(),
                "is_dir": p.is_dir(),
            }
        )

    required_namespace_coverage = {
        ns: any(
            hit["matched_namespace"] == ns
            for fr in file_reports
            for hit in fr["core_import_hits"]
        )
        for ns in required
    }

    is_core_backed_static = bool(bt_files) and total_core_import_hits > 0 and total_core_call_hits > 0
    missing_required_namespaces = [
        ns for ns, covered in required_namespace_coverage.items() if not covered
    ]

    if not bt_files:
        verdict = "blocked_no_backtesting_file_found"
    elif missing_required_namespaces:
        verdict = "not_verified_missing_required_core_namespace"
    elif total_core_call_hits == 0:
        verdict = "not_verified_imports_without_detected_core_calls"
    else:
        verdict = "verified_static_core_backed"

    return {
        "stage": stage,
        "bt_file_count": len(bt_files),
        "bt_files": [norm_path(p.relative_to(REPO)) for p in bt_files],
        "expected_core_file_status": expected_core_file_status,
        "required_core_namespaces": required,
        "required_namespace_coverage": required_namespace_coverage,
        "missing_required_namespaces": missing_required_namespaces,
        "total_core_import_hits": total_core_import_hits,
        "total_core_call_hits": total_core_call_hits,
        "is_core_backed_static": is_core_backed_static,
        "verdict": verdict,
        "file_reports": file_reports,
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    stage_reports = [audit_stage(stage, config) for stage, config in STAGES.items()]

    blocker_count = sum(1 for r in stage_reports if not str(r["verdict"]).startswith("verified"))
    summary = {
        "adapter_type": "stage40c1_core_call_verification_auditor",
        "artifact_type": "signalforge_stage40c1_core_call_verification",
        "contract": "stage40c1_core_call_verification",
        "is_ready": blocker_count == 0,
        "blocker_count": blocker_count,
        "blockers": [
            {
                "stage": r["stage"],
                "verdict": r["verdict"],
                "missing_required_namespaces": r["missing_required_namespaces"],
            }
            for r in stage_reports
            if not str(r["verdict"]).startswith("verified")
        ],
        "stage_count": len(stage_reports),
        "verified_stage_count": sum(1 for r in stage_reports if str(r["verdict"]).startswith("verified")),
        "stage_reports": [
            {
                "stage": r["stage"],
                "verdict": r["verdict"],
                "bt_file_count": r["bt_file_count"],
                "bt_files": r["bt_files"],
                "total_core_import_hits": r["total_core_import_hits"],
                "total_core_call_hits": r["total_core_call_hits"],
                "missing_required_namespaces": r["missing_required_namespaces"],
                "required_namespace_coverage": r["required_namespace_coverage"],
                "expected_core_file_status": r["expected_core_file_status"],
            }
            for r in stage_reports
        ],
        "paths": {
            "summary_path": "artifacts/stage40c1_core_call_verification/signalforge_stage40c1_core_call_verification_summary.json",
            "detail_path": "artifacts/stage40c1_core_call_verification/signalforge_stage40c1_core_call_verification_detail.json",
        },
    }

    detail = {
        **summary,
        "stage_reports_detail": stage_reports,
    }

    (OUT / "signalforge_stage40c1_core_call_verification_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (OUT / "signalforge_stage40c1_core_call_verification_detail.json").write_text(
        json.dumps(detail, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
