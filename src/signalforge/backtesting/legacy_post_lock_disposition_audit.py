from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


OUTPUT_ROOT = Path("artifacts/migrated_workflow_dry_run_20210601_20260531")

LEGACY_ARTIFACT_ROOT = Path(os.environ.get(
    "SIGNALFORGE_LEGACY_POST_LOCK_DISPOSITION_ARTIFACT_ROOT",
    r"C:\Users\02011715\Documents\SignalForge\raw_data_layer\artifacts",
))


CATEGORY_RULES = [
    {
        "category": "already_migrated_or_superseded_by_v3_2_2_lock",
        "patterns": [
            "v3_2_1_paper_candidate_ruleset_lock",
            "v3_2_2_paper_candidate_ruleset_lock",
            "v3_2_1_spread_guardrail_metrics_stress",
            "v3_2_1_native_quote",
            "v3_2_2_native_quote",
            "v3_2_2_symbol_regime",
            "v3_2_2_iron_butterfly",
            "v3_2_2_pre_broker",
        ],
        "recommended_action": "do_not_remigrate_for_historical_closure",
    },
    {
        "category": "paper_trading_runtime_candidate",
        "patterns": [
            "ibkr_paper",
            "paper_order",
            "paper_trading_pipeline",
            "primary_strategy_candidate_profile",
            "primary_strategy_paper_order_intent",
        ],
        "recommended_action": "review_for_runtime_or_paper_trading_migration",
    },
    {
        "category": "deployment_readiness_candidate",
        "patterns": [
            "deployment",
            "execution_translation",
            "broker",
            "readiness",
            "portfolio_deployment_readiness",
        ],
        "recommended_action": "review_after_runtime_paper_trade_design",
    },
    {
        "category": "complete_ruleset_reporting_candidate",
        "patterns": [
            "complete_ruleset",
            "anchored",
            "drawdown",
            "metrics_report_complete_ruleset",
        ],
        "recommended_action": "review_for_reporting_snapshot_migration",
    },
    {
        "category": "large_research_or_optimization_artifact",
        "patterns": [
            "historical_expectancy_candidate_rows",
            "historical_strategy_candidate_rows",
            "portfolio_exit_path",
            "minimum_capital",
            "contract_granular",
            "open_exposure",
            "option_behavior_source_readiness",
            "partitioned_option_behavior",
        ],
        "recommended_action": "archive_reference_only_unless_needed_for_new_research",
    },
    {
        "category": "candidate_snapshot_or_project_metadata",
        "patterns": [
            "project_current_candidate_snapshot",
            "project_metrics_snapshot",
            "portfolio_candidate_selection",
            "positive_candidate_fixture",
            "current_candidate",
        ],
        "recommended_action": "review_for_current_project_snapshot_migration",
    },
]


def classify_name(name: str) -> tuple[str, str]:
    low = name.lower()

    for rule in CATEGORY_RULES:
        if any(pattern.lower() in low for pattern in rule["patterns"]):
            return rule["category"], rule["recommended_action"]

    return "uncategorized_legacy_post_lock_artifact", "manual_review_required"


def folder_inventory(folder: Path) -> dict[str, Any]:
    files = [path for path in folder.rglob("*") if path.is_file()]
    py_files = [path for path in files if path.suffix.lower() == ".py"]
    json_files = [path for path in files if path.suffix.lower() == ".json"]
    jsonl_files = [path for path in files if path.suffix.lower() == ".jsonl"]
    md_files = [path for path in files if path.suffix.lower() in {".md", ".markdown"}]

    category, recommended_action = classify_name(folder.name)

    return {
        "name": folder.name,
        "path": str(folder),
        "category": category,
        "recommended_action": recommended_action,
        "file_count": len(files),
        "total_bytes": sum(path.stat().st_size for path in files),
        "py_file_count": len(py_files),
        "json_file_count": len(json_files),
        "jsonl_file_count": len(jsonl_files),
        "markdown_file_count": len(md_files),
        "sample_files": [str(path.relative_to(folder)) for path in files[:10]],
    }


