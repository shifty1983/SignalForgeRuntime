import importlib
import json
from pathlib import Path
from typing import Any, Dict, List


OUT_DIR = Path("docs/expected_value_engine")

HANDOFF_CONTRACT_PATH = Path(
    "configs/paper_live_engine/signalforge_v21_paper_live_engine_handoff_contract.json"
)

REQUIRED_MODULE_IMPORTS = [
    "signalforge.engines.strategy_selection.canonical_expectancy_snapshot_adapter",
    "signalforge.engines.strategy_selection.expected_value_scoring",
]

OPTIONAL_MODULE_CANDIDATES = {
    "candidate_ingestion_adapter": [
        "paper_live_engine.candidate_ingestion_adapter",
        "signalforge.paper_live_engine.candidate_ingestion_adapter",
    ],
    "legacy_domain_facade": [
        "paper_live_engine.legacy_domain_facade",
        "signalforge.paper_live_engine.legacy_domain_facade",
    ],
    "legacy_domain_snapshot_adapter": [
        "paper_live_engine.legacy_domain_snapshot_adapter",
        "signalforge.paper_live_engine.legacy_domain_snapshot_adapter",
    ],
}

ORDER_FIELD_NAMES = [
    "order_intent",
    "broker_order_id",
    "automatic_action",
    "automatic_strategy_change",
    "automatic_parameter_change",
    "automatic_pause_action",
    "paper_order_created",
    "live_order_created",
    "live_trade_supported",
]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []

    with path.open("r", encoding="utf-8-sig") as f:
        for line in f:
            text = line.strip()
            if not text:
                continue

            value = json.loads(text)
            if isinstance(value, dict):
                rows.append(value)

    return rows


def import_smoke(module_name: str, required: bool) -> dict[str, Any]:
    try:
        module = importlib.import_module(module_name)
        return {
            "module": module_name,
            "required": required,
            "ok": True,
            "error_type": None,
            "error": None,
            "module_file": getattr(module, "__file__", None),
        }
    except Exception as exc:
        return {
            "module": module_name,
            "required": required,
            "ok": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "module_file": None,
        }


def optional_import_discovery() -> list[dict[str, Any]]:
    rows = []

    for role, candidates in OPTIONAL_MODULE_CANDIDATES.items():
        role_rows = []

        for module_name in candidates:
            row = import_smoke(module_name, required=False)
            row["role"] = role
            role_rows.append(row)

        any_ok = any(row["ok"] for row in role_rows)

        for row in role_rows:
            row["role_resolved"] = any_ok
            rows.append(row)

    return rows


def nested_order_fields(value: Any, prefix: str = "") -> list[dict[str, Any]]:
    rows = []

    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)

            if key in ORDER_FIELD_NAMES:
                rows.append({
                    "field": path,
                    "value": item,
                })

            rows.extend(nested_order_fields(item, path))

    elif isinstance(value, list):
        for index, item in enumerate(value):
            rows.extend(nested_order_fields(item, f"{prefix}[{index}]"))

    return rows


