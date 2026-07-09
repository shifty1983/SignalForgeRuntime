import importlib
import inspect
import json
from pathlib import Path
from typing import Any, Dict, List


OUT_DIR = Path("docs/strategy_selection_engine")

PAIRS = [
    {
        "stage": "stage09_structure_availability",
        "old_module": "signalforge.options_execution.strategy_structure_availability_v21",
        "engine_module": "signalforge.engines.strategy_selection.strategy_structure_availability_v21",
        "entrypoints": [
            "build_strategy_structure_availability",
            "create_sqlite",
            "main",
        ],
    },
    {
        "stage": "stage10_resolved_execution_rules",
        "old_module": "signalforge.options_execution.resolved_strategy_execution_rules_v21",
        "engine_module": "signalforge.engines.strategy_selection.resolved_strategy_execution_rules_v21",
        "entrypoints": [
            "build_resolved_rules",
            "resolve_row",
            "main",
        ],
    },
    {
        "stage": "stage11_execution_qualified_candidates",
        "old_module": "signalforge.options_execution.execution_qualified_historical_strategy_candidates_v21",
        "engine_module": "signalforge.engines.strategy_selection.execution_qualified_historical_strategy_candidates_v21",
        "entrypoints": [
            "build_execution_qualified_candidates",
            "main",
        ],
    },
    {
        "stage": "stage12_repaired_strategy_candidates",
        "old_module": "signalforge.options_execution.repaired_historical_strategy_candidates_v13_v21",
        "engine_module": "signalforge.engines.strategy_selection.repaired_historical_strategy_candidates_v13_v21",
        "entrypoints": [
            "build_repaired_candidates",
            "load_rules",
            "main",
        ],
    },
]


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def smoke_resolve_row(old_func: Any, engine_func: Any) -> Dict[str, Any]:
    fixtures = [
        (
            {
                "symbol": "SPY",
                "as_of_date": "2024-01-02",
                "strategy_name": "long_call",
                "strategy_available": True,
                "is_available": True,
                "availability_state": "available",
            },
            {
                "symbol": "SPY",
                "as_of_date": "2024-01-02",
                "strategy_name": "long_call",
                "execution_state": "allowed",
                "final_execution_state": "allowed",
            },
        ),
        (
            {
                "symbol": "QQQ",
                "as_of_date": "2024-01-02",
                "strategy_name": "put_credit_spread",
                "strategy_available": False,
                "is_available": False,
                "availability_state": "unavailable",
            },
            None,
        ),
    ]

    rows = []
    blockers = []
    warnings = []

    for index, args in enumerate(fixtures, start=1):
        try:
            old_result = old_func(*args)
            old_error = None
        except Exception as exc:
            old_result = None
            old_error = f"{type(exc).__name__}: {exc}"

        try:
            engine_result = engine_func(*args)
            engine_error = None
        except Exception as exc:
            engine_result = None
            engine_error = f"{type(exc).__name__}: {exc}"

        same_output = canonical_json(old_result) == canonical_json(engine_result)
        same_error = old_error == engine_error

        row = {
            "fixture_index": index,
            "same_output": same_output,
            "same_error": same_error,
            "old_error": old_error,
            "engine_error": engine_error,
            "old_result": old_result,
            "engine_result": engine_result,
        }

        rows.append(row)

        if old_error or engine_error:
            if same_error:
                warnings.append(f"resolve_row_fixture_{index}_same_exception_not_blocking_wrapper_parity")
            else:
                blockers.append(f"resolve_row_fixture_{index}_different_exception")
        elif not same_output:
            blockers.append(f"resolve_row_fixture_{index}_different_output")

    return {
        "rows": rows,
        "blockers": blockers,
        "warnings": warnings,
        "executed_fixture_count": len(rows),
        "parity_pass": len(blockers) == 0,
    }