def build_legacy_post_lock_disposition_audit() -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []

    if not LEGACY_ARTIFACT_ROOT.exists():
        blockers.append(f"legacy_artifact_root_missing: {LEGACY_ARTIFACT_ROOT}")
        folders: list[Path] = []
    else:
        folders = sorted(path for path in LEGACY_ARTIFACT_ROOT.iterdir() if path.is_dir())

    legacy_rows = [
        folder_inventory(folder)
        for folder in folders
        if any(
            token in folder.name.lower()
            for token in [
                "complete_ruleset",
                "current",
                "paper",
                "broker",
                "execution",
                "runtime",
                "deployment",
                "readiness",
                "locked",
                "drawdown",
                "anchored",
                "metrics",
                "candidate",
                "option_behavior_source_readiness",
                "minimum_capital",
                "open_exposure",
                "contract_granular",
            ]
        )
    ]

    category_counts: dict[str, int] = {}
    action_counts: dict[str, int] = {}

    for row in legacy_rows:
        category_counts[row["category"]] = category_counts.get(row["category"], 0) + 1
        action_counts[row["recommended_action"]] = action_counts.get(row["recommended_action"], 0) + 1

    uncategorized = [
        row for row in legacy_rows
        if row["category"] == "uncategorized_legacy_post_lock_artifact"
    ]

    runtime_candidates = [
        row for row in legacy_rows
        if row["recommended_action"] == "review_for_runtime_or_paper_trading_migration"
    ]

    deployment_candidates = [
        row for row in legacy_rows
        if row["recommended_action"] == "review_after_runtime_paper_trade_design"
    ]

    if uncategorized:
        warnings.append("Some legacy post-lock artifacts are uncategorized and need manual review.")

    if runtime_candidates:
        warnings.append("Paper-trading/runtime candidates found; review before building the runtime migration plan.")

    if deployment_candidates:
        warnings.append("Deployment-readiness candidates found; defer until runtime paper-trading design is stable.")

    return {
        "adapter_type": "legacy_post_lock_disposition_audit_builder",
        "artifact_type": "signalforge_legacy_post_lock_disposition_audit",
        "contract": "legacy_post_lock_disposition_audit",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,
        "legacy_artifact_root": str(LEGACY_ARTIFACT_ROOT),
        "legacy_post_lock_artifact_count": len(legacy_rows),
        "category_counts": category_counts,
        "recommended_action_counts": action_counts,
        "runtime_candidate_count": len(runtime_candidates),
        "deployment_candidate_count": len(deployment_candidates),
        "uncategorized_count": len(uncategorized),
        "runtime_candidates": runtime_candidates,
        "deployment_candidates": deployment_candidates,
        "uncategorized_artifacts": uncategorized,
        "legacy_post_lock_artifacts": legacy_rows,
        "readiness_scope": "classifies_legacy_post_lock_artifacts_for_next_migration_or_archive_decision",
    }


def build_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# SignalForge Legacy Post-Lock Disposition Audit",
        "",
        f"Is ready: `{result['is_ready']}`",
        f"Blocker count: `{result['blocker_count']}`",
        f"Warning count: `{result['warning_count']}`",
        f"Legacy post-lock artifact count: `{result['legacy_post_lock_artifact_count']}`",
        "",
        "## Category counts",
        "",
    ]

    for category, count in sorted(result["category_counts"].items()):
        lines.append(f"- `{category}`: {count}")

    lines.extend(["", "## Recommended action counts", ""])

    for action, count in sorted(result["recommended_action_counts"].items()):
        lines.append(f"- `{action}`: {count}")

    lines.extend(["", "## Runtime / paper-trading candidates", ""])

    for row in result["runtime_candidates"]:
        lines.append(f"- `{row['name']}` files={row['file_count']} bytes={row['total_bytes']}")

    lines.extend(["", "## Deployment-readiness candidates", ""])

    for row in result["deployment_candidates"]:
        lines.append(f"- `{row['name']}` files={row['file_count']} bytes={row['total_bytes']}")

    lines.extend(["", "## Uncategorized artifacts", ""])

    for row in result["uncategorized_artifacts"]:
        lines.append(f"- `{row['name']}` files={row['file_count']} bytes={row['total_bytes']}")

    lines.append("")
    return "\n".join(lines)


def main() -> int:
    result = build_legacy_post_lock_disposition_audit()

    json_path = OUTPUT_ROOT / "signalforge_legacy_post_lock_disposition_audit.json"
    md_path = OUTPUT_ROOT / "signalforge_legacy_post_lock_disposition_audit.md"

    json_path.write_text(json.dumps(result, indent=2, sort_keys=True, default=str), encoding="utf-8")
    md_path.write_text(build_markdown(result), encoding="utf-8")

    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())


