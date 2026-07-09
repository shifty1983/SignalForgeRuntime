import importlib
import json
from pathlib import Path
from typing import Any, Dict, List


OUT_DIR = Path("docs/expected_value_engine")

CANONICAL_ROWS_PATH = Path(
    "data/canonical/signalforge_pipeline/18_walk_forward_expectancy/"
    "signalforge_walk_forward_expectancy_rows.jsonl"
)

CANONICAL_SUMMARY_PATH = Path(
    "data/canonical/signalforge_pipeline/18_walk_forward_expectancy/"
    "signalforge_walk_forward_expectancy_summary.json"
)

HANDOFF_CONTRACT_PATH = Path(
    "configs/paper_live_engine/signalforge_v21_paper_live_engine_handoff_contract.json"
)

ADAPTER_MODULE = (
    "signalforge.engines.strategy_selection."
    "canonical_expectancy_snapshot_adapter"
)

ADAPTER_ENTRYPOINT = "build_canonical_expectancy_snapshot_adapter"

EXPECTED_VALUE_MODULE = (
    "signalforge.engines.strategy_selection.expected_value_scoring"
)

EXPECTED_VALUE_ENTRYPOINT = "build_signalforge_expected_value_scoring"


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


def safe_get(value: Any, *keys: str) -> Any:
    current = value

    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)

    return current


