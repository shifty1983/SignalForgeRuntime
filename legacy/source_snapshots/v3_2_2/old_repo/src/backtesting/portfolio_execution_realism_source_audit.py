
from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping


NUMERIC_TEXT_RE = re.compile(r"^\s*[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?%?\s*$")

FIELD_GROUPS: dict[str, tuple[str, ...]] = {
    "bid_fields": ("bid",),
    "ask_fields": ("ask",),
    "mid_fields": ("mid", "mark"),
    "spread_fields": ("spread", "bid_ask", "bidask"),
    "entry_price_fields": ("entry", "open_price", "open", "entry_price", "entry_value"),
    "exit_price_fields": ("exit", "close_price", "close", "exit_price", "exit_value"),
    "leg_payload_fields": ("leg", "legs", "selected_legs", "entry_legs", "exit_legs", "option_legs"),
    "contract_count_fields": ("contract_count", "contracts", "quantity", "qty", "contract_quantity"),
    "option_symbol_fields": ("option_symbol", "contract_symbol", "occ_symbol", "option_contract"),
    "liquidity_fields": ("open_interest", "volume", "liquidity", "spread_width", "quote_count"),
    "realization_date_fields": ("portfolio_realization_date", "outcome_availability_date", "selected_outcome_availability_date"),
}

EVIDENCE_GROUPS = (
    "has_bid",
    "has_ask",
    "has_bid_and_ask",
    "has_mid_or_mark",
    "has_spread",
    "has_entry_price",
    "has_exit_price",
    "has_leg_payload",
    "has_contract_count",
    "has_option_symbol",
    "has_liquidity",
    "has_realization_date",
)


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    rows: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8-sig", errors="ignore") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue

            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc

            if isinstance(payload, dict):
                rows.append(payload)
            else:
                raise ValueError(f"Expected JSON object at {path}:{line_number}")

    return rows


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


def _path_contains_any(path: str, needles: tuple[str, ...]) -> bool:
    parts = _path_parts(path)
    joined = "_".join(parts)
    return any(needle.lower() in joined for needle in needles)


def flatten_payload(payload: Any, prefix: str = "", *, max_list_items: int = 3) -> list[tuple[str, Any]]:
    """Flatten payload into (path, scalar/container-summary) pairs.

    Lists are sampled to avoid massive field catalogs, but list container paths are
    still recorded so leg arrays are visible even if deep contents vary.
    """
    output: list[tuple[str, Any]] = []

    if isinstance(payload, dict):
        if prefix:
            output.append((prefix, payload))
        for key, value in payload.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            output.extend(flatten_payload(value, child_prefix, max_list_items=max_list_items))
        return output

    if isinstance(payload, list):
        if prefix:
            output.append((prefix, payload))
        for index, item in enumerate(payload[:max_list_items]):
            child_prefix = f"{prefix}[*]" if prefix else "[*]"
            output.extend(flatten_payload(item, child_prefix, max_list_items=max_list_items))
        return output

    if prefix:
        output.append((prefix, payload))
    return output


