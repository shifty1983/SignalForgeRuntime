from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


OUTPUT_ROOT = Path("artifacts/migrated_workflow_dry_run_20210601_20260531")

LEG_SELECTION_MODULE = "signalforge.backtesting.historical_strategy_leg_selection_rows_cli"

GENERATED_SELECTION_ROWS = (
    OUTPUT_ROOT
    / "stage7_strategy_selection_rebuild"
    / "signalforge_historical_strategy_selection_rows.jsonl"
)

GENERATED_EXPECTANCY_ROWS = (
    OUTPUT_ROOT
    / "stage1_artifact_mirror"
    / "03b_walk_forward_expectancy_safe_all_quote_rows"
    / "walk_forward_expectancy_safe_all_quote_rows.jsonl"
)

GENERATED_CANDIDATE_ROWS = (
    OUTPUT_ROOT
    / "stage5_candidate_rows_rebuild"
    / "signalforge_historical_strategy_candidate_rows.jsonl"
)

SOURCE_LEG_SELECTION_ROWS = (
    OUTPUT_ROOT
    / "stage1_artifact_mirror"
    / "05_historical_strategy_leg_selection_rows"
    / "historical_strategy_leg_selection_rows_rows.jsonl"
)

SOURCE_LEG_SELECTION_SUMMARY = (
    OUTPUT_ROOT
    / "stage1_artifact_mirror"
    / "05_historical_strategy_leg_selection_rows"
    / "historical_strategy_leg_selection_rows_summary.json"
)

STAGE8_OUTPUT_DIR = OUTPUT_ROOT / "stage8_strategy_leg_selection_rebuild"


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


def build_stage8_strategy_leg_selection_rebuild_probe() -> dict[str, Any]:
    cli_help = capture_cli_help(LEG_SELECTION_MODULE)
    help_text = f'{cli_help.get("stdout", "")}\n{cli_help.get("stderr", "")}'.lower()

    detected_flags = []
    for token in [
        "--strategy-selection-rows",
        "--selection-rows",
        "--historical-strategy-selection-rows",
        "--expectancy-rows",
        "--walk-forward-expectancy-rows",
        "--candidate-rows",
        "--raw-option-input",
        "--strategy-candidate-rows",
        "--historical-strategy-candidate-rows",
        "--option-rows",
        "--option-chain-rows",
        "--output-dir",
        "--output",
    ]:
        if token in help_text:
            detected_flags.append(token)

    blockers: list[str] = []

    if not SOURCE_LEG_SELECTION_ROWS.exists():
        blockers.append("source_leg_selection_rows_missing")

    if not SOURCE_LEG_SELECTION_SUMMARY.exists():
        blockers.append("source_leg_selection_summary_missing")

    if not cli_help["help_ready"]:
        blockers.append("strategy_leg_selection_cli_help_failed")

    if "--output-dir" not in detected_flags:
        blockers.append("leg_selection_output_dir_flag_not_detected")

    if "--raw-option-input" not in detected_flags:
        blockers.append("leg_selection_raw_option_input_flag_not_detected")

    if not any(flag in detected_flags for flag in [
        "--strategy-selection-rows",
        "--selection-rows",
        "--historical-strategy-selection-rows",
        "--expectancy-rows",
        "--walk-forward-expectancy-rows",
        "--candidate-rows",
        "--raw-option-input",
        "--strategy-candidate-rows",
        "--historical-strategy-candidate-rows",
    ]):
        blockers.append("leg_selection_input_rows_flag_not_detected")

    return {
        "adapter_type": "migrated_workflow_stage8_strategy_leg_selection_rebuild_probe_builder",
        "artifact_type": "signalforge_migrated_workflow_stage8_strategy_leg_selection_rebuild_probe",
        "candidate_id": "signalforge_v3_2_2_paper_candidate",
        "module": LEG_SELECTION_MODULE,
        "generated_selection_rows": str(GENERATED_SELECTION_ROWS),
        "generated_expectancy_rows": str(GENERATED_EXPECTANCY_ROWS),
        "generated_candidate_rows": str(GENERATED_CANDIDATE_ROWS),
        "source_leg_selection_rows": str(SOURCE_LEG_SELECTION_ROWS),
        "source_leg_selection_summary": str(SOURCE_LEG_SELECTION_SUMMARY),
        "planned_output_dir": str(STAGE8_OUTPUT_DIR),
        "cli_help": cli_help,
        "detected_flags": detected_flags,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "is_ready": len(blockers) == 0,
        "readiness_scope": "historical_strategy_leg_selection_cli_contract_probe",
    }


def main() -> int:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    STAGE8_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    result = build_stage8_strategy_leg_selection_rebuild_probe()

    output_path = OUTPUT_ROOT / "signalforge_migrated_workflow_stage8_strategy_leg_selection_rebuild_probe.json"
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")

    help_path = OUTPUT_ROOT / "stage8_strategy_leg_selection_cli_help.txt"
    help_path.write_text(
        f'{result["cli_help"].get("stdout", "")}\n{result["cli_help"].get("stderr", "")}',
        encoding="utf-8",
    )

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
