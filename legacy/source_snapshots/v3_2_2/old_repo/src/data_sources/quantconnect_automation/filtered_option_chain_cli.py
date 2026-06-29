from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .filtered_option_chain_plan import (
    FILTERED_OPTION_CHAIN_ARTIFACT_TYPE,
    FILTERED_OPTION_CHAIN_SUMMARY_SCHEMA_VERSION,
    build_filtered_option_chain_export_plan,
    build_quantconnect_research_export_script,
    load_manifest,
)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a QuantConnect filtered option-chain export plan and generated Research script."
    )
    parser.add_argument("--manifest", required=True, help="Path to the filtered option-chain manifest JSON.")
    parser.add_argument("--output-dir", required=True, help="Directory where the plan, script, and summary are written.")
    args = parser.parse_args(argv)

    manifest = load_manifest(args.manifest)
    plan = build_filtered_option_chain_export_plan(manifest)
    script = build_quantconnect_research_export_script(plan)

    output_dir = Path(args.output_dir)
    plan_path = output_dir / "signalforge_quantconnect_filtered_option_chain_export_plan.json"
    script_path = output_dir / "quantconnect_filtered_option_chain_export_research_script.py"
    summary_path = output_dir / "signalforge_quantconnect_filtered_option_chain_export_summary.json"

    _write_json(plan_path, plan)
    _write_text(script_path, script)

    summary = {
        "artifact_type": f"{FILTERED_OPTION_CHAIN_ARTIFACT_TYPE}_cli_summary",
        "schema_version": FILTERED_OPTION_CHAIN_SUMMARY_SCHEMA_VERSION,
        "status": "ready" if plan.get("is_ready") else "blocked",
        "is_ready": bool(plan.get("is_ready")),
        "manifest": str(args.manifest),
        "output_dir": str(output_dir),
        "plan_file": str(plan_path),
        "research_script_file": str(script_path),
        "start": plan.get("start"),
        "end": plan.get("end"),
        "date_alignment": plan.get("date_alignment"),
        "symbol_count": plan.get("symbol_count", 0),
        "symbol_batch_count": plan.get("symbol_batch_count", 0),
        "date_window_count": plan.get("date_window_count", 0),
        "export_job_count": plan.get("export_job_count", 0),
        "min_dte": plan.get("min_dte"),
        "max_dte": plan.get("max_dte"),
        "strike_window_percent": plan.get("strike_window_percent"),
        "moneyness_lower_bound": plan.get("moneyness_lower_bound"),
        "moneyness_upper_bound": plan.get("moneyness_upper_bound"),
        "object_store_prefix": plan.get("object_store_prefix"),
        "requires_manual_approval": True,
        "warning_count": plan.get("warning_count", 0),
        "warnings": plan.get("warnings", []),
        "blocker_count": plan.get("blocker_count", 0),
        "blockers": plan.get("blockers", []),
        "explicit_exclusions": plan.get("explicit_exclusions", []),
    }
    _write_json(summary_path, summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["is_ready"] else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
