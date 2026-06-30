from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


OUTPUT_ROOT = Path("artifacts/migrated_workflow_dry_run_20210601_20260531")

EXPECTANCY_MODULE = "signalforge.backtesting.walk_forward_expectancy_cli"

SOURCE_OUTCOME_ROWS = (
    OUTPUT_ROOT
    / "stage1_artifact_mirror"
    / "02b_historical_strategy_outcome_rows_complete_quote"
    / "historical_strategy_outcome_rows_complete_quote_rows.jsonl"
)

SOURCE_EXPECTANCY_SUMMARY = (
    OUTPUT_ROOT
    / "stage1_artifact_mirror"
    / "03_walk_forward_expectancy"
    / "walk_forward_expectancy_summary.json"
)

STAGE6_OUTPUT_DIR = OUTPUT_ROOT / "stage6_walk_forward_expectancy_rebuild"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def capture_cli_help(module: str) -> dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, "-m", module, "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    return {
        "module": module,
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "help_ready": completed.returncode == 0,
    }


def build_stage6_expectancy_rebuild_probe() -> dict[str, Any]:
    cli_help = capture_cli_help(EXPECTANCY_MODULE)
    help_text = f'{cli_help.get("stdout", "")}\n{cli_help.get("stderr", "")}'.lower()

    detected_flags = []
    for token in [
        "--decision-rows",
        "--minimum-sample-count",
        "--output-dir",
        "--output",
    ]:
        if token in help_text:
            detected_flags.append(token)

    source_summary = read_json(SOURCE_EXPECTANCY_SUMMARY) if SOURCE_EXPECTANCY_SUMMARY.exists() else {}
    source_paths = source_summary.get("paths") or {}

    blockers: list[str] = []

    if not SOURCE_OUTCOME_ROWS.exists():
        blockers.append("source_strategy_outcome_rows_missing")

    if not SOURCE_EXPECTANCY_SUMMARY.exists():
        blockers.append("source_expectancy_summary_missing")

    if not cli_help["help_ready"]:
        blockers.append("walk_forward_expectancy_cli_help_failed")

    if "--decision-rows" not in detected_flags:
        blockers.append("expectancy_decision_rows_flag_not_detected")

    if "--output-dir" not in detected_flags:
        blockers.append("expectancy_output_dir_flag_not_detected")

    return {
        "adapter_type": "migrated_workflow_stage6_expectancy_rebuild_probe_builder",
        "artifact_type": "signalforge_migrated_workflow_stage6_expectancy_rebuild_probe",
        "candidate_id": "signalforge_v3_2_2_paper_candidate",
        "module": EXPECTANCY_MODULE,
        "source_strategy_outcome_rows": str(SOURCE_OUTCOME_ROWS),
        "source_expectancy_summary": str(SOURCE_EXPECTANCY_SUMMARY),
        "source_expectancy_paths": source_paths,
        "planned_output_dir": str(STAGE6_OUTPUT_DIR),
        "cli_help": cli_help,
        "detected_flags": detected_flags,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "is_ready": len(blockers) == 0,
        "readiness_scope": "walk_forward_expectancy_cli_uses_strategy_outcome_rows_via_decision_rows_flag",
    }


def main() -> int:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    STAGE6_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    result = build_stage6_expectancy_rebuild_probe()

    output_path = OUTPUT_ROOT / "signalforge_migrated_workflow_stage6_expectancy_rebuild_probe.json"
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")

    help_path = OUTPUT_ROOT / "stage6_walk_forward_expectancy_cli_help.txt"
    help_path.write_text(
        f'{result["cli_help"].get("stdout", "")}\n{result["cli_help"].get("stderr", "")}',
        encoding="utf-8",
    )

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())


