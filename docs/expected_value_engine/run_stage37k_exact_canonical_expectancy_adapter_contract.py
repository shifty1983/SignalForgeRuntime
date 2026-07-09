import json
from collections import Counter
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

EXPECTED_ADAPTER_TARGET = (
    "src/signalforge/engines/strategy_selection/"
    "canonical_expectancy_snapshot_adapter.py"
)

EXPECTED_ENGINE_CONSUMER = (
    "signalforge.engines.strategy_selection.expected_value_scoring."
    "build_signalforge_expected_value_scoring"
)

LOCKED_PAPER_RULE = (
    "paper consumes canonical locked walk-forward expectancy snapshot; "
    "paper does not recompute walk-forward expectancy"
)


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


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def as_int(value: Any) -> int | None:
    try:
        if value in {None, ""}:
            return None
        return int(float(value))
    except Exception:
        return None


def as_float(value: Any) -> float | None:
    try:
        if value in {None, ""}:
            return None
        return float(value)
    except Exception:
        return None


def classify_expectancy(row: dict[str, Any]) -> dict[str, Any]:
    state = clean_text(row.get("expectancy_state")).lower()
    sample_count = as_int(row.get("expectancy_sample_count")) or 0
    minimum_sample_count = as_int(row.get("expectancy_minimum_sample_count")) or 0
    avg_return = as_float(row.get("expectancy_average_return"))
    win_rate = as_float(row.get("expectancy_win_rate"))

    if state in {"no_prior_sample", "missing", "missing_expectancy", "unavailable"} or sample_count <= 0:
        return {
            "coverage_status": "missing_expectancy",
            "expected_value_state": "data_review",
            "handoff_status": "data_review",
            "reason": "missing_or_no_prior_expectancy_sample",
        }

    if minimum_sample_count > 0 and sample_count < minimum_sample_count:
        return {
            "coverage_status": "sample_limited",
            "expected_value_state": "sample_limited",
            "handoff_status": "review",
            "reason": "sample_limited_expectancy",
        }

    if (avg_return is not None and avg_return > 0) or (win_rate is not None and win_rate > 0.5):
        return {
            "coverage_status": "covered",
            "expected_value_state": "positive_expectancy_candidate",
            "handoff_status": "candidate",
            "reason": "positive_expectancy_evidence",
        }

    return {
        "coverage_status": "covered",
        "expected_value_state": "non_positive_expectancy",
        "handoff_status": "blocked",
        "reason": "non_positive_expectancy",
    }


def strategy_for_row(row: dict[str, Any]) -> str:
    return (
        clean_text(row.get("strategy_name"))
        or clean_text(row.get("strategy"))
        or clean_text(row.get("candidate_strategy"))
        or clean_text(row.get("strategy_family"))
    )


def contract_validation(rows: list[dict[str, Any]]) -> dict[str, Any]:
    required_source_fields = [
        "symbol",
        "decision_date",
        "expectancy_state",
        "expectancy_sample_count",
        "expectancy_minimum_sample_count",
        "uses_current_row_outcome",
        "uses_future_rows",
        "training_window_end",
    ]

    missing_field_counts = Counter()
    no_lookahead_violation_count = 0
    empty_strategy_count = 0
    empty_symbol_count = 0

    coverage_counts = Counter()
    ev_state_counts = Counter()
    handoff_counts = Counter()
    reason_counts = Counter()
    strategy_counts = Counter()
    scope_counts = Counter()

    for row in rows:
        for field in required_source_fields:
            if field not in row:
                missing_field_counts[field] += 1

        if row.get("uses_current_row_outcome") is True or row.get("uses_future_rows") is True:
            no_lookahead_violation_count += 1

        strategy = strategy_for_row(row)
        symbol = clean_text(row.get("symbol"))

        if not strategy:
            empty_strategy_count += 1

        if not symbol:
            empty_symbol_count += 1

        classification = classify_expectancy(row)

        coverage_counts[classification["coverage_status"]] += 1
        ev_state_counts[classification["expected_value_state"]] += 1
        handoff_counts[classification["handoff_status"]] += 1
        reason_counts[classification["reason"]] += 1
        strategy_counts[strategy] += 1
        scope_counts[clean_text(row.get("expectancy_scope"))] += 1

    return {
        "required_source_fields": required_source_fields,
        "missing_field_counts": dict(missing_field_counts),
        "no_lookahead_violation_count": no_lookahead_violation_count,
        "empty_strategy_count": empty_strategy_count,
        "empty_symbol_count": empty_symbol_count,
        "coverage_status_counts": dict(coverage_counts),
        "expected_value_state_counts": dict(ev_state_counts),
        "handoff_status_counts": dict(handoff_counts),
        "reason_counts": dict(reason_counts),
        "top_strategy_counts": dict(strategy_counts.most_common(20)),
        "expectancy_scope_counts": dict(scope_counts),
    }


