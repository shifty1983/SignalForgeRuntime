import ast
import importlib
import json
from pathlib import Path
from typing import Any, Dict, List


SRC_ROOT = Path("src")
OUT_DIR = Path("docs/strategy_selection_engine")

ENGINE_MODULES = [
    "signalforge.engines.strategy_selection.strategy_family_eligibility",
    "signalforge.engines.strategy_selection.strategy_structure_availability_v21",
    "signalforge.engines.strategy_selection.resolved_strategy_execution_rules_v21",
    "signalforge.engines.strategy_selection.execution_qualified_historical_strategy_candidates_v21",
    "signalforge.engines.strategy_selection.repaired_historical_strategy_candidates_v13_v21",
    "signalforge.engines.strategy_selection.candidates",
    "signalforge.engines.strategy_selection.contract_candidate_scoring",
    "signalforge.engines.strategy_selection.expected_value_scoring",
    "signalforge.engines.strategy_selection.filters",
    "signalforge.engines.strategy_selection.ranking",
    "signalforge.engines.strategy_selection.selector",
    "signalforge.engines.strategy_selection.portfolio_candidate_input",
    "signalforge.engines.strategy_selection.allocation",
    "signalforge.engines.strategy_selection.selection_report",
]

OLD_OWNER_MODULES = [
    "signalforge.options_execution.strategy_structure_availability_v21",
    "signalforge.options_execution.resolved_strategy_execution_rules_v21",
    "signalforge.options_execution.execution_qualified_historical_strategy_candidates_v21",
    "signalforge.options_execution.repaired_historical_strategy_candidates_v13_v21",
    "signalforge.backtesting.historical_strategy_candidate_rows_builder",
    "signalforge.backtesting.historical_strategy_selection_rows_builder",
    "signalforge.backtesting.historical_strategy_leg_selection_rows_builder",
    "signalforge.backtesting.walk_forward_expectancy_builder",
    "signalforge.backtesting.walk_forward_expectancy_availability_safe_builder",
]

KEY_TERMS = [
    "strategy_structure_availability",
    "resolved_strategy_execution_rules",
    "execution_qualified_historical_strategy_candidates",
    "repaired_historical_strategy_candidates",
    "historical_strategy_candidate_rows",
    "historical_strategy_selection_rows",
    "walk_forward_expectancy",
    "strategy_selection",
    "selector",
    "ranking",
    "portfolio_candidate_input",
    "expected_value_scoring",
]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def rel(path: Path) -> str:
    return str(path).replace("\\", "/")


def parse_imports(path: Path) -> List[str]:
    imports = []
    try:
        tree = ast.parse(read_text(path))
    except SyntaxError:
        return imports

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")

    return imports


def classify_path(path_text: str) -> str:
    if "/engines/strategy_selection/" in path_text:
        return "engine_strategy_selection"
    if "/options_execution/" in path_text:
        return "legacy_options_execution_owner_or_wrapper_candidate"
    if "/backtesting/" in path_text:
        return "backtesting_consumer_or_legacy_owner"
    if "/paper_live_engine/" in path_text:
        return "paper_live_engine_consumer"
    if "/bootstrap/" in path_text:
        return "bootstrap_consumer"
    return "other_consumer"


def recommended_action(bucket: str, old_hits: List[str], engine_hits: List[str], term_hits: List[str]) -> str:
    if bucket == "engine_strategy_selection":
        return "keep_engine_source"
    if old_hits and bucket == "legacy_options_execution_owner_or_wrapper_candidate":
        return "convert_to_thin_compatibility_wrapper_after_backtest_parity"
    if old_hits and bucket == "backtesting_consumer_or_legacy_owner":
        return "replace_logic_or_imports_with_engine_module_after_boundary_review"
    if engine_hits:
        return "already_points_to_engine_review_only"
    if term_hits and bucket == "backtesting_consumer_or_legacy_owner":
        return "inspect_for_embedded_strategy_selection_logic"
    if term_hits:
        return "review_reference"
    return "none"


