import importlib
import json
import py_compile
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List


OUT_DIR = Path("docs/expected_value_engine")

ADAPTER_PATH = Path("src/signalforge/engines/strategy_selection/canonical_expectancy_snapshot_adapter.py")

CANONICAL_ROWS_PATH = Path(
    "data/canonical/signalforge_pipeline/18_walk_forward_expectancy/"
    "signalforge_walk_forward_expectancy_rows.jsonl"
)

CANONICAL_SUMMARY_PATH = Path(
    "data/canonical/signalforge_pipeline/18_walk_forward_expectancy/"
    "signalforge_walk_forward_expectancy_summary.json"
)

EXPECTED_VALUE_MODULE = "signalforge.engines.strategy_selection.expected_value_scoring"
EXPECTED_VALUE_ENTRYPOINT = "build_signalforge_expected_value_scoring"


ADAPTER_SOURCE = r'''"""Canonical walk-forward expectancy snapshot adapter.

This module converts the locked canonical walk-forward expectancy snapshot into
engine-consumable expected-value review items.

It does not build walk-forward expectancy, authorize trades, create orders, or
promote legacy expected-value research logic.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Mapping, Sequence


CANONICAL_EXPECTANCY_ADAPTER_SCHEMA_VERSION = "signalforge_canonical_expectancy_snapshot_adapter.v1"

CANONICAL_EXPECTANCY_CONTRACT = "canonical_expectancy_snapshot_adapter"

SOURCE_EXPECTANCY_CONTRACT = "walk_forward_expectancy"

REVIEW_SCOPE = "canonical_walk_forward_expectancy_to_expected_value_review_handoff"

PAPER_RULE = (
    "paper consumes canonical locked walk-forward expectancy snapshot; "
    "paper does not recompute walk-forward expectancy"
)

REQUIRED_SOURCE_FIELDS = (
    "symbol",
    "decision_date",
    "expectancy_state",
    "expectancy_sample_count",
    "expectancy_minimum_sample_count",
    "uses_current_row_outcome",
    "uses_future_rows",
    "training_window_end",
)

ROW_CONTAINER_KEYS = (
    "rows",
    "items",
    "data",
    "expectancy_rows",
    "walk_forward_expectancy_rows",
)


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None

    try:
        return int(float(value))
    except Exception:
        return None


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None

    try:
        return float(value)
    except Exception:
        return None


def _is_mapping_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _extract_rows(snapshot_source: Mapping[str, Any] | Sequence[Any] | None) -> list[dict[str, Any]]:
    if snapshot_source is None:
        return []

    if _is_mapping_sequence(snapshot_source):
        return [dict(row) for row in snapshot_source if isinstance(row, Mapping)]

    if isinstance(snapshot_source, Mapping):
        for key in ROW_CONTAINER_KEYS:
            value = snapshot_source.get(key)

            if _is_mapping_sequence(value):
                return [dict(row) for row in value if isinstance(row, Mapping)]

    return []


def _strategy_for_row(row: Mapping[str, Any]) -> str:
    return (
        _clean_text(row.get("strategy_name"))
        or _clean_text(row.get("strategy"))
        or _clean_text(row.get("candidate_strategy"))
        or _clean_text(row.get("strategy_family"))
    )


def _classify_expectancy(row: Mapping[str, Any]) -> dict[str, Any]:
    state = _clean_text(row.get("expectancy_state")).lower()
    sample_count = _as_int(row.get("expectancy_sample_count")) or 0
    minimum_sample_count = _as_int(row.get("expectancy_minimum_sample_count")) or 0
    avg_return = _as_float(row.get("expectancy_average_return"))
    win_rate = _as_float(row.get("expectancy_win_rate"))

    if state in {"no_prior_sample", "missing", "missing_expectancy", "unavailable"} or sample_count <= 0:
        return {
            "coverage_status": "missing_expectancy",
            "expected_value_state": "data_review",
            "handoff_status": "data_review",
            "reason": "missing_or_no_prior_expectancy_sample",
            "sample_count": sample_count,
            "minimum_sample_count": minimum_sample_count,
            "avg_return": avg_return,
            "win_rate": win_rate,
        }

    if minimum_sample_count > 0 and sample_count < minimum_sample_count:
        return {
            "coverage_status": "sample_limited",
            "expected_value_state": "sample_limited",
            "handoff_status": "review",
            "reason": "sample_limited_expectancy",
            "sample_count": sample_count,
            "minimum_sample_count": minimum_sample_count,
            "avg_return": avg_return,
            "win_rate": win_rate,
        }

    if (avg_return is not None and avg_return > 0) or (win_rate is not None and win_rate > 0.5):
        return {
            "coverage_status": "covered",
            "expected_value_state": "positive_expectancy_candidate",
            "handoff_status": "candidate",
            "reason": "positive_expectancy_evidence",
            "sample_count": sample_count,
            "minimum_sample_count": minimum_sample_count,
            "avg_return": avg_return,
            "win_rate": win_rate,
        }

    return {
        "coverage_status": "covered",
        "expected_value_state": "non_positive_expectancy",
        "handoff_status": "blocked",
        "reason": "non_positive_expectancy",
        "sample_count": sample_count,
        "minimum_sample_count": minimum_sample_count,
        "avg_return": avg_return,
        "win_rate": win_rate,
    }


def _canonical_row_to_expected_value_item(row: Mapping[str, Any]) -> dict[str, Any]:
    strategy = _strategy_for_row(row)
    symbol = _clean_text(row.get("symbol"))
    classification = _classify_expectancy(row)
    handoff_status = classification["handoff_status"]

    favored_families: list[str] = []
    allowed_families: list[str] = []
    blocked_families: list[str] = []

    if strategy:
        if handoff_status == "candidate":
            favored_families.append(strategy)
            allowed_families.append(strategy)
        elif handoff_status == "review":
            allowed_families.append(strategy)
        elif handoff_status == "blocked":
            blocked_families.append(strategy)

    blocked_reasons = []
    constraint_flags = []

    if classification["reason"] != "positive_expectancy_evidence":
        blocked_reasons.append(classification["reason"])

    if classification["coverage_status"] in {"missing_expectancy", "sample_limited"}:
        constraint_flags.append(classification["coverage_status"])

    if handoff_status == "blocked":
        constraint_flags.append("non_positive_expectancy")

    return {
        "symbol": symbol,
        "underlying_symbol": symbol,
        "strategy_family": strategy,
        "strategy_name": strategy,
        "candidate_strategy": strategy,
        "candidate_id": row.get("candidate_id") or row.get("strategy_candidate_id"),
        "strategy_candidate_id": row.get("strategy_candidate_id") or row.get("candidate_id"),
        "decision_date": row.get("decision_date") or row.get("date"),
        "date": row.get("date") or row.get("decision_date"),

        "coverage_status": classification["coverage_status"],
        "expected_value_state": classification["expected_value_state"],
        "expected_value_handoff_status": handoff_status,
        "handoff_status": handoff_status,

        "favored_families": favored_families,
        "allowed_families": allowed_families,
        "blocked_families": blocked_families,

        "risk_flags": [],
        "constraint_flags": constraint_flags,
        "blocked_reasons": blocked_reasons,

        "premium_bias": row.get("premium_bias"),
        "expectancy_state": row.get("expectancy_state"),
        "expectancy_scope": row.get("expectancy_scope"),
        "expectancy_sample_count": classification["sample_count"],
        "expectancy_minimum_sample_count": classification["minimum_sample_count"],
        "expectancy_average_return": classification["avg_return"],
        "expectancy_median_return": _as_float(row.get("expectancy_median_return")),
        "expectancy_win_rate": classification["win_rate"],

        "uses_current_row_outcome": row.get("uses_current_row_outcome"),
        "uses_future_rows": row.get("uses_future_rows"),
        "training_window_start": row.get("training_window_start"),
        "training_window_end": row.get("training_window_end"),

        "source_expectancy_contract": SOURCE_EXPECTANCY_CONTRACT,
        "source_expectancy_adapter_schema_version": CANONICAL_EXPECTANCY_ADAPTER_SCHEMA_VERSION,
    }


def _summary(items: Sequence[Mapping[str, Any]], source_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    coverage_counts = Counter(_clean_text(item.get("coverage_status")) for item in items)
    ev_state_counts = Counter(_clean_text(item.get("expected_value_state")) for item in items)
    handoff_counts = Counter(_clean_text(item.get("handoff_status")) for item in items)
    strategy_counts = Counter(_clean_text(item.get("strategy_name")) for item in items)
    scope_counts = Counter(_clean_text(row.get("expectancy_scope")) for row in source_rows)

    return {
        "input_row_count": len(source_rows),
        "output_item_count": len(items),
        "coverage_status_counts": dict(coverage_counts),
        "expected_value_state_counts": dict(ev_state_counts),
        "handoff_status_counts": dict(handoff_counts),
        "top_strategy_counts": dict(strategy_counts.most_common(20)),
        "expectancy_scope_counts": dict(scope_counts),
    }


def build_canonical_expectancy_snapshot_adapter(
    snapshot_source: Mapping[str, Any] | Sequence[Any] | None,
    *,
    source_rows_path: str | None = None,
    source_summary_path: str | None = None,
) -> dict[str, Any]:
    """Build expected-value review items from canonical walk-forward expectancy rows."""

    rows = _extract_rows(snapshot_source)

    blockers: list[str] = []
    warnings: list[str] = [
        "expected_value_adapter_is_review_handoff_not_trade_authorization",
        "paper_must_not_recompute_walk_forward_expectancy_inside_decision_loop",
        "legacy_expected_value_domain_not_used",
    ]

    if not rows:
        blockers.append("no_canonical_expectancy_rows_provided")

    missing_field_counts: Counter[str] = Counter()
    lookahead_violation_count = 0
    empty_symbol_count = 0
    empty_strategy_count = 0

    for row in rows:
        for field in REQUIRED_SOURCE_FIELDS:
            if field not in row:
                missing_field_counts[field] += 1

        if row.get("uses_current_row_outcome") is True or row.get("uses_future_rows") is True:
            lookahead_violation_count += 1

        if not _clean_text(row.get("symbol")):
            empty_symbol_count += 1

        if not _strategy_for_row(row):
            empty_strategy_count += 1

    if missing_field_counts:
        blockers.append(f"missing_required_source_fields_{dict(missing_field_counts)}")

    if lookahead_violation_count:
        blockers.append(f"lookahead_violation_count_{lookahead_violation_count}")

    if empty_symbol_count:
        blockers.append(f"empty_symbol_count_{empty_symbol_count}")

    if empty_strategy_count:
        blockers.append(f"empty_strategy_count_{empty_strategy_count}")

    items = [_canonical_row_to_expected_value_item(row) for row in rows] if not blockers else []
    summary = _summary(items, rows)

    return {
        "adapter_type": "canonical_expectancy_snapshot_adapter_builder",
        "artifact_type": "signalforge_canonical_expectancy_snapshot_adapter",
        "contract": CANONICAL_EXPECTANCY_CONTRACT,
        "schema_version": CANONICAL_EXPECTANCY_ADAPTER_SCHEMA_VERSION,
        "status": "ready_for_expected_value_review" if not blockers else "blocked",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,

        "review_scope": REVIEW_SCOPE,
        "paper_rule": PAPER_RULE,
        "source_rows_path": source_rows_path,
        "source_summary_path": source_summary_path,

        "input_row_count": len(rows),
        "output_item_count": len(items),
        "expected_value_items": items,
        "items": items,
        "rows": items,
        "adapter_summary": summary,

        "order_intent": None,
        "broker_order_id": None,
        "paper_order_created": False,
        "live_order_created": False,
        "live_trade_supported": False,
    }


__all__ = [
    "CANONICAL_EXPECTANCY_ADAPTER_SCHEMA_VERSION",
    "CANONICAL_EXPECTANCY_CONTRACT",
    "SOURCE_EXPECTANCY_CONTRACT",
    "REVIEW_SCOPE",
    "PAPER_RULE",
    "REQUIRED_SOURCE_FIELDS",
    "build_canonical_expectancy_snapshot_adapter",
]
'''


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


