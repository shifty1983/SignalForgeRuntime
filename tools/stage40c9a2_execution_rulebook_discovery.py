from __future__ import annotations

import json
from pathlib import Path


REPO = Path(".").resolve()
OUT = REPO / "artifacts/stage40c9a2_execution_rulebook_discovery"

SOURCE_ROOTS = [
    REPO / "src",
    REPO / "tools",
    REPO / "docs",
]

ARTIFACT_ROOT = REPO / "artifacts"

CONTENT_TERMS = [
    "portfolio_execution_translation_rulebook",
    "execution_translation_rulebook",
    "translation_rulebook",
    "execution_gap_audit",
    "execution_gap_resolution",
    "broker_capability_warning",
    "broker_capability",
    "paper_trade_supported",
    "live_trade_supported",
    "close_rule_mapped_strategy_count",
    "defense_rule_mapped_strategy_count",
    "unmapped_exit_logic",
    "execution_translation",
    "execution rulebook",
    "rulebook",
]

FILENAME_TERMS = [
    "rulebook",
    "translation",
    "execution",
    "deployment",
    "readiness",
    "broker",
    "live",
    "paper",
]


def rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def safe_read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig", errors="ignore")
    except Exception:
        return ""


def should_skip(path: Path) -> bool:
    skip_parts = {".git", ".venv", "venv", "__pycache__"}
    return bool(set(path.parts) & skip_parts)


def score_text(text: str) -> dict:
    lowered = text.lower()
    hits = {term: lowered.count(term.lower()) for term in CONTENT_TERMS}
    score = sum(hits.values())
    return {
        "score": score,
        "hits": {k: v for k, v in hits.items() if v},
    }


def discover_source_files() -> list[dict]:
    rows = []

    for root in SOURCE_ROOTS:
        if not root.exists():
            continue

        for path in root.rglob("*"):
            if should_skip(path) or not path.is_file():
                continue

            if path.suffix.lower() not in {".py", ".json", ".jsonl", ".md", ".txt", ".ps1"}:
                continue

            name_lower = path.name.lower()
            name_hits = [t for t in FILENAME_TERMS if t in name_lower]

            text = safe_read(path)
            scored = score_text(text)

            if name_hits or scored["score"] > 0:
                rows.append({
                    "path": rel(path),
                    "suffix": path.suffix,
                    "name_hits": name_hits,
                    "content_score": scored["score"],
                    "content_hits": scored["hits"],
                    "size_bytes": path.stat().st_size,
                })

    return sorted(
        rows,
        key=lambda r: (
            -r["content_score"],
            -len(r["name_hits"]),
            r["path"],
        ),
    )


def discover_artifact_paths() -> list[dict]:
    rows = []

    if not ARTIFACT_ROOT.exists():
        return rows

    for path in ARTIFACT_ROOT.rglob("*"):
        if should_skip(path) or not path.is_file():
            continue

        path_lower = rel(path).lower()
        name_hits = [t for t in CONTENT_TERMS + FILENAME_TERMS if t.lower() in path_lower]

        if name_hits:
            rows.append({
                "path": rel(path),
                "suffix": path.suffix,
                "path_hits": name_hits,
                "size_bytes": path.stat().st_size,
            })

    return sorted(rows, key=lambda r: (-len(r["path_hits"]), r["path"]))


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    source_matches = discover_source_files()
    artifact_matches = discover_artifact_paths()

    likely_source_candidates = [
        row for row in source_matches
        if row["path"].endswith(".py") and (
            row["content_score"] > 0
            or row["name_hits"]
        )
    ]

    likely_rulebook_candidates = [
        row for row in likely_source_candidates
        if (
            "rulebook" in row["path"].lower()
            or "translation" in row["path"].lower()
            or row["content_hits"].get("portfolio_execution_translation_rulebook", 0) > 0
            or row["content_hits"].get("execution_translation_rulebook", 0) > 0
            or row["content_hits"].get("close_rule_mapped_strategy_count", 0) > 0
            or row["content_hits"].get("defense_rule_mapped_strategy_count", 0) > 0
        )
    ]

    summary = {
        "adapter_type": "stage40c9a2_execution_rulebook_discovery",
        "artifact_type": "signalforge_stage40c9a2_execution_rulebook_discovery",
        "contract": "stage40c9a2_execution_rulebook_discovery",
        "is_ready": len(likely_rulebook_candidates) > 0,
        "stage": "26_execution_translation_rulebook",
        "source_match_count": len(source_matches),
        "artifact_path_match_count": len(artifact_matches),
        "likely_source_candidate_count": len(likely_source_candidates),
        "likely_rulebook_candidate_count": len(likely_rulebook_candidates),
        "likely_rulebook_candidates": likely_rulebook_candidates[:25],
        "top_source_matches": source_matches[:50],
        "top_artifact_path_matches": artifact_matches[:50],
        "paths": {
            "summary_path": "artifacts/stage40c9a2_execution_rulebook_discovery/signalforge_stage40c9a2_execution_rulebook_discovery_summary.json",
            "detail_path": "artifacts/stage40c9a2_execution_rulebook_discovery/signalforge_stage40c9a2_execution_rulebook_discovery_detail.json",
        },
    }

    detail = {
        **summary,
        "source_matches": source_matches,
        "artifact_path_matches": artifact_matches,
    }

    (OUT / "signalforge_stage40c9a2_execution_rulebook_discovery_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    (OUT / "signalforge_stage40c9a2_execution_rulebook_discovery_detail.json").write_text(
        json.dumps(detail, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