def main() -> None:
    blockers: List[str] = []
    warnings: List[str] = []

    if not HANDOFF_CONTRACT_PATH.exists():
        blockers.append(f"missing_handoff_contract_path_{HANDOFF_CONTRACT_PATH}")

    handoff_contract = read_json(HANDOFF_CONTRACT_PATH) if HANDOFF_CONTRACT_PATH.exists() else {}
    patch = handoff_contract.get("expectancy_snapshot_adapter") if isinstance(handoff_contract, dict) else None

    if not isinstance(patch, dict):
        blockers.append("handoff_contract_missing_expectancy_snapshot_adapter_patch")

    required_import_rows = [import_smoke(module_name, required=True) for module_name in REQUIRED_MODULE_IMPORTS]
    optional_import_rows = optional_import_discovery()
    import_rows = required_import_rows + optional_import_rows

    failed_required_imports = [row for row in required_import_rows if row["ok"] is not True]
    if failed_required_imports:
        blockers.append(f"required_module_import_failures_{[row['module'] for row in failed_required_imports]}")

    adapter_artifact = None
    ev_artifact = None
    runtime_rows: List[Dict[str, Any]] = []

    if isinstance(patch, dict) and not failed_required_imports:
        source_rows_path = Path(patch.get("source_rows_path", ""))
        source_summary_path = Path(patch.get("source_summary_path", ""))

        if not source_rows_path.exists():
            blockers.append(f"missing_patch_source_rows_path_{source_rows_path}")

        if not source_summary_path.exists():
            blockers.append(f"missing_patch_source_summary_path_{source_summary_path}")

        if source_rows_path.exists() and source_summary_path.exists():
            rows = read_jsonl(source_rows_path)
            source_summary = read_json(source_summary_path)

            adapter_module = importlib.import_module(patch["adapter_module"])
            adapter_func = getattr(adapter_module, patch["adapter_entrypoint"])

            consumer_module = importlib.import_module(patch["consumer_module"])
            consumer_func = getattr(consumer_module, patch["consumer_entrypoint"])

            adapter_artifact = adapter_func(
                rows,
                source_rows_path=str(source_rows_path),
                source_summary_path=str(source_summary_path),
            )

            ev_artifact = consumer_func(adapter_artifact)

            runtime_rows.extend([
                {
                    "check": "source_summary_ready",
                    "expected": True,
                    "actual": source_summary.get("is_ready") if isinstance(source_summary, dict) else None,
                    "passed": isinstance(source_summary, dict) and source_summary.get("is_ready") is True,
                },
                {
                    "check": "adapter_artifact_ready",
                    "expected": True,
                    "actual": adapter_artifact.get("is_ready") if isinstance(adapter_artifact, dict) else None,
                    "passed": isinstance(adapter_artifact, dict) and adapter_artifact.get("is_ready") is True,
                },
                {
                    "check": "adapter_item_count_matches_patch",
                    "expected": patch.get("adapter_output_item_count"),
                    "actual": adapter_artifact.get("output_item_count") if isinstance(adapter_artifact, dict) else None,
                    "passed": (
                        isinstance(adapter_artifact, dict)
                        and adapter_artifact.get("output_item_count") == patch.get("adapter_output_item_count")
                    ),
                },
                {
                    "check": "ev_scoring_contract",
                    "expected": patch.get("consumer_contract"),
                    "actual": ev_artifact.get("contract") if isinstance(ev_artifact, dict) else None,
                    "passed": (
                        isinstance(ev_artifact, dict)
                        and ev_artifact.get("contract") == patch.get("consumer_contract")
                    ),
                },
                {
                    "check": "ev_scoring_status",
                    "expected": "needs_review",
                    "actual": ev_artifact.get("status") if isinstance(ev_artifact, dict) else None,
                    "passed": isinstance(ev_artifact, dict) and ev_artifact.get("status") == "needs_review",
                },
                {
                    "check": "ev_scoring_requires_manual_approval",
                    "expected": True,
                    "actual": ev_artifact.get("requires_manual_approval") if isinstance(ev_artifact, dict) else None,
                    "passed": isinstance(ev_artifact, dict) and ev_artifact.get("requires_manual_approval") is True,
                },
                {
                    "check": "ev_scoring_no_order_intent",
                    "expected": None,
                    "actual": ev_artifact.get("order_intent") if isinstance(ev_artifact, dict) else None,
                    "passed": isinstance(ev_artifact, dict) and ev_artifact.get("order_intent") is None,
                },
            ])

    order_field_rows = []

    if isinstance(handoff_contract, dict):
        order_field_rows.extend([
            {"source": "handoff_contract", **row}
            for row in nested_order_fields(handoff_contract)
        ])

    if isinstance(adapter_artifact, dict):
        order_field_rows.extend([
            {"source": "adapter_artifact", **row}
            for row in nested_order_fields(adapter_artifact)
        ])

    if isinstance(ev_artifact, dict):
        order_field_rows.extend([
            {"source": "expected_value_scoring_artifact", **row}
            for row in nested_order_fields(ev_artifact)
        ])

    unsafe_order_rows = [
        row for row in order_field_rows
        if (
            (row["field"].endswith("order_intent") and row["value"] is not None)
            or (row["field"].endswith("broker_order_id") and row["value"] is not None)
            or (row["field"].endswith("paper_order_created") and row["value"] is True)
            or (row["field"].endswith("live_order_created") and row["value"] is True)
            or (row["field"].endswith("live_trade_supported") and row["value"] is True)
            or (row["field"].endswith("automatic_action") and row["value"] is not None)
            or (row["field"].endswith("automatic_strategy_change") and row["value"] is not None)
            or (row["field"].endswith("automatic_parameter_change") and row["value"] is not None)
            or (row["field"].endswith("automatic_pause_action") and row["value"] is not None)
        )
    ]

    failed_runtime_checks = [row for row in runtime_rows if row["passed"] is not True]

    if failed_runtime_checks:
        blockers.append(f"runtime_readiness_failures_{[row['check'] for row in failed_runtime_checks]}")

    if unsafe_order_rows:
        blockers.append(f"unsafe_order_fields_present_{len(unsafe_order_rows)}")

    unresolved_optional_roles = sorted({
        row["role"]
        for row in optional_import_rows
        if row.get("role_resolved") is not True
    })

    if unresolved_optional_roles:
        warnings.append(f"optional_paper_live_bridge_modules_not_resolved_{unresolved_optional_roles}")

    warnings.append("stage37o2_is_import_and_runtime_smoke_only")
    warnings.append("paper_handoff_expectancy_adapter_is_attached_but_not_trade_authorizing")
    warnings.append("expected_value_scoring_intentionally_remains_needs_review")
    warnings.append("data_canonical_runtime_files_should_not_be_force_added_to_git")

    summary = {
        "adapter_type": "paper_handoff_contract_import_smoke_builder",
        "artifact_type": "signalforge_paper_handoff_contract_import_smoke",
        "contract": "paper_handoff_contract_import_smoke",
        "stage": "37O2",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,
        "handoff_contract_path": str(HANDOFF_CONTRACT_PATH),
        "expectancy_snapshot_adapter_patch_present": isinstance(patch, dict),
        "required_module_import_count": len(required_import_rows),
        "required_module_import_ok_count": sum(1 for row in required_import_rows if row["ok"]),
        "optional_module_import_count": len(optional_import_rows),
        "optional_module_import_ok_count": sum(1 for row in optional_import_rows if row["ok"]),
        "runtime_check_count": len(runtime_rows),
        "runtime_check_pass_count": sum(1 for row in runtime_rows if row["passed"]),
        "order_field_count": len(order_field_rows),
        "unsafe_order_field_count": len(unsafe_order_rows),
        "adapter_artifact_is_ready": adapter_artifact.get("is_ready") if isinstance(adapter_artifact, dict) else None,
        "adapter_output_item_count": adapter_artifact.get("output_item_count") if isinstance(adapter_artifact, dict) else None,
        "ev_scoring_status": ev_artifact.get("status") if isinstance(ev_artifact, dict) else None,
        "ev_scoring_is_ready": ev_artifact.get("is_ready") if isinstance(ev_artifact, dict) else None,
        "ev_scoring_requires_manual_approval": ev_artifact.get("requires_manual_approval") if isinstance(ev_artifact, dict) else None,
        "ev_scoring_order_intent": ev_artifact.get("order_intent") if isinstance(ev_artifact, dict) else None,
        "paper_order_created": False,
        "live_order_created": False,
        "live_trade_supported": False,
        "next_step": "stage37p_expectancy_handoff_closure_manifest",
    }

    summary_path = OUT_DIR / "signalforge_stage37o2_paper_handoff_contract_import_smoke_summary.json"
    import_rows_path = OUT_DIR / "signalforge_stage37o2_paper_handoff_contract_import_smoke_import_rows.jsonl"
    runtime_rows_path = OUT_DIR / "signalforge_stage37o2_paper_handoff_contract_import_smoke_runtime_rows.jsonl"
    order_rows_path = OUT_DIR / "signalforge_stage37o2_paper_handoff_contract_import_smoke_order_field_rows.jsonl"
    md_path = OUT_DIR / "signalforge_stage37o2_paper_handoff_contract_import_smoke.md"

    summary_path.write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")

    with import_rows_path.open("w", encoding="utf-8") as f:
        for row in import_rows:
            f.write(json.dumps(row, default=str) + "\n")

    with runtime_rows_path.open("w", encoding="utf-8") as f:
        for row in runtime_rows:
            f.write(json.dumps(row, default=str) + "\n")

    with order_rows_path.open("w", encoding="utf-8") as f:
        for row in order_field_rows:
            f.write(json.dumps(row, default=str) + "\n")

    md = [
        "# Stage 37O2 Paper Handoff Contract Import Smoke",
        "",
        f"- is_ready: {summary['is_ready']}",
        f"- blocker_count: {summary['blocker_count']}",
        f"- expectancy_snapshot_adapter_patch_present: {summary['expectancy_snapshot_adapter_patch_present']}",
        f"- required_module_import_ok_count: {summary['required_module_import_ok_count']} / {summary['required_module_import_count']}",
        f"- optional_module_import_ok_count: {summary['optional_module_import_ok_count']} / {summary['optional_module_import_count']}",
        f"- runtime_check_pass_count: {summary['runtime_check_pass_count']} / {summary['runtime_check_count']}",
        f"- unsafe_order_field_count: {summary['unsafe_order_field_count']}",
        f"- adapter_artifact_is_ready: {summary['adapter_artifact_is_ready']}",
        f"- adapter_output_item_count: {summary['adapter_output_item_count']}",
        f"- ev_scoring_status: {summary['ev_scoring_status']}",
        f"- ev_scoring_is_ready: {summary['ev_scoring_is_ready']}",
        f"- ev_scoring_requires_manual_approval: {summary['ev_scoring_requires_manual_approval']}",
        f"- ev_scoring_order_intent: {summary['ev_scoring_order_intent']}",
        f"- paper_order_created: {summary['paper_order_created']}",
        f"- live_order_created: {summary['live_order_created']}",
        f"- live_trade_supported: {summary['live_trade_supported']}",
    ]

    if blockers:
        md.extend(["", "## Blockers", ""])
        for blocker in blockers:
            md.append(f"- {blocker}")

    if warnings:
        md.extend(["", "## Warnings", ""])
        for warning in warnings:
            md.append(f"- {warning}")

    md_path.write_text("\n".join(md), encoding="utf-8")

    print("\n--- Stage 37O2 paper handoff contract import smoke compact ---")
    for key in [
        "is_ready",
        "blocker_count",
        "warning_count",
        "expectancy_snapshot_adapter_patch_present",
        "required_module_import_count",
        "required_module_import_ok_count",
        "optional_module_import_count",
        "optional_module_import_ok_count",
        "runtime_check_count",
        "runtime_check_pass_count",
        "order_field_count",
        "unsafe_order_field_count",
        "adapter_artifact_is_ready",
        "adapter_output_item_count",
        "ev_scoring_status",
        "ev_scoring_is_ready",
        "ev_scoring_requires_manual_approval",
        "ev_scoring_order_intent",
        "paper_order_created",
        "live_order_created",
        "live_trade_supported",
    ]:
        print(f"{key}: {summary[key]}")

    print(f"summary_path: {summary_path}")
    print(f"import_rows_path: {import_rows_path}")
    print(f"runtime_rows_path: {runtime_rows_path}")
    print(f"order_rows_path: {order_rows_path}")
    print(f"md_path: {md_path}")

    print("\n--- Stage 37O2 import rows compact ---")
    print("role\tmodule\trequired\tok\trole_resolved\terror\tfile")
    for row in import_rows:
        print(
            f"{row.get('role')}\t{row['module']}\t{row['required']}\t"
            f"{row['ok']}\t{row.get('role_resolved')}\t{row['error']}\t{row['module_file']}"
        )

    print("\n--- Stage 37O2 runtime rows compact ---")
    print("check\texpected\tactual\tpassed")
    for row in runtime_rows:
        print(f"{row['check']}\t{row['expected']}\t{row['actual']}\t{row['passed']}")

    if blockers:
        print("\n--- Stage 37O2 blockers ---")
        for blocker in blockers:
            print(blocker)
        raise SystemExit(1)

    if warnings:
        print("\n--- Stage 37O2 warnings ---")
        for warning in warnings:
            print(warning)


if __name__ == "__main__":
    main()
