from __future__ import annotations

import ast
import json
import py_compile
from pathlib import Path
from typing import Any


REPO = Path(".").resolve()
OUT = REPO / "artifacts/stage40c10_final_core_migration_closure"


CORE_FILES = [
    # Stage 06
    ("06_historical_decision_rows", "src/signalforge/engines/behavior/historical_decision_rows_core.py"),
    ("06_historical_weekly_regime_index", "src/signalforge/engines/regime/historical_weekly_regime_index.py"),

    # Stage 12 / 15 / 16
    ("12_term_structure_candidate_augmentation", "src/signalforge/engines/strategy_selection/term_structure_candidate_augmentation.py"),
    ("15_selector_candidate_input", "src/signalforge/engines/strategy_selection/selector_candidate_input.py"),
    ("16_leg_selection", "src/signalforge/engines/strategy_selection/leg_selection.py"),

    # Stage 18 / 19 / 21
    ("18_expectancy", "src/signalforge/engines/strategy_selection/expectancy.py"),
    ("18_expectancy_availability_safe", "src/signalforge/engines/strategy_selection/expectancy_availability_safe.py"),
    ("19_selection_pipeline_facade", "src/signalforge/engines/strategy_selection/selection_pipeline.py"),
    ("21_pruned_selection", "src/signalforge/engines/strategy_selection/pruned_selection.py"),

    # Stage 23 / 24 / 24A
    ("23_selected_trade_sequence", "src/signalforge/engines/portfolio_construction/selected_trade_sequence.py"),
    ("24_position_sizing", "src/signalforge/engines/portfolio_construction/position_sizing.py"),
    ("24A_value_ranked_allocator", "src/signalforge/engines/portfolio_construction/value_ranked_allocator.py"),
    ("24A_value_ranked_allocator_v2", "src/signalforge/engines/portfolio_construction/value_ranked_allocator_v2.py"),

    # v21 current steps 27-29
    ("27_resolved_execution_rules_v21", "src/signalforge/engines/strategy_selection/resolved_strategy_execution_rules_v21.py"),
    ("28_execution_qualified_candidates_v21", "src/signalforge/engines/strategy_selection/execution_qualified_historical_strategy_candidates_v21.py"),
    ("28_repaired_candidates_v13_v21", "src/signalforge/engines/strategy_selection/repaired_historical_strategy_candidates_v13_v21.py"),
    ("29_metric_driven_execution_overlay_v21", "src/signalforge/options_execution/metric_driven_execution_overlay_v21.py"),
    ("29_option_contract_execution_features_v21", "src/signalforge/options_execution/option_contract_execution_features_v21.py"),
    ("29_options_execution_resolved_rules_bridge", "src/signalforge/options_execution/resolved_strategy_execution_rules_v21.py"),
]


WRAPPER_CHECKS = [
    ("06_historical_decision_rows_shim", "src/signalforge/backtesting/historical_decision_rows.py", "signalforge.engines"),
    ("12_term_structure_tool_wrapper", "tools/augment_repaired_candidates_with_term_structure.py", "signalforge.engines.strategy_selection.term_structure_candidate_augmentation"),
    ("15_selector_candidate_input_tool_wrapper", "tools/build_v13_v21_selector_candidate_input.py", "signalforge.engines.strategy_selection.selector_candidate_input"),
    ("16_leg_selection_shim", "src/signalforge/backtesting/historical_strategy_leg_selection_rows_builder.py", "signalforge.engines.strategy_selection.leg_selection"),
    ("18_expectancy_shim", "src/signalforge/backtesting/walk_forward_expectancy_builder.py", "signalforge.engines.strategy_selection.expectancy"),
    ("18_expectancy_availability_safe_shim", "src/signalforge/backtesting/walk_forward_expectancy_availability_safe_builder.py", "signalforge.engines.strategy_selection.expectancy_availability_safe"),
    ("19_baseline_selection_core_backed", "src/signalforge/backtesting/historical_strategy_selection_rows_builder.py", "signalforge.engines.strategy_selection"),
    ("21_pruned_selection_shim", "src/signalforge/backtesting/historical_strategy_selection_cohort_risk_cli.py", "signalforge.engines.strategy_selection.pruned_selection"),
    ("23_selected_trade_sequence_shim", "src/signalforge/backtesting/portfolio_selected_trade_sequence.py", "signalforge.engines.portfolio_construction.selected_trade_sequence"),
    ("24_position_sizing_shim", "src/signalforge/backtesting/portfolio_position_sizing_replay.py", "signalforge.engines.portfolio_construction.position_sizing"),
    ("24A_value_ranked_allocator_v2_shim", "src/signalforge/backtesting/portfolio_value_ranked_allocator_v2.py", "signalforge.engines.portfolio_construction.value_ranked_allocator_v2"),
    ("24A_value_ranked_allocator_current_shim", "src/signalforge/backtesting/portfolio_value_ranked_allocator_v2_1_cli.py", "signalforge.engines.portfolio_construction.value_ranked_allocator"),
]


