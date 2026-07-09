import ast
import importlib
import json
from pathlib import Path
from typing import Any, Dict, List


OUT_DIR = Path("docs/expected_value_engine")

ENGINE_PATH = Path("src/signalforge/engines/strategy_selection/expected_value_scoring.py")
ENGINE_MODULE = "signalforge.engines.strategy_selection.expected_value_scoring"
ENGINE_ENTRYPOINT = "build_signalforge_expected_value_scoring"

CANONICAL_ROWS_PATH = Path(
    "data/canonical/signalforge_pipeline/18_walk_forward_expectancy/"
    "signalforge_walk_forward_expectancy_rows.jsonl"
)

SAMPLE_LIMIT = 50


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def read_jsonl(path: Path, limit: int) -> list[dict[str, Any]]:
    rows = []

    with path.open("r", encoding="utf-8-sig") as f:
        for line in f:
            text = line.strip()
            if not text:
                continue

            value = json.loads(text)

            if isinstance(value, dict):
                rows.append(value)

            if len(rows) >= limit:
                break

    return rows


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


def canonical_row_to_engine_item(row: dict[str, Any]) -> dict[str, Any]:
    strategy = (
        clean_text(row.get("strategy_name"))
        or clean_text(row.get("strategy"))
        or clean_text(row.get("candidate_strategy"))
        or clean_text(row.get("strategy_family"))
    )

    symbol = clean_text(row.get("symbol"))
    state = clean_text(row.get("expectancy_state")).lower()
    sample_count = as_int(row.get("expectancy_sample_count")) or 0
    minimum_sample_count = as_int(row.get("expectancy_minimum_sample_count")) or 0
    avg_return = as_float(row.get("expectancy_average_return"))
    win_rate = as_float(row.get("expectancy_win_rate"))

    if state in {"no_prior_sample", "missing", "missing_expectancy", "unavailable"} or sample_count <= 0:
        coverage_status = "missing_expectancy"
        expected_value_state = "data_review"
        handoff_status = "data_review"
        blocked_reasons = ["missing_or_no_prior_expectancy_sample"]
        favored_families = []
        allowed_families = []
        blocked_families = []

    elif minimum_sample_count > 0 and sample_count < minimum_sample_count:
        coverage_status = "sample_limited"
        expected_value_state = "sample_limited"
        handoff_status = "review"
        blocked_reasons = ["sample_limited_expectancy"]
        favored_families = []
        allowed_families = [strategy] if strategy else []
        blocked_families = []

    elif (avg_return is not None and avg_return > 0) or (win_rate is not None and win_rate > 0.5):
        coverage_status = "covered"
        expected_value_state = "positive_expectancy_candidate"
        handoff_status = "candidate"
        blocked_reasons = []
        favored_families = [strategy] if strategy else []
        allowed_families = [strategy] if strategy else []
        blocked_families = []

    else:
        coverage_status = "covered"
        expected_value_state = "non_positive_expectancy"
        handoff_status = "blocked"
        blocked_reasons = ["non_positive_expectancy"]
        favored_families = []
        allowed_families = []
        blocked_families = [strategy] if strategy else []

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

        "coverage_status": coverage_status,
        "expected_value_state": expected_value_state,
        "expected_value_handoff_status": handoff_status,
        "handoff_status": handoff_status,

        "favored_families": favored_families,
        "allowed_families": allowed_families,
        "blocked_families": blocked_families,

        "risk_flags": [],
        "constraint_flags": blocked_reasons,
        "blocked_reasons": blocked_reasons,

        "premium_bias": row.get("premium_bias"),
        "expectancy_state": row.get("expectancy_state"),
        "expectancy_scope": row.get("expectancy_scope"),
        "expectancy_sample_count": sample_count,
        "expectancy_minimum_sample_count": minimum_sample_count,
        "expectancy_average_return": avg_return,
        "expectancy_median_return": as_float(row.get("expectancy_median_return")),
        "expectancy_win_rate": win_rate,

        "uses_current_row_outcome": row.get("uses_current_row_outcome"),
        "uses_future_rows": row.get("uses_future_rows"),
        "training_window_start": row.get("training_window_start"),
        "training_window_end": row.get("training_window_end"),
    }