def write_adapter() -> None:
    ADAPTER_PATH.parent.mkdir(parents=True, exist_ok=True)

    if ADAPTER_PATH.exists():
        backup = OUT_DIR / "stage37l_canonical_expectancy_snapshot_adapter.py.before_stage37l"
        backup.write_text(ADAPTER_PATH.read_text(encoding="utf-8"), encoding="utf-8")

    ADAPTER_PATH.write_text(ADAPTER_SOURCE, encoding="utf-8")


def run_expected_value_scoring(adapter_artifact: dict[str, Any]) -> dict[str, Any]:
    module = importlib.import_module(EXPECTED_VALUE_MODULE)
    func = getattr(module, EXPECTED_VALUE_ENTRYPOINT)
    result = func(adapter_artifact)

    return {
        "artifact_type": result.get("artifact_type") if isinstance(result, dict) else None,
        "contract": result.get("contract") if isinstance(result, dict) else None,
        "status": result.get("status") if isinstance(result, dict) else None,
        "is_ready": result.get("is_ready") if isinstance(result, dict) else None,
        "requires_manual_approval": result.get("requires_manual_approval") if isinstance(result, dict) else None,
        "review_scope": result.get("review_scope") if isinstance(result, dict) else None,
        "expected_value_item_count": len(result.get("expected_value_items", [])) if isinstance(result, dict) else None,
        "ev_item_count": len(result.get("ev_items", [])) if isinstance(result, dict) else None,
        "order_intent": result.get("order_intent") if isinstance(result, dict) else None,
        "broker_order_id": result.get("broker_order_id") if isinstance(result, dict) else None,
        "automatic_action": result.get("automatic_action") if isinstance(result, dict) else None,
    }


