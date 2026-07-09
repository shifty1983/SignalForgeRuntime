from __future__ import annotations

import ast
import json
import py_compile
from pathlib import Path
from typing import Any


REPO = Path(".").resolve()
OUT = REPO / "artifacts/stage40c9d_v21_steps_27_29_rules_closure_audit"

LEGACY_EXCLUDED = REPO / "src/signalforge/rulebooks/v3_2_2.py"

TARGETS = [
    {
        "label": "resolved_execution_rules_v21",
        "path": REPO / "src/signalforge/engines/strategy_selection/resolved_strategy_execution_rules_v21.py",
        "expected_role": "core_v21_resolved_execution_rules",
        "required": True,
    },
    {
        "label": "execution_qualified_candidates_v21",
        "path": REPO / "src/signalforge/engines/strategy_selection/execution_qualified_historical_strategy_candidates_v21.py",
        "expected_role": "core_v21_execution_qualified_candidates",
        "required": True,
    },
    {
        "label": "repaired_candidates_v13_v21",
        "path": REPO / "src/signalforge/engines/strategy_selection/repaired_historical_strategy_candidates_v13_v21.py",
        "expected_role": "core_v13_v21_candidate_repair_or_rule_preparation",
        "required": True,
    },
    {
        "label": "metric_driven_execution_overlay_v21",
        "path": REPO / "src/signalforge/options_execution/metric_driven_execution_overlay_v21.py",
        "expected_role": "options_execution_v21_metric_overlay",
        "required": True,
    },
    {
        "label": "option_contract_execution_features_v21",
        "path": REPO / "src/signalforge/options_execution/option_contract_execution_features_v21.py",
        "expected_role": "options_execution_v21_contract_features",
        "required": True,
    },
    {
        "label": "options_execution_resolved_rules_bridge",
        "path": REPO / "src/signalforge/options_execution/resolved_strategy_execution_rules_v21.py",
        "expected_role": "options_execution_bridge_or_alias",
        "required": False,
    },
]

ARTIFACT_EXPECTATIONS = [
    {
        "label": "canonical_resolved_execution_rules_v21_rows",
        "path": REPO / "artifacts/canonical_replay_validation/v21_restart_from_corrected_option_layer/10_resolved_execution_rules_v21/signalforge_resolved_strategy_execution_rules_v21.jsonl",
        "required": False,
    },
    {
        "label": "canonical_resolved_execution_rules_v21_summary",
        "path": REPO / "artifacts/canonical_replay_validation/v21_restart_from_corrected_option_layer/10_resolved_execution_rules_v21/signalforge_resolved_strategy_execution_rules_v21_summary.json",
        "required": False,
    },
    {
        "label": "canonical_execution_qualified_candidates_v21_rows",
        "path": REPO / "artifacts/canonical_replay_validation/v21_restart_from_corrected_option_layer/11_execution_qualified_strategy_candidates/signalforge_repaired_execution_qualified_historical_strategy_candidates_v13_v21.jsonl",
        "required": False,
    },
    {
        "label": "canonical_metric_driven_overlay_v21_rows",
        "path": REPO / "artifacts/canonical_replay_validation/v21_restart_from_corrected_option_layer/10a_metric_driven_overlay_v21/signalforge_metric_driven_execution_overlay_v21.jsonl",
        "required": False,
    },
]

SEARCH_ROOTS = [
    REPO / "src",
    REPO / "tools",
]


def rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def safe_read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig", errors="ignore")
    except Exception:
        return ""


def module_name(path: Path) -> str:
    return rel(path).replace("src/", "").replace("/", ".").removesuffix(".py")


def compile_ok(path: Path) -> tuple[bool, str | None]:
    try:
        py_compile.compile(str(path), doraise=True)
        return True, None
    except Exception as exc:
        return False, str(exc)


