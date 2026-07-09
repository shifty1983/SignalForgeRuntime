from __future__ import annotations

import importlib
import json
import py_compile
import subprocess
from pathlib import Path
from typing import Any


REPO = Path(".").resolve()
OUT = REPO / "artifacts/stage40d0_post_commit_core_smoke"


CORE_MODULES = [
    "signalforge.engines.behavior.historical_decision_rows_core",
    "signalforge.engines.regime.historical_weekly_regime_index",
    "signalforge.engines.strategy_selection.term_structure_candidate_augmentation",
    "signalforge.engines.strategy_selection.selector_candidate_input",
    "signalforge.engines.strategy_selection.leg_selection",
    "signalforge.engines.strategy_selection.expectancy",
    "signalforge.engines.strategy_selection.expectancy_availability_safe",
    "signalforge.engines.strategy_selection.selection_pipeline",
    "signalforge.engines.strategy_selection.pruned_selection",
    "signalforge.engines.portfolio_construction.selected_trade_sequence",
    "signalforge.engines.portfolio_construction.position_sizing",
    "signalforge.engines.portfolio_construction.value_ranked_allocator",
    "signalforge.engines.portfolio_construction.value_ranked_allocator_v2",
    "signalforge.engines.strategy_selection.resolved_strategy_execution_rules_v21",
    "signalforge.engines.strategy_selection.execution_qualified_historical_strategy_candidates_v21",
    "signalforge.engines.strategy_selection.repaired_historical_strategy_candidates_v13_v21",
    "signalforge.options_execution.metric_driven_execution_overlay_v21",
    "signalforge.options_execution.option_contract_execution_features_v21",
    "signalforge.options_execution.resolved_strategy_execution_rules_v21",
]


WRAPPER_FILES = [
    {
        "label": "historical_decision_rows",
        "path": "src/signalforge/backtesting/historical_decision_rows.py",
        "must_contain": "signalforge.engines",
    },
    {
        "label": "term_structure_tool",
        "path": "tools/augment_repaired_candidates_with_term_structure.py",
        "must_contain": "signalforge.engines.strategy_selection.term_structure_candidate_augmentation",
    },
    {
        "label": "selector_candidate_input_tool",
        "path": "tools/build_v13_v21_selector_candidate_input.py",
        "must_contain": "signalforge.engines.strategy_selection.selector_candidate_input",
    },
    {
        "label": "leg_selection",
        "path": "src/signalforge/backtesting/historical_strategy_leg_selection_rows_builder.py",
        "must_contain": "signalforge.engines.strategy_selection.leg_selection",
    },
    {
        "label": "expectancy",
        "path": "src/signalforge/backtesting/walk_forward_expectancy_builder.py",
        "must_contain": "signalforge.engines.strategy_selection.expectancy",
    },
    {
        "label": "expectancy_availability_safe",
        "path": "src/signalforge/backtesting/walk_forward_expectancy_availability_safe_builder.py",
        "must_contain": "signalforge.engines.strategy_selection.expectancy_availability_safe",
    },
    {
        "label": "pruned_selection",
        "path": "src/signalforge/backtesting/historical_strategy_selection_cohort_risk_cli.py",
        "must_contain": "signalforge.engines.strategy_selection.pruned_selection",
    },
    {
        "label": "selected_trade_sequence",
        "path": "src/signalforge/backtesting/portfolio_selected_trade_sequence.py",
        "must_contain": "signalforge.engines.portfolio_construction.selected_trade_sequence",
    },
    {
        "label": "position_sizing",
        "path": "src/signalforge/backtesting/portfolio_position_sizing_replay.py",
        "must_contain": "signalforge.engines.portfolio_construction.position_sizing",
    },
    {
        "label": "value_ranked_allocator_v2",
        "path": "src/signalforge/backtesting/portfolio_value_ranked_allocator_v2.py",
        "must_contain": "signalforge.engines.portfolio_construction.value_ranked_allocator_v2",
    },
    {
        "label": "value_ranked_allocator_current",
        "path": "src/signalforge/backtesting/portfolio_value_ranked_allocator_v2_1_cli.py",
        "must_contain": "signalforge.engines.portfolio_construction.value_ranked_allocator",
    },
]


CLI_HELP_MODULES = [
    "src.signalforge.backtesting.historical_strategy_selection_cohort_risk_cli",
    "src.signalforge.backtesting.portfolio_value_ranked_allocator_v2_1_cli",
]


def rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def compile_path(path: Path) -> tuple[bool, str | None]:
    try:
        py_compile.compile(str(path), doraise=True)
        return True, None
    except Exception as exc:
        return False, str(exc)


