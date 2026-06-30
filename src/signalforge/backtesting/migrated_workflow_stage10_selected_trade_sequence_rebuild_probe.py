from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


OUTPUT_ROOT = Path("artifacts/migrated_workflow_dry_run_20210601_20260531")

SELECTED_SEQUENCE_MODULE = "signalforge.backtesting.portfolio_selected_trade_sequence_cli"

GENERATED_SELECTION_ROWS = (
    OUTPUT_ROOT
    / "stage7_strategy_selection_rebuild"
    / "signalforge_historical_strategy_selection_rows.jsonl"
)

GENERATED_LEG_SELECTION_ROWS = (
    OUTPUT_ROOT
    / "stage8_strategy_leg_selection_rebuild"
    / "signalforge_historical_strategy_leg_selection_rows.jsonl"
)

GENERATED_POSITION_SIZING_ROWS = (
    OUTPUT_ROOT
    / "stage9_position_sizing_rebuild"
    / "signalforge_portfolio_position_sizing_replay.jsonl"
)

GENERATED_POSITION_SIZING_SUMMARY = (
    OUTPUT_ROOT
    / "stage9_position_sizing_rebuild"
    / "signalforge_portfolio_position_sizing_replay_summary.json"
)

SOURCE_SELECTED_SEQUENCE_ROWS = (
    OUTPUT_ROOT
    / "stage1_artifact_mirror"
    / "07_portfolio_selected_trade_sequence"
    / "portfolio_selected_trade_sequence_rows.jsonl"
)

SOURCE_SELECTED_SEQUENCE_SUMMARY = (
    OUTPUT_ROOT
    / "stage1_artifact_mirror"
    / "07_portfolio_selected_trade_sequence"
    / "portfolio_selected_trade_sequence_summary.json"
)

STAGE10_OUTPUT_DIR = OUTPUT_ROOT / "stage10_selected_trade_sequence_rebuild"


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


def build_stage10_selected_trade_sequence_rebuild_probe() -> dict[str, Any]:
    cli_help = capture_cli_help(SELECTED_SEQUENCE_MODULE)
    help_text = f'{cli_help.get("stdout", "")}\n{cli_help.get("stderr", "")}'.lower()

    tokens = [
        "--selected-strategy-outcome-rows",
        "--selected-strategy-outcome-summary",
        "--strategy-selection-rows",
        "--strategy-selection-summary",
        "--selection-rows",
        "--selected-strategy-rows",
        "--leg-selection-rows",
        "--position-sizing-rows",
        "--position-sizing-summary",
        "--sized-position-rows",
        "--portfolio-position-sizing-rows",
        "--output-dir",
        "--output",
        "--max-trades-per-day",
        "--max-symbol-trades-per-day",
        "--min-realized-return",
        "--max-realized-return",
    ]

    detected_flags = [token for token in tokens if token in help_text]

    blockers: list[str] = []

    if not cli_help["help_ready"]:
        blockers.append("selected_trade_sequence_cli_help_failed")

    if not SOURCE_SELECTED_SEQUENCE_ROWS.exists():
        blockers.append("source_selected_trade_sequence_rows_missing")

    if not SOURCE_SELECTED_SEQUENCE_SUMMARY.exists():
        blockers.append("source_selected_trade_sequence_summary_missing")

    if "--output-dir" not in detected_flags and "--output" not in detected_flags:
        blockers.append("selected_trade_sequence_output_flag_not_detected")

    if not any(flag in detected_flags for flag in [
        "--selected-strategy-outcome-rows",
        "--selected-strategy-outcome-summary",
        "--strategy-selection-rows",
        "--strategy-selection-summary",
        "--selection-rows",
        "--selected-strategy-rows",
        "--leg-selection-rows",
        "--position-sizing-rows",
        "--portfolio-position-sizing-rows",
        "--sized-position-rows",
    ]):
        blockers.append("selected_trade_sequence_input_rows_flag_not_detected")

    return {
        "adapter_type": "migrated_workflow_stage10_selected_trade_sequence_rebuild_probe_builder",
        "artifact_type": "signalforge_migrated_workflow_stage10_selected_trade_sequence_rebuild_probe",
        "candidate_id": "signalforge_v3_2_2_paper_candidate",
        "module": SELECTED_SEQUENCE_MODULE,
        "generated_selection_rows": str(GENERATED_SELECTION_ROWS),
        "generated_leg_selection_rows": str(GENERATED_LEG_SELECTION_ROWS),
        "generated_position_sizing_rows": str(GENERATED_POSITION_SIZING_ROWS),
        "generated_position_sizing_summary": str(GENERATED_POSITION_SIZING_SUMMARY),
        "source_selected_trade_sequence_rows": str(SOURCE_SELECTED_SEQUENCE_ROWS),
        "source_selected_trade_sequence_summary": str(SOURCE_SELECTED_SEQUENCE_SUMMARY),
        "planned_output_dir": str(STAGE10_OUTPUT_DIR),
        "cli_help": cli_help,
        "detected_flags": detected_flags,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "is_ready": len(blockers) == 0,
        "readiness_scope": "portfolio_selected_trade_sequence_cli_contract_probe",
    }


def main() -> int:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    STAGE10_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    result = build_stage10_selected_trade_sequence_rebuild_probe()

    output_path = OUTPUT_ROOT / "signalforge_migrated_workflow_stage10_selected_trade_sequence_rebuild_probe.json"
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")

    help_path = OUTPUT_ROOT / "stage10_selected_trade_sequence_cli_help.txt"
    help_path.write_text(
        f'{result["cli_help"].get("stdout", "")}\n{result["cli_help"].get("stderr", "")}',
        encoding="utf-8",
    )

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

