from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping


NUMERIC_TEXT_RE = re.compile(r"^\s*[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?%?\s*$")

EVIDENCE_GROUPS = (
    "has_entry_date",
    "has_exit_or_outcome_date",
    "has_realization_date",
    "has_expiration_or_dte",
    "has_holding_period",
    "has_entry_legs",
    "has_exit_legs",
    "has_entry_bid_ask",
    "has_exit_bid_ask",
    "has_exit_mid_or_mark",
    "has_final_return_or_pnl",
    "has_mae",
    "has_mfe",
    "has_mae_and_mfe",
    "has_intermediate_path",
    "has_daily_or_intraperiod_quotes",
    "has_greek_snapshot",
    "has_greek_path",
    "has_behavior_snapshot",
    "has_behavior_path",
)

ENTRY_DATE_TERMS = (
    "entry_date",
    "open_date",
    "trade_date",
    "decision_date",
    "quote_date",
)
EXIT_DATE_TERMS = (
    "exit_date",
    "close_date",
    "outcome_date",
    "target_exit_date",
    "selected_outcome_date",
)
REALIZATION_DATE_TERMS = (
    "portfolio_realization_date",
    "outcome_availability_date",
    "selected_outcome_availability_date",
)
EXPIRATION_DTE_TERMS = (
    "expiration",
    "expiry",
    "dte",
    "days_to_expiration",
    "days_until_expiration",
)
HOLDING_TERMS = (
    "holding_period",
    "holding_days",
    "holding_period_days",
    "days_held",
)
ENTRY_LEG_TERMS = (
    "entry_legs",
    "open_legs",
    "selected_legs",
    "source_candidate.entry_legs",
)
EXIT_LEG_TERMS = (
    "exit_legs",
    "close_legs",
    "outcome_legs",
    "source_outcome.exit_legs",
)
FINAL_RETURN_TERMS = (
    "realized_return",
    "strategy_adjusted_return",
    "strategy_return",
    "realized_pnl",
    "realized_pnl_dollars",
    "strategy_pnl",
    "pnl",
)
MAE_TERMS = (
    "mae",
    "max_adverse",
    "maximum_adverse",
    "adverse_excursion",
    "drawdown_within_trade",
)
MFE_TERMS = (
    "mfe",
    "max_favorable",
    "maximum_favorable",
    "favorable_excursion",
    "runup_within_trade",
)
PATH_TERMS = (
    "path",
    "timeline",
    "series",
    "daily",
    "intraday",
    "observation",
    "observations",
    "snapshot",
    "snapshots",
    "quote_history",
    "holding_period_quotes",
    "intermediate_quotes",
    "mark_path",
    "price_path",
    "return_path",
)
QUOTE_PATH_TERMS = (
    "quote_path",
    "quote_history",
    "holding_period_quotes",
    "intermediate_quotes",
    "daily_quotes",
    "intraday_quotes",
)
GREEK_TERMS = (
    "delta",
    "gamma",
    "theta",
    "vega",
    "rho",
    "greek",
    "greeks",
)
BEHAVIOR_TERMS = (
    "regime",
    "asset_behavior",
    "option_behavior",
    "options_behavior",
    "behavior_state",
    "behavior_path",
    "regime_path",
)


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    path = Path(path)
    with path.open("r", encoding="utf-8-sig", errors="ignore") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                value = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"Expected JSON object at {path}:{line_number}")
            payloads.append(value)
    return payloads


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def write_jsonl(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")))
            handle.write("\n")


def _is_present(value: Any) -> bool:
    return value not in (None, "", [], {})


def _is_numeric_like(value: Any) -> bool:
    if value is None or isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return math.isfinite(float(value))
    if isinstance(value, str):
        return bool(NUMERIC_TEXT_RE.match(value))
    return False


def _path_parts(path: str) -> list[str]:
    cleaned = path.replace("[*]", "").replace("[0]", "")
    return [part.lower() for part in cleaned.split(".") if part]


def _path_contains_any(path: str, terms: tuple[str, ...]) -> bool:
    parts = _path_parts(path)
    joined = ".".join(parts)
    snake = "_".join(parts)
    return any(term.lower() in joined or term.lower() in snake for term in terms)


def _path_contains_bid_ask(path: str) -> bool:
    lower = path.lower()
    return ("bid" in lower and "ask" in lower) or "bid_ask" in lower or "bidask" in lower


def flatten_payload(payload: Any, prefix: str = "", *, max_list_items: int = 5) -> list[tuple[str, Any]]:
    output: list[tuple[str, Any]] = []
    if isinstance(payload, dict):
        if prefix:
            output.append((prefix, payload))
        for key, value in payload.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            output.extend(flatten_payload(value, child, max_list_items=max_list_items))
        return output

    if isinstance(payload, list):
        if prefix:
            output.append((prefix, payload))
        for item in payload[:max_list_items]:
            child = f"{prefix}[*]" if prefix else "[*]"
            output.extend(flatten_payload(item, child, max_list_items=max_list_items))
        return output

    if prefix:
        output.append((prefix, payload))
    return output


def _present_paths(row: dict[str, Any]) -> tuple[list[str], list[str], list[tuple[str, Any]]]:
    flattened = flatten_payload(row)
    present = [path for path, value in flattened if _is_present(value)]
    numeric = [path for path, value in flattened if _is_numeric_like(value)]
    return present, numeric, flattened


def detect_exit_policy_evidence(row: dict[str, Any]) -> dict[str, Any]:
    present_paths, numeric_paths, flattened = _present_paths(row)

    entry_date_paths = [path for path in present_paths if _path_contains_any(path, ENTRY_DATE_TERMS)]
    exit_date_paths = [path for path in present_paths if _path_contains_any(path, EXIT_DATE_TERMS)]
    realization_date_paths = [path for path in present_paths if _path_contains_any(path, REALIZATION_DATE_TERMS)]
    expiration_dte_paths = [path for path in present_paths if _path_contains_any(path, EXPIRATION_DTE_TERMS)]
    holding_paths = [path for path in numeric_paths if _path_contains_any(path, HOLDING_TERMS)]
    entry_leg_paths = [path for path in present_paths if _path_contains_any(path, ENTRY_LEG_TERMS)]
    exit_leg_paths = [path for path in present_paths if _path_contains_any(path, EXIT_LEG_TERMS)]
    final_return_paths = [path for path in numeric_paths if _path_contains_any(path, FINAL_RETURN_TERMS)]
    mae_paths = [path for path in numeric_paths if _path_contains_any(path, MAE_TERMS)]
    mfe_paths = [path for path in numeric_paths if _path_contains_any(path, MFE_TERMS)]

    entry_bid_ask_paths = [
        path for path in numeric_paths
        if _path_contains_any(path, ("entry", "open", "selected_legs", "source_candidate", "entry_legs"))
        and ("bid" in path.lower() or "ask" in path.lower() or _path_contains_bid_ask(path))
    ]
    exit_bid_ask_paths = [
        path for path in numeric_paths
        if _path_contains_any(path, ("exit", "close", "outcome", "exit_legs", "source_outcome"))
        and ("bid" in path.lower() or "ask" in path.lower() or _path_contains_bid_ask(path))
    ]
    exit_mid_mark_paths = [
        path for path in numeric_paths
        if _path_contains_any(path, ("exit", "close", "outcome", "exit_legs", "source_outcome"))
        and _path_contains_any(path, ("mid", "mark"))
    ]

    path_paths = [path for path in present_paths if _path_contains_any(path, PATH_TERMS)]
    quote_path_paths = [path for path in present_paths if _path_contains_any(path, QUOTE_PATH_TERMS)]
    greek_snapshot_paths = [path for path in numeric_paths if _path_contains_any(path, GREEK_TERMS)]
    greek_path_paths = [
        path for path in present_paths
        if _path_contains_any(path, PATH_TERMS) and _path_contains_any(path, GREEK_TERMS)
    ]
    behavior_snapshot_paths = [path for path in present_paths if _path_contains_any(path, BEHAVIOR_TERMS)]
    behavior_path_paths = [
        path for path in present_paths
        if _path_contains_any(path, PATH_TERMS) and _path_contains_any(path, BEHAVIOR_TERMS)
    ]

    # Treat explicit MAE/MFE as a path-derived proxy, but keep it separate from true quote-path evidence.
    has_mae = bool(mae_paths)
    has_mfe = bool(mfe_paths)

    return {
        "has_entry_date": bool(entry_date_paths),
        "has_exit_or_outcome_date": bool(exit_date_paths),
        "has_realization_date": bool(realization_date_paths),
        "has_expiration_or_dte": bool(expiration_dte_paths),
        "has_holding_period": bool(holding_paths),
        "has_entry_legs": bool(entry_leg_paths),
        "has_exit_legs": bool(exit_leg_paths),
        "has_entry_bid_ask": bool(entry_bid_ask_paths),
        "has_exit_bid_ask": bool(exit_bid_ask_paths),
        "has_exit_mid_or_mark": bool(exit_mid_mark_paths),
        "has_final_return_or_pnl": bool(final_return_paths),
        "has_mae": has_mae,
        "has_mfe": has_mfe,
        "has_mae_and_mfe": has_mae and has_mfe,
        "has_intermediate_path": bool(path_paths),
        "has_daily_or_intraperiod_quotes": bool(quote_path_paths),
        "has_greek_snapshot": bool(greek_snapshot_paths),
        "has_greek_path": bool(greek_path_paths),
        "has_behavior_snapshot": bool(behavior_snapshot_paths),
        "has_behavior_path": bool(behavior_path_paths),
        "evidence_paths": {
            "entry_date": sorted(set(entry_date_paths))[:25],
            "exit_or_outcome_date": sorted(set(exit_date_paths))[:25],
            "realization_date": sorted(set(realization_date_paths))[:25],
            "expiration_or_dte": sorted(set(expiration_dte_paths))[:25],
            "holding_period": sorted(set(holding_paths))[:25],
            "entry_legs": sorted(set(entry_leg_paths))[:25],
            "exit_legs": sorted(set(exit_leg_paths))[:25],
            "entry_bid_ask": sorted(set(entry_bid_ask_paths))[:25],
            "exit_bid_ask": sorted(set(exit_bid_ask_paths))[:25],
            "exit_mid_or_mark": sorted(set(exit_mid_mark_paths))[:25],
            "final_return_or_pnl": sorted(set(final_return_paths))[:25],
            "mae": sorted(set(mae_paths))[:25],
            "mfe": sorted(set(mfe_paths))[:25],
            "intermediate_path": sorted(set(path_paths))[:25],
            "daily_or_intraperiod_quotes": sorted(set(quote_path_paths))[:25],
            "greek_snapshot": sorted(set(greek_snapshot_paths))[:25],
            "greek_path": sorted(set(greek_path_paths))[:25],
            "behavior_snapshot": sorted(set(behavior_snapshot_paths))[:25],
            "behavior_path": sorted(set(behavior_path_paths))[:25],
        },
        "present_field_count": len(set(present_paths)),
        "numeric_field_count": len(set(numeric_paths)),
        "sample_present_paths": sorted(set(present_paths))[:75],
    }


def _scope_rows(rows: list[dict[str, Any]], *, selected_only: bool, sized_only: bool, complete_only: bool) -> list[dict[str, Any]]:
    scoped = rows
    if selected_only:
        scoped = [
            row for row in scoped
            if row.get("selection_state") == "selected"
            or row.get("is_selected_trade") is True
            or row.get("selected_strategy")
        ]
    if sized_only:
        scoped = [row for row in scoped if row.get("sizing_state") == "sized"]
    if complete_only:
        scoped = [
            row for row in scoped
            if row.get("data_state") in (None, "complete")
            and row.get("outcome_state") in (None, "complete")
        ]
    return scoped


def summarize_artifact(
    *,
    artifact_name: str,
    path: str | Path,
    rows: list[dict[str, Any]],
    selected_only: bool = False,
    sized_only: bool = False,
    complete_only: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, int]]:
    scoped_rows = _scope_rows(rows, selected_only=selected_only, sized_only=sized_only, complete_only=complete_only)
    coverage_counts: Counter[str] = Counter()
    field_catalog: Counter[str] = Counter()
    numeric_catalog: Counter[str] = Counter()
    detail_rows: list[dict[str, Any]] = []

    for index, row in enumerate(scoped_rows):
        evidence = detect_exit_policy_evidence(row)
        for group in EVIDENCE_GROUPS:
            if evidence[group]:
                coverage_counts[group] += 1
        for field_path, value in flatten_payload(row):
            if _is_present(value):
                field_catalog[field_path] += 1
            if _is_numeric_like(value):
                numeric_catalog[field_path] += 1

        needs_detail = not (
            evidence["has_entry_date"]
            and evidence["has_exit_or_outcome_date"]
            and evidence["has_final_return_or_pnl"]
        )
        if index < 100 or needs_detail:
            detail_rows.append(
                {
                    "artifact_name": artifact_name,
                    "row_index": index,
                    "symbol": row.get("symbol") or row.get("underlying"),
                    "strategy": row.get("selected_strategy") or row.get("strategy"),
                    "decision_date": row.get("decision_date"),
                    "outcome_date": row.get("selected_outcome_date") or row.get("outcome_date"),
                    "portfolio_realization_date": row.get("portfolio_realization_date"),
                    **{group: evidence[group] for group in EVIDENCE_GROUPS},
                    "evidence_paths": evidence["evidence_paths"],
                }
            )

    row_count = len(scoped_rows)
    coverage_pct = {
        group: (coverage_counts[group] / row_count if row_count else None)
        for group in EVIDENCE_GROUPS
    }
    summary = {
        "artifact_name": artifact_name,
        "path": str(path),
        "raw_row_count": len(rows),
        "scoped_row_count": row_count,
        "selected_only": selected_only,
        "sized_only": sized_only,
        "complete_only": complete_only,
        "coverage_counts": dict(sorted(coverage_counts.items())),
        "coverage_pct": coverage_pct,
        "field_catalog_top": dict(field_catalog.most_common(120)),
        "numeric_field_catalog_top": dict(numeric_catalog.most_common(120)),
        "best_evidence_paths": {
            group: sorted(
                {
                    path
                    for detail in detail_rows
                    for path in detail.get("evidence_paths", {}).get(group.replace("has_", ""), [])
                }
            )[:30]
            for group in EVIDENCE_GROUPS
        },
    }
    return summary, detail_rows, dict(field_catalog)


