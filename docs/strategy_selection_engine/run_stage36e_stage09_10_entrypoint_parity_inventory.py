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
    },
    {
        "stage": "stage10_resolved_execution_rules",
        "old_module": "signalforge.options_execution.resolved_strategy_execution_rules_v21",
        "engine_module": "signalforge.engines.strategy_selection.resolved_strategy_execution_rules_v21",
    },
    {
        "stage": "stage11_execution_qualified_candidates",
        "old_module": "signalforge.options_execution.execution_qualified_historical_strategy_candidates_v21",
        "engine_module": "signalforge.engines.strategy_selection.execution_qualified_historical_strategy_candidates_v21",
    },
    {
        "stage": "stage12_repaired_strategy_candidates",
        "old_module": "signalforge.options_execution.repaired_historical_strategy_candidates_v13_v21",
        "engine_module": "signalforge.engines.strategy_selection.repaired_historical_strategy_candidates_v13_v21",
    },
]


ENTRYPOINT_NAME_HINTS = (
    "build",
    "builder",
    "run",
    "resolve",
    "repair",
    "qualify",
    "write",
    "load",
    "main",
    "create",
)


def public_names(module: Any) -> List[str]:
    return sorted(name for name in dir(module) if not name.startswith("_"))


def classify_export(obj: Any) -> str:
    if inspect.isclass(obj):
        return "class"
    if inspect.isfunction(obj):
        return "function"
    if inspect.ismodule(obj):
        return "module"
    return type(obj).__name__


def safe_signature(obj: Any) -> str | None:
    try:
        if inspect.isfunction(obj) or inspect.isclass(obj):
            return str(inspect.signature(obj))
    except Exception:
        return None
    return None


def is_likely_entrypoint(name: str, kind: str) -> bool:
    lowered = name.lower()
    if kind not in {"function", "class"}:
        return False
    return any(hint in lowered for hint in ENTRYPOINT_NAME_HINTS)


def main() -> None:
    blockers: List[str] = []
    warnings: List[str] = []
    rows: List[Dict[str, Any]] = []

    for pair in PAIRS:
        stage = pair["stage"]
        old_module_name = pair["old_module"]
        engine_module_name = pair["engine_module"]

        try:
            old_module = importlib.import_module(old_module_name)
            engine_module = importlib.import_module(engine_module_name)
        except Exception as exc:
            blockers.append(f"import_failed_{stage}: {exc}")
            continue

        old_names = set(public_names(old_module))
        engine_names = set(public_names(engine_module))

        missing_from_old_wrapper = sorted(engine_names - old_names)
        extra_in_old_wrapper = sorted(old_names - engine_names)

        if missing_from_old_wrapper:
            blockers.append(f"{stage}_wrapper_missing_engine_exports")

        for name in sorted(engine_names):
            old_obj = getattr(old_module, name, None)
            engine_obj = getattr(engine_module, name, None)

            kind = classify_export(engine_obj)
            same_object = old_obj is engine_obj

            # Constants may not always be same object after import *, but functions/classes should be.
            if kind in {"function", "class"} and not same_object:
                blockers.append(f"{stage}_{name}_function_or_class_not_same_object")

            rows.append({
                "stage": stage,
                "name": name,
                "kind": kind,
                "same_object": same_object,
                "signature": safe_signature(engine_obj),
                "likely_entrypoint": is_likely_entrypoint(name, kind),
                "old_module": old_module_name,
                "engine_module": engine_module_name,
                "old_file": getattr(old_module, "__file__", None),
                "engine_file": getattr(engine_module, "__file__", None),
            })

        rows.append({
            "stage": stage,
            "name": "__module_export_comparison__",
            "kind": "comparison",
            "same_object": True,
            "signature": None,
            "likely_entrypoint": False,
            "old_module": old_module_name,
            "engine_module": engine_module_name,
            "missing_from_old_wrapper": missing_from_old_wrapper,
            "extra_in_old_wrapper": extra_in_old_wrapper,
            "old_file": getattr(old_module, "__file__", None),
            "engine_file": getattr(engine_module, "__file__", None),
        })

    likely_entrypoint_rows = [
        row for row in rows
        if row.get("likely_entrypoint") is True
    ]

    warnings.append("stage36e_is_entrypoint_and_wrapper_identity_inventory_not_data_replay")
    warnings.append("next_stage_should_use_likely_entrypoints_for_small_fixture_output_parity")

    summary = {
        "adapter_type": "stage09_10_entrypoint_parity_inventory_builder",
        "artifact_type": "signalforge_stage09_10_entrypoint_parity_inventory",
        "contract": "stage09_10_entrypoint_parity_inventory",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,
        "module_pair_count": len(PAIRS),
        "export_row_count": len(rows),
        "likely_entrypoint_count": len(likely_entrypoint_rows),
        "paper_order_created": False,
        "live_order_created": False,
        "live_trade_supported": False,
        "next_step": "stage36f_small_fixture_stage09_10_output_parity",
    }

    summary_path = OUT_DIR / "signalforge_stage36e_stage09_10_entrypoint_parity_inventory_summary.json"
    rows_path = OUT_DIR / "signalforge_stage36e_stage09_10_entrypoint_parity_inventory_rows.jsonl"
    md_path = OUT_DIR / "signalforge_stage36e_stage09_10_entrypoint_parity_inventory.md"

    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    with rows_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")

    md = [
        "# Stage 36E Stage 09/10 Entrypoint + Wrapper Parity Inventory",
        "",
        f"- is_ready: {summary['is_ready']}",
        f"- blocker_count: {summary['blocker_count']}",
        f"- module_pair_count: {summary['module_pair_count']}",
        f"- export_row_count: {summary['export_row_count']}",
        f"- likely_entrypoint_count: {summary['likely_entrypoint_count']}",
        f"- paper_order_created: {summary['paper_order_created']}",
        f"- live_order_created: {summary['live_order_created']}",
        f"- live_trade_supported: {summary['live_trade_supported']}",
        "",
        "## Likely Entrypoints",
        "",
        "| stage | name | kind | signature | same object through wrapper |",
        "|---|---|---|---|---:|",
    ]

    for row in likely_entrypoint_rows:
        md.append(
            f"| {row['stage']} | `{row['name']}` | {row['kind']} | "
            f"`{row.get('signature') or ''}` | {row['same_object']} |"
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

    print("\n--- Stage 36E Stage 09/10 entrypoint parity inventory compact ---")
    for key in [
        "is_ready",
        "blocker_count",
        "warning_count",
        "module_pair_count",
        "export_row_count",
        "likely_entrypoint_count",
        "paper_order_created",
        "live_order_created",
        "live_trade_supported",
    ]:
        print(f"{key}: {summary[key]}")

    print(f"summary_path: {summary_path}")
    print(f"rows_path: {rows_path}")
    print(f"md_path: {md_path}")

    print("\n--- Stage 36E likely entrypoints compact ---")
    print("stage\tkind\tname\tsignature\tsame_object")
    for row in likely_entrypoint_rows:
        print(
            f"{row['stage']}\t{row['kind']}\t{row['name']}\t"
            f"{row.get('signature') or ''}\t{row['same_object']}"
        )

    if blockers:
        print("\n--- Stage 36E blockers ---")
        for blocker in blockers:
            print(blocker)
        raise SystemExit(1)

    if warnings:
        print("\n--- Stage 36E warnings ---")
        for warning in warnings:
            print(warning)


if __name__ == "__main__":
    main()
