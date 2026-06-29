from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable
import json
import re

from src.data_sources.historical_edge_validation.combined_summary import EXPLICIT_EXCLUSIONS
from src.strategy_selection.historical_replay_matrix_metadata_stamp import (
    MATRIX_METADATA_KEY,
    matrix_metadata_coverage,
    stamp_matrix_metadata,
)


CONTRACT_OUTCOME_FILE = "signalforge_qc_contract_outcome_snapshots.json"
REPLAY_MANIFEST_FILE = "signalforge_qc_replay_manifest.json"
WINDOW_SUMMARY_FILE = "signalforge_historical_edge_validation_combined_summary.json"


def read_json(path: str | Path) -> Any:
    source = Path(path)
    return json.loads(source.read_text(encoding="utf-8-sig"))


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def discover_decoded_window_roots(paths: Iterable[str | Path]) -> list[Path]:
    discovered: list[Path] = []

    for raw_path in paths:
        path = Path(raw_path)

        if not path.exists():
            continue

        if path.is_dir() and path.name.startswith("quantconnect_research_export_decoded_batches_"):
            discovered.append(path)
            continue

        if path.is_dir():
            discovered.extend(
                sorted(
                    child
                    for child in path.rglob("quantconnect_research_export_decoded_batches_*")
                    if child.is_dir()
                )
            )

    return sorted(dict.fromkeys(discovered), key=lambda item: str(item))


def discover_window_summary_sources(paths: Iterable[str | Path]) -> list[Path]:
    discovered: list[Path] = []

    for raw_path in paths:
        path = Path(raw_path)

        if not path.exists():
            continue

        if path.is_file():
            discovered.append(path)
            continue

        if path.is_dir():
            discovered.extend(sorted(path.rglob(WINDOW_SUMMARY_FILE)))

    return sorted(dict.fromkeys(discovered), key=lambda item: str(item))


def _window_id_from_decoded_root(path: Path) -> str:
    return path.name.replace("quantconnect_research_export_decoded_batches_", "")


def _extract_rows(payload: Any, preferred_keys: list[str]) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]

    if not isinstance(payload, dict):
        return []

    for key in preferred_keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]

    for value in payload.values():
        if isinstance(value, list) and all(isinstance(row, dict) for row in value[:10]):
            return value

    return []


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None

    if isinstance(value, bool):
        return float(value)

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _integer(value: Any) -> int:
    number = _number(value)
    if number is None:
        return 0
    return int(number)


def _boolean(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "ready", "win", "positive"}:
            return True
        if lowered in {"false", "0", "no", "loss", "negative"}:
            return False

    return None


def _first_present(row: dict[str, Any], names: list[str]) -> Any:
    for name in names:
        if name in row and row.get(name) not in (None, ""):
            return row.get(name)

    contract = row.get("contract")
    if isinstance(contract, dict):
        for name in names:
            if name in contract and contract.get(name) not in (None, ""):
                return contract.get(name)

    underlying = row.get("underlying")
    if isinstance(underlying, dict):
        for name in names:
            if name in underlying and underlying.get(name) not in (None, ""):
                return underlying.get(name)

    return None


def _symbol_from_row(row: dict[str, Any]) -> str | None:
    value = _first_present(
        row,
        [
            "symbol",
            "underlying_symbol",
            "asset_symbol",
            "ticker",
            "root_symbol",
            "canonical_symbol",
        ],
    )

    if value:
        return str(value).strip().upper()

    contract = row.get("contract")
    if isinstance(contract, str) and contract.strip():
        token = contract.strip().split()[0]
        if token:
            return token.upper()

    return None


def _horizon_from_row(row: dict[str, Any]) -> str:
    value = _first_present(
        row,
        [
            "horizon_days",
            "outcome_horizon_days",
            "holding_period_days",
            "days_forward",
            "forward_days",
            "horizon",
            "outcome_horizon",
        ],
    )

    if value is None or value == "":
        return "unknown"

    number = _number(value)
    if number is not None:
        return str(int(number))

    match = re.search(r"\d+", str(value))
    if match:
        return match.group(0)

    return str(value)


def _strategy_adjustment_policy_from_row(row: dict[str, Any]) -> str | None:
    value = _first_present(
        row,
        [
            "strategy_adjustment_policy",
            "strategy_adjustment",
            "adjustment_policy",
            "strategy_family",
            "option_strategy_family",
        ],
    )

    if value in (None, ""):
        return None

    return str(value).strip()


