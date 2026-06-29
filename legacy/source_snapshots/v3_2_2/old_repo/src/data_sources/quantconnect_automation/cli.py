from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from .lean_cli_plan import DATA_PULL_ARTIFACT_TYPE, build_download_plan, load_manifest


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _run_commands(plan: dict[str, Any], *, cwd: str | None) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for command in plan.get("commands", []):
        args = [str(part) for part in command.get("args", [])]
        completed = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)
        results.append(
            {
                "index": command.get("index"),
                "purpose": command.get("purpose"),
                "returncode": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
                "status": "ready" if completed.returncode == 0 else "blocked",
            }
        )
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build or execute a QuantConnect LEAN CLI data pull plan.")
    parser.add_argument("--manifest", required=True, help="Path to the QuantConnect data automation manifest JSON.")
    parser.add_argument("--output-dir", required=True, help="Directory where the plan and execution summary are written.")
    parser.add_argument("--lean-workspace", default=None, help="Optional LEAN organization workspace to use as subprocess cwd.")
    parser.add_argument("--execute", action="store_true", help="Execute the planned LEAN CLI commands.")
    parser.add_argument(
        "--confirm-paid-data-downloads",
        action="store_true",
        help="Required with --execute because LEAN data downloads can consume QCC or require subscriptions.",
    )
    args = parser.parse_args(argv)

    manifest = load_manifest(args.manifest)
    plan = build_download_plan(manifest)

    output_dir = Path(args.output_dir)
    plan_path = output_dir / "signalforge_quantconnect_lean_rest_data_pull_plan.json"
    _write_json(plan_path, plan)

    execution_results: list[dict[str, Any]] = []
    execution_status = "dry_run"
    if args.execute:
        if not args.confirm_paid_data_downloads:
            execution_status = "blocked"
            execution_results.append(
                {
                    "status": "blocked",
                    "blocker": "confirm_paid_data_downloads_required",
                    "message": "Pass --confirm-paid-data-downloads to execute QuantConnect data download commands.",
                }
            )
        elif not plan.get("is_ready"):
            execution_status = "blocked"
            execution_results.append({"status": "blocked", "blocker": "plan_not_ready"})
        else:
            execution_results = _run_commands(plan, cwd=args.lean_workspace)
            execution_status = "ready" if all(item.get("returncode") == 0 for item in execution_results) else "blocked"

    summary = {
        "artifact_type": f"{DATA_PULL_ARTIFACT_TYPE}_cli_summary",
        "schema_version": "signalforge_quantconnect_lean_rest_data_pull_cli_summary.v1",
        "status": execution_status,
        "is_ready": execution_status in {"dry_run", "ready"},
        "manifest": str(args.manifest),
        "output_dir": str(output_dir),
        "plan_file": str(plan_path),
        "command_count": plan.get("command_count", 0),
        "execute": args.execute,
        "requires_manual_approval": True,
        "execution_results": execution_results,
        "explicit_exclusions": plan.get("explicit_exclusions", []),
    }
    summary_path = output_dir / "signalforge_quantconnect_lean_rest_data_pull_summary.json"
    _write_json(summary_path, summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["is_ready"] else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
