from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any


REPO = Path(".").resolve()
OUT = REPO / "artifacts/stage40c3c_stage15_candidate_input_discovery"

SEARCH_ROOTS = [
    REPO / "src",
    REPO / "tools",
]

EXCLUDED_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "artifacts",
}

STAGE15_MARKERS = [
    "leg_selection_candidate_input",
    "candidate_input_term",
    "candidate input",
    "selector_candidate_input",
    "build_historical_strategy_leg_selection_candidate",
    "leg selection candidate",
    "term_hpd5",
    "hpd5",
]

STAGE16_MARKERS = [
    "build_historical_strategy_leg_selection_rows",
    "select_legs_for_candidate",
]


def rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def should_skip(path: Path) -> bool:
    return bool(set(path.parts) & EXCLUDED_DIR_NAMES)


def safe_parse(path: Path) -> ast.Module | None:
    try:
        return ast.parse(read(path), filename=str(path))
    except SyntaxError:
        return None


def function_names(path: Path) -> list[str]:
    tree = safe_parse(path)
    if tree is None:
        return []
    return [
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def imports(path: Path) -> list[dict[str, Any]]:
    tree = safe_parse(path)
    if tree is None:
        return []

    rows = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                rows.append({
                    "line": node.lineno,
                    "kind": "import",
                    "module": alias.name,
                    "name": None,
                    "asname": alias.asname,
                })
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                rows.append({
                    "line": node.lineno,
                    "kind": "from",
                    "module": node.module or "",
                    "name": alias.name,
                    "asname": alias.asname,
                })
    return rows


def discover_files() -> list[dict[str, Any]]:
    rows = []

    for root in SEARCH_ROOTS:
        if not root.exists():
            continue

        for path in sorted(root.rglob("*.py")):
            if should_skip(path):
                continue

            try:
                text = read(path)
            except UnicodeDecodeError:
                continue

            lowered = text.lower()
            stage15_hits = [m for m in STAGE15_MARKERS if m.lower() in lowered]
            stage16_hits = [m for m in STAGE16_MARKERS if m.lower() in lowered]

            if not stage15_hits and not stage16_hits:
                continue

            funcs = function_names(path)
            imps = imports(path)

            rows.append({
                "path": rel(path),
                "stage15_marker_hits": stage15_hits,
                "stage16_marker_hits": stage16_hits,
                "function_count": len(funcs),
                "functions": funcs,
                "import_count": len(imps),
                "imports": imps,
                "looks_like_stage15": bool(stage15_hits) and not path.name.startswith("stage40c"),
                "looks_like_stage16": bool(stage16_hits),
                "is_tooling_audit_file": path.name.startswith("stage40c"),
            })

    return rows


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    files = discover_files()

    likely_stage15_files = [
        f for f in files
        if f["looks_like_stage15"] and not f["is_tooling_audit_file"]
    ]

    likely_stage16_files = [
        f for f in files
        if f["looks_like_stage16"] and not f["is_tooling_audit_file"]
    ]

    if likely_stage15_files:
        verdict = "stage15_candidate_input_file_exists_audit_or_promote_next"
    else:
        verdict = "no_separate_stage15_builder_found_stage15_absorbed_or_artifact_only"

    summary = {
        "adapter_type": "stage40c3c_stage15_candidate_input_discovery_auditor",
        "artifact_type": "signalforge_stage40c3c_stage15_candidate_input_discovery",
        "contract": "stage40c3c_stage15_candidate_input_discovery",
        "is_ready": True,
        "verdict": verdict,
        "discovered_file_count": len(files),
        "likely_stage15_file_count": len(likely_stage15_files),
        "likely_stage16_file_count": len(likely_stage16_files),
        "likely_stage15_files": [
            {
                "path": f["path"],
                "stage15_marker_hits": f["stage15_marker_hits"],
                "function_count": f["function_count"],
                "functions": f["functions"],
            }
            for f in likely_stage15_files
        ],
        "likely_stage16_files": [
            {
                "path": f["path"],
                "stage16_marker_hits": f["stage16_marker_hits"],
                "function_count": f["function_count"],
                "functions": f["functions"][:12],
            }
            for f in likely_stage16_files
        ],
        "paths": {
            "summary_path": "artifacts/stage40c3c_stage15_candidate_input_discovery/signalforge_stage40c3c_stage15_candidate_input_discovery_summary.json",
            "detail_path": "artifacts/stage40c3c_stage15_candidate_input_discovery/signalforge_stage40c3c_stage15_candidate_input_discovery_detail.json",
        },
    }

    detail = {
        **summary,
        "discovered_files": files,
    }

    (OUT / "signalforge_stage40c3c_stage15_candidate_input_discovery_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    (OUT / "signalforge_stage40c3c_stage15_candidate_input_discovery_detail.json").write_text(
        json.dumps(detail, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