def _max_coverage(by_name: dict[str, dict[str, Any]], artifact_names: Iterable[str], key: str) -> float | None:
    values = []
    for name in artifact_names:
        value = by_name.get(name, {}).get("coverage_pct", {}).get(key)
        if value is not None:
            values.append(value)
    return max(values, default=None)


def _coverage(by_name: dict[str, dict[str, Any]], name: str, key: str) -> float | None:
    return by_name.get(name, {}).get("coverage_pct", {}).get(key)


def build_portfolio_exit_policy_source_audit(
    *,
    output_dir: str | Path,
    leg_selection_rows_path: str | Path | None = None,
    quote_outcome_rows_path: str | Path | None = None,
    strategy_selection_rows_path: str | Path | None = None,
    selected_strategy_outcome_rows_path: str | Path | None = None,
    portfolio_selected_trade_sequence_rows_path: str | Path | None = None,
    position_sizing_rows_path: str | Path | None = None,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    summary_path = output_path / "signalforge_portfolio_exit_policy_source_audit_summary.json"
    details_path = output_path / "signalforge_portfolio_exit_policy_source_audit_rows.jsonl"
    catalog_path = output_path / "signalforge_portfolio_exit_policy_source_audit_field_catalog.json"

    inputs = [
        ("leg_selection_rows", leg_selection_rows_path, False, False, False),
        ("quote_outcome_rows", quote_outcome_rows_path, False, False, True),
        ("strategy_selection_rows", strategy_selection_rows_path, True, False, False),
        ("selected_strategy_outcome_rows", selected_strategy_outcome_rows_path, True, False, False),
        ("portfolio_selected_trade_sequence_rows", portfolio_selected_trade_sequence_rows_path, False, False, False),
        ("position_sizing_rows", position_sizing_rows_path, False, True, False),
    ]

    artifact_summaries: list[dict[str, Any]] = []
    detail_rows: list[dict[str, Any]] = []
    global_field_catalog: dict[str, dict[str, int]] = {}
    missing_inputs: list[str] = []
    unreadable_inputs: list[dict[str, str]] = []

    for artifact_name, path, selected_only, sized_only, complete_only in inputs:
        if path is None:
            missing_inputs.append(artifact_name)
            continue
        try:
            rows = read_jsonl(path)
        except Exception as exc:
            unreadable_inputs.append({"artifact_name": artifact_name, "path": str(path), "error": str(exc)})
            continue
        artifact_summary, artifact_details, field_catalog = summarize_artifact(
            artifact_name=artifact_name,
            path=path,
            rows=rows,
            selected_only=selected_only,
            sized_only=sized_only,
            complete_only=complete_only,
        )
        artifact_summaries.append(artifact_summary)
        detail_rows.extend(artifact_details)
        global_field_catalog[artifact_name] = field_catalog

    by_name = {summary["artifact_name"]: summary for summary in artifact_summaries}
    upstream_names = ["leg_selection_rows", "quote_outcome_rows", "strategy_selection_rows"]
    portfolio_names = ["selected_strategy_outcome_rows", "portfolio_selected_trade_sequence_rows", "position_sizing_rows"]

    portfolio_final_return = _coverage(by_name, "position_sizing_rows", "has_final_return_or_pnl")
    portfolio_entry_date = _coverage(by_name, "position_sizing_rows", "has_entry_date")
    portfolio_exit_date = _coverage(by_name, "position_sizing_rows", "has_exit_or_outcome_date")
    portfolio_realization_date = _coverage(by_name, "position_sizing_rows", "has_realization_date")
    portfolio_exit_legs = _coverage(by_name, "position_sizing_rows", "has_exit_legs")
    portfolio_exit_bid_ask = _coverage(by_name, "position_sizing_rows", "has_exit_bid_ask")
    portfolio_mae_mfe = _coverage(by_name, "position_sizing_rows", "has_mae_and_mfe")
    portfolio_path = _coverage(by_name, "position_sizing_rows", "has_intermediate_path")
    portfolio_quote_path = _coverage(by_name, "position_sizing_rows", "has_daily_or_intraperiod_quotes")
    portfolio_dte = _coverage(by_name, "position_sizing_rows", "has_expiration_or_dte")
    portfolio_holding = _coverage(by_name, "position_sizing_rows", "has_holding_period")
    portfolio_greek_path = _coverage(by_name, "position_sizing_rows", "has_greek_path")
    portfolio_behavior_path = _coverage(by_name, "position_sizing_rows", "has_behavior_path")

    upstream_exit_legs = _max_coverage(by_name, upstream_names, "has_exit_legs")
    upstream_exit_bid_ask = _max_coverage(by_name, upstream_names, "has_exit_bid_ask")
    upstream_mae_mfe = _max_coverage(by_name, upstream_names, "has_mae_and_mfe")
    upstream_path = _max_coverage(by_name, upstream_names, "has_intermediate_path")
    upstream_quote_path = _max_coverage(by_name, upstream_names, "has_daily_or_intraperiod_quotes")
    upstream_dte = _max_coverage(by_name, upstream_names, "has_expiration_or_dte")

    blockers: list[str] = []
    warnings: list[str] = []

    if unreadable_inputs:
        blockers.append("one_or_more_inputs_unreadable")

    if portfolio_final_return is not None and portfolio_final_return < 0.95:
        warnings.append("portfolio_ledger_missing_final_return_or_pnl")
    if portfolio_entry_date is not None and portfolio_entry_date < 0.95:
        warnings.append("portfolio_ledger_missing_entry_date")
    if portfolio_exit_date is not None and portfolio_exit_date < 0.95 and portfolio_realization_date is not None and portfolio_realization_date < 0.95:
        warnings.append("portfolio_ledger_missing_exit_or_realization_date")
    if portfolio_exit_bid_ask is not None and portfolio_exit_bid_ask < 0.95:
        warnings.append("portfolio_ledger_missing_exit_bid_ask_coverage")
    if portfolio_mae_mfe is not None and portfolio_mae_mfe < 0.95:
        warnings.append("portfolio_ledger_missing_mae_mfe_coverage")
    if portfolio_quote_path is not None and portfolio_quote_path < 0.95:
        warnings.append("portfolio_ledger_missing_daily_or_intraperiod_quote_path")
    if portfolio_dte is not None and portfolio_dte < 0.95:
        warnings.append("portfolio_ledger_missing_expiration_or_dte")

    if upstream_exit_bid_ask is not None and portfolio_exit_bid_ask is not None and upstream_exit_bid_ask >= 0.95 and portfolio_exit_bid_ask < 0.95:
        warnings.append("exit_bid_ask_exists_upstream_but_not_portfolio_ledger")
    if upstream_exit_legs is not None and portfolio_exit_legs is not None and upstream_exit_legs >= 0.95 and portfolio_exit_legs < 0.95:
        warnings.append("exit_legs_exist_upstream_but_not_portfolio_ledger")
    if upstream_mae_mfe is not None and portfolio_mae_mfe is not None and upstream_mae_mfe >= 0.95 and portfolio_mae_mfe < 0.95:
        warnings.append("mae_mfe_exists_upstream_but_not_portfolio_ledger")
    if upstream_quote_path is not None and portfolio_quote_path is not None and upstream_quote_path >= 0.95 and portfolio_quote_path < 0.95:
        warnings.append("quote_path_exists_upstream_but_not_portfolio_ledger")

    can_test_final_outcome_exits = bool(portfolio_final_return is not None and portfolio_final_return >= 0.95)
    can_test_fixed_horizon_exits = bool(
        can_test_final_outcome_exits
        and ((portfolio_exit_date is not None and portfolio_exit_date >= 0.95) or (portfolio_realization_date is not None and portfolio_realization_date >= 0.95))
    )
    can_test_dte_exits = bool(can_test_final_outcome_exits and portfolio_dte is not None and portfolio_dte >= 0.95)
    can_test_quote_native_exit_cost = bool(portfolio_exit_bid_ask is not None and portfolio_exit_bid_ask >= 0.95)
    can_test_mae_mfe_profit_stop_approx = bool(portfolio_mae_mfe is not None and portfolio_mae_mfe >= 0.95)
    can_test_true_path_dependent_exits = bool(portfolio_quote_path is not None and portfolio_quote_path >= 0.95)
    can_test_greek_triggered_exits = bool(portfolio_greek_path is not None and portfolio_greek_path >= 0.95)
    can_test_behavior_triggered_exits = bool(portfolio_behavior_path is not None and portfolio_behavior_path >= 0.95)

    if blockers:
        readiness_state = "blocked"
    elif can_test_true_path_dependent_exits:
        readiness_state = "path_ready"
    elif can_test_mae_mfe_profit_stop_approx:
        readiness_state = "mae_mfe_ready"
    elif can_test_final_outcome_exits:
        readiness_state = "final_outcome_only"
    else:
        readiness_state = "needs_enrichment"

    recommendations: list[str] = []
    if readiness_state == "path_ready":
        recommendations.append("Exit-policy source coverage is sufficient for true path-dependent exit sensitivity using available quote paths.")
    elif readiness_state == "mae_mfe_ready":
        recommendations.append("Use MAE/MFE-based profit-target and loss-stop approximation first; do not claim true path-dependent exit simulation without daily quote path rows.")
    elif readiness_state == "final_outcome_only":
        recommendations.append("Only final-outcome exit approximations are currently supported. Build MAE/MFE or daily holding-period quote paths before optimizing profit targets, stop losses, DTE exits, or defensive exits.")
    else:
        recommendations.append("Patch upstream outcome generation and/or Phase 5/6 handoff to carry entry dates, exit/outcome dates, realized return/PnL, exit legs, and MAE/MFE or quote-path observations.")

    if upstream_exit_bid_ask is not None and upstream_exit_bid_ask >= 0.95 and (portfolio_exit_bid_ask or 0.0) < 0.95:
        recommendations.append("Patch the Phase 5/6 handoff to carry exit bid/ask/mid fields into the final portfolio ledger.")
    if upstream_dte is not None and upstream_dte >= 0.95 and (portfolio_dte or 0.0) < 0.95:
        recommendations.append("Patch the Phase 5/6 handoff to carry expiration/DTE fields into the final portfolio ledger.")
    if not can_test_true_path_dependent_exits:
        recommendations.append("Do not run real profit-target, stop-loss, delta/theta/vega, or regime-flip exit optimization until path evidence is available; otherwise label scenarios as approximations.")

    summary = {
        "adapter_type": "portfolio_exit_policy_source_audit_builder",
        "artifact_type": "signalforge_portfolio_exit_policy_source_audit",
        "contract": "portfolio_exit_policy_source_audit",
        "is_ready": readiness_state != "blocked",
        "readiness_state": readiness_state,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,
        "missing_optional_inputs": missing_inputs,
        "unreadable_inputs": unreadable_inputs,
        "artifact_summaries": artifact_summaries,
        "exit_policy_capabilities": {
            "can_test_final_outcome_exit_approximations": can_test_final_outcome_exits,
            "can_test_fixed_horizon_or_close_on_outcome_date": can_test_fixed_horizon_exits,
            "can_test_dte_exit_rules": can_test_dte_exits,
            "can_test_quote_native_exit_costs": can_test_quote_native_exit_cost,
            "can_test_mae_mfe_profit_target_loss_stop_approximations": can_test_mae_mfe_profit_stop_approx,
            "can_test_true_path_dependent_exits": can_test_true_path_dependent_exits,
            "can_test_greek_triggered_exits": can_test_greek_triggered_exits,
            "can_test_behavior_triggered_exits": can_test_behavior_triggered_exits,
        },
        "handoff_coverage": {
            "position_sizing_final_return_or_pnl_coverage": portfolio_final_return,
            "position_sizing_entry_date_coverage": portfolio_entry_date,
            "position_sizing_exit_or_outcome_date_coverage": portfolio_exit_date,
            "position_sizing_realization_date_coverage": portfolio_realization_date,
            "position_sizing_expiration_or_dte_coverage": portfolio_dte,
            "position_sizing_holding_period_coverage": portfolio_holding,
            "position_sizing_exit_leg_coverage": portfolio_exit_legs,
            "position_sizing_exit_bid_ask_coverage": portfolio_exit_bid_ask,
            "position_sizing_mae_mfe_coverage": portfolio_mae_mfe,
            "position_sizing_intermediate_path_coverage": portfolio_path,
            "position_sizing_quote_path_coverage": portfolio_quote_path,
            "position_sizing_greek_path_coverage": portfolio_greek_path,
            "position_sizing_behavior_path_coverage": portfolio_behavior_path,
            "upstream_best_exit_leg_coverage": upstream_exit_legs,
            "upstream_best_exit_bid_ask_coverage": upstream_exit_bid_ask,
            "upstream_best_mae_mfe_coverage": upstream_mae_mfe,
            "upstream_best_intermediate_path_coverage": upstream_path,
            "upstream_best_quote_path_coverage": upstream_quote_path,
            "upstream_best_expiration_or_dte_coverage": upstream_dte,
        },
        "next_build_recommendations": recommendations,
        "paths": {
            "summary_path": str(summary_path),
            "details_path": str(details_path),
            "field_catalog_path": str(catalog_path),
        },
        "explicit_exclusions": [
            "exit_rule_optimization",
            "defensive_adjustment_simulation",
            "broker_order_routing",
            "live_execution",
            "strategy_reselection",
            "expectancy_rebuild",
            "portfolio_reconstruction",
        ],
    }

    write_json(summary_path, summary)
    write_jsonl(details_path, detail_rows)
    write_json(catalog_path, global_field_catalog)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit whether SignalForge artifacts contain enough source data for exit-policy sensitivity."
    )
    parser.add_argument("--leg-selection-rows", default=None)
    parser.add_argument("--quote-outcome-rows", default=None)
    parser.add_argument("--strategy-selection-rows", default=None)
    parser.add_argument("--selected-strategy-outcome-rows", default=None)
    parser.add_argument("--portfolio-selected-trade-sequence-rows", default=None)
    parser.add_argument("--position-sizing-rows", default=None)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--fail-on-blocker", action="store_true")
    args = parser.parse_args()

    summary = build_portfolio_exit_policy_source_audit(
        output_dir=args.output_dir,
        leg_selection_rows_path=args.leg_selection_rows,
        quote_outcome_rows_path=args.quote_outcome_rows,
        strategy_selection_rows_path=args.strategy_selection_rows,
        selected_strategy_outcome_rows_path=args.selected_strategy_outcome_rows,
        portfolio_selected_trade_sequence_rows_path=args.portfolio_selected_trade_sequence_rows,
        position_sizing_rows_path=args.position_sizing_rows,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    if args.fail_on_blocker and summary.get("blocker_count", 0) > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
