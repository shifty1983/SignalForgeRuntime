from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any


REPO = Path(".").resolve()
OUT = REPO / "artifacts/stage40c9c_v21_steps_27_29_rule_source_locator"

SOURCE_ROOTS = [
    REPO / "src",
    REPO / "tools",
    REPO / "docs",
]

ARTIFACT_ROOTS = [
    REPO / "artifacts",
]

EXCLUDE_SOURCE_PATHS = {
    "src/signalforge/rulebooks/v3_2_2.py",
}

EXCLUDE_NAME_PREFIXES = [
    "stage40c9a",
    "stage40c9b",
    "stage40c9c",
]

STAGE_TERMS = [
    "stage27",
    "stage_27",
    "stage 27",
    "27_",
    "step27",
    "step_27",
    "step 27",
    "stage28",
    "stage_28",
    "stage 28",
    "28_",
    "step28",
    "step_28",
    "step 28",
    "stage29",
    "stage_29",
    "stage 29",
    "29_",
    "step29",
    "step_29",
    "step 29",
]

V21_RULE_TERMS = [
    "v21",
    "resolved_execution_rules_v21",
    "resolved_strategy_execution_rules_v21",
    "signalforge_resolved_strategy_execution_rules_v21",
    "execution_rules_v21",
    "strategy_execution_rules",
    "resolved execution rules",
    "execution qualified",
    "execution_qualified",
    "execution rejected",
    "execution_rejected",
    "paper_order_intent",
    "broker_translation",
    "order_intent",
    "broker intent",
    "rule",
    "rules",
    "ruleset",
    "execution rule",
    "strategy rule",
]

CANONICAL_ARTIFACT_TERMS = [
    "canonical_replay_validation",
    "v21_restart_from_corrected_option_layer",
    "10_resolved_execution_rules_v21",
    "11_execution_qualified_strategy_candidates",
    "resolved_execution_rules",
    "execution_qualified_historical_strategy_candidates",
    "paper_order_intent_broker_translation",
]

LOGIC_TERMS = [
    "def ",
    "class ",
    "argparse",
    "read_jsonl",
    "write_jsonl",
    "build_",
    "main(",
    "if __name__",
]


def rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def safe_read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig", errors="ignore")
    except Exception:
        return ""


def should_skip(path: Path) -> bool:
    if set(path.parts) & {".git", ".venv", "venv", "__pycache__"}:
        return True

    r = rel(path)
    if r in EXCLUDE_SOURCE_PATHS:
        return True

    return any(path.name.startswith(prefix) for prefix in EXCLUDE_NAME_PREFIXES)


def count_terms(text: str, terms: list[str]) -> dict[str, int]:
    lowered = text.lower()
    return {
        term: lowered.count(term.lower())
        for term in terms
        if lowered.count(term.lower())
    }


def stage_hits(path_text: str, text: str) -> dict[str, Any]:
    combined = f"{path_text}\n{text}".lower()

    return {
        "stage_27": any(t in combined for t in ["stage27", "stage_27", "stage 27", "step27", "step_27", "step 27", "/27_", "\\27_"]),
        "stage_28": any(t in combined for t in ["stage28", "stage_28", "stage 28", "step28", "step_28", "step 28", "/28_", "\\28_"]),
        "stage_29": any(t in combined for t in ["stage29", "stage_29", "stage 29", "step29", "step_29", "step 29", "/29_", "\\29_"]),
    }


def source_function_count(path: Path) -> int:
    if path.suffix.lower() != ".py":
        return 0

    try:
        tree = ast.parse(safe_read(path), filename=str(path))
    except SyntaxError:
        return 0

    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    )


def source_files() -> list[dict[str, Any]]:
    rows = []

    for root in SOURCE_ROOTS:
        if not root.exists():
            continue

        for path in root.rglob("*"):
            if not path.is_file() or should_skip(path):
                continue

            if path.suffix.lower() not in {".py", ".md", ".json", ".jsonl", ".txt", ".ps1"}:
                continue

            r = rel(path)
            text = safe_read(path)

            v21_hits = count_terms(r + "\n" + text, V21_RULE_TERMS)
            stage_term_hits = count_terms(r + "\n" + text, STAGE_TERMS)
            canonical_hits = count_terms(r + "\n" + text, CANONICAL_ARTIFACT_TERMS)
            logic_hits = count_terms(text, LOGIC_TERMS)
            stages = stage_hits(r, text)

            score = (
                sum(v21_hits.values()) * 3
                + sum(stage_term_hits.values()) * 4
                + sum(canonical_hits.values()) * 5
                + sum(logic_hits.values())
            )

            if score <= 0:
                continue

            rows.append({
                "path": r,
                "suffix": path.suffix,
                "score": score,
                "function_count": source_function_count(path),
                "stage_hits": stages,
                "v21_rule_hits": v21_hits,
                "stage_term_hits": stage_term_hits,
                "canonical_artifact_hits": canonical_hits,
                "logic_hits": logic_hits,
                "size_bytes": path.stat().st_size,
            })

    return sorted(rows, key=lambda r: (-r["score"], -r["function_count"], r["path"]))