def main() -> None:
    blockers: List[str] = []
    warnings: List[str] = []
    rows: List[Dict[str, Any]] = []

    for module in ENGINE_MODULES:
        try:
            importlib.import_module(module)
        except Exception as exc:
            blockers.append(f"engine_module_import_failed_{module}: {exc}")

    py_files = sorted(SRC_ROOT.rglob("*.py"))

    for path in py_files:
        if "__pycache__" in path.parts:
            continue

        text = read_text(path)
        path_text = rel(path)
        imports = parse_imports(path)

        old_import_hits = [
            module for module in OLD_OWNER_MODULES
            if module in imports or f"from {module}" in text or f"import {module}" in text
        ]

        old_text_hits = [
            module for module in OLD_OWNER_MODULES
            if module in text
        ]

        engine_import_hits = [
            module for module in ENGINE_MODULES
            if module in imports or f"from {module}" in text or f"import {module}" in text
        ]

        engine_text_hits = [
            module for module in ENGINE_MODULES
            if module in text
        ]

        term_hits = [
            term for term in KEY_TERMS
            if term in text or term in path.name
        ]

        if not old_import_hits and not old_text_hits and not engine_import_hits and not engine_text_hits and not term_hits:
            continue

        bucket = classify_path(path_text)

        rows.append({
            "path": path_text,
            "bucket": bucket,
            "old_import_hits": old_import_hits,
            "old_text_hits": old_text_hits,
            "engine_import_hits": engine_import_hits,
            "engine_text_hits": engine_text_hits,
            "term_hits": sorted(set(term_hits)),
            "recommended_action": recommended_action(
                bucket=bucket,
                old_hits=old_import_hits or old_text_hits,
                engine_hits=engine_import_hits or engine_text_hits,
                term_hits=term_hits,
            ),
        })

    rows = sorted(rows, key=lambda r: (r["bucket"], r["path"]))

    bucket_counts: Dict[str, int] = {}
    action_counts: Dict[str, int] = {}
    for row in rows:
        bucket_counts[row["bucket"]] = bucket_counts.get(row["bucket"], 0) + 1
        action_counts[row["recommended_action"]] = action_counts.get(row["recommended_action"], 0) + 1

    old_owner_rows = [
        row for row in rows
        if row["old_import_hits"] or row["old_text_hits"]
    ]

    backtesting_boundary_rows = [
        row for row in rows
        if row["bucket"] == "backtesting_consumer_or_legacy_owner"
    ]

    if old_owner_rows:
        warnings.append("old_owner_references_detected_expected_before_wrapper_migration")

    warnings.append("stage36b_is_read_only_no_imports_modified")
    warnings.append("next_stage_should_create_wrappers_or_update_backtesting_imports_one_group_at_a_time")

    summary = {
        "adapter_type": "backtesting_to_engine_import_boundary_map_builder",
        "artifact_type": "signalforge_backtesting_to_engine_import_boundary_map",
        "contract": "backtesting_to_engine_import_boundary_map",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,
        "engine_module_count": len(ENGINE_MODULES),
        "matched_file_count": len(rows),
        "old_owner_reference_file_count": len(old_owner_rows),
        "backtesting_boundary_file_count": len(backtesting_boundary_rows),
        "bucket_counts": dict(sorted(bucket_counts.items())),
        "action_counts": dict(sorted(action_counts.items())),
        "live_trade_supported": False,
        "paper_order_created": False,
        "live_order_created": False,
        "next_step": "stage36c_create_options_execution_compatibility_wrappers_or_update_backtesting_imports",
    }

    summary_path = OUT_DIR / "signalforge_stage36b_backtesting_to_engine_import_boundary_map_summary.json"
    rows_path = OUT_DIR / "signalforge_stage36b_backtesting_to_engine_import_boundary_map_rows.jsonl"
    md_path = OUT_DIR / "signalforge_stage36b_backtesting_to_engine_import_boundary_map.md"

    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    with rows_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")

    md = [
        "# Stage 36B Backtesting-to-Engine Import Boundary Map",
        "",
        f"- is_ready: {summary['is_ready']}",
        f"- blocker_count: {summary['blocker_count']}",
        f"- matched_file_count: {summary['matched_file_count']}",
        f"- old_owner_reference_file_count: {summary['old_owner_reference_file_count']}",
        f"- backtesting_boundary_file_count: {summary['backtesting_boundary_file_count']}",
        f"- live_trade_supported: {summary['live_trade_supported']}",
        f"- paper_order_created: {summary['paper_order_created']}",
        f"- live_order_created: {summary['live_order_created']}",
        "",
        "## Bucket Counts",
        "",
    ]

    for bucket, count in summary["bucket_counts"].items():
        md.append(f"- {bucket}: {count}")

    md.extend(["", "## Action Counts", ""])
    for action, count in summary["action_counts"].items():
        md.append(f"- {action}: {count}")

    md.extend([
        "",
        "## Boundary Rows",
        "",
        "| bucket | action | path | old refs | engine refs | terms |",
        "|---|---|---|---|---|---|",
    ])

    for row in rows[:160]:
        old_refs = ", ".join(sorted(set(row["old_import_hits"] + row["old_text_hits"])))
        engine_refs = ", ".join(sorted(set(row["engine_import_hits"] + row["engine_text_hits"])))
        terms = ", ".join(row["term_hits"])
        md.append(
            f"| {row['bucket']} | {row['recommended_action']} | `{row['path']}` | "
            f"{old_refs} | {engine_refs} | {terms} |"
        )

    if blockers:
        md.extend(["", "## Blockers", ""])
        for blocker in blockers:
            md.append(f"- {blocker}")

    if warnings:
        md.extend(["", "## Warnings", ""])
        for warning in warnings:
            md.append(f"- {warning}")

    md_path.write_text("\n".join(md), encoding="utf-8")

    print("\n--- Stage 36B backtesting-to-engine import boundary map compact ---")
    for key in [
        "is_ready",
        "blocker_count",
        "warning_count",
        "engine_module_count",
        "matched_file_count",
        "old_owner_reference_file_count",
        "backtesting_boundary_file_count",
        "live_trade_supported",
        "paper_order_created",
        "live_order_created",
    ]:
        print(f"{key}: {summary[key]}")

    print(f"summary_path: {summary_path}")
    print(f"rows_path: {rows_path}")
    print(f"md_path: {md_path}")

    print("\n--- Stage 36B bucket counts ---")
    for bucket, count in summary["bucket_counts"].items():
        print(f"{bucket}: {count}")

    print("\n--- Stage 36B action counts ---")
    for action, count in summary["action_counts"].items():
        print(f"{action}: {count}")

    print("\n--- Stage 36B high-priority boundary rows ---")
    print("bucket\taction\tpath")
    for row in rows:
        if row["recommended_action"] in {
            "convert_to_thin_compatibility_wrapper_after_backtest_parity",
            "replace_logic_or_imports_with_engine_module_after_boundary_review",
            "inspect_for_embedded_strategy_selection_logic",
        }:
            print(f"{row['bucket']}\t{row['recommended_action']}\t{row['path']}")

    if blockers:
        print("\n--- Stage 36B blockers ---")
        for blocker in blockers:
            print(blocker)
        raise SystemExit(1)

    if warnings:
        print("\n--- Stage 36B warnings ---")
        for warning in warnings:
            print(warning)


if __name__ == "__main__":
    main()
