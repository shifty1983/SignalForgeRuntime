from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


OUTPUT_ROOT = Path("artifacts/migrated_workflow_dry_run_20210601_20260531")

POSITION_SIZING_MODULE = "signalforge.backtesting.portfolio_position_sizing_replay_cli"

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

SOURCE_POSITION_SIZING_ROWS = (
    OUTPUT_ROOT
    / "stage1_artifact_mirror"
    / "06_portfolio_position_sizing_replay"
    / "portfolio_position_sizing_replay_rows.jsonl"
)

SOURCE_POSITION_SIZING_SUMMARY = (
    OUTPUT_ROOT
    / "stage1_artifact_mirror"
    / "06_portfolio_position_sizing_replay"
    / "portfolio_position_sizing_replay_summary.json"
)

STAGE9_OUTPUT_DIR = OUTPUT_ROOT / "stage9_position_sizing_rebuild"


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


def build_stage9_position_sizing_rebuild_probe() -> dict[str, Any]:
    cli_help = capture_cli_help(POSITION_SIZING_MODULE)
    help_text = f'{cli_help.get("stdout", "")}\n{cli_help.get("stderr", "")}'.lower()

    tokens = [
        "--selected-trade-sequence-rows",
        "--selected-trade-sequence-summary",
        "--strategy-selection-rows",
        "--selection-rows",
        "--selected-strategy-rows",
        "--leg-selection-rows",
        "--position-sizing-rows",
        "--output-dir",
        "--output",
        "--initial-capital",
        "--starting-capital",
        "--risk-per-trade",
        "--max-risk-per-trade",
        "--max-positions",
        "--max-open-positions",
        "--portfolio-allocation",
        "--capital",
    ]

    detected_flags = [token for token in tokens if token in help_text]

    blockers: list[str] = []

    if not cli_help["help_ready"]:
        blockers.append("position_sizing_cli_help_failed")

    if not SOURCE_POSITION_SIZING_ROWS.exists():
        blockers.append("source_position_sizing_rows_missing")

    if not SOURCE_POSITION_SIZING_SUMMARY.exists():
        blockers.append("source_position_sizing_summary_missing")

    if "--output-dir" not in detected_flags and "--output" not in detected_flags:
        blockers.append("position_sizing_output_flag_not_detected")

    if not all(flag in detected_flags for flag in [
        "--selected-trade-sequence-rows",
        "--selected-trade-sequence-summary",
    ]):
        blockers.append("position_sizing_selected_trade_sequence_input_flags_not_detected")

    return {
        "adapter_type": "migrated_workflow_stage9_position_sizing_rebuild_probe_builder",
        "artifact_type": "signalforge_migrated_workflow_stage9_position_sizing_rebuild_probe",
        "candidate_id": "signalforge_v3_2_2_paper_candidate",
        "module": POSITION_SIZING_MODULE,
        "generated_selection_rows": str(GENERATED_SELECTION_ROWS),
        "generated_leg_selection_rows": str(GENERATED_LEG_SELECTION_ROWS),
        "source_position_sizing_rows": str(SOURCE_POSITION_SIZING_ROWS),
        "source_position_sizing_summary": str(SOURCE_POSITION_SIZING_SUMMARY),
        "planned_output_dir": str(STAGE9_OUTPUT_DIR),
        "cli_help": cli_help,
        "detected_flags": detected_flags,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "is_ready": len(blockers) == 0,
        "readiness_scope": "portfolio_position_sizing_replay_cli_requires_selected_trade_sequence_inputs",
    }


def main() -> int:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    STAGE9_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    result = build_stage9_position_sizing_rebuild_probe()

    output_path = OUTPUT_ROOT / "signalforge_migrated_workflow_stage9_position_sizing_rebuild_probe.json"
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")

    help_path = OUTPUT_ROOT / "stage9_position_sizing_cli_help.txt"
    help_path.write_text(
        f'{result["cli_help"].get("stdout", "")}\n{result["cli_help"].get("stderr", "")}',
        encoding="utf-8",
    )

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())