def _strategy_adjusted_return_from_row(row: dict[str, Any]) -> float | None:
    explicit_adjusted = _number(
        _first_present(
            row,
            [
                "strategy_adjusted_return",
                "strategy_adjusted_contract_mark_return",
                "adjusted_contract_mark_return",
                "return_strategy_adjusted",
            ],
        )
    )

    if explicit_adjusted is not None:
        return explicit_adjusted

    raw_contract_return = _contract_return_from_row(row)
    if raw_contract_return is None:
        return None

    policy = (_strategy_adjustment_policy_from_row(row) or "").lower()

    if (
        "invert_short_premium_contract_mark" in policy
        or "defined_risk_short_premium" in policy
        or policy == ""
    ):
        return -raw_contract_return

    return raw_contract_return


def _contract_return_from_row(row: dict[str, Any]) -> float | None:
    return _number(
        _first_present(
            row,
            [
                "contract_mark_return",
                "mark_return",
                "contract_return",
                "average_contract_mark_return",
                "return",
            ],
        )
    )


def _favorable_from_row(row: dict[str, Any], strategy_adjusted_return: float | None) -> bool | None:
    value = _first_present(
        row,
        [
            "is_strategy_adjusted_win",
            "strategy_adjusted_win",
            "is_favorable",
            "favorable",
            "is_positive",
            "win",
        ],
    )

    parsed = _boolean(value)
    if parsed is not None:
        return parsed

    if strategy_adjusted_return is None:
        return None

    return strategy_adjusted_return > 0


def _load_manifest_summary(decoded_root: Path) -> dict[str, Any]:
    submitted_symbol_count = 0
    submitted_candidate_count = 0
    batch_manifest_count = 0
    batch_summaries: list[dict[str, Any]] = []

    for batch_dir in sorted(decoded_root.glob("batch_*")):
        manifest_path = batch_dir / REPLAY_MANIFEST_FILE
        if not manifest_path.exists():
            continue

        manifest = read_json(manifest_path)
        batch_manifest_count += 1

        symbol_count = _integer(manifest.get("symbol_count"))
        candidate_count = _integer(manifest.get("candidate_count"))

        submitted_symbol_count += symbol_count
        submitted_candidate_count += candidate_count

        batch_summaries.append(
            {
                "batch_id": batch_dir.name,
                "symbol_count": symbol_count,
                "candidate_count": candidate_count,
                "request_id": manifest.get("request_id"),
            }
        )

    return {
        "batch_manifest_count": batch_manifest_count,
        "submitted_symbol_count": submitted_symbol_count,
        "submitted_candidate_count": submitted_candidate_count,
        "batch_manifest_summaries": batch_summaries,
    }


def _load_normalized_outcomes(decoded_roots: list[Path]) -> tuple[list[dict[str, Any]], list[str]]:
    outcomes: list[dict[str, Any]] = []
    warnings: list[str] = []

    for decoded_root in decoded_roots:
        window_id = _window_id_from_decoded_root(decoded_root)

        for batch_dir in sorted(decoded_root.glob("batch_*")):
            outcome_path = batch_dir / CONTRACT_OUTCOME_FILE

            if not outcome_path.exists():
                warnings.append(f"missing outcome file: {outcome_path}")
                continue

            payload = read_json(outcome_path)
            rows = _extract_rows(payload, ["contract_outcome_snapshots", "rows", "data", "items"])

            for index, row in enumerate(rows):
                symbol = _symbol_from_row(row)
                horizon = _horizon_from_row(row)
                strategy_adjusted_return = _strategy_adjusted_return_from_row(row)
                contract_return = _contract_return_from_row(row)
                favorable = _favorable_from_row(row, strategy_adjusted_return)

                stamped = stamp_matrix_metadata(
                    row,
                    source_refs={
                        "source_path": str(outcome_path),
                        "window_id": window_id,
                        "batch_id": batch_dir.name,
                        "row_index": index,
                    },
                )
                metadata = stamped.get(MATRIX_METADATA_KEY) if isinstance(stamped.get(MATRIX_METADATA_KEY), dict) else {}

                outcomes.append(
                    {
                        "window_id": window_id,
                        "batch_id": batch_dir.name,
                        "row_index": index,
                        "symbol": symbol or metadata.get("symbol") or "UNKNOWN",
                        "horizon": horizon if horizon != "unknown" else str(metadata.get("horizon_days") or "unknown"),
                        "strategy_adjusted_return": strategy_adjusted_return,
                        "contract_return": contract_return,
                        "is_favorable": favorable,
                        "source_path": str(outcome_path),
                        "matrix_metadata": metadata,
                        "matrix_metadata_state": stamped.get("matrix_metadata_state"),
                        "matrix_metadata_missing_fields": stamped.get("matrix_metadata_missing_fields") or [],
                        "matrix_cell_key": stamped.get("matrix_cell_key"),
                    }
                )

    return outcomes, warnings