def detect_row_evidence(row: dict[str, Any]) -> dict[str, Any]:
    flattened = flatten_payload(row)
    present_paths = [path for path, value in flattened if _is_present(value)]
    numeric_paths = [path for path, value in flattened if _is_numeric_like(value)]

    path_counter = Counter(present_paths)

    bid_paths = [
        path for path in numeric_paths
        if _path_contains_any(path, ("bid",)) and not _path_contains_any(path, ("forbidden",))
    ]
    ask_paths = [
        path for path in numeric_paths
        if _path_contains_any(path, ("ask",)) and not _path_contains_any(path, ("mask",))
    ]
    mid_paths = [path for path in numeric_paths if _path_contains_any(path, ("mid", "mark"))]
    spread_paths = [path for path in numeric_paths if _path_contains_any(path, ("spread", "bid_ask", "bidask"))]
    entry_paths = [path for path in numeric_paths if _path_contains_any(path, ("entry", "open_price", "entry_price", "entry_value"))]
    exit_paths = [path for path in numeric_paths if _path_contains_any(path, ("exit", "close_price", "exit_price", "exit_value"))]
    leg_paths = [path for path in present_paths if _path_contains_any(path, ("leg", "legs", "selected_legs", "entry_legs", "exit_legs", "option_legs"))]
    contract_count_paths = [path for path in numeric_paths if _path_contains_any(path, ("contract_count", "contracts", "quantity", "qty", "contract_quantity"))]
    option_symbol_paths = [path for path in present_paths if _path_contains_any(path, ("option_symbol", "contract_symbol", "occ_symbol", "option_contract"))]
    liquidity_paths = [path for path in present_paths if _path_contains_any(path, ("open_interest", "volume", "liquidity", "spread_width", "quote_count"))]
    realization_date_paths = [path for path in present_paths if _path_contains_any(path, ("portfolio_realization_date", "outcome_availability_date", "selected_outcome_availability_date"))]

    return {
        "has_bid": bool(bid_paths),
        "has_ask": bool(ask_paths),
        "has_bid_and_ask": bool(bid_paths and ask_paths),
        "has_mid_or_mark": bool(mid_paths),
        "has_spread": bool(spread_paths),
        "has_entry_price": bool(entry_paths),
        "has_exit_price": bool(exit_paths),
        "has_leg_payload": bool(leg_paths),
        "has_contract_count": bool(contract_count_paths),
        "has_option_symbol": bool(option_symbol_paths),
        "has_liquidity": bool(liquidity_paths),
        "has_realization_date": bool(realization_date_paths),
        "evidence_paths": {
            "bid": sorted(set(bid_paths))[:20],
            "ask": sorted(set(ask_paths))[:20],
            "mid_or_mark": sorted(set(mid_paths))[:20],
            "spread": sorted(set(spread_paths))[:20],
            "entry_price": sorted(set(entry_paths))[:20],
            "exit_price": sorted(set(exit_paths))[:20],
            "leg_payload": sorted(set(leg_paths))[:20],
            "contract_count": sorted(set(contract_count_paths))[:20],
            "option_symbol": sorted(set(option_symbol_paths))[:20],
            "liquidity": sorted(set(liquidity_paths))[:20],
            "realization_date": sorted(set(realization_date_paths))[:20],
        },
        "present_field_count": len(set(present_paths)),
        "numeric_field_count": len(set(numeric_paths)),
        "sample_present_paths": sorted(path_counter)[:50],
    }


