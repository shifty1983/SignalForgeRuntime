import copy
import importlib
import json
from pathlib import Path
from typing import Any, Dict, List


OUT_DIR = Path("docs/expected_value_engine")

HANDOFF_CONTRACT_PATH = Path(
    "configs/paper_live_engine/signalforge_v21_paper_live_engine_handoff_contract.json"
)

PROPOSED_PATCH_PATH = Path(
    "docs/expected_value_engine/signalforge_stage37m_proposed_paper_handoff_expectancy_patch.json"
)

BACKUP_PATH = OUT_DIR / "stage37n_signalforge_v21_paper_live_engine_handoff_contract_before_expectancy_patch.json"

CANONICAL_ROWS_PATH = Path(
    "data/canonical/signalforge_pipeline/18_walk_forward_expectancy/"
    "signalforge_walk_forward_expectancy_rows.jsonl"
)

CANONICAL_SUMMARY_PATH = Path(
    "data/canonical/signalforge_pipeline/18_walk_forward_expectancy/"
    "signalforge_walk_forward_expectancy_summary.json"
)

ADAPTER_MODULE = (
    "signalforge.engines.strategy_selection."
    "canonical_expectancy_snapshot_adapter"
)

ADAPTER_ENTRYPOINT = "build_canonical_expectancy_snapshot_adapter"

EV_MODULE = "signalforge.engines.strategy_selection.expected_value_scoring"
EV_ENTRYPOINT = "build_signalforge_expected_value_scoring"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, default=str) + "\n", encoding="utf-8")


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


def safe_get(value: Any, *keys: str) -> Any:
    current = value

    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)

    return current


def flatten_paths(value: Any, prefix: str = "") -> list[dict[str, Any]]:
    rows = []

    if isinstance(value, dict):
        for key, item in value.items():
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            key_l = str(key).lower()

            if "path" in key_l or "file" in key_l or "artifact" in key_l:
                rows.append({
                    "field": next_prefix,
                    "value": item,
                })

            rows.extend(flatten_paths(item, next_prefix))

    elif isinstance(value, list):
        for index, item in enumerate(value):
            rows.extend(flatten_paths(item, f"{prefix}[{index}]"))

    return rows