def source_for_node(lines: list[str], node: ast.AST) -> str:
    start = getattr(node, "lineno", 1)
    end = getattr(node, "end_lineno", start)
    return "\n".join(lines[start - 1:end])


def top_level_functions(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    }


def top_level_assignments(tree: ast.Module, lines: list[str]) -> dict[str, str]:
    assignments = {}

    for node in tree.body:
        names = []

        if isinstance(node, ast.Assign):
            for target in node.targets:
                for child in ast.walk(target):
                    if isinstance(child, ast.Name):
                        names.append(child.id)

        elif isinstance(node, ast.AnnAssign):
            for child in ast.walk(node.target):
                if isinstance(child, ast.Name):
                    names.append(child.id)

        for name in names:
            assignments[name] = source_for_node(lines, node)

    return assignments


def function_source_rows() -> list[dict[str, Any]]:
    text = read_text(ENGINE_PATH)
    lines = text.splitlines()
    tree = ast.parse(text)
    functions = top_level_functions(tree)

    target_names = [
        "build_signalforge_expected_value_scoring",
        "_extract_items",
        "_looks_like_items",
        "_build_ev_item",
        "_item_ev_state",
        "_candidate_ev_state",
        "_candidate_handoff_status",
        "_blocked_result",
    ]

    rows = []

    for name in target_names:
        node = functions.get(name)
        if node is None:
            rows.append({
                "function": name,
                "exists": False,
                "lineno": None,
                "end_lineno": None,
                "source": None,
            })
            continue

        rows.append({
            "function": name,
            "exists": True,
            "lineno": node.lineno,
            "end_lineno": getattr(node, "end_lineno", node.lineno),
            "source": source_for_node(lines, node),
        })

    return rows


def assignment_rows() -> list[dict[str, Any]]:
    text = read_text(ENGINE_PATH)
    lines = text.splitlines()
    tree = ast.parse(text)
    assignments = top_level_assignments(tree, lines)

    wanted = [
        "ELIGIBILITY_ITEM_KEYS",
        "EXPECTED_VALUE_SCORING_SCHEMA_VERSION",
        "FAMILY_ORDER",
        "NON_EV_FAMILIES",
        "BASE_SCORE_ALLOWED",
        "BASE_SCORE_FAVORED",
        "BLOCKED_HANDOFF",
        "DATA_REVIEW_HANDOFF",
        "EV_CONSTRAINED_HANDOFF",
    ]

    rows = []

    for name in wanted:
        rows.append({
            "name": name,
            "exists": name in assignments,
            "source": assignments.get(name),
        })

    return rows