def build_contract_rows() -> list[dict[str, Any]]:
    return [
        {
            "contract_section": "ownership",
            "field": "source_owner",
            "value": "data/canonical/signalforge_pipeline/18_walk_forward_expectancy",
            "requirement": "canonical snapshot is the active source of truth",
        },
        {
            "contract_section": "ownership",
            "field": "producer_owner",
            "value": "src/signalforge/backtesting/walk_forward_expectancy_builder.py",
            "requirement": "walk-forward generation remains backtesting-owned",
        },
        {
            "contract_section": "ownership",
            "field": "adapter_target",
            "value": EXPECTED_ADAPTER_TARGET,
            "requirement": "adapter may be promoted only after parity tests",
        },
        {
            "contract_section": "ownership",
            "field": "consumer",
            "value": EXPECTED_ENGINE_CONSUMER,
            "requirement": "engine consumes adapted items as review/handoff scoring, not direct execution",
        },
        {
            "contract_section": "paper_rule",
            "field": "locked_expectancy",
            "value": LOCKED_PAPER_RULE,
            "requirement": "no expectancy recomputation inside paper decision loop",
        },
        {
            "contract_section": "safety",
            "field": "lookahead_guard",
            "value": "uses_current_row_outcome=False and uses_future_rows=False",
            "requirement": "required for every row consumed by paper snapshot adapter",
        },
        {
            "contract_section": "safety",
            "field": "manual_review_state",
            "value": "expected_value_scoring output may remain is_ready=False with requires_manual_approval=True",
            "requirement": "EV scoring does not authorize trades by itself",
        },
        {
            "contract_section": "legacy",
            "field": "legacy_expected_value_domain",
            "value": "research_candidate_only",
            "requirement": "legacy EV logic cannot be promoted without A/B backtest proof",
        },
    ]