DEFERRED_BACKTESTING_ACCOUNTING = [
    ("25_equity_reconstruction", "src/signalforge/backtesting/portfolio_equity_reconstruction.py"),
]


CLOSURE_ARTIFACTS = [
    ("21_pruned_selection", "artifacts/stage40c6b_pruned_selection_core_promotion/signalforge_stage40c6b_pruned_selection_closure_summary.json"),
    ("23_selected_trade_sequence", "artifacts/stage40c7b_selected_trade_sequence_core_promotion/signalforge_stage40c7b_selected_trade_sequence_closure_summary.json"),
    ("24_position_sizing", "artifacts/stage40c8b_position_sizing_core_promotion/signalforge_stage40c8b_position_sizing_closure_summary.json"),
    ("24A_value_ranked_allocator", "artifacts/stage40c8d_value_ranked_allocator_core_promotion/signalforge_stage40c8d_value_ranked_allocator_closure_summary.json"),
    ("27_29_v21_rules", "artifacts/stage40c9d_v21_steps_27_29_rules_closure_audit/signalforge_stage40c9d_v21_steps_27_29_rules_closure_audit_summary.json"),
]


LEGACY_EXCLUDED = "src/signalforge/rulebooks/v3_2_2.py"


def path_obj(path_text: str) -> Path:
    return REPO / path_text


def compile_file(path: Path) -> tuple[bool, str | None]:
    try:
        py_compile.compile(str(path), doraise=True)
        return True, None
    except Exception as exc:
        return False, str(exc)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="ignore")


def function_count(path: Path) -> int:
    if not path.exists() or path.suffix.lower() != ".py":
        return 0

    try:
        tree = ast.parse(read(path), filename=str(path))
    except SyntaxError:
        return 0

    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    )


def assignment_count(path: Path) -> int:
    if not path.exists() or path.suffix.lower() != ".py":
        return 0

    try:
        tree = ast.parse(read(path), filename=str(path))
    except SyntaxError:
        return 0

    return sum(
        1
        for node in tree.body
        if isinstance(node, (ast.Assign, ast.AnnAssign))
    )


def inspect_core(label: str, path_text: str) -> dict[str, Any]:
    path = path_obj(path_text)
    exists = path.exists()
    c_ok, c_error = compile_file(path) if exists else (False, "missing")

    return {
        "label": label,
        "path": path_text,
        "exists": exists,
        "compile_ok": c_ok,
        "compile_error": c_error,
        "function_count": function_count(path),
        "assignment_count": assignment_count(path),
        "is_ready": exists and c_ok,
    }


def inspect_wrapper(label: str, path_text: str, expected_text: str) -> dict[str, Any]:
    path = path_obj(path_text)
    exists = path.exists()
    text = read(path) if exists else ""
    contains_expected_core = expected_text in text
    c_ok, c_error = compile_file(path) if exists and path.suffix.lower() == ".py" else (False, "missing")

    return {
        "label": label,
        "path": path_text,
        "expected_core_text": expected_text,
        "exists": exists,
        "compile_ok": c_ok,
        "compile_error": c_error,
        "contains_expected_core_text": contains_expected_core,
        "function_count": function_count(path),
        "is_ready": exists and c_ok and contains_expected_core,
    }


def inspect_deferred(label: str, path_text: str) -> dict[str, Any]:
    path = path_obj(path_text)
    exists = path.exists()
    c_ok, c_error = compile_file(path) if exists else (False, "missing")

    return {
        "label": label,
        "path": path_text,
        "exists": exists,
        "compile_ok": c_ok,
        "compile_error": c_error,
        "classification": "deferred_backtesting_accounting_not_core_decision_engine",
        "is_ready": exists and c_ok,
    }