def summarize_result(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {
            "result_type": type(result).__name__,
            "result_keys": None,
            "top_level": None,
            "nested_counts": {},
            "sample_items": [],
        }

    nested_counts = {}
    sample_items = []

    for key, value in result.items():
        if isinstance(value, list):
            nested_counts[key] = len(value)
            if value and isinstance(value[0], dict):
                sample_items.append({
                    "key": key,
                    "sample": value[0],
                })

        elif isinstance(value, dict):
            for nested_key, nested_value in value.items():
                if isinstance(nested_value, list):
                    nested_counts[f"{key}.{nested_key}"] = len(nested_value)

    top_level = {
        key: value
        for key, value in result.items()
        if not isinstance(value, (list, dict))
    }

    return {
        "result_type": type(result).__name__,
        "result_keys": sorted(result.keys()),
        "top_level": top_level,
        "nested_counts": nested_counts,
        "sample_items": sample_items[:5],
    }


def run_variant(name: str, source: Any) -> dict[str, Any]:
    module = importlib.import_module(ENGINE_MODULE)
    func = getattr(module, ENGINE_ENTRYPOINT)

    try:
        result = func(source)
        compact = summarize_result(result)

        return {
            "variant": name,
            "ok": True,
            "error_type": None,
            "error": None,
            **compact,
        }

    except Exception as exc:
        return {
            "variant": name,
            "ok": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "result_type": None,
            "result_keys": None,
            "top_level": None,
            "nested_counts": {},
            "sample_items": [],
        }


def main() -> None:
    blockers: List[str] = []
    warnings: List[str] = []

    if not ENGINE_PATH.exists():
        blockers.append(f"missing_engine_path_{ENGINE_PATH}")

    if not CANONICAL_ROWS_PATH.exists():
        blockers.append(f"missing_canonical_rows_path_{CANONICAL_ROWS_PATH}")

    source_rows = function_source_rows() if ENGINE_PATH.exists() else []
    constants_rows = assignment_rows() if ENGINE_PATH.exists() else []

    canonical_rows = read_jsonl(CANONICAL_ROWS_PATH, SAMPLE_LIMIT) if CANONICAL_ROWS_PATH.exists() else []
    adapter_items = [canonical_row_to_engine_item(row) for row in canonical_rows]

    result_rows = []

    if not blockers:
        variants = {
            "raw_canonical_rows_list": canonical_rows,
            "raw_canonical_rows_wrapped_rows": {"rows": canonical_rows},
            "adapter_items_list": adapter_items,
            "adapter_items_wrapped_items": {"items": adapter_items},
            "adapter_items_wrapped_eligibility_items": {"eligibility_items": adapter_items},
            "adapter_items_wrapped_strategy_family_eligibility_items": {"strategy_family_eligibility_items": adapter_items},
        }

        for name, source in variants.items():
            result_rows.append(run_variant(name, source))

    ready_like_rows = [
        row for row in result_rows
        if row["ok"]
        and isinstance(row.get("top_level"), dict)
        and row["top_level"].get("is_ready") is True
    ]

    produced_item_rows = [
        row for row in result_rows
        if row["ok"]
        and row.get("nested_counts")
    ]

    if not ready_like_rows:
        warnings.append("engine_result_has_no_is_ready_true_variant")

    if not produced_item_rows:
        warnings.append("engine_result_has_no_obvious_list_output_counts")

    warnings.append("stage37j_is_read_only_no_logic_moved")
    warnings.append("inspect_output_shape_before_adapter_promotion")
    warnings.append("canonical_expectancy_snapshot_remains_source_of_truth")

    summary = {
        "adapter_type": "expected_value_scoring_readiness_contract_inspection_builder",
        "artifact_type": "signalforge_expected_value_scoring_readiness_contract_inspection",
        "contract": "expected_value_scoring_readiness_contract_inspection",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,
        "engine_path": str(ENGINE_PATH),
        "engine_module": ENGINE_MODULE,
        "engine_entrypoint": ENGINE_ENTRYPOINT,
        "canonical_rows_path": str(CANONICAL_ROWS_PATH),
        "sample_limit": SAMPLE_LIMIT,
        "source_function_count": len(source_rows),
        "constant_count": len(constants_rows),
        "variant_result_count": len(result_rows),
        "ready_like_variant_count": len(ready_like_rows),
        "produced_item_variant_count": len(produced_item_rows),
        "paper_order_created": False,
        "live_order_created": False,
        "live_trade_supported": False,
        "next_step": "stage37k_define_exact_canonical_expectancy_adapter_contract",
    }

    summary_path = OUT_DIR / "signalforge_stage37j_expected_value_scoring_readiness_contract_summary.json"
    source_rows_path = OUT_DIR / "signalforge_stage37j_expected_value_scoring_readiness_contract_source_rows.jsonl"
    constants_rows_path = OUT_DIR / "signalforge_stage37j_expected_value_scoring_readiness_contract_constants_rows.jsonl"
    result_rows_path = OUT_DIR / "signalforge_stage37j_expected_value_scoring_readiness_contract_result_rows.jsonl"
    md_path = OUT_DIR / "signalforge_stage37j_expected_value_scoring_readiness_contract.md"

    summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    with source_rows_path.open("w", encoding="utf-8") as f:
        for row in source_rows:
            f.write(json.dumps(row, default=str) + "\n")

    with constants_rows_path.open("w", encoding="utf-8") as f:
        for row in constants_rows:
            f.write(json.dumps(row, default=str) + "\n")

    with result_rows_path.open("w", encoding="utf-8") as f:
        for row in result_rows:
            f.write(json.dumps(row, default=str) + "\n")

    md = [
        "# Stage 37J Expected-Value Scoring Readiness Contract Inspection",
        "",
        f"- is_ready: {summary['is_ready']}",
        f"- blocker_count: {summary['blocker_count']}",
        f"- variant_result_count: {summary['variant_result_count']}",
        f"- ready_like_variant_count: {summary['ready_like_variant_count']}",
        f"- produced_item_variant_count: {summary['produced_item_variant_count']}",
        f"- paper_order_created: {summary['paper_order_created']}",
        f"- live_order_created: {summary['live_order_created']}",
        f"- live_trade_supported: {summary['live_trade_supported']}",
        "",
        "## Variant Results",
        "",
        "| variant | ok | top level | nested counts | result keys | error |",
        "|---|---:|---|---|---|---|",
    ]

    for row in result_rows:
        md.append(
            f"| {row['variant']} | {row['ok']} | {row['top_level']} | "
            f"{row['nested_counts']} | {row['result_keys']} | {row['error']} |"
        )

    md.extend(["", "## Constants", ""])

    for row in constants_rows:
        md.extend([
            f"### `{row['name']}`",
            "",
            "```python",
            row["source"] or "",
            "```",
            "",
        ])

    md.extend(["", "## Source Slices", ""])

    for row in source_rows:
        md.extend([
            f"### `{row['function']}`",
            "",
            f"- exists: {row['exists']}",
            f"- lines: {row['lineno']}-{row['end_lineno']}",
            "",
            "```python",
            row["source"] or "",
            "```",
            "",
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

    print("\n--- Stage 37J expected-value scoring readiness contract compact ---")
    for key in [
        "is_ready",
        "blocker_count",
        "warning_count",
        "source_function_count",
        "constant_count",
        "variant_result_count",
        "ready_like_variant_count",
        "produced_item_variant_count",
        "paper_order_created",
        "live_order_created",
        "live_trade_supported",
    ]:
        print(f"{key}: {summary[key]}")

    print(f"summary_path: {summary_path}")
    print(f"source_rows_path: {source_rows_path}")
    print(f"constants_rows_path: {constants_rows_path}")
    print(f"result_rows_path: {result_rows_path}")
    print(f"md_path: {md_path}")

    print("\n--- Stage 37J result rows compact ---")
    print("variant\tok\ttop_level\tnested_counts\tresult_keys\terror")
    for row in result_rows:
        print(
            f"{row['variant']}\t{row['ok']}\t"
            f"{json.dumps(row['top_level'], default=str)}\t"
            f"{json.dumps(row['nested_counts'], default=str)}\t"
            f"{json.dumps(row['result_keys'], default=str)}\t"
            f"{row['error']}"
        )

    print("\n--- Stage 37J constants compact ---")
    print("name\texists")
    for row in constants_rows:
        print(f"{row['name']}\t{row['exists']}")

    if blockers:
        print("\n--- Stage 37J blockers ---")
        for blocker in blockers:
            print(blocker)
        raise SystemExit(1)

    if warnings:
        print("\n--- Stage 37J warnings ---")
        for warning in warnings:
            print(warning)


if __name__ == "__main__":
    main()
