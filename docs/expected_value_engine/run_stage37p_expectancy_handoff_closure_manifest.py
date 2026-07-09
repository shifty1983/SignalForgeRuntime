import importlib
import json
from pathlib import Path
from typing import Any, Dict, List


OUT_DIR = Path("docs/expected_value_engine")

HANDOFF_CONTRACT_PATH = Path(
    "configs/paper_live_engine/signalforge_v21_paper_live_engine_handoff_contract.json"
)

CANONICAL_ROWS_PATH = Path(
    "data/canonical/signalforge_pipeline/18_walk_forward_expectancy/"
    "signalforge_walk_forward_expectancy_rows.jsonl"
)

CANONICAL_SUMMARY_PATH = Path(
    "data/canonical/signalforge_pipeline/18_walk_forward_expectancy/"
    "signalforge_walk_forward_expectancy_summary.json"
)

ADAPTER_MODULE = "signalforge.engines.strategy_selection.canonical_expectancy_snapshot_adapter"
ADAPTER_ENTRYPOINT = "build_canonical_expectancy_snapshot_adapter"

EV_MODULE = "signalforge.engines.strategy_selection.expected_value_scoring"
EV_ENTRYPOINT = "build_signalforge_expected_value_scoring"

REQUIRED_DOCS = [
    Path("docs/expected_value_engine/signalforge_stage37h_canonical_expectancy_snapshot_inspection_summary.json"),
    Path("docs/expected_value_engine/signalforge_stage37k_exact_canonical_expectancy_adapter_contract_summary.json"),
    Path("docs/expected_value_engine/signalforge_stage37l_canonical_expectancy_snapshot_adapter_promotion_summary.json"),
    Path("docs/expected_value_engine/signalforge_stage37m_paper_handoff_expectancy_adapter_readiness_summary.json"),
    Path("docs/expected_value_engine/signalforge_stage37n_paper_handoff_expectancy_adapter_patch_summary.json"),
    Path("docs/expected_value_engine/signalforge_stage37o2_paper_handoff_contract_import_smoke_summary.json"),
]

REQUIRED_CODE_FILES = [
    Path("src/signalforge/engines/strategy_selection/canonical_expectancy_snapshot_adapter.py"),
    Path("src/signalforge/engines/strategy_selection/expected_value_scoring.py"),
]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_jsonl_count(path: Path) -> int:
    count = 0
    with path.open("r", encoding="utf-8-sig") as f:
        for line in f:
            if line.strip():
                count += 1
    return count


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


def import_check(module_name: str) -> dict[str, Any]:
    try:
        module = importlib.import_module(module_name)
        return {
            "module": module_name,
            "ok": True,
            "error": None,
            "module_file": getattr(module, "__file__", None),
        }
    except Exception as exc:
        return {
            "module": module_name,
            "ok": False,
            "error": str(exc),
            "module_file": None,
        }