def _load_window_summaries(source_paths: list[Path]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    for source_path in source_paths:
        record = read_json(source_path)
        record["_source_path"] = str(source_path)
        records.append(record)

    return records


def _summarize_group(rows: list[dict[str, Any]], group_field: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in rows:
        key = str(row.get(group_field) or "UNKNOWN")
        grouped[key].append(row)

    summaries: list[dict[str, Any]] = []

    for key, items in grouped.items():
        returns = [
            row["strategy_adjusted_return"]
            for row in items
            if row.get("strategy_adjusted_return") is not None
        ]

        wins = [
            row["is_favorable"]
            for row in items
            if row.get("is_favorable") is not None
        ]

        windows = sorted({row["window_id"] for row in items})
        window_returns: dict[str, list[float]] = defaultdict(list)

        for row in items:
            value = row.get("strategy_adjusted_return")
            if value is not None:
                window_returns[row["window_id"]].append(value)

        positive_windows = 0
        negative_windows = 0

        for values in window_returns.values():
            if not values:
                continue
            average_value = sum(values) / len(values)
            if average_value > 0:
                positive_windows += 1
            elif average_value < 0:
                negative_windows += 1

        total_return = sum(returns) if returns else None
        average_return = round(total_return / len(returns), 6) if returns else None

        summaries.append(
            {
                group_field: key,
                "outcome_count": len(items),
                "return_observation_count": len(returns),
                "win_observation_count": len(wins),
                "win_rate": round(sum(1 for win in wins if win) / len(wins), 6) if wins else None,
                "average_strategy_adjusted_return": average_return,
                "total_strategy_adjusted_return": round(total_return, 6) if total_return is not None else None,
                "min_strategy_adjusted_return": round(min(returns), 6) if returns else None,
                "max_strategy_adjusted_return": round(max(returns), 6) if returns else None,
                "window_count": len(windows),
                "positive_window_count": positive_windows,
                "negative_window_count": negative_windows,
            }
        )

    return summaries


def _window_outcome_summaries(outcomes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = _summarize_group(outcomes, "window_id")

    for summary in summaries:
        window_id = summary["window_id"]
        window_rows = [row for row in outcomes if row["window_id"] == window_id]
        summary["outcome_symbol_count"] = len({row["symbol"] for row in window_rows if row["symbol"] != "UNKNOWN"})

    return sorted(summaries, key=lambda row: str(row["window_id"]), reverse=True)


def _matrix_metadata_diagnostics_summary(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    coverage = matrix_metadata_coverage(outcomes)
    ready_to_build = bool(coverage.get("ready_to_build_exact_matrix_edge_summary"))
    return {
        "matrix_metadata_envelope_key": MATRIX_METADATA_KEY,
        "outcome_record_count": len(outcomes),
        "exact_matrix_cell_ready_record_count": coverage.get("exact_matrix_cell_ready_record_count", 0),
        "needs_review_record_count": coverage.get("needs_review_record_count", 0),
        "mapped_required_field_counts": coverage.get("mapped_required_field_counts", {}),
        "missing_required_field_counts": coverage.get("missing_required_field_counts", {}),
        "ready_to_build_exact_matrix_edge_summary": ready_to_build,
        "recommended_next_step": (
            "build_exact_matrix_edge_summary"
            if ready_to_build
            else "ensure_contract_outcome_snapshots_include_complete_matrix_metadata"
        ),
    }


def _matrix_cell_outcome_summaries(outcomes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ready_rows = [row for row in outcomes if row.get("matrix_cell_key")]
    return _summarize_group(ready_rows, "matrix_cell_key") if ready_rows else []


def _coverage_summary(decoded_roots: list[Path], outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    by_window: list[dict[str, Any]] = []

    total_submitted_symbols = 0
    total_submitted_candidates = 0
    total_outcome_symbol_windows = 0

    for decoded_root in decoded_roots:
        window_id = _window_id_from_decoded_root(decoded_root)
        manifest_summary = _load_manifest_summary(decoded_root)

        outcome_symbols = {
            row["symbol"]
            for row in outcomes
            if row["window_id"] == window_id and row["symbol"] != "UNKNOWN"
        }

        submitted_symbols = manifest_summary["submitted_symbol_count"]
        submitted_candidates = manifest_summary["submitted_candidate_count"]
        outcome_symbol_count = len(outcome_symbols)

        total_submitted_symbols += submitted_symbols
        total_submitted_candidates += submitted_candidates
        total_outcome_symbol_windows += outcome_symbol_count

        denominator = submitted_candidates or submitted_symbols
        coverage_ratio = round(outcome_symbol_count / denominator, 6) if denominator else None

        by_window.append(
            {
                "window_id": window_id,
                "submitted_symbol_count": submitted_symbols,
                "submitted_candidate_count": submitted_candidates,
                "outcome_symbol_count": outcome_symbol_count,
                "outcome_coverage_ratio": coverage_ratio,
                "batch_manifest_count": manifest_summary["batch_manifest_count"],
            }
        )

    total_denominator = total_submitted_candidates or total_submitted_symbols

    return {
        "coverage_interpretation": (
            "Outcome coverage compares unique outcome symbols per window to submitted "
            "candidate count when available, otherwise submitted symbol count."
        ),
        "submitted_symbol_window_count": total_submitted_symbols,
        "submitted_candidate_window_count": total_submitted_candidates,
        "outcome_symbol_window_count": total_outcome_symbol_windows,
        "overall_outcome_coverage_ratio": (
            round(total_outcome_symbol_windows / total_denominator, 6)
            if total_denominator
            else None
        ),
        "by_window": sorted(by_window, key=lambda row: str(row["window_id"]), reverse=True),
    }


def _weak_window_diagnostics(
    window_summaries: list[dict[str, Any]],
    window_outcomes: list[dict[str, Any]],
) -> dict[str, Any]:
    combined_by_window = {
        str(record.get("window_id")): record
        for record in window_summaries
        if record.get("window_id")
    }

    outcome_by_window = {
        str(record.get("window_id")): record
        for record in window_outcomes
        if record.get("window_id")
    }

    window_ids = sorted(set(combined_by_window) | set(outcome_by_window), reverse=True)
    rows: list[dict[str, Any]] = []

    for window_id in window_ids:
        combined = combined_by_window.get(window_id, {})
        outcome = outcome_by_window.get(window_id, {})

        rows.append(
            {
                "window_id": window_id,
                "status": combined.get("status"),
                "historical_edge_state": combined.get("historical_edge_state"),
                "historical_edge_score": _number(combined.get("historical_edge_score")),
                "summary_strategy_adjusted_win_rate": _number(
                    combined.get("strategy_adjusted_win_rate")
                ),
                "summary_average_strategy_adjusted_return": _number(
                    combined.get("average_strategy_adjusted_return")
                ),
                "outcome_average_strategy_adjusted_return": outcome.get(
                    "average_strategy_adjusted_return"
                ),
                "outcome_min_strategy_adjusted_return": outcome.get(
                    "min_strategy_adjusted_return"
                ),
                "outcome_count": _integer(
                    combined.get("contract_outcome_count") or outcome.get("outcome_count")
                ),
                "outcome_symbol_count": _integer(
                    combined.get("symbol_count") or outcome.get("outcome_symbol_count")
                ),
            }
        )

    weak_rows = sorted(
        rows,
        key=lambda row: (
            row["summary_average_strategy_adjusted_return"]
            if row["summary_average_strategy_adjusted_return"] is not None
            else 999999.0
        ),
    )

    non_positive_rows = [
        row
        for row in rows
        if row["historical_edge_state"] != "historical_positive_edge_candidate"
        or (
            row["summary_average_strategy_adjusted_return"] is not None
            and row["summary_average_strategy_adjusted_return"] < 0
        )
    ]

    return {
        "weakest_windows_by_summary_average_return": weak_rows[:10],
        "non_positive_or_negative_average_windows": non_positive_rows,
    }


def build_historical_edge_validation_diagnostics(
    *,
    decoded_window_roots: list[Path],
    window_summary_records: list[dict[str, Any]] | None = None,
    period_id: str | None = None,
    worst_outcome_limit: int = 50,
    symbol_limit: int = 50,
) -> dict[str, Any]:
    window_summary_records = window_summary_records or []

    outcomes, warnings = _load_normalized_outcomes(decoded_window_roots)

    symbol_summaries = _summarize_group(outcomes, "symbol")
    horizon_summaries = _summarize_group(outcomes, "horizon")
    window_outcomes = _window_outcome_summaries(outcomes)
    matrix_metadata_diagnostics_summary = _matrix_metadata_diagnostics_summary(outcomes)
    matrix_cell_outcome_summaries = _matrix_cell_outcome_summaries(outcomes)

    symbol_summaries_known = [
        row for row in symbol_summaries if row.get("symbol") != "UNKNOWN"
    ]

    top_positive_symbols = sorted(
        symbol_summaries_known,
        key=lambda row: row.get("total_strategy_adjusted_return")
        if row.get("total_strategy_adjusted_return") is not None
        else -999999.0,
        reverse=True,
    )[:symbol_limit]

    top_negative_symbols = sorted(
        symbol_summaries_known,
        key=lambda row: row.get("total_strategy_adjusted_return")
        if row.get("total_strategy_adjusted_return") is not None
        else 999999.0,
    )[:symbol_limit]

    worst_outcomes = sorted(
        [
            row
            for row in outcomes
            if row.get("strategy_adjusted_return") is not None
        ],
        key=lambda row: row["strategy_adjusted_return"],
    )[:worst_outcome_limit]

    best_outcomes = sorted(
        [
            row
            for row in outcomes
            if row.get("strategy_adjusted_return") is not None
        ],
        key=lambda row: row["strategy_adjusted_return"],
        reverse=True,
    )[:worst_outcome_limit]

    total_abs_symbol_return = sum(
        abs(row["total_strategy_adjusted_return"])
        for row in symbol_summaries_known
        if row.get("total_strategy_adjusted_return") is not None
    )
    top_10_abs_symbol_return = sum(
        abs(row["total_strategy_adjusted_return"])
        for row in sorted(
            [
                row
                for row in symbol_summaries_known
                if row.get("total_strategy_adjusted_return") is not None
            ],
            key=lambda row: abs(row["total_strategy_adjusted_return"]),
            reverse=True,
        )[:10]
    )

    concentration_ratio = (
        round(top_10_abs_symbol_return / total_abs_symbol_return, 6)
        if total_abs_symbol_return
        else None
    )

    coverage = _coverage_summary(decoded_window_roots, outcomes)

    diagnostics = {
        "adapter_type": "historical_edge_validation_diagnostics_builder",
        "artifact_type": "signalforge_historical_edge_validation_diagnostics",
        "schema_version": "signalforge_historical_edge_validation_diagnostics.v1",
        "period_id": period_id,
        "status": "ready" if decoded_window_roots and not warnings else "needs_review",
        "is_ready": bool(decoded_window_roots) and not warnings,
        "decoded_window_count": len(decoded_window_roots),
        "outcome_record_count": len(outcomes),
        "unique_outcome_symbol_count": len(
            {row["symbol"] for row in outcomes if row["symbol"] != "UNKNOWN"}
        ),
        "horizon_count": len({row["horizon"] for row in outcomes}),
        "coverage_summary": coverage,
        "weak_window_diagnostics": _weak_window_diagnostics(
            window_summary_records,
            window_outcomes,
        ),
        "symbol_concentration_summary": {
            "symbol_count": len(symbol_summaries_known),
            "top_10_absolute_return_contribution_ratio": concentration_ratio,
            "interpretation": (
                "Contribution ratio is based on absolute summed strategy-adjusted "
                "outcome returns, not executed portfolio PnL."
            ),
        },
        "top_positive_symbols": top_positive_symbols,
        "top_negative_symbols": top_negative_symbols,
        "horizon_sensitivity_summary": sorted(
            horizon_summaries,
            key=lambda row: (
                _integer(row.get("horizon")) if str(row.get("horizon")).isdigit() else 999999
            ),
        ),
        "window_outcome_summaries": window_outcomes,
        "matrix_metadata_diagnostics_summary": matrix_metadata_diagnostics_summary,
        "matrix_cell_outcome_summaries": matrix_cell_outcome_summaries,
        "ready_to_build_exact_matrix_edge_summary": matrix_metadata_diagnostics_summary.get("ready_to_build_exact_matrix_edge_summary", False),
        "exact_matrix_cell_ready_record_count": matrix_metadata_diagnostics_summary.get("exact_matrix_cell_ready_record_count", 0),
        "worst_outcomes": worst_outcomes,
        "best_outcomes": best_outcomes,
        "warnings": warnings,
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
        "automatic_action": None,
        "automatic_close_order": None,
        "automatic_defense_order": None,
        "automatic_roll_order": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
    }

    return diagnostics