def import_module(name: str) -> dict[str, Any]:
    try:
        module = importlib.import_module(name)
        return {
            "module": name,
            "ok": True,
            "file": getattr(module, "__file__", None),
            "error": None,
        }
    except Exception as exc:
        return {
            "module": name,
            "ok": False,
            "file": None,
            "error": repr(exc),
        }


def inspect_wrapper(spec: dict[str, str]) -> dict[str, Any]:
    path = REPO / spec["path"]
    exists = path.exists()
    text = path.read_text(encoding="utf-8-sig", errors="ignore") if exists else ""
    compile_ok, compile_error = compile_path(path) if exists else (False, "missing")

    return {
        "label": spec["label"],
        "path": spec["path"],
        "exists": exists,
        "compile_ok": compile_ok,
        "compile_error": compile_error,
        "must_contain": spec["must_contain"],
        "contains_required_core_reference": spec["must_contain"] in text,
        "is_ready": exists and compile_ok and spec["must_contain"] in text,
    }


def cli_help_smoke(module: str) -> dict[str, Any]:
    cmd = ["python", "-m", module, "--help"]

    try:
        proc = subprocess.run(
            cmd,
            cwd=REPO,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=30,
        )

        return {
            "module": module,
            "cmd": " ".join(cmd),
            "returncode": proc.returncode,
            "ok": proc.returncode == 0,
            "output_head": proc.stdout.splitlines()[:30],
        }

    except Exception as exc:
        return {
            "module": module,
            "cmd": " ".join(cmd),
            "returncode": None,
            "ok": False,
            "error": repr(exc),
            "output_head": [],
        }


def git(args: list[str]) -> dict[str, Any]:
    proc = subprocess.run(
        ["git", *args],
        cwd=REPO,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    return {
        "cmd": "git " + " ".join(args),
        "returncode": proc.returncode,
        "ok": proc.returncode == 0,
        "output": proc.stdout,
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    git_head = git(["log", "--oneline", "-1"])
    git_status = git(["status", "--short"])

    core_import_reports = [import_module(name) for name in CORE_MODULES]
    wrapper_reports = [inspect_wrapper(spec) for spec in WRAPPER_FILES]
    cli_help_reports = [cli_help_smoke(module) for module in CLI_HELP_MODULES]

    production_blockers = []

    production_blockers.extend([
        {
            "category": "core_import_failed",
            "module": row["module"],
            "error": row["error"],
        }
        for row in core_import_reports
        if not row["ok"]
    ])

    production_blockers.extend([
        {
            "category": "wrapper_not_ready",
            "label": row["label"],
            "path": row["path"],
            "compile_error": row["compile_error"],
            "must_contain": row["must_contain"],
        }
        for row in wrapper_reports
        if not row["is_ready"]
    ])

    production_blockers.extend([
        {
            "category": "cli_help_failed",
            "module": row["module"],
            "returncode": row["returncode"],
            "error": row.get("error"),
            "output_head": row.get("output_head", []),
        }
        for row in cli_help_reports
        if not row["ok"]
    ])

    summary = {
        "adapter_type": "stage40d0_post_commit_core_smoke_runner",
        "artifact_type": "signalforge_stage40d0_post_commit_core_smoke",
        "contract": "stage40d0_post_commit_core_smoke",
        "is_ready": len(production_blockers) == 0,
        "closure_state": "post_commit_core_smoke_passed" if len(production_blockers) == 0 else "post_commit_core_smoke_blocked",
        "git_head": git_head["output"].strip(),
        "git_status_short": git_status["output"].splitlines(),
        "core_module_count": len(core_import_reports),
        "core_module_import_ok_count": sum(1 for row in core_import_reports if row["ok"]),
        "wrapper_file_count": len(wrapper_reports),
        "wrapper_file_ready_count": sum(1 for row in wrapper_reports if row["is_ready"]),
        "cli_help_count": len(cli_help_reports),
        "cli_help_ok_count": sum(1 for row in cli_help_reports if row["ok"]),
        "production_blocker_count": len(production_blockers),
        "production_blockers": production_blockers,
        "paths": {
            "summary_path": "artifacts/stage40d0_post_commit_core_smoke/signalforge_stage40d0_post_commit_core_smoke_summary.json",
            "detail_path": "artifacts/stage40d0_post_commit_core_smoke/signalforge_stage40d0_post_commit_core_smoke_detail.json",
        },
    }

    detail = {
        **summary,
        "core_import_reports": core_import_reports,
        "wrapper_reports": wrapper_reports,
        "cli_help_reports": cli_help_reports,
    }

    (OUT / "signalforge_stage40d0_post_commit_core_smoke_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    (OUT / "signalforge_stage40d0_post_commit_core_smoke_detail.json").write_text(
        json.dumps(detail, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
