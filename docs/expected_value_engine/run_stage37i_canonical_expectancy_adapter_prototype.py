import importlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Sequence


OUT_DIR = Path("docs/expected_value_engine")

CANONICAL_ROWS_PATH = Path(
    "data/canonical/signalforge_pipeline/18_walk_forward_expectancy/"
    "signalforge_walk_forward_expectancy_rows.jsonl"
)

CANONICAL_SUMMARY_PATH = Path(
    "data/canonical/signalforge_pipeline/18_walk_forward_expectancy/"
    "signalforge_walk_forward_expectancy_summary.json"
)

ENGINE_MODULE = "signalforge.engines.strategy_selection.expected_value_scoring"
ENGINE_ENTRYPOINT = "build_signalforge_expected_value_scoring"

SAMPLE_LIMIT = 500


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_jsonl(path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8-sig") as f:
        for line in f:
            text = line.strip()
            if not text:
                continue

            item = json.loads(text)

            if isinstance(item, dict):
                rows.append(item)

            if limit is not None and len(rows) >= limit:
                break

    return rows


def count_jsonl(path: Path) -> int:
    count = 0

    with path.open("r", encoding="utf-8-sig") as f:
        for line in f:
            if line.strip():
                count += 1

    return count


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def as_float(value: Any) -> float | None:
    try:
        if value in {None, ""}:
            return None
        return float(value)
    except Exception:
        return None


def as_int(value: Any) -> int | None:
    try:
        if value in {None, ""}:
            return None
        return int(float(value))
    except Exception:
        return None


def expectancy_quality(row: MappingLike) -> dict[str, Any]:
    state = clean_text(row.get("expectancy_state")).lower()
    sample_count = as_int(row.get("expectancy_sample_count")) or 0
    minimum_sample_count = as_int(row.get("expectancy_minimum_sample_count")) or 0
    avg_return = as_float(row.get("expectancy_average_return"))
    win_rate = as_float(row.get("expectancy_win_rate"))

    has_prior_sample = sample_count > 0
    meets_sample = sample_count >= minimum_sample_count if minimum_sample_count > 0 else sample_count > 0
    positive_avg = avg_return is not None and avg_return > 0
    positive_win = win_rate is not None and win_rate > 0.5

    if state in {"no_prior_sample", "missing", "missing_expectancy", "unavailable"} or not has_prior_sample:
        coverage_status = "missing_expectancy"
        expected_value_state = "data_review"
        handoff_status = "data_review"
        blocked_reasons = ["missing_or_no_prior_expectancy_sample"]

    elif not meets_sample:
        coverage_status = "sample_limited"
        expected_value_state = "sample_limited"
        handoff_status = "review"
        blocked_reasons = ["sample_limited_expectancy"]

    elif positive_avg or positive_win:
        coverage_status = "covered"
        expected_value_state = "positive_expectancy_candidate"
        handoff_status = "candidate"
        blocked_reasons = []

    else:
        coverage_status = "covered"
        expected_value_state = "non_positive_expectancy"
        handoff_status = "blocked"
        blocked_reasons = ["non_positive_expectancy"]

    return {
        "coverage_status": coverage_status,
        "expected_value_state": expected_value_state,
        "handoff_status": handoff_status,
        "blocked_reasons": blocked_reasons,
        "sample_count": sample_count,
        "minimum_sample_count": minimum_sample_count,
        "avg_return": avg_return,
        "win_rate": win_rate,
    }


MappingLike = Dict[str, Any]


def canonical_row_to_engine_item(row: MappingLike) -> dict[str, Any]:
    strategy = (
        clean_text(row.get("strategy_name"))
        or clean_text(row.get("strategy"))
        or clean_text(row.get("candidate_strategy"))
        or clean_text(row.get("strategy_family"))
    )

    symbol = clean_text(row.get("symbol"))
    quality = expectancy_quality(row)

    favored_families: list[str] = []
    allowed_families: list[str] = []
    blocked_families: list[str] = []

    if strategy:
        if quality["handoff_status"] in {"candidate", "review"}:
            allowed_families.append(strategy)

        if quality["handoff_status"] == "candidate":
            favored_families.append(strategy)

        if quality["handoff_status"] == "blocked":
            blocked_families.append(strategy)

    risk_flags = []
    constraint_flags = []

    if quality["coverage_status"] == "sample_limited":
        constraint_flags.append("sample_limited_expectancy")

    if quality["coverage_status"] == "missing_expectancy":
        constraint_flags.append("missing_expectancy")

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

        "coverage_status": quality["coverage_status"],
        "expected_value_state": quality["expected_value_state"],
        "expected_value_handoff_status": quality["handoff_status"],
        "handoff_status": quality["handoff_status"],

        "favored_families": favored_families,
        "allowed_families": allowed_families,
        "blocked_families": blocked_families,

        "risk_flags": risk_flags,
        "constraint_flags": constraint_flags,
        "blocked_reasons": quality["blocked_reasons"],

        "premium_bias": row.get("premium_bias"),
        "expectancy_state": row.get("expectancy_state"),
        "expectancy_scope": row.get("expectancy_scope"),
        "expectancy_sample_count": quality["sample_count"],
        "expectancy_minimum_sample_count": quality["minimum_sample_count"],
        "expectancy_average_return": quality["avg_return"],
        "expectancy_median_return": as_float(row.get("expectancy_median_return")),
        "expectancy_win_rate": quality["win_rate"],
        "is_sample_limited": row.get("is_sample_limited"),

        "uses_current_row_outcome": row.get("uses_current_row_outcome"),
        "uses_future_rows": row.get("uses_future_rows"),
        "training_window_start": row.get("training_window_start"),
        "training_window_end": row.get("training_window_end"),

        "source_expectancy_contract": "walk_forward_expectancy",
        "source_expectancy_artifact": "data/canonical/signalforge_pipeline/18_walk_forward_expectancy",
    }