def main() -> None:
    blockers: List[str] = []
    warnings: List[str] = []

    if not CANONICAL_ROWS_PATH.exists():
        blockers.append(f"missing_canonical_rows_path_{CANONICAL_ROWS_PATH}")

    if not CANONICAL_SUMMARY_PATH.exists():
        blockers.append(f"missing_canonical_summary_path_{CANONICAL_SUMMARY_PATH}")

    if not HANDOFF_CONTRACT_PATH.exists():
        blockers.append(f"missing_handoff_contract_path_{HANDOFF_CONTRACT_PATH}")

    handoff_contract = read_json(HANDOFF_CONTRACT_PATH) if HANDOFF_CONTRACT_PATH.exists() else {}
    canonical_summary = read_json(CANONICAL_SUMMARY_PATH) if CANONICAL_SUMMARY_PATH.exists() else {}

    adapter_module = importlib.import_module(ADAPTER_MODULE)
    adapter_func = getattr(adapter_module, ADAPTER_ENTRYPOINT)

    ev_module = importlib.import_module(EXPECTED_VALUE_MODULE)
    ev_func = getattr(ev_module, EXPECTED_VALUE_ENTRYPOINT)

    canonical_rows = read_jsonl(CANONICAL_ROWS_PATH) if CANONICAL_ROWS_PATH.exists() else []

    adapter_artifact = adapter_func(
        canonical_rows,
        source_rows_path=str(CANONICAL_ROWS_PATH),
        source_summary_path=str(CANONICAL_SUMMARY_PATH),
    )

    ev_artifact = ev_func(adapter_artifact)

    handoff_path_rows = flatten_paths(handoff_contract)

    handoff_text = json.dumps(handoff_contract, default=str).lower()

    expectancy_contract_mentions = [
        needle for needle in [
            "expectancy",
            "expected_value",
            "walk_forward",
            "canonical",
            "18_walk_forward_expectancy",
        ]
        if needle in handoff_text
    ]

    paper_candidate_id = (
        handoff_contract.get("paper_candidate_id")
        or safe_get(handoff_contract, "paper_candidate", "paper_candidate_id")
        or safe_get(handoff_contract, "candidate", "paper_candidate_id")
        or safe_get(handoff_contract, "lock", "paper_candidate_id")
    )

    paper_trade_supported = (
        handoff_contract.get("paper_trade_supported")
        or safe_get(handoff_contract, "execution_gap_resolution", "paper_trade_supported")
        or safe_get(handoff_contract, "paper_candidate", "paper_trade_supported")
    )

    live_trade_supported = (
        handoff_contract.get("live_trade_supported")
        or safe_get(handoff_contract, "execution_gap_resolution", "live_trade_supported")
        or safe_get(handoff_contract, "paper_candidate", "live_trade_supported")
    )

    proposed_handoff_patch = {
        "expectancy_snapshot_adapter": {
            "adapter_module": ADAPTER_MODULE,
            "adapter_entrypoint": ADAPTER_ENTRYPOINT,
            "source_rows_path": str(CANONICAL_ROWS_PATH),
            "source_summary_path": str(CANONICAL_SUMMARY_PATH),
            "source_contract": canonical_summary.get("contract"),
            "source_artifact_type": canonical_summary.get("artifact_type"),
            "source_is_ready": canonical_summary.get("is_ready"),
            "adapter_contract": adapter_artifact.get("contract"),
            "adapter_schema_version": adapter_artifact.get("schema_version"),
            "adapter_status": adapter_artifact.get("status"),
            "adapter_is_ready": adapter_artifact.get("is_ready"),
            "adapter_output_item_count": adapter_artifact.get("output_item_count"),
            "consumer_module": EXPECTED_VALUE_MODULE,
            "consumer_entrypoint": EXPECTED_VALUE_ENTRYPOINT,
            "consumer_contract": ev_artifact.get("contract") if isinstance(ev_artifact, dict) else None,
            "consumer_status": ev_artifact.get("status") if isinstance(ev_artifact, dict) else None,
            "consumer_is_ready": ev_artifact.get("is_ready") if isinstance(ev_artifact, dict) else None,
            "consumer_requires_manual_approval": ev_artifact.get("requires_manual_approval") if isinstance(ev_artifact, dict) else None,
            "paper_rule": adapter_artifact.get("paper_rule"),
            "trade_authorization": "not_authorized_by_expectancy_adapter_or_expected_value_scoring",
        }
    }

    readiness_rows = [
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
            "check": "ev_scoring_does_not_create_order_intent",
            "expected": None,
            "actual": ev_artifact.get("order_intent") if isinstance(ev_artifact, dict) else None,
            "passed": isinstance(ev_artifact, dict) and ev_artifact.get("order_intent") is None,
        },
    ]

    failed_checks = [row for row in readiness_rows if row["passed"] is not True]

    if failed_checks:
        blockers.append(f"paper_handoff_expectancy_adapter_readiness_failed_{[row['check'] for row in failed_checks]}")

    warnings.append("stage37m_is_read_only_no_handoff_contract_modified")
    warnings.append("proposed_handoff_patch_written_to_docs_only")
    warnings.append("expectancy_adapter_and_expected_value_scoring_do_not_authorize_trades")
    warnings.append("data_canonical_runtime_files_should_not_be_force_added_to_git")

    summary = {
        "adapter_type": "paper_handoff_expectancy_adapter_readiness_builder",
        "artifact_type": "signalforge_paper_handoff_expectancy_adapter_readiness",
        "contract": "paper_handoff_expectancy_adapter_readiness",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,
        "handoff_contract_path": str(HANDOFF_CONTRACT_PATH),
        "paper_candidate_id": paper_candidate_id,
        "paper_trade_supported": paper_trade_supported,
        "live_trade_supported_from_contract": live_trade_supported,
        "expectancy_contract_mentions": expectancy_contract_mentions,
        "canonical_rows_path": str(CANONICAL_ROWS_PATH),
        "canonical_summary_path": str(CANONICAL_SUMMARY_PATH),
        "canonical_row_count": len(canonical_rows),
        "canonical_summary_is_ready": canonical_summary.get("is_ready"),
        "adapter_module": ADAPTER_MODULE,
        "adapter_entrypoint": ADAPTER_ENTRYPOINT,
        "adapter_is_ready": adapter_artifact.get("is_ready"),
        "adapter_output_item_count": adapter_artifact.get("output_item_count"),
        "ev_scoring_status": ev_artifact.get("status") if isinstance(ev_artifact, dict) else None,
        "ev_scoring_is_ready": ev_artifact.get("is_ready") if isinstance(ev_artifact, dict) else None,
        "ev_scoring_requires_manual_approval": ev_artifact.get("requires_manual_approval") if isinstance(ev_artifact, dict) else None,
        "ev_scoring_order_intent": ev_artifact.get("order_intent") if isinstance(ev_artifact, dict) else None,
        "readiness_rows": readiness_rows,
        "proposed_handoff_patch": proposed_handoff_patch,
        "paper_order_created": False,
        "live_order_created": False,
        "live_trade_supported": False,
        "next_step": "stage37n_apply_paper_handoff_expectancy_adapter_patch_after_review",
    }

    summary_path = OUT_DIR / "signalforge_stage37m_paper_handoff_expectancy_adapter_readiness_summary.json"
    readiness_rows_path = OUT_DIR / "signalforge_stage37m_paper_handoff_expectancy_adapter_readiness_rows.jsonl"
    handoff_path_rows_path = OUT_DIR / "signalforge_stage37m_paper_handoff_contract_path_rows.jsonl"
    proposed_patch_path = OUT_DIR / "signalforge_stage37m_proposed_paper_handoff_expectancy_patch.json"
    md_path = OUT_DIR / "signalforge_stage37m_paper_handoff_expectancy_adapter_readiness.md"

    summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    proposed_patch_path.write_text(json.dumps(proposed_handoff_patch, indent=2, default=str), encoding="utf-8")

    with readiness_rows_path.open("w", encoding="utf-8") as f:
        for row in readiness_rows:
            f.write(json.dumps(row, default=str) + "\n")

    with handoff_path_rows_path.open("w", encoding="utf-8") as f:
        for row in handoff_path_rows:
            f.write(json.dumps(row, default=str) + "\n")

    md = [
        "# Stage 37M Paper Handoff Expectancy Adapter Readiness",
        "",
        f"- is_ready: {summary['is_ready']}",
        f"- blocker_count: {summary['blocker_count']}",
        f"- handoff_contract_path: `{summary['handoff_contract_path']}`",
        f"- paper_candidate_id: `{summary['paper_candidate_id']}`",
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

    md.extend([
        "",
        "## Proposed Handoff Patch",
        "",
        "```json",
        json.dumps(proposed_handoff_patch, indent=2, default=str),
        "```",
    ])

    if blockers:
        md.extend(["", "## Blockers", ""])
        for blocker in blockers:
            md.append(f"- {blocker}")

    if warnings:
        md.extend(["", "## Warnings", ""])
        for warning in warnings:
            md.append(f"- {warning}")

    md_path.write_text("\n".join(md), encoding="utf-8")

    print("\n--- Stage 37M paper handoff expectancy adapter readiness compact ---")
    for key in [
        "is_ready",
        "blocker_count",
        "warning_count",
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
    print(f"paper_candidate_id: {summary['paper_candidate_id']}")
    print(f"summary_path: {summary_path}")
    print(f"readiness_rows_path: {readiness_rows_path}")
    print(f"handoff_path_rows_path: {handoff_path_rows_path}")
    print(f"proposed_patch_path: {proposed_patch_path}")
    print(f"md_path: {md_path}")

    print("\n--- Stage 37M readiness rows compact ---")
    print("check\texpected\tactual\tpassed")
    for row in readiness_rows:
        print(f"{row['check']}\t{row['expected']}\t{row['actual']}\t{row['passed']}")

    print("\n--- Stage 37M proposed handoff patch compact ---")
    print(json.dumps(proposed_handoff_patch, indent=2, default=str))

    if blockers:
        print("\n--- Stage 37M blockers ---")
        for blocker in blockers:
            print(blocker)
        raise SystemExit(1)

    if warnings:
        print("\n--- Stage 37M warnings ---")
        for warning in warnings:
            print(warning)


if __name__ == "__main__":
    main()