def inspect_closure_artifact(label: str, path_text: str) -> dict[str, Any]:
    path = path_obj(path_text)
    exists = path.exists()

    payload = None
    is_ready = False
    closure_state = None
    production_blocker_count = None

    if exists:
        try:
            payload = json.loads(read(path))
            is_ready = payload.get("is_ready") is True
            closure_state = payload.get("closure_state")
            production_blocker_count = payload.get("production_blocker_count")
        except Exception:
            is_ready = False

    return {
        "label": label,
        "path": path_text,
        "exists": exists,
        "is_ready": is_ready,
        "closure_state": closure_state,
        "production_blocker_count": production_blocker_count,
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    core_reports = [inspect_core(label, path) for label, path in CORE_FILES]
    wrapper_reports = [inspect_wrapper(label, path, expected) for label, path, expected in WRAPPER_CHECKS]
    deferred_reports = [inspect_deferred(label, path) for label, path in DEFERRED_BACKTESTING_ACCOUNTING]
    closure_reports = [inspect_closure_artifact(label, path) for label, path in CLOSURE_ARTIFACTS]

    legacy_path = path_obj(LEGACY_EXCLUDED)

    production_blockers = []

    production_blockers.extend([
        {
            "category": "core_file_not_ready",
            "label": r["label"],
            "path": r["path"],
            "reason": r.get("compile_error"),
        }
        for r in core_reports
        if not r["is_ready"]
    ])

    production_blockers.extend([
        {
            "category": "wrapper_not_core_backed",
            "label": r["label"],
            "path": r["path"],
            "expected_core_text": r["expected_core_text"],
            "reason": r.get("compile_error") or "missing_expected_core_text",
        }
        for r in wrapper_reports
        if not r["is_ready"]
    ])

    production_blockers.extend([
        {
            "category": "deferred_accounting_file_not_ready",
            "label": r["label"],
            "path": r["path"],
            "reason": r.get("compile_error"),
        }
        for r in deferred_reports
        if not r["is_ready"]
    ])

    production_blockers.extend([
        {
            "category": "closure_artifact_not_ready",
            "label": r["label"],
            "path": r["path"],
            "reason": "missing_or_not_ready",
        }
        for r in closure_reports
        if not r["is_ready"]
    ])

    summary = {
        "adapter_type": "stage40c10_final_core_migration_closure_auditor",
        "artifact_type": "signalforge_stage40c10_final_core_migration_closure",
        "contract": "stage40c10_final_core_migration_closure",
        "is_ready": len(production_blockers) == 0,
        "closure_state": "closed_core_migration_ready_to_commit" if len(production_blockers) == 0 else "blocked_core_migration_review_required",
        "legacy_rulebook_excluded": LEGACY_EXCLUDED,
        "legacy_rulebook_exists": legacy_path.exists(),
        "legacy_rulebook_action": "excluded_no_promotion",
        "core_file_count": len(core_reports),
        "core_file_ready_count": sum(1 for r in core_reports if r["is_ready"]),
        "wrapper_file_count": len(wrapper_reports),
        "wrapper_file_ready_count": sum(1 for r in wrapper_reports if r["is_ready"]),
        "deferred_accounting_file_count": len(deferred_reports),
        "deferred_accounting_ready_count": sum(1 for r in deferred_reports if r["is_ready"]),
        "closure_artifact_count": len(closure_reports),
        "closure_artifact_ready_count": sum(1 for r in closure_reports if r["is_ready"]),
        "production_blocker_count": len(production_blockers),
        "production_blockers": production_blockers,
        "closed_stages": [
            "06_historical_decision_rows",
            "07_strategy_family_eligibility",
            "12_term_structure_candidate_augmentation",
            "15_selector_candidate_input",
            "16_leg_selection",
            "18_walk_forward_expectancy",
            "19_strategy_selection_baseline",
            "21_pruned_selection",
            "23_selected_trade_sequence",
            "24_position_sizing",
            "24A_value_ranked_allocator",
            "27_29_v21_execution_rules",
        ],
        "deferred_stages": [
            "17_quote_outcomes_historical_replay",
            "25_equity_reconstruction_backtesting_accounting",
        ],
        "paths": {
            "summary_path": "artifacts/stage40c10_final_core_migration_closure/signalforge_stage40c10_final_core_migration_closure_summary.json",
            "detail_path": "artifacts/stage40c10_final_core_migration_closure/signalforge_stage40c10_final_core_migration_closure_detail.json",
        },
    }

    detail = {
        **summary,
        "core_reports": core_reports,
        "wrapper_reports": wrapper_reports,
        "deferred_reports": deferred_reports,
        "closure_reports": closure_reports,
    }

    (OUT / "signalforge_stage40c10_final_core_migration_closure_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    (OUT / "signalforge_stage40c10_final_core_migration_closure_detail.json").write_text(
        json.dumps(detail, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["is_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