def build_engine_input_variants(items: Sequence[MappingLike], module: Any) -> dict[str, Any]:
    variants: dict[str, Any] = {
        "items_list": list(items),
        "items_key": {"items": list(items)},
        "rows_key": {"rows": list(items)},
        "eligibility_items_key": {"eligibility_items": list(items)},
        "expected_value_items_key": {"expected_value_items": list(items)},
        "strategy_selection_items_key": {"strategy_selection_items": list(items)},
        "artifact_wrapped_items": {
            "artifact_type": "signalforge_locked_expectancy_snapshot_adapter",
            "contract": "locked_expectancy_snapshot_adapter",
            "items": list(items),
        },
    }

    for attr in ["ELIGIBILITY_ITEM_KEYS", "ITEM_KEYS", "SOURCE_ITEM_KEYS"]:
        keys = getattr(module, attr, None)
        if isinstance(keys, (list, tuple, set)):
            for key in keys:
                if isinstance(key, str):
                    variants[f"module_declared_key_{key}"] = {key: list(items)}

    return variants


def engine_result(source: Any) -> dict[str, Any]:
    module = importlib.import_module(ENGINE_MODULE)
    func = getattr(module, ENGINE_ENTRYPOINT)

    try:
        result = func(source)
    except Exception as exc:
        return {
            "ok": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "result": None,
            "result_type": None,
            "artifact_type": None,
            "contract": None,
            "is_ready": None,
            "blocker_count": None,
            "blockers": None,
            "warning_count": None,
            "warnings": None,
            "result_keys": None,
            "item_count_fields": {},
            "summary": None,
        }

    item_count_fields = {}
    if isinstance(result, dict):
        for key, value in result.items():
            if "count" in str(key).lower():
                item_count_fields[key] = value

    return {
        "ok": True,
        "error_type": None,
        "error": None,
        "result": result,
        "result_type": type(result).__name__,
        "artifact_type": result.get("artifact_type") if isinstance(result, dict) else None,
        "contract": result.get("contract") if isinstance(result, dict) else None,
        "is_ready": result.get("is_ready") if isinstance(result, dict) else None,
        "blocker_count": result.get("blocker_count") if isinstance(result, dict) else None,
        "blockers": result.get("blockers") if isinstance(result, dict) else None,
        "warning_count": result.get("warning_count") if isinstance(result, dict) else None,
        "warnings": result.get("warnings") if isinstance(result, dict) else None,
        "result_keys": sorted(result.keys()) if isinstance(result, dict) else None,
        "item_count_fields": item_count_fields,
        "summary": result.get("summary") if isinstance(result, dict) else None,
    }


