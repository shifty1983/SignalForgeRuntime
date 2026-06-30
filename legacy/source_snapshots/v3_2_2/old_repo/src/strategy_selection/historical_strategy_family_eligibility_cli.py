from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from src.signalforge.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS
from src.signalforge.engines.strategy_selection.strategy_family_eligibility import (
    _build_eligibility_item,
)


SCHEMA_VERSION = "signalforge_historical_strategy_family_eligibility.v1"
COVERAGE_POLICY_SCHEMA_VERSION = "signalforge_replay_option_coverage_policy.v1"

DEFAULT_ALIGNMENT_ROWS = (
    "artifacts/historical_regime_asset_options_alignment/"
    "signalforge_historical_regime_asset_options_alignment_rows.jsonl"
)
DEFAULT_ALIGNMENT_SUMMARY = (
    "artifacts/historical_regime_asset_options_alignment/"
    "signalforge_historical_regime_asset_options_alignment_summary.json"
)
DEFAULT_SYMBOL_POLICY = "config/qc_5y_data_inventory_symbol_policy.json"
DEFAULT_OUTPUT_DIR = "artifacts/historical_strategy_family_eligibility"

ROW_CSV_FIELDS = [
    "quote_date",
    "symbol",
    "coverage_status",
    "expected_value_handoff_status",
    "ev_eligible",
    "risk_adjustment_required",
    "data_review_required",
    "hard_blocked",
    "replay_coverage_state",
    "replay_option_coverage_pct",
    "replay_aligned_date_count",
    "replay_target_date_count",
    "asset_behavior_state",
    "options_behavior_state",
    "premium_bias",
    "strategy_environment_bias",
    "favored_strategy_families",
    "allowed_strategy_families",
    "discouraged_strategy_families",
    "blocked_strategy_families",
    "risk_flags",
    "constraint_flags",
    "needs_review_reasons",
]