def summarize_artifact(
    *,
    artifact_name: str,
    path: str | Path,
    rows: list[dict[str, Any]],
    selected_only: bool = False,
    sized_only: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, int]]:
    scoped_rows = rows

    if selected_only:
        scoped_rows = [
            row for row in scoped_rows
            if row.get("selection_state") == "selected"
            or row.get("is_selected_trade") is True
            or row.get("selected_strategy")
        ]

    if sized_only:
        scoped_rows = [
            row for row in scoped_rows
            if row.get("sizing_state") == "sized"
        ]

    coverage_counts: Counter[str] = Counter()
    field_catalog: Counter[str] = Counter()
    numeric_catalog: Counter[str] = Counter()
    detail_rows: list[dict[str, Any]] = []

    for index, row in enumerate(scoped_rows):
        evidence = detect_row_evidence(row)

        for group in EVIDENCE_GROUPS:
            if evidence[group]:
                coverage_counts[group] += 1

        for field_path, value in flatten_payload(row):
            if _is_present(value):
                field_catalog[field_path] += 1
            if _is_numeric_like(value):
                numeric_catalog[field_path] += 1

        if index < 100 or not (evidence["has_bid_and_ask"] and evidence["has_leg_payload"] and evidence["has_spread"]):
            detail_rows.append(
                {
                    "artifact_name": artifact_name,
                    "row_index": index,
                    "date": row.get("portfolio_realization_date")
                    or row.get("selected_outcome_availability_date")
                    or row.get("outcome_availability_date")
                    or row.get("decision_date")
                    or row.get("date"),
                    "symbol": row.get("symbol") or row.get("underlying"),
                    "strategy": row.get("selected_strategy") or row.get("strategy"),
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
        "coverage_counts": dict(sorted(coverage_counts.items())),
        "coverage_pct": coverage_pct,
        "field_catalog_top": dict(field_catalog.most_common(100)),
        "numeric_field_catalog_top": dict(numeric_catalog.most_common(100)),
        "best_evidence_paths": {
            group: sorted(
                {
                    path
                    for detail in detail_rows
                    for path in detail.get("evidence_paths", {}).get(group.replace("has_", ""), [])
                }
            )[:25]
            for group in EVIDENCE_GROUPS
        },
    }

    return summary, detail_rows, dict(field_catalog)


def build_portfolio_execution_realism_source_audit(
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
    summary_path = output_path / "signalforge_portfolio_execution_realism_source_audit_summary.json"
    details_path = output_path / "signalforge_portfolio_execution_realism_source_audit_rows.jsonl"
    catalog_path = output_path / "signalforge_portfolio_execution_realism_source_audit_field_catalog.json"

    inputs = [
        ("leg_selection_rows", leg_selection_rows_path, False, False),
        ("quote_outcome_rows", quote_outcome_rows_path, False, False),
        ("strategy_selection_rows", strategy_selection_rows_path, True, False),
        ("selected_strategy_outcome_rows", selected_strategy_outcome_rows_path, True, False),
        ("portfolio_selected_trade_sequence_rows", portfolio_selected_trade_sequence_rows_path, False, False),
        ("position_sizing_rows", position_sizing_rows_path, False, True),
    ]

    artifact_summaries: list[dict[str, Any]] = []
    detail_rows: list[dict[str, Any]] = []
    global_field_catalog: dict[str, dict[str, int]] = {}
    missing_inputs: list[str] = []
    unreadable_inputs: list[dict[str, str]] = []

    for artifact_name, path, selected_only, sized_only in inputs:
        if path is None:
            missing_inputs.append(artifact_name)
            continue

        try:
            rows = read_jsonl(path)
        except Exception as exc:
            unreadable_inputs.append(
                {
                    "artifact_name": artifact_name,
                    "path": str(path),
                    "error": str(exc),
                }
            )
            continue

        artifact_summary, artifact_details, field_catalog = summarize_artifact(
            artifact_name=artifact_name,
            path=path,
            rows=rows,
            selected_only=selected_only,
            sized_only=sized_only,
        )
        artifact_summaries.append(artifact_summary)
        detail_rows.extend(artifact_details)
        global_field_catalog[artifact_name] = field_catalog

    by_name = {item["artifact_name"]: item for item in artifact_summaries}

    def coverage(name: str, key: str) -> float | None:
        artifact = by_name.get(name)
        if not artifact:
            return None
        return artifact.get("coverage_pct", {}).get(key)

    warnings: list[str] = []
    blockers: list[str] = []

    if unreadable_inputs:
        blockers.append("one_or_more_inputs_unreadable")

    position_spread_coverage = coverage("position_sizing_rows", "has_spread")
    position_bid_ask_coverage = coverage("position_sizing_rows", "has_bid_and_ask")
    position_leg_coverage = coverage("position_sizing_rows", "has_leg_payload")
    position_contract_coverage = coverage("position_sizing_rows", "has_contract_count")

    upstream_leg_coverage = max(
        [
            value
            for value in [
                coverage("leg_selection_rows", "has_leg_payload"),
                coverage("quote_outcome_rows", "has_leg_payload"),
                coverage("strategy_selection_rows", "has_leg_payload"),
            ]
            if value is not None
        ],
        default=None,
    )

    upstream_spread_coverage = max(
        [
            value
            for value in [
                coverage("leg_selection_rows", "has_spread"),
                coverage("quote_outcome_rows", "has_spread"),
                coverage("strategy_selection_rows", "has_spread"),
            ]
            if value is not None
        ],
        default=None,
    )

    upstream_bid_ask_coverage = max(
        [
            value
            for value in [
                coverage("leg_selection_rows", "has_bid_and_ask"),
                coverage("quote_outcome_rows", "has_bid_and_ask"),
                coverage("strategy_selection_rows", "has_bid_and_ask"),
            ]
            if value is not None
        ],
        default=None,
    )

    if position_bid_ask_coverage is not None and position_bid_ask_coverage < 0.95:
        warnings.append("portfolio_ledger_missing_bid_ask_coverage")

    if position_spread_coverage is not None and position_spread_coverage < 0.95:
        warnings.append("portfolio_ledger_missing_spread_coverage")

    if position_leg_coverage is not None and position_leg_coverage < 0.95:
        warnings.append("portfolio_ledger_missing_leg_payload_coverage")

    if position_contract_coverage is not None and position_contract_coverage < 0.95:
        warnings.append("portfolio_ledger_missing_contract_count_coverage")

    if upstream_bid_ask_coverage is not None and position_bid_ask_coverage is not None:
        if upstream_bid_ask_coverage >= 0.95 and position_bid_ask_coverage < 0.95:
            warnings.append("bid_ask_exists_upstream_but_not_portfolio_ledger")

    if upstream_spread_coverage is not None and position_spread_coverage is not None:
        if upstream_spread_coverage >= 0.95 and position_spread_coverage < 0.95:
            warnings.append("spread_exists_upstream_but_not_portfolio_ledger")

    if upstream_leg_coverage is not None and position_leg_coverage is not None:
        if upstream_leg_coverage >= 0.95 and position_leg_coverage < 0.95:
            warnings.append("leg_payload_exists_upstream_but_not_portfolio_ledger")

    readiness_state = "blocked" if blockers else "needs_enrichment" if warnings else "pass"

    recommendations: list[str] = []

    if "leg_payload_exists_upstream_but_not_portfolio_ledger" in warnings:
        recommendations.append(
            "Patch selected_strategy_outcome_rows, portfolio_selected_trade_sequence, and position_sizing_replay to carry selected/entry/exit leg payloads forward."
        )

    if "bid_ask_exists_upstream_but_not_portfolio_ledger" in warnings or "spread_exists_upstream_but_not_portfolio_ledger" in warnings:
        recommendations.append(
            "Patch the Phase 5/6 handoff to carry bid, ask, mid, mark, spread_pct, spread_dollars, and quote source fields into the final portfolio ledger."
        )

    if position_contract_coverage is not None and position_contract_coverage < 0.95:
        recommendations.append(
            "Add contract_count/contract_quantity to the portfolio ledger. If actual quantity is not available, add an explicit fallback_contract_count field so fee stress is auditable."
        )

    if position_bid_ask_coverage is not None and position_bid_ask_coverage < 0.95:
        recommendations.append(
            "Do not treat execution_skip_wide_spreads as quote-native yet; it will be a no-op until spread_pct fields are present."
        )

    if not recommendations:
        recommendations.append(
            "Execution-realism source coverage is sufficient for quote-native fill, spread-skip, and fee stress modeling."
        )

    summary = {
        "adapter_type": "portfolio_execution_realism_source_audit_builder",
        "artifact_type": "signalforge_portfolio_execution_realism_source_audit",
        "contract": "portfolio_execution_realism_source_audit",
        "is_ready": readiness_state != "blocked",
        "readiness_state": readiness_state,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,
        "missing_optional_inputs": missing_inputs,
        "unreadable_inputs": unreadable_inputs,
        "artifact_summaries": artifact_summaries,
        "handoff_coverage": {
            "position_sizing_bid_ask_coverage": position_bid_ask_coverage,
            "position_sizing_spread_coverage": position_spread_coverage,
            "position_sizing_leg_payload_coverage": position_leg_coverage,
            "position_sizing_contract_count_coverage": position_contract_coverage,
            "upstream_best_bid_ask_coverage": upstream_bid_ask_coverage,
            "upstream_best_spread_coverage": upstream_spread_coverage,
            "upstream_best_leg_payload_coverage": upstream_leg_coverage,
        },
        "next_build_recommendations": recommendations,
        "paths": {
            "summary_path": str(summary_path),
            "details_path": str(details_path),
            "field_catalog_path": str(catalog_path),
        },
        "explicit_exclusions": [
            "broker_api_calls",
            "order_routing",
            "order_submission",
            "live_execution",
            "new_strategy_selection_logic",
            "expectancy_rebuild",
            "portfolio_reconstruction",
            "stress_recalculation",
        ],
    }

    write_json(summary_path, summary)
    write_jsonl(details_path, detail_rows)
    write_json(catalog_path, global_field_catalog)

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit execution-realism field coverage across SignalForge portfolio backtest artifacts."
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

    summary = build_portfolio_execution_realism_source_audit(
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