def sample_distribution(items: Sequence[MappingLike]) -> dict[str, Any]:
    coverage = Counter(clean_text(item.get("coverage_status")) for item in items)
    ev_state = Counter(clean_text(item.get("expected_value_state")) for item in items)
    handoff = Counter(clean_text(item.get("handoff_status")) for item in items)
    strategies = Counter(clean_text(item.get("strategy_name")) for item in items)

    return {
        "coverage_status_counts": dict(coverage),
        "expected_value_state_counts": dict(ev_state),
        "handoff_status_counts": dict(handoff),
        "top_strategy_counts": dict(strategies.most_common(20)),
    }


def main() -> None:
    blockers: List[str] = []
    warnings: List[str] = []

    if not CANONICAL_ROWS_PATH.exists():
        blockers.append(f"missing_canonical_rows_path_{CANONICAL_ROWS_PATH}")

    if not CANONICAL_SUMMARY_PATH.exists():
        blockers.append(f"missing_canonical_summary_path_{CANONICAL_SUMMARY_PATH}")

    canonical_summary = read_json(CANONICAL_SUMMARY_PATH) if CANONICAL_SUMMARY_PATH.exists() else None
    canonical_total_count = count_jsonl(CANONICAL_ROWS_PATH) if CANONICAL_ROWS_PATH.exists() else 0
    canonical_rows = read_jsonl(CANONICAL_ROWS_PATH, limit=SAMPLE_LIMIT) if CANONICAL_ROWS_PATH.exists() else []

    engine_items = [canonical_row_to_engine_item(row) for row in canonical_rows]

    module = importlib.import_module(ENGINE_MODULE)
    module_constants = {}

    for attr in [
        "ELIGIBILITY_ITEM_KEYS",
        "EXPECTED_VALUE_SCORING_SCHEMA_VERSION",
        "FAMILY_ORDER",
        "NON_EV_FAMILIES",
        "COVERED_CAPABILITIES",
        "DEPENDS_ON_CAPABILITIES",
    ]:
        if hasattr(module, attr):
            value = getattr(module, attr)
            try:
                json.dumps(value, default=str)
                module_constants[attr] = value
            except Exception:
                module_constants[attr] = repr(value)

    variants = build_engine_input_variants(engine_items, module)

    smoke_rows = []
    for name, source in variants.items():
        result = engine_result(source)

        smoke_rows.append({
            "variant": name,
            "source_type": type(source).__name__,
            "source_item_count": len(source) if isinstance(source, list) else len(source.get("items", [])) if isinstance(source, dict) and isinstance(source.get("items"), list) else None,
            "ok": result["ok"],
            "error_type": result["error_type"],
            "error": result["error"],
            "artifact_type": result["artifact_type"],
            "contract": result["contract"],
            "is_ready": result["is_ready"],
            "blocker_count": result["blocker_count"],
            "blockers": result["blockers"],
            "warning_count": result["warning_count"],
            "warnings": result["warnings"],
            "item_count_fields": result["item_count_fields"],
            "summary": result["summary"],
            "result_keys": result["result_keys"],
        })

    ready_smoke_rows = [
        row for row in smoke_rows
        if row["ok"] and row["is_ready"] is True
    ]

    acceptable_smoke_rows = [
        row for row in smoke_rows
        if row["ok"]
        and (
            row["is_ready"] is True
            or row["blocker_count"] in {0, None}
        )
    ]

    adapter_contract = {
        "adapter_name": "canonical_walk_forward_expectancy_snapshot_adapter",
        "source_owner": "data/canonical/signalforge_pipeline/18_walk_forward_expectancy",
        "source_rows_path": str(CANONICAL_ROWS_PATH),
        "source_summary_path": str(CANONICAL_SUMMARY_PATH),
        "producer_owner": "src/signalforge/backtesting/walk_forward_expectancy_builder.py",
        "consumer_candidate": f"{ENGINE_MODULE}.{ENGINE_ENTRYPOINT}",
        "adapter_output_shape": "sequence_of_engine_expected_value_scoring_items",
        "paper_rule": "paper consumes locked canonical expectancy snapshot and does not recompute walk-forward expectancy",
        "required_source_fields": [
            "symbol",
            "strategy_name or strategy",
            "decision_date or date",
            "expectancy_state",
            "expectancy_sample_count",
            "expectancy_minimum_sample_count",
            "expectancy_average_return",
            "expectancy_win_rate",
            "uses_current_row_outcome",
            "uses_future_rows",
            "training_window_end",
        ],
        "required_output_fields": [
            "symbol",
            "strategy_family",
            "strategy_name",
            "decision_date",
            "coverage_status",
            "expected_value_state",
            "favored_families",
            "allowed_families",
            "blocked_families",
            "constraint_flags",
            "blocked_reasons",
        ],
    }

    if not ready_smoke_rows:
        warnings.append("adapter_items_built_but_current_engine_did_not_return_ready_true_for_any_variant")
        warnings.append("next_stage_should_inspect_expected_value_scoring_readiness_contract_before_wiring")

    warnings.append("stage37i_is_docs_only_no_production_logic_moved")
    warnings.append("canonical_expectancy_snapshot_is_selected_source_of_truth")
    warnings.append("legacy_expected_value_domain_remains_research_only_until_ab_backtested")

    summary = {
        "adapter_type": "canonical_expectancy_adapter_prototype_builder",
        "artifact_type": "signalforge_canonical_expectancy_adapter_prototype",
        "contract": "canonical_expectancy_adapter_prototype",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,
        "canonical_rows_path": str(CANONICAL_ROWS_PATH),
        "canonical_summary_path": str(CANONICAL_SUMMARY_PATH),
        "canonical_summary_is_ready": canonical_summary.get("is_ready") if isinstance(canonical_summary, dict) else None,
        "canonical_summary_artifact_type": canonical_summary.get("artifact_type") if isinstance(canonical_summary, dict) else None,
        "canonical_total_row_count": canonical_total_count,
        "sample_limit": SAMPLE_LIMIT,
        "adapter_item_count": len(engine_items),
        "adapter_item_distribution": sample_distribution(engine_items),
        "engine_module": ENGINE_MODULE,
        "engine_entrypoint": ENGINE_ENTRYPOINT,
        "module_constants": module_constants,
        "smoke_row_count": len(smoke_rows),
        "ready_smoke_count": len(ready_smoke_rows),
        "acceptable_smoke_count": len(acceptable_smoke_rows),
        "adapter_contract": adapter_contract,
        "paper_order_created": False,
        "live_order_created": False,
        "live_trade_supported": False,
        "next_step": (
            "stage37j_inspect_expected_value_scoring_readiness_contract"
            if not ready_smoke_rows
            else "stage37j_promote_canonical_expectancy_adapter_with_parity_tests"
        ),
    }

    summary_path = OUT_DIR / "signalforge_stage37i_canonical_expectancy_adapter_prototype_summary.json"
    smoke_rows_path = OUT_DIR / "signalforge_stage37i_canonical_expectancy_adapter_prototype_smoke_rows.jsonl"
    adapter_sample_rows_path = OUT_DIR / "signalforge_stage37i_canonical_expectancy_adapter_prototype_sample_rows.jsonl"
    md_path = OUT_DIR / "signalforge_stage37i_canonical_expectancy_adapter_prototype.md"

    summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    with smoke_rows_path.open("w", encoding="utf-8") as f:
        for row in smoke_rows:
            f.write(json.dumps(row, default=str) + "\n")

    with adapter_sample_rows_path.open("w", encoding="utf-8") as f:
        for row in engine_items[:100]:
            f.write(json.dumps(row, default=str) + "\n")

    md = [
        "# Stage 37I Canonical Expectancy Adapter Prototype",
        "",
        f"- is_ready: {summary['is_ready']}",
        f"- blocker_count: {summary['blocker_count']}",
        f"- canonical_summary_is_ready: {summary['canonical_summary_is_ready']}",
        f"- canonical_total_row_count: {summary['canonical_total_row_count']}",
        f"- adapter_item_count: {summary['adapter_item_count']}",
        f"- smoke_row_count: {summary['smoke_row_count']}",
        f"- ready_smoke_count: {summary['ready_smoke_count']}",
        f"- acceptable_smoke_count: {summary['acceptable_smoke_count']}",
        f"- paper_order_created: {summary['paper_order_created']}",
        f"- live_order_created: {summary['live_order_created']}",
        f"- live_trade_supported: {summary['live_trade_supported']}",
        "",
        "## Adapter Contract",
        "",
        "```json",
        json.dumps(adapter_contract, indent=2, default=str),
        "```",
        "",
        "## Adapter Item Distribution",
        "",
        "```json",
        json.dumps(summary["adapter_item_distribution"], indent=2, default=str),
        "```",
        "",
        "## Engine Module Constants",
        "",
        "```json",
        json.dumps(module_constants, indent=2, default=str),
        "```",
        "",
        "## Engine Smoke Rows",
        "",
        "| variant | source items | ok | ready | blockers | warnings | count fields | summary | error |",
        "|---|---:|---:|---:|---|---|---|---|---|",
    ]

    for row in smoke_rows:
        md.append(
            f"| {row['variant']} | {row['source_item_count']} | {row['ok']} | {row['is_ready']} | "
            f"{row['blockers']} | {row['warnings']} | {row['item_count_fields']} | "
            f"{row['summary']} | {row['error']} |"
        )

    md.extend([
        "",
        "## Adapter Sample Rows",
        "",
        "```json",
        json.dumps(engine_items[:5], indent=2, default=str),
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

    print("\n--- Stage 37I canonical expectancy adapter prototype compact ---")
    for key in [
        "is_ready",
        "blocker_count",
        "warning_count",
        "canonical_summary_is_ready",
        "canonical_total_row_count",
        "sample_limit",
        "adapter_item_count",
        "smoke_row_count",
        "ready_smoke_count",
        "acceptable_smoke_count",
        "paper_order_created",
        "live_order_created",
        "live_trade_supported",
    ]:
        print(f"{key}: {summary[key]}")

    print(f"summary_path: {summary_path}")
    print(f"smoke_rows_path: {smoke_rows_path}")
    print(f"adapter_sample_rows_path: {adapter_sample_rows_path}")
    print(f"md_path: {md_path}")

    print("\n--- Stage 37I adapter item distribution ---")
    print(json.dumps(summary["adapter_item_distribution"], indent=2, default=str))

    print("\n--- Stage 37I module constants ---")
    print(json.dumps(module_constants, indent=2, default=str))

    print("\n--- Stage 37I engine smoke compact ---")
    print("variant\tsource_items\tok\tready\tblocker_count\twarning_count\tcount_fields\tblockers\terror")
    for row in smoke_rows:
        print(
            f"{row['variant']}\t{row['source_item_count']}\t{row['ok']}\t"
            f"{row['is_ready']}\t{row['blocker_count']}\t{row['warning_count']}\t"
            f"{row['item_count_fields']}\t{row['blockers']}\t{row['error']}"
        )

    if blockers:
        print("\n--- Stage 37I blockers ---")
        for blocker in blockers:
            print(blocker)
        raise SystemExit(1)

    if warnings:
        print("\n--- Stage 37I warnings ---")
        for warning in warnings:
            print(warning)


if __name__ == "__main__":
    main()