def function_names(path: Path) -> list[str]:
    if not path.exists() or path.suffix.lower() != ".py":
        return []

    try:
        tree = ast.parse(read(path), filename=str(path))
    except SyntaxError:
        return []

    return [
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def import_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or path.suffix.lower() != ".py":
        return []

    try:
        tree = ast.parse(read(path), filename=str(path))
    except SyntaxError:
        return []

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


def top_level_assignment_names(path: Path) -> list[str]:
    if not path.exists() or path.suffix.lower() != ".py":
        return []

    try:
        tree = ast.parse(read(path), filename=str(path))
    except SyntaxError:
        return []

    names = []

    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.append(target.id)

        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                names.append(node.target.id)

    return names


def inspect_target(spec: dict[str, Any]) -> dict[str, Any]:
    path = spec["path"]
    exists = path.exists()
    funcs = function_names(path)
    assignments = top_level_assignment_names(path)
    imports = import_rows(path)
    c_ok, c_error = compile_ok(path) if exists and path.suffix.lower() == ".py" else (False, "missing_or_not_python")

    path_text = rel(path) if exists or path.is_absolute() else str(path)
    module = module_name(path) if path.suffix.lower() == ".py" else None

    if not exists and spec["required"]:
        classification = "missing_required_v21_rule_source"
    elif not exists:
        classification = "optional_v21_rule_bridge_missing"
    elif str(path).replace("\\", "/").endswith("src/signalforge/rulebooks/v3_2_2.py"):
        classification = "legacy_rulebook_excluded"
    elif "src/signalforge/engines/" in path_text:
        classification = "current_v21_core_engine_source"
    elif "src/signalforge/options_execution/" in path_text:
        classification = "current_v21_options_execution_source"
    elif "src/signalforge/backtesting/" in path_text:
        classification = "backtesting_surface_needs_review"
    else:
        classification = "source_needs_review"

    return {
        "label": spec["label"],
        "path": rel(path),
        "module": module,
        "expected_role": spec["expected_role"],
        "required": spec["required"],
        "exists": exists,
        "compile_ok": c_ok,
        "compile_error": c_error,
        "function_count": len(funcs),
        "functions": funcs,
        "assignment_count": len(assignments),
        "assignments": assignments,
        "import_count": len(imports),
        "imports": imports,
        "classification": classification,
    }


def inspect_artifact(spec: dict[str, Any]) -> dict[str, Any]:
    path = spec["path"]

    return {
        "label": spec["label"],
        "path": rel(path),
        "required": spec["required"],
        "exists": path.exists(),
        "size_bytes": path.stat().st_size if path.exists() else None,
    }


def find_consumers(target_modules: list[str]) -> list[dict[str, Any]]:
    rows = []

    for root in SEARCH_ROOTS:
        if not root.exists():
            continue

        for path in root.rglob("*.py"):
            if set(path.parts) & {".git", ".venv", "venv", "__pycache__", "artifacts"}:
                continue

            text = safe_read(path)
            lowered = text.lower()

            hits = {
                module: lowered.count(module.lower())
                for module in target_modules
                if lowered.count(module.lower())
            }

            if hits:
                rows.append({
                    "path": rel(path),
                    "hit_count": sum(hits.values()),
                    "hits": hits,
                    "size_bytes": path.stat().st_size,
                })

    return sorted(rows, key=lambda r: (-r["hit_count"], r["path"]))


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    target_reports = [inspect_target(spec) for spec in TARGETS]
    artifact_reports = [inspect_artifact(spec) for spec in ARTIFACT_EXPECTATIONS]

    target_modules = [
        r["module"]
        for r in target_reports
        if r.get("module")
    ]

    consumers = find_consumers(target_modules)

    missing_required_sources = [
        r for r in target_reports
        if r["required"] and not r["exists"]
    ]

    compile_failures = [
        r for r in target_reports
        if r["exists"] and not r["compile_ok"]
    ]

    backtesting_sources = [
        r for r in target_reports
        if r["classification"] == "backtesting_surface_needs_review"
    ]

    legacy_excluded_exists = LEGACY_EXCLUDED.exists()

    production_blockers = (
        missing_required_sources
        + compile_failures
        + backtesting_sources
    )

    summary = {
        "adapter_type": "stage40c9d_v21_steps_27_29_rules_closure_auditor",
        "artifact_type": "signalforge_stage40c9d_v21_steps_27_29_rules_closure_audit",
        "contract": "stage40c9d_v21_steps_27_29_rules_closure_audit",
        "is_ready": len(production_blockers) == 0,
        "stage": "v21_canonical_steps_27_29_rules",
        "legacy_rulebook_excluded": rel(LEGACY_EXCLUDED),
        "legacy_rulebook_exists": legacy_excluded_exists,
        "target_count": len(target_reports),
        "required_target_count": sum(1 for r in target_reports if r["required"]),
        "existing_target_count": sum(1 for r in target_reports if r["exists"]),
        "compile_ok_target_count": sum(1 for r in target_reports if r["exists"] and r["compile_ok"]),
        "current_core_or_options_source_count": sum(
            1 for r in target_reports
            if r["classification"] in {
                "current_v21_core_engine_source",
                "current_v21_options_execution_source",
            }
        ),
        "artifact_expectation_count": len(artifact_reports),
        "existing_artifact_count": sum(1 for r in artifact_reports if r["exists"]),
        "consumer_count": len(consumers),
        "production_blocker_count": len(production_blockers),
        "closure_state": "closed_current_v21_rules_no_legacy_rulebook_promotion" if len(production_blockers) == 0 else "blocked_v21_rule_source_review",
        "target_reports": [
            {
                "label": r["label"],
                "path": r["path"],
                "expected_role": r["expected_role"],
                "required": r["required"],
                "exists": r["exists"],
                "compile_ok": r["compile_ok"],
                "function_count": r["function_count"],
                "assignment_count": r["assignment_count"],
                "classification": r["classification"],
            }
            for r in target_reports
        ],
        "artifact_reports": artifact_reports,
        "top_consumers": consumers[:25],
        "paths": {
            "summary_path": "artifacts/stage40c9d_v21_steps_27_29_rules_closure_audit/signalforge_stage40c9d_v21_steps_27_29_rules_closure_audit_summary.json",
            "detail_path": "artifacts/stage40c9d_v21_steps_27_29_rules_closure_audit/signalforge_stage40c9d_v21_steps_27_29_rules_closure_audit_detail.json",
        },
    }

    detail = {
        **summary,
        "target_reports_detail": target_reports,
        "consumers": consumers,
    }

    (OUT / "signalforge_stage40c9d_v21_steps_27_29_rules_closure_audit_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    (OUT / "signalforge_stage40c9d_v21_steps_27_29_rules_closure_audit_detail.json").write_text(
        json.dumps(detail, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