COVERAGE_CSV_FIELDS = [
    "symbol",
    "aligned_date_count",
    "target_date_count",
    "missing_date_count",
    "aligned_coverage_pct",
    "replay_coverage_state",
    "is_strategy_generation_eligible",
    "symbol_policy_role",
]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    result = build_historical_strategy_family_eligibility(
        alignment_rows_path=Path(args.alignment_rows),
        alignment_summary_path=Path(args.alignment_summary) if args.alignment_summary else None,
        symbol_policy_path=Path(args.symbol_policy) if args.symbol_policy else None,
        output_dir=Path(args.output_dir),
        full_coverage_pct=float(args.full_coverage_pct),
        eligible_coverage_pct=float(args.eligible_coverage_pct),
        sparse_review_coverage_pct=float(args.sparse_review_coverage_pct),
        eligible_coverage_states=_parse_csv_set(args.eligible_coverage_states),
        include_data_review_rows=bool(args.include_data_review_rows),
    )

    print(json.dumps(result["summary"], indent=2, sort_keys=True, default=str))
    return 0 if result["summary"].get("status") != "blocked" else 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build historical SignalForge strategy-family eligibility rows from "
            "historical regime/asset/options alignment, while applying replay option "
            "coverage policy at strategy-generation time. This does not choose contracts, "
            "model fills, submit orders, or make automatic strategy changes."
        )
    )
    parser.add_argument("--alignment-rows", default=DEFAULT_ALIGNMENT_ROWS)
    parser.add_argument("--alignment-summary", default=DEFAULT_ALIGNMENT_SUMMARY)
    parser.add_argument("--symbol-policy", default=DEFAULT_SYMBOL_POLICY)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--full-coverage-pct",
        type=float,
        default=95.0,
        help="Coverage percent at or above this value is full_coverage_core.",
    )
    parser.add_argument(
        "--eligible-coverage-pct",
        type=float,
        default=50.0,
        help="Coverage percent at or above this value is eligible.",
    )
    parser.add_argument(
        "--sparse-review-coverage-pct",
        type=float,
        default=20.0,
        help="Coverage percent at or above this value but below eligible is sparse_review.",
    )
    parser.add_argument(
        "--eligible-coverage-states",
        default="full_coverage_core,eligible",
        help=(
            "Comma-separated replay coverage states allowed into strategy-family eligibility. "
            "Default excludes sparse_review and exclude_from_replay_strategy_generation."
        ),
    )
    parser.add_argument(
        "--include-data-review-rows",
        action="store_true",
        help=(
            "Keep alignment rows that the strategy-family builder marks data_review_required. "
            "By default they are written too; this flag is retained for explicit compatibility."
        ),
    )
    return parser


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def build_historical_strategy_family_eligibility(
    *,
    alignment_rows_path: Path,
    alignment_summary_path: Path | None,
    symbol_policy_path: Path | None,
    output_dir: Path,
    full_coverage_pct: float,
    eligible_coverage_pct: float,
    sparse_review_coverage_pct: float,
    eligible_coverage_states: set[str],
    include_data_review_rows: bool = False,
) -> dict[str, Any]:
    _require_file(alignment_rows_path)
    if alignment_summary_path is not None:
        _require_file(alignment_summary_path)
    if symbol_policy_path is not None:
        _require_file(symbol_policy_path)

    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / "signalforge_historical_strategy_family_eligibility.json"
    summary_path = output_dir / "signalforge_historical_strategy_family_eligibility_summary.json"
    rows_path = output_dir / "signalforge_historical_strategy_family_eligibility_rows.jsonl"
    rows_csv_path = output_dir / "signalforge_historical_strategy_family_eligibility_rows.csv"
    coverage_policy_path = output_dir / "signalforge_replay_option_coverage_policy.json"
    coverage_csv_path = output_dir / "signalforge_replay_option_coverage_by_symbol.csv"

    alignment_rows = [row for row in _iter_jsonl(alignment_rows_path) if isinstance(row, Mapping)]
    alignment_summary = _read_json(alignment_summary_path) if alignment_summary_path else {}
    symbol_policy = _read_json(symbol_policy_path) if symbol_policy_path else {}

    if not alignment_rows:
        result = _blocked_result(
            blocked_reasons=["missing_alignment_rows"],
            result_path=result_path,
            summary_path=summary_path,
            rows_path=rows_path,
            rows_csv_path=rows_csv_path,
            coverage_policy_path=coverage_policy_path,
            coverage_csv_path=coverage_csv_path,
            alignment_rows_path=alignment_rows_path,
            alignment_summary_path=alignment_summary_path,
            symbol_policy_path=symbol_policy_path,
        )
        _write_json(result_path, result["result"])
        _write_json(summary_path, result["summary"])
        return result

    target_date_count = _target_date_count(alignment_rows, alignment_summary)
    target_dates = sorted({_get_date(row) for row in alignment_rows if _get_date(row)})

    broad_symbol_universe = _broad_symbol_universe(alignment_rows, symbol_policy)
    coverage_by_symbol = _build_coverage_by_symbol(
        alignment_rows=alignment_rows,
        broad_symbol_universe=broad_symbol_universe,
        target_date_count=target_date_count,
        full_coverage_pct=full_coverage_pct,
        eligible_coverage_pct=eligible_coverage_pct,
        sparse_review_coverage_pct=sparse_review_coverage_pct,
        eligible_coverage_states=eligible_coverage_states,
        symbol_policy=symbol_policy,
    )

    _write_coverage_policy(
        coverage_policy_path=coverage_policy_path,
        coverage_csv_path=coverage_csv_path,
        coverage_by_symbol=coverage_by_symbol,
        alignment_summary=alignment_summary,
        symbol_policy=symbol_policy,
        full_coverage_pct=full_coverage_pct,
        eligible_coverage_pct=eligible_coverage_pct,
        sparse_review_coverage_pct=sparse_review_coverage_pct,
        eligible_coverage_states=eligible_coverage_states,
        target_dates=target_dates,
    )

    eligible_items: list[dict[str, Any]] = []
    skipped_alignment_rows: list[dict[str, Any]] = []
    row_errors: list[dict[str, Any]] = []
    skipped_by_state: Counter[str] = Counter()

    with rows_path.open("w", encoding="utf-8") as jsonl_handle, rows_csv_path.open("w", newline="", encoding="utf-8") as csv_handle:
        writer = csv.DictWriter(csv_handle, fieldnames=ROW_CSV_FIELDS)
        writer.writeheader()

        for alignment_row in alignment_rows:
            symbol = _clean_symbol(_first_value(alignment_row, ("symbol", "underlying_symbol", "ticker")))
            date_text = _get_date(alignment_row)
            symbol_coverage = coverage_by_symbol.get(symbol or "") or {}
            replay_state = str(symbol_coverage.get("replay_coverage_state") or "unknown")

            if replay_state not in eligible_coverage_states:
                skipped_by_state[replay_state] += 1
                if len(skipped_alignment_rows) < 100:
                    skipped_alignment_rows.append(
                        {
                            "quote_date": date_text,
                            "symbol": symbol,
                            "replay_coverage_state": replay_state,
                            "aligned_coverage_pct": symbol_coverage.get("aligned_coverage_pct"),
                            "reason": "symbol_replay_option_coverage_not_strategy_generation_eligible",
                        }
                    )
                continue

            try:
                item = _build_eligibility_item(alignment_row)
            except Exception as exc:  # pragma: no cover - defensive for schema drift
                if len(row_errors) < 100:
                    row_errors.append(
                        {
                            "quote_date": date_text,
                            "symbol": symbol,
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        }
                    )
                continue

            # Keep the historical replay dimensions explicit. The current/latest builder
            # intentionally does not own dates, so the historical adapter stamps them here.
            item["artifact_type"] = "historical_strategy_family_eligibility_item"
            item["schema_version"] = "signalforge_historical_strategy_family_eligibility_item.v1"
            item["quote_date"] = date_text
            item["as_of_date"] = date_text
            item["historical_replay_mode"] = True
            item["source_alignment_coverage_status"] = alignment_row.get("coverage_status")
            item["source_alignment_strategy_selection_handoff"] = alignment_row.get("strategy_selection_handoff")
            item["replay_coverage_state"] = replay_state
            item["replay_option_coverage_pct"] = symbol_coverage.get("aligned_coverage_pct")
            item["replay_aligned_date_count"] = symbol_coverage.get("aligned_date_count")
            item["replay_target_date_count"] = symbol_coverage.get("target_date_count")
            item["replay_missing_date_count"] = symbol_coverage.get("missing_date_count")
            item["symbol_policy_role"] = symbol_coverage.get("symbol_policy_role")
            item["source_refs"] = {
                "alignment_rows": str(alignment_rows_path),
                "alignment_summary": str(alignment_summary_path) if alignment_summary_path else None,
                "symbol_policy": str(symbol_policy_path) if symbol_policy_path else None,
                "replay_option_coverage_policy": str(coverage_policy_path),
            }

            matrix_metadata = item.get("matrix_dimension_metadata")
            if isinstance(matrix_metadata, dict):
                matrix_metadata["quote_date"] = date_text
                matrix_metadata["as_of_date"] = date_text
                matrix_metadata["replay_coverage_state"] = replay_state

            eligible_items.append(item)
            jsonl_handle.write(json.dumps(item, sort_keys=True, default=str) + "\n")
            writer.writerow({field: _csv_value(item.get(field)) for field in ROW_CSV_FIELDS})

    summary = _build_summary(
        alignment_rows=alignment_rows,
        eligible_items=eligible_items,
        coverage_by_symbol=coverage_by_symbol,
        skipped_by_state=skipped_by_state,
        skipped_alignment_rows=skipped_alignment_rows,
        row_errors=row_errors,
        target_date_count=target_date_count,
        target_dates=target_dates,
        alignment_summary=alignment_summary,
        symbol_policy=symbol_policy,
        eligible_coverage_states=eligible_coverage_states,
        full_coverage_pct=full_coverage_pct,
        eligible_coverage_pct=eligible_coverage_pct,
        sparse_review_coverage_pct=sparse_review_coverage_pct,
        result_path=result_path,
        summary_path=summary_path,
        rows_path=rows_path,
        rows_csv_path=rows_csv_path,
        coverage_policy_path=coverage_policy_path,
        coverage_csv_path=coverage_csv_path,
        alignment_rows_path=alignment_rows_path,
        alignment_summary_path=alignment_summary_path,
        symbol_policy_path=symbol_policy_path,
    )

    result = {
        "artifact_type": "signalforge_historical_strategy_family_eligibility",
        "schema_version": SCHEMA_VERSION,
        "status": summary["status"],
        "is_ready": summary["is_ready"],
        "requires_manual_approval": True,
        "contract": "historical_strategy_family_eligibility",
        "adapter_type": "historical_strategy_family_eligibility_builder",
        "review_scope": "historical_strategy_family_policy_eligibility_not_contract_selection_or_execution",
        "source_artifacts": {
            "alignment_rows": "signalforge_historical_regime_asset_options_alignment_rows.jsonl",
            "alignment_summary": alignment_summary.get("artifact_type"),
            "symbol_policy": symbol_policy.get("artifact_type"),
            "replay_option_coverage_policy": "signalforge_replay_option_coverage_policy",
        },
        "source_paths": {
            "alignment_rows": str(alignment_rows_path),
            "alignment_summary": str(alignment_summary_path) if alignment_summary_path else None,
            "symbol_policy": str(symbol_policy_path) if symbol_policy_path else None,
            "replay_option_coverage_policy": str(coverage_policy_path),
        },
        "strategy_generation_coverage_gate": {
            "eligible_coverage_states": sorted(eligible_coverage_states),
            "full_coverage_pct": full_coverage_pct,
            "eligible_coverage_pct": eligible_coverage_pct,
            "sparse_review_coverage_pct": sparse_review_coverage_pct,
        },
        "historical_strategy_family_eligibility_items": eligible_items[:50000],
        "eligibility_items": eligible_items[:50000],
        "historical_strategy_family_eligibility_summary": summary,
        "replay_option_coverage_policy": {
            "path": str(coverage_policy_path),
            "csv_path": str(coverage_csv_path),
            "symbol_count": len(coverage_by_symbol),
            "coverage_state_counts": summary["replay_coverage_state_symbol_counts"],
        },
        "sample_skipped_alignment_rows": skipped_alignment_rows,
        "row_error_examples": row_errors,
        "next_step": "historical_expectancy_candidate_rows",
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }

    _write_json(result_path, result)
    _write_json(summary_path, summary)
    return {"result": result, "summary": summary}