def main() -> None:
    blockers: List[str] = []
    warnings: List[str] = []
    rows: List[Dict[str, Any]] = []
    callable_smoke = {}

    for pair in PAIRS:
        old_module = importlib.import_module(pair["old_module"])
        engine_module = importlib.import_module(pair["engine_module"])

        old_public = {name for name in dir(old_module) if not name.startswith("_")}
        engine_public = {name for name in dir(engine_module) if not name.startswith("_")}

        missing_from_wrapper = sorted(engine_public - old_public)
        extra_in_wrapper = sorted(old_public - engine_public)

        if missing_from_wrapper:
            blockers.append(f"{pair['stage']}_missing_wrapper_exports")

        for entrypoint in pair["entrypoints"]:
            old_obj = getattr(old_module, entrypoint, None)
            engine_obj = getattr(engine_module, entrypoint, None)

            same_object = old_obj is engine_obj
            signature = None

            try:
                signature = str(inspect.signature(engine_obj))
            except Exception:
                pass

            row = {
                "stage": pair["stage"],
                "entrypoint": entrypoint,
                "old_module": pair["old_module"],
                "engine_module": pair["engine_module"],
                "exists_in_wrapper": old_obj is not None,
                "exists_in_engine": engine_obj is not None,
                "same_object": same_object,
                "signature": signature,
                "old_file": getattr(old_module, "__file__", None),
                "engine_file": getattr(engine_module, "__file__", None),
                "missing_from_wrapper_count": len(missing_from_wrapper),
                "extra_in_wrapper_count": len(extra_in_wrapper),
            }

            rows.append(row)

            if old_obj is None:
                blockers.append(f"{pair['stage']}_{entrypoint}_missing_in_wrapper")

            if engine_obj is None:
                blockers.append(f"{pair['stage']}_{entrypoint}_missing_in_engine")

            if old_obj is not None and engine_obj is not None and not same_object:
                blockers.append(f"{pair['stage']}_{entrypoint}_not_same_object")

            if pair["stage"] == "stage10_resolved_execution_rules" and entrypoint == "resolve_row":
                smoke = smoke_resolve_row(old_obj, engine_obj)
                callable_smoke["resolve_row"] = smoke
                blockers.extend(smoke["blockers"])
                warnings.extend(smoke["warnings"])

    warnings.append("stage36f_does_not_run_full_historical_replay")
    warnings.append("same_object_wrapper_identity_guarantees_same_entrypoint_execution_path")

    same_object_count = sum(1 for row in rows if row["same_object"])
    expected_same_object_count = len(rows)

    if same_object_count != expected_same_object_count:
        blockers.append("not_all_entrypoints_same_object")

    summary = {
        "adapter_type": "wrapper_engine_parity_closure_builder",
        "artifact_type": "signalforge_wrapper_engine_parity_closure",
        "contract": "wrapper_engine_parity_closure",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,
        "module_pair_count": len(PAIRS),
        "entrypoint_count": len(rows),
        "same_object_count": same_object_count,
        "expected_same_object_count": expected_same_object_count,
        "callable_smoke": callable_smoke,
        "source_of_truth": "signalforge.engines.strategy_selection",
        "compatibility_namespace": "signalforge.options_execution",
        "paper_order_created": False,
        "live_order_created": False,
        "live_trade_supported": False,
        "parity_state": "wrapper_and_engine_entrypoints_identical" if len(blockers) == 0 else "parity_not_closed",
        "next_step": "stage36g_backtesting_import_cleanup_or_engine_replay_parity",
    }

    summary_path = OUT_DIR / "signalforge_stage36f_wrapper_engine_parity_closure_summary.json"
    rows_path = OUT_DIR / "signalforge_stage36f_wrapper_engine_parity_closure_rows.jsonl"
    md_path = OUT_DIR / "signalforge_stage36f_wrapper_engine_parity_closure.md"

    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    with rows_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")

    md = [
        "# Stage 36F Wrapper/Engine Parity Closure",
        "",
        f"- is_ready: {summary['is_ready']}",
        f"- blocker_count: {summary['blocker_count']}",
        f"- parity_state: {summary['parity_state']}",
        f"- module_pair_count: {summary['module_pair_count']}",
        f"- entrypoint_count: {summary['entrypoint_count']}",
        f"- same_object_count: {summary['same_object_count']}",
        f"- expected_same_object_count: {summary['expected_same_object_count']}",
        f"- paper_order_created: {summary['paper_order_created']}",
        f"- live_order_created: {summary['live_order_created']}",
        f"- live_trade_supported: {summary['live_trade_supported']}",
        "",
        "## Entrypoints",
        "",
        "| stage | entrypoint | same object | signature |",
        "|---|---|---:|---|",
    ]

    for row in rows:
        md.append(
            f"| {row['stage']} | `{row['entrypoint']}` | {row['same_object']} | `{row['signature'] or ''}` |"
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

    print("\n--- Stage 36F wrapper/engine parity closure compact ---")
    for key in [
        "is_ready",
        "blocker_count",
        "warning_count",
        "parity_state",
        "module_pair_count",
        "entrypoint_count",
        "same_object_count",
        "expected_same_object_count",
        "paper_order_created",
        "live_order_created",
        "live_trade_supported",
    ]:
        print(f"{key}: {summary[key]}")

    print(f"summary_path: {summary_path}")
    print(f"rows_path: {rows_path}")
    print(f"md_path: {md_path}")

    print("\n--- Stage 36F entrypoint rows compact ---")
    print("stage\tentrypoint\tsame_object\tsignature")
    for row in rows:
        print(f"{row['stage']}\t{row['entrypoint']}\t{row['same_object']}\t{row['signature'] or ''}")

    if callable_smoke:
        print("\n--- Stage 36F callable smoke compact ---")
        for name, smoke in callable_smoke.items():
            print(f"{name}_parity_pass: {smoke['parity_pass']}")
            print(f"{name}_executed_fixture_count: {smoke['executed_fixture_count']}")

    if blockers:
        print("\n--- Stage 36F blockers ---")
        for blocker in blockers:
            print(blocker)
        raise SystemExit(1)

    if warnings:
        print("\n--- Stage 36F warnings ---")
        for warning in warnings:
            print(warning)


if __name__ == "__main__":
    main()