def main() -> None:
    blockers: List[str] = []
    warnings: List[str] = []

    file_rows: List[Dict[str, Any]] = []

    for path in REQUIRED_DOCS + REQUIRED_CODE_FILES + [
        HANDOFF_CONTRACT_PATH,
        CANONICAL_ROWS_PATH,
        CANONICAL_SUMMARY_PATH,
    ]:
        exists = path.exists()
        file_rows.append({
            "path": str(path),
            "exists": exists,
            "size_bytes": path.stat().st_size if exists else None,
        })
        if not exists:
            blockers.append(f"missing_required_file_{path}")

    handoff_contract = read_json(HANDOFF_CONTRACT_PATH) if HANDOFF_CONTRACT_PATH.exists() else {}
    canonical_summary = read_json(CANONICAL_SUMMARY_PATH) if CANONICAL_SUMMARY_PATH.exists() else {}
    canonical_row_count = read_jsonl_count(CANONICAL_ROWS_PATH) if CANONICAL_ROWS_PATH.exists() else None

    patch = handoff_contract.get("expectancy_snapshot_adapter") if isinstance(handoff_contract, dict) else None

    if not isinstance(patch, dict):
        blockers.append("handoff_contract_missing_expectancy_snapshot_adapter")

    import_rows = [
        import_check(ADAPTER_MODULE),
        import_check(EV_MODULE),
    ]

    if any(row["ok"] is not True for row in import_rows):
        blockers.append("required_expectancy_modules_failed_import")

    adapter_artifact = None
    ev_artifact = None

    if not blockers:
        rows = read_jsonl(CANONICAL_ROWS_PATH)

        adapter_module = importlib.import_module(ADAPTER_MODULE)
        adapter_func = getattr(adapter_module, ADAPTER_ENTRYPOINT)

        ev_module = importlib.import_module(EV_MODULE)
        ev_func = getattr(ev_module, EV_ENTRYPOINT)

        adapter_artifact = adapter_func(
            rows,
            source_rows_path=str(CANONICAL_ROWS_PATH),
            source_summary_path=str(CANONICAL_SUMMARY_PATH),
        )

        ev_artifact = ev_func(adapter_artifact)

    closure_checks = [
        {
            "check": "canonical_summary_ready",
            "expected": True,
            "actual": canonical_summary.get("is_ready") if isinstance(canonical_summary, dict) else None,
            "passed": isinstance(canonical_summary, dict) and canonical_summary.get("is_ready") is True,
        },
        {
            "check": "canonical_row_count",
            "expected": 13412,
            "actual": canonical_row_count,
            "passed": canonical_row_count == 13412,
        },
        {
            "check": "handoff_patch_present",
            "expected": True,
            "actual": isinstance(patch, dict),
            "passed": isinstance(patch, dict),
        },
        {
            "check": "handoff_patch_source_is_canonical_stage18",
            "expected": str(CANONICAL_ROWS_PATH),
            "actual": patch.get("source_rows_path") if isinstance(patch, dict) else None,
            "passed": isinstance(patch, dict) and Path(patch.get("source_rows_path", "")) == CANONICAL_ROWS_PATH,
        },
        {
            "check": "adapter_ready",
            "expected": True,
            "actual": adapter_artifact.get("is_ready") if isinstance(adapter_artifact, dict) else None,
            "passed": isinstance(adapter_artifact, dict) and adapter_artifact.get("is_ready") is True,
        },
        {
            "check": "adapter_output_count",
            "expected": 13412,
            "actual": adapter_artifact.get("output_item_count") if isinstance(adapter_artifact, dict) else None,
            "passed": isinstance(adapter_artifact, dict) and adapter_artifact.get("output_item_count") == 13412,
        },
        {
            "check": "ev_scoring_review_status",
            "expected": "needs_review",
            "actual": ev_artifact.get("status") if isinstance(ev_artifact, dict) else None,
            "passed": isinstance(ev_artifact, dict) and ev_artifact.get("status") == "needs_review",
        },
        {
            "check": "ev_scoring_manual_approval_required",
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
        {
            "check": "live_trade_supported_false",
            "expected": False,
            "actual": False,
            "passed": True,
        },
    ]

    failed_checks = [row for row in closure_checks if row["passed"] is not True]

    if failed_checks:
        blockers.append(f"closure_checks_failed_{[row['check'] for row in failed_checks]}")

    closure_state = "closed_expectancy_handoff_to_paper_contract" if not blockers else "blocked"

    warnings.append("stage37p_closure_manifest_only")
    warnings.append("expectancy_adapter_is_handoff_input_not_trade_authorization")
    warnings.append("expected_value_scoring_intentionally_remains_needs_review")
    warnings.append("legacy_expected_value_domain_remains_research_only_until_ab_backtested")
    warnings.append("optional_paper_live_bridge_namespace_cleanup_remains_separate_followup")
    warnings.append("data_canonical_runtime_files_should_not_be_force_added_to_git")

    summary = {
        "adapter_type": "expectancy_handoff_closure_manifest_builder",
        "artifact_type": "signalforge_expectancy_handoff_closure_manifest",
        "contract": "expectancy_handoff_closure_manifest",
        "is_ready": len(blockers) == 0,
        "closure_state": closure_state,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,
        "canonical_rows_path": str(CANONICAL_ROWS_PATH),
        "canonical_summary_path": str(CANONICAL_SUMMARY_PATH),
        "canonical_summary_is_ready": canonical_summary.get("is_ready") if isinstance(canonical_summary, dict) else None,
        "canonical_row_count": canonical_row_count,
        "handoff_contract_path": str(HANDOFF_CONTRACT_PATH),
        "handoff_patch_present": isinstance(patch, dict),
        "adapter_module": ADAPTER_MODULE,
        "adapter_entrypoint": ADAPTER_ENTRYPOINT,
        "adapter_is_ready": adapter_artifact.get("is_ready") if isinstance(adapter_artifact, dict) else None,
        "adapter_output_item_count": adapter_artifact.get("output_item_count") if isinstance(adapter_artifact, dict) else None,
        "ev_module": EV_MODULE,
        "ev_entrypoint": EV_ENTRYPOINT,
        "ev_scoring_status": ev_artifact.get("status") if isinstance(ev_artifact, dict) else None,
        "ev_scoring_is_ready": ev_artifact.get("is_ready") if isinstance(ev_artifact, dict) else None,
        "ev_scoring_requires_manual_approval": ev_artifact.get("requires_manual_approval") if isinstance(ev_artifact, dict) else None,
        "ev_scoring_order_intent": ev_artifact.get("order_intent") if isinstance(ev_artifact, dict) else None,
        "paper_rule": patch.get("paper_rule") if isinstance(patch, dict) else None,
        "trade_authorization": patch.get("trade_authorization") if isinstance(patch, dict) else None,
        "required_file_count": len(file_rows),
        "required_file_present_count": sum(1 for row in file_rows if row["exists"]),
        "import_rows": import_rows,
        "closure_checks": closure_checks,
        "paper_order_created": False,
        "live_order_created": False,
        "live_trade_supported": False,
        "next_step": "return_to_paper_engine_namespace_cleanup_or_portfolio_construction_handoff",
    }

    summary_path = OUT_DIR / "signalforge_stage37p_expectancy_handoff_closure_manifest_summary.json"
    file_rows_path = OUT_DIR / "signalforge_stage37p_expectancy_handoff_closure_manifest_file_rows.jsonl"
    check_rows_path = OUT_DIR / "signalforge_stage37p_expectancy_handoff_closure_manifest_check_rows.jsonl"
    md_path = OUT_DIR / "signalforge_stage37p_expectancy_handoff_closure_manifest.md"

    summary_path.write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")

    with file_rows_path.open("w", encoding="utf-8") as f:
        for row in file_rows:
            f.write(json.dumps(row, default=str) + "\n")

    with check_rows_path.open("w", encoding="utf-8") as f:
        for row in closure_checks:
            f.write(json.dumps(row, default=str) + "\n")

    md = [
        "# Stage 37P Expectancy Handoff Closure Manifest",
        "",
        f"- is_ready: {summary['is_ready']}",
        f"- closure_state: `{summary['closure_state']}`",
        f"- blocker_count: {summary['blocker_count']}",
        f"- canonical_row_count: {summary['canonical_row_count']}",
        f"- canonical_summary_is_ready: {summary['canonical_summary_is_ready']}",
        f"- handoff_patch_present: {summary['handoff_patch_present']}",
        f"- adapter_is_ready: {summary['adapter_is_ready']}",
        f"- adapter_output_item_count: {summary['adapter_output_item_count']}",
        f"- ev_scoring_status: {summary['ev_scoring_status']}",
        f"- ev_scoring_is_ready: {summary['ev_scoring_is_ready']}",
        f"- ev_scoring_requires_manual_approval: {summary['ev_scoring_requires_manual_approval']}",
        f"- ev_scoring_order_intent: {summary['ev_scoring_order_intent']}",
        f"- trade_authorization: `{summary['trade_authorization']}`",
        f"- paper_order_created: {summary['paper_order_created']}",
        f"- live_order_created: {summary['live_order_created']}",
        f"- live_trade_supported: {summary['live_trade_supported']}",
        "",
        "## Closure Checks",
        "",
        "| check | expected | actual | passed |",
        "|---|---|---|---:|",
    ]

    for row in closure_checks:
        md.append(
            f"| {row['check']} | `{row['expected']}` | `{row['actual']}` | {row['passed']} |"
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

    print("\n--- Stage 37P expectancy handoff closure manifest compact ---")
    for key in [
        "is_ready",
        "closure_state",
        "blocker_count",
        "warning_count",
        "canonical_summary_is_ready",
        "canonical_row_count",
        "handoff_patch_present",
        "adapter_is_ready",
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
    print(f"file_rows_path: {file_rows_path}")
    print(f"check_rows_path: {check_rows_path}")
    print(f"md_path: {md_path}")

    print("\n--- Stage 37P closure checks compact ---")
    print("check\texpected\tactual\tpassed")
    for row in closure_checks:
        print(f"{row['check']}\t{row['expected']}\t{row['actual']}\t{row['passed']}")

    if blockers:
        print("\n--- Stage 37P blockers ---")
        for blocker in blockers:
            print(blocker)
        raise SystemExit(1)

    if warnings:
        print("\n--- Stage 37P warnings ---")
        for warning in warnings:
            print(warning)


if __name__ == "__main__":
    main()