def main() -> None:
    blockers: List[str] = []
    warnings: List[str] = []

    if not CANONICAL_ROWS_PATH.exists():
        blockers.append(f"missing_canonical_rows_path_{CANONICAL_ROWS_PATH}")

    if not CANONICAL_SUMMARY_PATH.exists():
        blockers.append(f"missing_canonical_summary_path_{CANONICAL_SUMMARY_PATH}")

    summary_json = read_json(CANONICAL_SUMMARY_PATH) if CANONICAL_SUMMARY_PATH.exists() else {}
    rows = read_jsonl(CANONICAL_ROWS_PATH) if CANONICAL_ROWS_PATH.exists() else []

    validation = contract_validation(rows) if rows else {}
    contract_rows = build_contract_rows()

    if summary_json.get("is_ready") is not True:
        blockers.append("canonical_expectancy_summary_not_ready")

    if validation.get("no_lookahead_violation_count", 0) != 0:
        blockers.append("canonical_expectancy_has_lookahead_violations")

    if validation.get("empty_strategy_count", 0) != 0:
        blockers.append("canonical_expectancy_has_empty_strategy_rows")

    if validation.get("empty_symbol_count", 0) != 0:
        blockers.append("canonical_expectancy_has_empty_symbol_rows")

    missing_field_counts = validation.get("missing_field_counts", {})
    missing_required = {
        key: value
        for key, value in missing_field_counts.items()
        if value
    }

    if missing_required:
        blockers.append(f"canonical_expectancy_missing_required_fields_{missing_required}")

    warnings.append("stage37k_is_contract_only_no_production_logic_moved")
    warnings.append("expected_value_scoring_is_review_handoff_not_trade_authorization")
    warnings.append("legacy_expected_value_domain_remains_research_only_until_ab_backtested")
    warnings.append("data_canonical_runtime_files_should_not_be_force_added_to_git")

    summary = {
        "adapter_type": "exact_canonical_expectancy_adapter_contract_builder",
        "artifact_type": "signalforge_exact_canonical_expectancy_adapter_contract",
        "contract": "exact_canonical_expectancy_adapter_contract",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,
        "canonical_rows_path": str(CANONICAL_ROWS_PATH),
        "canonical_summary_path": str(CANONICAL_SUMMARY_PATH),
        "canonical_summary_is_ready": summary_json.get("is_ready"),
        "canonical_summary_artifact_type": summary_json.get("artifact_type"),
        "canonical_summary_contract": summary_json.get("contract"),
        "canonical_row_count": len(rows),
        "adapter_target": EXPECTED_ADAPTER_TARGET,
        "engine_consumer": EXPECTED_ENGINE_CONSUMER,
        "paper_rule": LOCKED_PAPER_RULE,
        "validation": validation,
        "paper_order_created": False,
        "live_order_created": False,
        "live_trade_supported": False,
        "next_step": "stage37l_promote_canonical_expectancy_snapshot_adapter_with_parity_smoke",
    }

    summary_path = OUT_DIR / "signalforge_stage37k_exact_canonical_expectancy_adapter_contract_summary.json"
    contract_rows_path = OUT_DIR / "signalforge_stage37k_exact_canonical_expectancy_adapter_contract_rows.jsonl"
    md_path = OUT_DIR / "signalforge_stage37k_exact_canonical_expectancy_adapter_contract.md"

    summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    with contract_rows_path.open("w", encoding="utf-8") as f:
        for row in contract_rows:
            f.write(json.dumps(row, default=str) + "\n")

    md = [
        "# Stage 37K Exact Canonical Expectancy Adapter Contract",
        "",
        f"- is_ready: {summary['is_ready']}",
        f"- blocker_count: {summary['blocker_count']}",
        f"- canonical_summary_is_ready: {summary['canonical_summary_is_ready']}",
        f"- canonical_row_count: {summary['canonical_row_count']}",
        f"- adapter_target: `{summary['adapter_target']}`",
        f"- engine_consumer: `{summary['engine_consumer']}`",
        f"- paper_rule: {summary['paper_rule']}",
        f"- paper_order_created: {summary['paper_order_created']}",
        f"- live_order_created: {summary['live_order_created']}",
        f"- live_trade_supported: {summary['live_trade_supported']}",
        "",
        "## Contract Rows",
        "",
        "| section | field | value | requirement |",
        "|---|---|---|---|",
    ]

    for row in contract_rows:
        md.append(
            f"| {row['contract_section']} | {row['field']} | "
            f"`{row['value']}` | {row['requirement']} |"
        )

    md.extend([
        "",
        "## Validation",
        "",
        "```json",
        json.dumps(validation, indent=2, default=str),
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

    print("\n--- Stage 37K exact canonical expectancy adapter contract compact ---")
    for key in [
        "is_ready",
        "blocker_count",
        "warning_count",
        "canonical_summary_is_ready",
        "canonical_row_count",
        "paper_order_created",
        "live_order_created",
        "live_trade_supported",
    ]:
        print(f"{key}: {summary[key]}")

    print(f"adapter_target: {summary['adapter_target']}")
    print(f"engine_consumer: {summary['engine_consumer']}")
    print(f"summary_path: {summary_path}")
    print(f"contract_rows_path: {contract_rows_path}")
    print(f"md_path: {md_path}")

    print("\n--- Stage 37K validation compact ---")
    print(json.dumps(validation, indent=2, default=str))

    print("\n--- Stage 37K contract rows compact ---")
    print("section\tfield\tvalue\trequirement")
    for row in contract_rows:
        print(
            f"{row['contract_section']}\t{row['field']}\t"
            f"{row['value']}\t{row['requirement']}"
        )

    if blockers:
        print("\n--- Stage 37K blockers ---")
        for blocker in blockers:
            print(blocker)
        raise SystemExit(1)

    if warnings:
        print("\n--- Stage 37K warnings ---")
        for warning in warnings:
            print(warning)


if __name__ == "__main__":
    main()