# ---------------------------------------------------------------------------
# Coverage policy
# ---------------------------------------------------------------------------


def _build_coverage_by_symbol(
    *,
    alignment_rows: Sequence[Mapping[str, Any]],
    broad_symbol_universe: set[str],
    target_date_count: int,
    full_coverage_pct: float,
    eligible_coverage_pct: float,
    sparse_review_coverage_pct: float,
    eligible_coverage_states: set[str],
    symbol_policy: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    aligned_dates_by_symbol: dict[str, set[str]] = {symbol: set() for symbol in broad_symbol_universe}
    for row in alignment_rows:
        symbol = _clean_symbol(_first_value(row, ("symbol", "underlying_symbol", "ticker")))
        date_text = _get_date(row)
        if symbol and date_text:
            aligned_dates_by_symbol.setdefault(symbol, set()).add(date_text)

    output: dict[str, dict[str, Any]] = {}
    for symbol in sorted(aligned_dates_by_symbol):
        aligned_count = len(aligned_dates_by_symbol[symbol])
        pct = round((100.0 * aligned_count / target_date_count), 4) if target_date_count else 0.0
        state = _coverage_state(
            pct,
            full_coverage_pct=full_coverage_pct,
            eligible_coverage_pct=eligible_coverage_pct,
            sparse_review_coverage_pct=sparse_review_coverage_pct,
        )
        output[symbol] = {
            "symbol": symbol,
            "aligned_date_count": aligned_count,
            "target_date_count": target_date_count,
            "missing_date_count": max(target_date_count - aligned_count, 0),
            "aligned_coverage_pct": pct,
            "replay_coverage_state": state,
            "is_strategy_generation_eligible": state in eligible_coverage_states,
            "symbol_policy_role": _symbol_policy_role(symbol, symbol_policy),
        }
    return output


def _coverage_state(
    pct: float,
    *,
    full_coverage_pct: float,
    eligible_coverage_pct: float,
    sparse_review_coverage_pct: float,
) -> str:
    if pct >= full_coverage_pct:
        return "full_coverage_core"
    if pct >= eligible_coverage_pct:
        return "eligible"
    if pct >= sparse_review_coverage_pct:
        return "sparse_review"
    return "exclude_from_replay_strategy_generation"


def _write_coverage_policy(
    *,
    coverage_policy_path: Path,
    coverage_csv_path: Path,
    coverage_by_symbol: Mapping[str, Mapping[str, Any]],
    alignment_summary: Mapping[str, Any],
    symbol_policy: Mapping[str, Any],
    full_coverage_pct: float,
    eligible_coverage_pct: float,
    sparse_review_coverage_pct: float,
    eligible_coverage_states: set[str],
    target_dates: Sequence[str],
) -> None:
    state_counts = Counter(str(row.get("replay_coverage_state") or "unknown") for row in coverage_by_symbol.values())
    eligible_symbols = [symbol for symbol, row in coverage_by_symbol.items() if row.get("is_strategy_generation_eligible")]
    sparse_symbols = [symbol for symbol, row in coverage_by_symbol.items() if row.get("replay_coverage_state") == "sparse_review"]
    excluded_symbols = [
        symbol
        for symbol, row in coverage_by_symbol.items()
        if row.get("replay_coverage_state") == "exclude_from_replay_strategy_generation"
    ]

    coverage_policy = {
        "artifact_type": "signalforge_replay_option_coverage_policy",
        "schema_version": COVERAGE_POLICY_SCHEMA_VERSION,
        "status": "ready",
        "is_ready": True,
        "review_scope": "replay_option_symbol_coverage_gate_before_strategy_family_generation",
        "source_artifacts": {
            "alignment_summary": alignment_summary.get("artifact_type"),
            "symbol_policy": symbol_policy.get("artifact_type"),
        },
        "thresholds": {
            "full_coverage_pct": full_coverage_pct,
            "eligible_coverage_pct": eligible_coverage_pct,
            "sparse_review_coverage_pct": sparse_review_coverage_pct,
            "eligible_coverage_states": sorted(eligible_coverage_states),
        },
        "target_date_count": len(target_dates),
        "target_date_min": target_dates[0] if target_dates else None,
        "target_date_max": target_dates[-1] if target_dates else None,
        "symbol_count": len(coverage_by_symbol),
        "coverage_state_counts": dict(sorted(state_counts.items())),
        "strategy_generation_eligible_symbol_count": len(eligible_symbols),
        "sparse_review_symbol_count": len(sparse_symbols),
        "excluded_from_strategy_generation_symbol_count": len(excluded_symbols),
        "strategy_generation_eligible_symbols": sorted(eligible_symbols),
        "sparse_review_symbols": sorted(sparse_symbols),
        "excluded_from_strategy_generation_symbols": sorted(excluded_symbols),
        "coverage_by_symbol": {symbol: dict(row) for symbol, row in sorted(coverage_by_symbol.items())},
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }
    _write_json(coverage_policy_path, coverage_policy)

    with coverage_csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COVERAGE_CSV_FIELDS)
        writer.writeheader()
        for symbol, row in sorted(coverage_by_symbol.items()):
            writer.writerow({field: _csv_value(row.get(field)) for field in COVERAGE_CSV_FIELDS})