def main() -> None:
    blockers: List[str] = []
    warnings: List[str] = []

    for path, label in [
        (HANDOFF_CONTRACT_PATH, "handoff_contract"),
        (PROPOSED_PATCH_PATH, "proposed_patch"),
        (CANONICAL_ROWS_PATH, "canonical_rows"),
        (CANONICAL_SUMMARY_PATH, "canonical_summary"),
    ]:
        if not path.exists():
            blockers.append(f"missing_{label}_{path}")

    if blockers:
        raise SystemExit(json.dumps({"blockers": blockers}, indent=2))

    original_contract = read_json(HANDOFF_CONTRACT_PATH)
    proposed_patch = read_json(PROPOSED_PATCH_PATH)

    if "expectancy_snapshot_adapter" not in proposed_patch:
        blockers.append("proposed_patch_missing_expectancy_snapshot_adapter")

    if not isinstance(original_contract, dict):
        blockers.append("handoff_contract_not_json_object")

    if blockers:
        raise SystemExit(json.dumps({"blockers": blockers}, indent=2))

    BACKUP_PATH.write_text(
        HANDOFF_CONTRACT_PATH.read_text(encoding="utf-8-sig"),
        encoding="utf-8",
    )

    patched_contract = copy.deepcopy(original_contract)
    patched_contract["expectancy_snapshot_adapter"] = proposed_patch["expectancy_snapshot_adapter"]

    write_json(HANDOFF_CONTRACT_PATH, patched_contract)

    reloaded_contract = read_json(HANDOFF_CONTRACT_PATH)
    reloaded_patch = reloaded_contract.get("expectancy_snapshot_adapter")

    canonical_summary = read_json(CANONICAL_SUMMARY_PATH)
    canonical_rows = read_jsonl(CANONICAL_ROWS_PATH)

    adapter_module = importlib.import_module(ADAPTER_MODULE)
    adapter_func = getattr(adapter_module, ADAPTER_ENTRYPOINT)

    ev_module = importlib.import_module(EV_MODULE)
    ev_func = getattr(ev_module, EV_ENTRYPOINT)

    adapter_artifact = adapter_func(
        canonical_rows,
        source_rows_path=str(CANONICAL_ROWS_PATH),
        source_summary_path=str(CANONICAL_SUMMARY_PATH),
    )

    ev_artifact = ev_func(adapter_artifact)

    paper_candidate_id = (
        reloaded_contract.get("paper_candidate_id")
        or safe_get(reloaded_contract, "paper_candidate", "paper_candidate_id")
        or safe_get(reloaded_contract, "candidate", "paper_candidate_id")
        or safe_get(reloaded_contract, "lock", "paper_candidate_id")
    )

    readiness_rows = [
        {
            "check": "handoff_contract_reloaded",
            "expected": True,
            "actual": isinstance(reloaded_contract, dict),
            "passed": isinstance(reloaded_contract, dict),
        },
        {
            "check": "expectancy_snapshot_adapter_patch_present",
            "expected": True,
            "actual": isinstance(reloaded_patch, dict),
            "passed": isinstance(reloaded_patch, dict),
        },
        {
            "check": "patch_matches_stage37m_proposal",
            "expected": proposed_patch["expectancy_snapshot_adapter"],
            "actual": reloaded_patch,
            "passed": reloaded_patch == proposed_patch["expectancy_snapshot_adapter"],
        },
        {
            "check": "canonical_summary_ready",
            "expected": True,
            "actual": canonical_summary.get("is_ready"),
            "passed": canonical_summary.get("is_ready") is True,
        },
        {
            "check": "adapter_ready",
            "expected": True,
            "actual": adapter_artifact.get("is_ready"),
            "passed": adapter_artifact.get("is_ready") is True,
        },
        {
            "check": "adapter_item_count_matches_canonical",
            "expected": len(canonical_rows),
            "actual": adapter_artifact.get("output_item_count"),
            "passed": adapter_artifact.get("output_item_count") == len(canonical_rows),
        },
        {
            "check": "ev_scoring_remains_review",
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
        {
            "check": "contract_trade_authorization_guard",
            "expected": "not_authorized_by_expectancy_adapter_or_expected_value_scoring",
            "actual": reloaded_patch.get("trade_authorization") if isinstance(reloaded_patch, dict) else None,
            "passed": (
                isinstance(reloaded_patch, dict)
                and reloaded_patch.get("trade_authorization")
                == "not_authorized_by_expectancy_adapter_or_expected_value_scoring"
            ),
        },
    ]

    failed_checks = [
        row["check"]
        for row in readiness_rows
        if row["passed"] is not True
    ]

    if failed_checks:
        blockers.append(f"stage37n_failed_checks_{failed_checks}")

    warnings.append("stage37n_updates_handoff_contract_only")
    warnings.append("expectancy_adapter_and_expected_value_scoring_do_not_authorize_trades")
    warnings.append("expected_value_scoring_intentionally_remains_needs_review")
    warnings.append("data_canonical_runtime_files_should_not_be_force_added_to_git")

    summary = {
        "adapter_type": "paper_handoff_expectancy_adapter_patch_builder",
        "artifact_type": "signalforge_paper_handoff_expectancy_adapter_patch",
        "contract": "paper_handoff_expectancy_adapter_patch",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,
        "handoff_contract_path": str(HANDOFF_CONTRACT_PATH),
        "backup_path": str(BACKUP_PATH),
        "paper_candidate_id": paper_candidate_id,
        "patch_present": isinstance(reloaded_patch, dict),
        "canonical_row_count": len(canonical_rows),
        "canonical_summary_is_ready": canonical_summary.get("is_ready"),
        "adapter_is_ready": adapter_artifact.get("is_ready"),
        "adapter_output_item_count": adapter_artifact.get("output_item_count"),
        "ev_scoring_status": ev_artifact.get("status") if isinstance(ev_artifact, dict) else None,
        "ev_scoring_is_ready": ev_artifact.get("is_ready") if isinstance(ev_artifact, dict) else None,
        "ev_scoring_requires_manual_approval": ev_artifact.get("requires_manual_approval") if isinstance(ev_artifact, dict) else None,
        "ev_scoring_order_intent": ev_artifact.get("order_intent") if isinstance(ev_artifact, dict) else None,
        "readiness_rows": readiness_rows,
        "handoff_path_rows": flatten_paths(reloaded_contract),
        "paper_order_created": False,
        "live_order_created": False,
        "live_trade_supported": False,
        "next_step": "stage37o_paper_handoff_contract_import_smoke",
    }

    summary_path = OUT_DIR / "signalforge_stage37n_paper_handoff_expectancy_adapter_patch_summary.json"
    readiness_rows_path = OUT_DIR / "signalforge_stage37n_paper_handoff_expectancy_adapter_patch_rows.jsonl"
    handoff_path_rows_path = OUT_DIR / "signalforge_stage37n_paper_handoff_contract_path_rows.jsonl"
    md_path = OUT_DIR / "signalforge_stage37n_paper_handoff_expectancy_adapter_patch.md"

    write_json(summary_path, summary)

    with readiness_rows_path.open("w", encoding="utf-8") as f:
        for row in readiness_rows:
            f.write(json.dumps(row, default=str) + "\n")

    with handoff_path_rows_path.open("w", encoding="utf-8") as f:
        for row in summary["handoff_path_rows"]:
            f.write(json.dumps(row, default=str) + "\n")

    md = [
        "# Stage 37N Paper Handoff Expectancy Adapter Patch",
        "",
        f"- is_ready: {summary['is_ready']}",
        f"- blocker_count: {summary['blocker_count']}",
        f"- handoff_contract_path: `{summary['handoff_contract_path']}`",
        f"- backup_path: `{summary['backup_path']}`",
        f"- paper_candidate_id: `{summary['paper_candidate_id']}`",
        f"- patch_present: {summary['patch_present']}",
        f"- canonical_row_count: {summary['canonical_row_count']}",
        f"- canonical_summary_is_ready: {summary['canonical_summary_is_ready']}",
        f"- adapter_is_ready: {summary['adapter_is_ready']}",
        f"- adapter_output_item_count: {summary['adapter_output_item_count']}",
        f"- ev_scoring_status: {summary['ev_scoring_status']}",
        f"- ev_scoring_is_ready: {summary['ev_scoring_is_ready']}",
        f"- ev_scoring_requires_manual_approval: {summary['ev_scoring_requires_manual_approval']}",
        f"- ev_scoring_order_intent: {summary['ev_scoring_order_intent']}",
        f"- paper_order_created: {summary['paper_order_created']}",
        f"- live_order_created: {summary['live_order_created']}",
        f"- live_trade_supported: {summary['live_trade_supported']}",
        "",
        "## Readiness Checks",
        "",
        "| check | expected | actual | passed |",
        "|---|---|---|---:|",
    ]

    for row in readiness_rows:
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

    print("\n--- Stage 37N paper handoff expectancy adapter patch compact ---")
    for key in [
        "is_ready",
        "blocker_count",
        "warning_count",
        "patch_present",
        "canonical_row_count",
        "canonical_summary_is_ready",
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

    print(f"handoff_contract_path: {summary['handoff_contract_path']}")
    print(f"backup_path: {summary['backup_path']}")
    print(f"paper_candidate_id: {summary['paper_candidate_id']}")
    print(f"summary_path: {summary_path}")
    print(f"readiness_rows_path: {readiness_rows_path}")
    print(f"handoff_path_rows_path: {handoff_path_rows_path}")
    print(f"md_path: {md_path}")

    print("\n--- Stage 37N readiness rows compact ---")
    print("check\texpected\tactual\tpassed")
    for row in readiness_rows:
        print(f"{row['check']}\t{row['expected']}\t{row['actual']}\t{row['passed']}")

    if blockers:
        print("\n--- Stage 37N blockers ---")
        for blocker in blockers:
            print(blocker)
        raise SystemExit(1)

    if warnings:
        print("\n--- Stage 37N warnings ---")
        for warning in warnings:
            print(warning)


if __name__ == "__main__":
    main()