def main() -> None:
    blockers: List[str] = []
    warnings: List[str] = []

    if not CANONICAL_ROWS_PATH.exists():
        blockers.append(f"missing_canonical_rows_path_{CANONICAL_ROWS_PATH}")

    if not CANONICAL_SUMMARY_PATH.exists():
        blockers.append(f"missing_canonical_summary_path_{CANONICAL_SUMMARY_PATH}")

    if blockers:
        raise SystemExit(json.dumps({"blockers": blockers}, indent=2))

    write_adapter()
    py_compile.compile(str(ADAPTER_PATH), doraise=True)

    adapter_module = importlib.import_module(
        "signalforge.engines.strategy_selection.canonical_expectancy_snapshot_adapter"
    )

    rows = read_jsonl(CANONICAL_ROWS_PATH)
    canonical_summary = read_json(CANONICAL_SUMMARY_PATH)

    adapter_artifact = adapter_module.build_canonical_expectancy_snapshot_adapter(
        rows,
        source_rows_path=str(CANONICAL_ROWS_PATH),
        source_summary_path=str(CANONICAL_SUMMARY_PATH),
    )

    ev_scoring_result = run_expected_value_scoring(adapter_artifact)

    expected_counts = {
        "coverage_status_counts": {
            "missing_expectancy": 132,
            "sample_limited": 165,
            "covered": 13115,
        },
        "expected_value_state_counts": {
            "data_review": 132,
            "sample_limited": 165,
            "positive_expectancy_candidate": 9405,
            "non_positive_expectancy": 3710,
        },
        "handoff_status_counts": {
            "data_review": 132,
            "review": 165,
            "candidate": 9405,
            "blocked": 3710,
        },
    }

    adapter_summary = adapter_artifact.get("adapter_summary", {})

    parity_rows = []

    for group, expected in expected_counts.items():
        actual = adapter_summary.get(group, {})
        parity_rows.append({
            "group": group,
            "expected": expected,
            "actual": actual,
            "same": actual == expected,
        })

    if adapter_artifact.get("is_ready") is not True:
        blockers.append("adapter_artifact_not_ready")

    if adapter_artifact.get("input_row_count") != 13412:
        blockers.append(f"unexpected_adapter_input_row_count_{adapter_artifact.get('input_row_count')}")

    if adapter_artifact.get("output_item_count") != 13412:
        blockers.append(f"unexpected_adapter_output_item_count_{adapter_artifact.get('output_item_count')}")

    if any(row["same"] is not True for row in parity_rows):
        blockers.append("adapter_distribution_parity_failed")

    if ev_scoring_result.get("expected_value_item_count") != 13412:
        blockers.append(
            f"expected_value_scoring_item_count_mismatch_{ev_scoring_result.get('expected_value_item_count')}"
        )

    if ev_scoring_result.get("is_ready") is not False:
        blockers.append("expected_value_scoring_should_remain_review_not_ready")

    if ev_scoring_result.get("requires_manual_approval") is not True:
        blockers.append("expected_value_scoring_should_require_manual_approval")

    if ev_scoring_result.get("order_intent") is not None:
        blockers.append("expected_value_scoring_set_order_intent")

    warnings.append("stage37l_promotes_adapter_only_no_order_logic")
    warnings.append("expected_value_scoring_remains_review_handoff_not_trade_authorization")
    warnings.append("legacy_expected_value_domain_not_used")
    warnings.append("data_canonical_runtime_files_should_not_be_force_added_to_git")

    summary = {
        "adapter_type": "canonical_expectancy_snapshot_adapter_promotion_builder",
        "artifact_type": "signalforge_canonical_expectancy_snapshot_adapter_promotion",
        "contract": "canonical_expectancy_snapshot_adapter_promotion",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,
        "adapter_path": str(ADAPTER_PATH),
        "canonical_rows_path": str(CANONICAL_ROWS_PATH),
        "canonical_summary_path": str(CANONICAL_SUMMARY_PATH),
        "canonical_summary_is_ready": canonical_summary.get("is_ready"),
        "adapter_artifact_is_ready": adapter_artifact.get("is_ready"),
        "adapter_input_row_count": adapter_artifact.get("input_row_count"),
        "adapter_output_item_count": adapter_artifact.get("output_item_count"),
        "adapter_status": adapter_artifact.get("status"),
        "adapter_summary": adapter_summary,
        "expected_value_scoring_result": ev_scoring_result,
        "parity_rows": parity_rows,
        "paper_order_created": False,
        "live_order_created": False,
        "live_trade_supported": False,
        "next_step": "stage37m_wire_canonical_expectancy_adapter_into_paper_candidate_handoff_read_only",
    }

    summary_path = OUT_DIR / "signalforge_stage37l_canonical_expectancy_snapshot_adapter_promotion_summary.json"
    parity_rows_path = OUT_DIR / "signalforge_stage37l_canonical_expectancy_snapshot_adapter_promotion_parity_rows.jsonl"
    md_path = OUT_DIR / "signalforge_stage37l_canonical_expectancy_snapshot_adapter_promotion.md"

    summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    with parity_rows_path.open("w", encoding="utf-8") as f:
        for row in parity_rows:
            f.write(json.dumps(row, default=str) + "\n")

    md = [
        "# Stage 37L Canonical Expectancy Snapshot Adapter Promotion",
        "",
        f"- is_ready: {summary['is_ready']}",
        f"- blocker_count: {summary['blocker_count']}",
        f"- adapter_path: `{summary['adapter_path']}`",
        f"- canonical_summary_is_ready: {summary['canonical_summary_is_ready']}",
        f"- adapter_artifact_is_ready: {summary['adapter_artifact_is_ready']}",
        f"- adapter_input_row_count: {summary['adapter_input_row_count']}",
        f"- adapter_output_item_count: {summary['adapter_output_item_count']}",
        f"- expected_value_scoring_status: {ev_scoring_result.get('status')}",
        f"- expected_value_scoring_is_ready: {ev_scoring_result.get('is_ready')}",
        f"- expected_value_scoring_requires_manual_approval: {ev_scoring_result.get('requires_manual_approval')}",
        f"- expected_value_scoring_item_count: {ev_scoring_result.get('expected_value_item_count')}",
        f"- paper_order_created: {summary['paper_order_created']}",
        f"- live_order_created: {summary['live_order_created']}",
        f"- live_trade_supported: {summary['live_trade_supported']}",
        "",
        "## Adapter Summary",
        "",
        "```json",
        json.dumps(adapter_summary, indent=2, default=str),
        "```",
        "",
        "## Expected-Value Scoring Result",
        "",
        "```json",
        json.dumps(ev_scoring_result, indent=2, default=str),
        "```",
        "",
        "## Parity Rows",
        "",
        "| group | same | expected | actual |",
        "|---|---:|---|---|",
    ]

    for row in parity_rows:
        md.append(
            f"| {row['group']} | {row['same']} | "
            f"`{row['expected']}` | `{row['actual']}` |"
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

    print("\n--- Stage 37L canonical expectancy snapshot adapter promotion compact ---")
    for key in [
        "is_ready",
        "blocker_count",
        "warning_count",
        "canonical_summary_is_ready",
        "adapter_artifact_is_ready",
        "adapter_input_row_count",
        "adapter_output_item_count",
        "adapter_status",
        "paper_order_created",
        "live_order_created",
        "live_trade_supported",
    ]:
        print(f"{key}: {summary[key]}")

    print(f"adapter_path: {ADAPTER_PATH}")
    print(f"summary_path: {summary_path}")
    print(f"parity_rows_path: {parity_rows_path}")
    print(f"md_path: {md_path}")

    print("\n--- Stage 37L adapter distribution compact ---")
    print(json.dumps(adapter_summary, indent=2, default=str))

    print("\n--- Stage 37L expected-value scoring result compact ---")
    print(json.dumps(ev_scoring_result, indent=2, default=str))

    print("\n--- Stage 37L parity compact ---")
    print("group\tsame\texpected\tactual")
    for row in parity_rows:
        print(
            f"{row['group']}\t{row['same']}\t"
            f"{json.dumps(row['expected'], default=str)}\t"
            f"{json.dumps(row['actual'], default=str)}"
        )

    if blockers:
        print("\n--- Stage 37L blockers ---")
        for blocker in blockers:
            print(blocker)
        raise SystemExit(1)

    if warnings:
        print("\n--- Stage 37L warnings ---")
        for warning in warnings:
            print(warning)


if __name__ == "__main__":
    main()