def artifact_files() -> list[dict[str, Any]]:
    rows = []

    for root in ARTIFACT_ROOTS:
        if not root.exists():
            continue

        for path in root.rglob("*"):
            if not path.is_file() or should_skip(path):
                continue

            r = rel(path)
            path_lower = r.lower()

            v21_hits = count_terms(path_lower, V21_RULE_TERMS)
            stage_term_hits = count_terms(path_lower, STAGE_TERMS)
            canonical_hits = count_terms(path_lower, CANONICAL_ARTIFACT_TERMS)
            stages = stage_hits(r, "")

            score = (
                sum(v21_hits.values()) * 3
                + sum(stage_term_hits.values()) * 4
                + sum(canonical_hits.values()) * 5
            )

            if score <= 0:
                continue

            rows.append({
                "path": r,
                "suffix": path.suffix,
                "score": score,
                "stage_hits": stages,
                "v21_rule_hits": v21_hits,
                "stage_term_hits": stage_term_hits,
                "canonical_artifact_hits": canonical_hits,
                "size_bytes": path.stat().st_size,
            })

    return sorted(rows, key=lambda r: (-r["score"], r["path"]))


def infer_candidate_role(row: dict[str, Any]) -> str:
    p = row["path"].lower()
    hits = row.get("v21_rule_hits", {})
    canon = row.get("canonical_artifact_hits", {})

    if "resolved_execution_rules_v21" in p or "resolved_strategy_execution_rules_v21" in p:
        return "v21_resolved_execution_rules"

    if "execution_qualified" in p or "execution qualified" in p:
        return "v21_execution_qualified_candidates"

    if "paper_order_intent" in p or "broker_translation" in p or "order_intent" in p:
        return "v21_order_intent_or_broker_translation"

    if "rule" in p or hits.get("rule") or hits.get("rules") or hits.get("execution rule"):
        return "v21_rule_source_candidate"

    if canon:
        return "v21_canonical_artifact_reference"

    return "v21_related_unknown"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    sources = source_files()
    artifacts = artifact_files()

    python_candidates = [
        {**row, "candidate_role": infer_candidate_role(row)}
        for row in sources
        if row["suffix"] == ".py"
    ]

    high_confidence_sources = [
        row for row in python_candidates
        if (
            row["function_count"] > 0
            and (
                "v21" in row["path"].lower()
                or row["canonical_artifact_hits"]
                or row["stage_term_hits"]
                or row["v21_rule_hits"].get("resolved_execution_rules_v21")
                or row["v21_rule_hits"].get("resolved_strategy_execution_rules_v21")
                or row["v21_rule_hits"].get("paper_order_intent")
                or row["v21_rule_hits"].get("broker_translation")
            )
        )
    ]

    artifact_roles = [
        {**row, "candidate_role": infer_candidate_role(row)}
        for row in artifacts
    ]

    summary = {
        "adapter_type": "stage40c9c_v21_steps_27_29_rule_source_locator",
        "artifact_type": "signalforge_stage40c9c_v21_steps_27_29_rule_source_locator",
        "contract": "stage40c9c_v21_steps_27_29_rule_source_locator",
        "is_ready": len(high_confidence_sources) > 0 or len(artifact_roles) > 0,
        "stage": "v21_canonical_steps_27_29_rules",
        "excluded_legacy_rulebook": "src/signalforge/rulebooks/v3_2_2.py",
        "source_match_count": len(sources),
        "artifact_match_count": len(artifacts),
        "python_candidate_count": len(python_candidates),
        "high_confidence_source_count": len(high_confidence_sources),
        "top_high_confidence_sources": high_confidence_sources[:50],
        "top_python_candidates": python_candidates[:75],
        "top_artifact_candidates": artifact_roles[:75],
        "paths": {
            "summary_path": "artifacts/stage40c9c_v21_steps_27_29_rule_source_locator/signalforge_stage40c9c_v21_steps_27_29_rule_source_locator_summary.json",
            "detail_path": "artifacts/stage40c9c_v21_steps_27_29_rule_source_locator/signalforge_stage40c9c_v21_steps_27_29_rule_source_locator_detail.json",
        },
    }

    detail = {
        **summary,
        "all_sources": sources,
        "all_artifacts": artifact_roles,
    }

    (OUT / "signalforge_stage40c9c_v21_steps_27_29_rule_source_locator_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    (OUT / "signalforge_stage40c9c_v21_steps_27_29_rule_source_locator_detail.json").write_text(
        json.dumps(detail, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
