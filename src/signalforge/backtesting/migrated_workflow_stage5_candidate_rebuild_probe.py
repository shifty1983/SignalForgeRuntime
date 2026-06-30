from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


OUTPUT_ROOT = Path("artifacts/migrated_workflow_dry_run_20210601_20260531")
STAGE1_MANIFEST_PATH = (
    OUTPUT_ROOT / "signalforge_migrated_workflow_stage1_artifact_mirror_replay.json"
)

CANDIDATE_MODULE = "signalforge.backtesting.historical_strategy_candidate_rows_cli"
STAGE5_OUTPUT_DIR = OUTPUT_ROOT / "stage5_candidate_rows_rebuild"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def get_stage1_row_path(stage_name: str) -> str:
    enriched_decision_rows = (
        OUTPUT_ROOT
        / "stage1_artifact_mirror"
        / "01b_historical_decision_rows_enriched_term_structure"
        / "historical_decision_rows_enriched_term_structure_rows.jsonl"
    )

    if stage_name == "historical_decision_rows" and enriched_decision_rows.exists():
        return str(enriched_decision_rows)

    stage1 = read_json(STAGE1_MANIFEST_PATH)

    for stage in stage1["stage_results"]:
        if stage["stage"] == stage_name:
            row_artifact = stage.get("row_artifact")
            if not row_artifact:
                raise ValueError(f"No row artifact found for stage: {stage_name}")
            return row_artifact["destination_path"]

    raise ValueError(f"Stage not found in stage1 manifest: {stage_name}")


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


def build_stage5_candidate_rebuild_probe() -> dict[str, Any]:
    decision_rows_path = get_stage1_row_path("historical_decision_rows")
    cli_help = capture_cli_help(CANDIDATE_MODULE)

    help_text = f'{cli_help.get("stdout", "")}\n{cli_help.get("stderr", "")}'.lower()

    detected_flags = []
    for token in [
        "--decision-rows",
        "--decision-rows-path",
        "--historical-decision-rows",
        "--input",
        "--input-path",
        "--output-dir",
        "--output",
    ]:
        if token in help_text:
            detected_flags.append(token)

    blockers: list[str] = []

    if not Path(decision_rows_path).exists():
        blockers.append("mirrored_decision_rows_missing")

    if not cli_help["help_ready"]:
        blockers.append("candidate_rows_cli_help_failed")

    if not any(flag in detected_flags for flag in [
        "--decision-rows",
        "--decision-rows-path",
        "--historical-decision-rows",
        "--input",
        "--input-path",
    ]):
        blockers.append("candidate_rows_cli_input_flag_not_detected")

    if not any(flag in detected_flags for flag in ["--output-dir", "--output"]):
        blockers.append("candidate_rows_cli_output_flag_not_detected")

    return {
        "adapter_type": "migrated_workflow_stage5_candidate_rebuild_probe_builder",
        "artifact_type": "signalforge_migrated_workflow_stage5_candidate_rebuild_probe",
        "candidate_id": "signalforge_v3_2_2_paper_candidate",
        "module": CANDIDATE_MODULE,
        "decision_rows_path": decision_rows_path,
        "planned_output_dir": str(STAGE5_OUTPUT_DIR),
        "cli_help": cli_help,
        "detected_flags": detected_flags,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "is_ready": len(blockers) == 0,
        "readiness_scope": "historical_strategy_candidate_rows_cli_has_input_and_output_contract_for_first_rebuild",
    }


def main() -> int:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    STAGE5_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    result = build_stage5_candidate_rebuild_probe()
    output_path = OUTPUT_ROOT / "signalforge_migrated_workflow_stage5_candidate_rebuild_probe.json"
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")

    help_path = OUTPUT_ROOT / "stage5_candidate_rows_cli_help.txt"
    help_path.write_text(
        f'{result["cli_help"].get("stdout", "")}\n{result["cli_help"].get("stderr", "")}',
        encoding="utf-8",
    )

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())