# ---------------------------------------------------------------------------
# Summary/output
# ---------------------------------------------------------------------------


def _build_summary(
    *,
    alignment_rows: Sequence[Mapping[str, Any]],
    eligible_items: Sequence[Mapping[str, Any]],
    coverage_by_symbol: Mapping[str, Mapping[str, Any]],
    skipped_by_state: Counter[str],
    skipped_alignment_rows: Sequence[Mapping[str, Any]],
    row_errors: Sequence[Mapping[str, Any]],
    target_date_count: int,
    target_dates: Sequence[str],
    alignment_summary: Mapping[str, Any],
    symbol_policy: Mapping[str, Any],
    eligible_coverage_states: set[str],
    full_coverage_pct: float,
    eligible_coverage_pct: float,
    sparse_review_coverage_pct: float,
    result_path: Path,
    summary_path: Path,
    rows_path: Path,
    rows_csv_path: Path,
    coverage_policy_path: Path,
    coverage_csv_path: Path,
    alignment_rows_path: Path,
    alignment_summary_path: Path | None,
    symbol_policy_path: Path | None,
) -> dict[str, Any]:
    replay_state_symbol_counts = Counter(str(row.get("replay_coverage_state") or "unknown") for row in coverage_by_symbol.values())
    replay_state_row_counts = Counter(
        str((coverage_by_symbol.get(_clean_symbol(_first_value(row, ("symbol", "underlying_symbol", "ticker"))) or "") or {}).get("replay_coverage_state") or "unknown")
        for row in alignment_rows
    )
    coverage_status_counts = Counter(str(item.get("coverage_status") or "unknown") for item in eligible_items)
    handoff_counts = Counter(str(item.get("expected_value_handoff_status") or item.get("strategy_family_eligibility_handoff") or "unknown") for item in eligible_items)
    allowed_family_counts = Counter(family for item in eligible_items for family in _as_list(item.get("allowed_strategy_families")))
    favored_family_counts = Counter(family for item in eligible_items for family in _as_list(item.get("favored_strategy_families")))
    blocked_family_counts = Counter(family for item in eligible_items for family in _as_list(item.get("blocked_strategy_families")))
    risk_flag_counts = Counter(flag for item in eligible_items for flag in _as_list(item.get("risk_flags")))
    data_reason_counts = Counter(reason for item in eligible_items for reason in _as_list(item.get("data_review_reasons")))

    eligible_symbol_count = sum(1 for row in coverage_by_symbol.values() if row.get("is_strategy_generation_eligible"))
    sparse_symbol_count = replay_state_symbol_counts.get("sparse_review", 0)
    excluded_symbol_count = replay_state_symbol_counts.get("exclude_from_replay_strategy_generation", 0)
    eligible_row_count = len(eligible_items)
    ev_eligible_row_count = sum(1 for item in eligible_items if item.get("ev_eligible") is True)
    risk_adjusted_row_count = sum(1 for item in eligible_items if item.get("risk_adjustment_required") is True)
    data_review_row_count = sum(1 for item in eligible_items if item.get("data_review_required") is True)
    hard_blocked_row_count = sum(1 for item in eligible_items if item.get("hard_blocked") is True)
    skipped_alignment_row_count = sum(skipped_by_state.values())

    status = "ready" if eligible_row_count and not row_errors else "needs_review" if eligible_row_count else "blocked"

    return {
        "schema_version": "signalforge_historical_strategy_family_eligibility_cli_summary.v1",
        "operation_type": "signalforge_historical_strategy_family_eligibility_cli",
        "artifact_type": "signalforge_historical_strategy_family_eligibility",
        "status": status,
        "is_ready": status in {"ready", "needs_review"},
        "review_scope": "historical_strategy_family_policy_eligibility_with_replay_option_coverage_gate",
        "source_artifacts": {
            "alignment_summary": alignment_summary.get("artifact_type"),
            "symbol_policy": symbol_policy.get("artifact_type"),
        },
        "source_paths": {
            "alignment_rows": str(alignment_rows_path),
            "alignment_summary": str(alignment_summary_path) if alignment_summary_path else None,
            "symbol_policy": str(symbol_policy_path) if symbol_policy_path else None,
        },
        "target_date_count": target_date_count,
        "target_date_min": target_dates[0] if target_dates else None,
        "target_date_max": target_dates[-1] if target_dates else None,
        "input_alignment_row_count": len(alignment_rows),
        "historical_strategy_family_eligibility_row_count": eligible_row_count,
        "skipped_alignment_row_count": skipped_alignment_row_count,
        "skipped_alignment_row_counts_by_replay_coverage_state": dict(sorted(skipped_by_state.items())),
        "row_error_count": len(row_errors),
        "row_error_examples": list(row_errors),
        "strategy_generation_coverage_gate": {
            "eligible_coverage_states": sorted(eligible_coverage_states),
            "full_coverage_pct": full_coverage_pct,
            "eligible_coverage_pct": eligible_coverage_pct,
            "sparse_review_coverage_pct": sparse_review_coverage_pct,
        },
        "replay_coverage_state_symbol_counts": dict(sorted(replay_state_symbol_counts.items())),
        "replay_coverage_state_alignment_row_counts": dict(sorted(replay_state_row_counts.items())),
        "strategy_generation_eligible_symbol_count": eligible_symbol_count,
        "sparse_review_symbol_count": sparse_symbol_count,
        "excluded_from_strategy_generation_symbol_count": excluded_symbol_count,
        "coverage_status_counts": dict(sorted(coverage_status_counts.items())),
        "handoff_counts": dict(sorted(handoff_counts.items())),
        "ev_eligible_row_count": ev_eligible_row_count,
        "risk_adjusted_ev_row_count": risk_adjusted_row_count,
        "data_review_row_count": data_review_row_count,
        "hard_blocked_row_count": hard_blocked_row_count,
        "allowed_strategy_family_counts": dict(sorted(allowed_family_counts.items())),
        "favored_strategy_family_counts": dict(sorted(favored_family_counts.items())),
        "blocked_strategy_family_counts": dict(sorted(blocked_family_counts.items())),
        "risk_flag_counts": dict(sorted(risk_flag_counts.items())),
        "data_review_reason_counts": dict(sorted(data_reason_counts.items())),
        "sample_skipped_alignment_rows": list(skipped_alignment_rows),
        "paths": {
            "result": str(result_path),
            "summary": str(summary_path),
            "rows_jsonl": str(rows_path),
            "rows_csv": str(rows_csv_path),
            "replay_option_coverage_policy": str(coverage_policy_path),
            "replay_option_coverage_csv": str(coverage_csv_path),
        },
        "next_step": "historical_expectancy_candidate_rows",
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _blocked_result(
    *,
    blocked_reasons: Sequence[str],
    result_path: Path,
    summary_path: Path,
    rows_path: Path,
    rows_csv_path: Path,
    coverage_policy_path: Path,
    coverage_csv_path: Path,
    alignment_rows_path: Path,
    alignment_summary_path: Path | None,
    symbol_policy_path: Path | None,
) -> dict[str, Any]:
    summary = {
        "schema_version": "signalforge_historical_strategy_family_eligibility_cli_summary.v1",
        "operation_type": "signalforge_historical_strategy_family_eligibility_cli",
        "artifact_type": "signalforge_historical_strategy_family_eligibility",
        "status": "blocked",
        "is_ready": False,
        "blocked_reasons": list(blocked_reasons),
        "source_paths": {
            "alignment_rows": str(alignment_rows_path),
            "alignment_summary": str(alignment_summary_path) if alignment_summary_path else None,
            "symbol_policy": str(symbol_policy_path) if symbol_policy_path else None,
        },
        "input_alignment_row_count": 0,
        "historical_strategy_family_eligibility_row_count": 0,
        "paths": {
            "result": str(result_path),
            "summary": str(summary_path),
            "rows_jsonl": str(rows_path),
            "rows_csv": str(rows_csv_path),
            "replay_option_coverage_policy": str(coverage_policy_path),
            "replay_option_coverage_csv": str(coverage_csv_path),
        },
        "next_step": "provide_historical_alignment_rows",
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }
    result = {
        "artifact_type": "signalforge_historical_strategy_family_eligibility",
        "schema_version": SCHEMA_VERSION,
        "status": "blocked",
        "is_ready": False,
        "blocked_reasons": list(blocked_reasons),
        "historical_strategy_family_eligibility_items": [],
        "summary": summary,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }
    return {"result": result, "summary": summary}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _target_date_count(alignment_rows: Sequence[Mapping[str, Any]], alignment_summary: Mapping[str, Any]) -> int:
    raw_value = alignment_summary.get("target_date_count")
    if raw_value is not None:
        try:
            value = int(raw_value)
            if value > 0:
                return value
        except (TypeError, ValueError):
            pass
    return len({_get_date(row) for row in alignment_rows if _get_date(row)})


def _broad_symbol_universe(alignment_rows: Sequence[Mapping[str, Any]], symbol_policy: Mapping[str, Any]) -> set[str]:
    symbols = {_clean_symbol(_first_value(row, ("symbol", "underlying_symbol", "ticker"))) for row in alignment_rows}
    clean_symbols = {symbol for symbol in symbols if symbol}
    tradable_symbols = {_clean_symbol(symbol) for symbol in _as_list(symbol_policy.get("tradable_option_symbols"))}
    clean_symbols.update(symbol for symbol in tradable_symbols if symbol)
    return clean_symbols


def _symbol_policy_role(symbol: str, policy: Mapping[str, Any]) -> str:
    if symbol in {_clean_symbol(value) for value in _as_list(policy.get("tradable_option_symbols"))}:
        return "tradable_option_symbol"
    if symbol in {_clean_symbol(value) for value in _as_list(policy.get("context_only_symbols"))}:
        return "context_only_symbol"
    if symbol in {_clean_symbol(value) for value in _as_list(policy.get("accepted_missing_contract_outcome_symbols"))}:
        return "accepted_missing_contract_outcome_symbol"
    if symbol in {_clean_symbol(value) for value in _as_list(policy.get("accepted_missing_option_behavior_symbols"))}:
        return "accepted_missing_option_behavior_symbol"
    return "unclassified_symbol"


def _get_date(row: Mapping[str, Any]) -> str | None:
    value = _first_value(row, ("quote_date", "as_of_date", "date", "market_date"))
    return str(value)[:10] if value is not None and str(value).strip() else None


def _parse_csv_set(value: str | None) -> set[str]:
    if not value:
        return set()
    return {part.strip() for part in value.split(",") if part.strip()}


def _require_file(path: Path) -> None:
    if not path.exists():
        raise SystemExit(f"input file does not exist: {path}")
    if not path.is_file():
        raise SystemExit(f"input path is not a file: {path}")


def _read_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    return value if isinstance(value, dict) else {}


def _iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _first_value(item: Mapping[str, Any] | None, keys: Sequence[str]) -> Any:
    if item is None:
        return None
    for key in keys:
        if key in item:
            value = item.get(key)
            if value is not None:
                return value
    return None


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    if value is None:
        return []
    return [value]


def _clean_symbol(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    return text or None


def _csv_value(value: Any) -> Any:
    if isinstance(value, (list, tuple, set)):
        return "|".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True, default=str)
    return value


if __name__ == "__main__":
    raise SystemExit(main())
