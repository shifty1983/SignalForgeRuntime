from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Phase6PortfolioReconstructionQcManifestResult:
    manifest: dict[str, Any]


def read_json(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    with path.open("r", encoding="utf-8-sig") as f:
        value = json.load(f)

    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object at {path}")

    return value


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")


def _coerce_float(value: Any) -> float | None:
    if value is None or value == "":
        return None

    if isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None

    text = str(value).strip().replace(",", "")
    if not text:
        return None

    try:
        parsed = float(text)
    except ValueError:
        return None

    return parsed if math.isfinite(parsed) else None


def _coerce_int(value: Any) -> int | None:
    if value is None or value == "":
        return None

    if isinstance(value, bool):
        return None

    if isinstance(value, int):
        return value

    if isinstance(value, float) and value.is_integer():
        return int(value)

    text = str(value).strip()
    if not text:
        return None

    try:
        return int(text)
    except ValueError:
        return None


def _is_ready(payload: dict[str, Any]) -> bool:
    return bool(payload.get("is_ready")) and _coerce_int(payload.get("blocker_count")) == 0


def build_phase6_portfolio_reconstruction_qc_manifest(
    *,
    selected_trade_sequence_summary: dict[str, Any],
    position_sizing_summary: dict[str, Any],
    equity_reconstruction_summary: dict[str, Any],
    metrics_report: dict[str, Any],
    output_dir: str | Path,
) -> Phase6PortfolioReconstructionQcManifestResult:
    output_dir = Path(output_dir)
    blockers: list[str] = []
    warnings: list[str] = []

    if not _is_ready(selected_trade_sequence_summary):
        blockers.append("selected_trade_sequence_not_ready")

    if not _is_ready(position_sizing_summary):
        blockers.append("position_sizing_replay_not_ready")

    if not _is_ready(equity_reconstruction_summary):
        blockers.append("equity_reconstruction_not_ready")

    if not _is_ready(metrics_report):
        blockers.append("portfolio_metrics_report_not_ready")

    sequence_count = _coerce_int(
        selected_trade_sequence_summary.get("sequenced_trade_count")
    )
    sequence_input_count = _coerce_int(
        selected_trade_sequence_summary.get("input_selection_row_count")
    )
    sequence_usable_count = _coerce_int(
        selected_trade_sequence_summary.get("portfolio_usable_trade_count")
    )

    sizing_input_count = _coerce_int(
        position_sizing_summary.get("input_sequence_row_count")
    )
    sized_trade_count = _coerce_int(position_sizing_summary.get("sized_trade_count"))
    sizing_skipped_count = _coerce_int(
        position_sizing_summary.get("skipped_sequence_row_count")
    )

    equity_input_count = _coerce_int(
        equity_reconstruction_summary.get("input_position_sizing_row_count")
    )
    equity_sized_trade_count = _coerce_int(
        equity_reconstruction_summary.get("sized_trade_count")
    )
    equity_curve_row_count = _coerce_int(
        equity_reconstruction_summary.get("equity_curve_row_count")
    )

    metrics_trade_count = _coerce_int(
        metrics_report.get("trade_metrics", {}).get("trade_count")
    )
    metrics_equity_curve_row_count = _coerce_int(
        metrics_report.get("data_quality", {}).get("input_equity_curve_row_count")
    )
    metrics_sized_trade_count = _coerce_int(
        metrics_report.get("data_quality", {}).get("sized_trade_count")
    )

    if sequence_count is None or sequence_count <= 0:
        blockers.append("invalid_sequence_count")

    if sequence_input_count is not None and sequence_count is not None:
        if sequence_input_count != sequence_count:
            blockers.append("selection_input_sequence_count_mismatch")

    if sizing_input_count is not None and sequence_count is not None:
        if sizing_input_count != sequence_count:
            blockers.append("sizing_input_sequence_count_mismatch")

    if sized_trade_count is None or sized_trade_count <= 0:
        blockers.append("invalid_sized_trade_count")

    if sizing_skipped_count is None:
        blockers.append("missing_sizing_skipped_count")

    if (
        sized_trade_count is not None
        and sizing_skipped_count is not None
        and sizing_input_count is not None
    ):
        if sized_trade_count + sizing_skipped_count != sizing_input_count:
            blockers.append("sized_plus_skipped_count_mismatch")

    if equity_input_count is not None and sizing_input_count is not None:
        if equity_input_count != sizing_input_count:
            blockers.append("equity_input_sizing_count_mismatch")

    if equity_sized_trade_count is not None and sized_trade_count is not None:
        if equity_sized_trade_count != sized_trade_count:
            blockers.append("equity_sized_trade_count_mismatch")

    if metrics_trade_count is not None and sized_trade_count is not None:
        if metrics_trade_count != sized_trade_count:
            blockers.append("metrics_trade_count_mismatch")

    if metrics_sized_trade_count is not None and sized_trade_count is not None:
        if metrics_sized_trade_count != sized_trade_count:
            blockers.append("metrics_sized_trade_count_mismatch")

    if equity_curve_row_count is None or equity_curve_row_count <= 0:
        blockers.append("invalid_equity_curve_row_count")

    if (
        metrics_equity_curve_row_count is not None
        and equity_curve_row_count is not None
        and metrics_equity_curve_row_count != equity_curve_row_count
    ):
        blockers.append("metrics_equity_curve_row_count_mismatch")

    starting_equity = _coerce_float(metrics_report.get("overview", {}).get("starting_equity"))
    ending_equity = _coerce_float(metrics_report.get("overview", {}).get("ending_equity"))
    total_return_pct = _coerce_float(
        metrics_report.get("overview", {}).get("total_return_pct")
    )
    cagr = _coerce_float(metrics_report.get("overview", {}).get("cagr"))
    max_drawdown_pct = _coerce_float(
        metrics_report.get("risk_metrics", {}).get("max_drawdown_pct")
    )
    profit_factor = _coerce_float(
        metrics_report.get("trade_metrics", {}).get("profit_factor")
    )
    win_rate = _coerce_float(metrics_report.get("trade_metrics", {}).get("win_rate"))
    annualized_sharpe = _coerce_float(
        metrics_report.get("daily_metrics", {}).get("annualized_sharpe")
    )
    annualized_sortino = _coerce_float(
        metrics_report.get("daily_metrics", {}).get("annualized_sortino")
    )

    if starting_equity is None or starting_equity <= 0:
        blockers.append("invalid_metrics_starting_equity")

    if ending_equity is None or ending_equity <= 0:
        blockers.append("invalid_metrics_ending_equity")

    if total_return_pct is None:
        blockers.append("missing_total_return_pct")

    if cagr is None:
        blockers.append("missing_cagr")

    if max_drawdown_pct is None or max_drawdown_pct > 0:
        blockers.append("invalid_max_drawdown_pct")

    if profit_factor is None or profit_factor <= 0:
        blockers.append("invalid_profit_factor")

    if win_rate is None or win_rate < 0 or win_rate > 1:
        blockers.append("invalid_win_rate")

    if annualized_sharpe is None:
        blockers.append("missing_annualized_sharpe")

    if annualized_sortino is None:
        blockers.append("missing_annualized_sortino")

    equity_recognition_policy = equity_reconstruction_summary.get("equity_recognition_policy")
    if equity_recognition_policy != "realize_pnl_on_portfolio_realization_date_outcome_availability_date":
        blockers.append("unexpected_equity_recognition_policy")

    equity_realization_sources = equity_reconstruction_summary.get(
        "realization_date_source_counts",
        {},
    )
    equity_outcome_date_count = _coerce_int(
        equity_realization_sources.get("source_row.selected_outcome_availability_date")
    )
    if (
        sized_trade_count is not None
        and equity_outcome_date_count is not None
        and equity_outcome_date_count != sized_trade_count
    ):
        blockers.append("equity_realization_date_source_count_mismatch")

    if equity_realization_sources.get("decision_date_fallback"):
        blockers.append("equity_curve_uses_decision_date_fallback")

    non_positive_equity_row_count = _coerce_int(
        position_sizing_summary.get("non_positive_equity_row_count")
    )
    if non_positive_equity_row_count is None:
        blockers.append("missing_non_positive_equity_row_count")
    elif non_positive_equity_row_count != 0:
        blockers.append("non_positive_equity_rows_detected")

    leakage_flag_counts = position_sizing_summary.get("leakage_flag_counts", {})
    if leakage_flag_counts:
        blockers.append("leakage_flags_detected")

    return_bound_violation_counts = position_sizing_summary.get(
        "return_bound_violation_counts", {}
    )
    if return_bound_violation_counts:
        warnings.append("return_bound_violations_were_skipped")

    skipped_position_sizing_count = _coerce_int(
        metrics_report.get("data_quality", {}).get("skipped_position_sizing_row_count")
    )
    if skipped_position_sizing_count and skipped_position_sizing_count > 0:
        warnings.append("skipped_rows_present_by_design")

    manifest_path = output_dir / "signalforge_phase6_portfolio_reconstruction_qc_manifest.json"

    manifest = {
        "adapter_type": "phase6_portfolio_reconstruction_qc_manifest_builder",
        "artifact_type": "signalforge_phase6_portfolio_reconstruction_qc_manifest",
        "contract": "phase6_portfolio_reconstruction_qc_manifest",
        "is_ready": len(blockers) == 0,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "warning_count": len(warnings),
        "warnings": warnings,
        "phase6_completion": {
            "selected_trades_are_sequenced": _is_ready(selected_trade_sequence_summary),
            "position_sizing_is_applied": _is_ready(position_sizing_summary),
            "portfolio_equity_curve_is_produced": _is_ready(
                equity_reconstruction_summary
            ),
            "drawdown_and_return_metrics_are_calculated": _is_ready(metrics_report),
        },
        "row_count_reconciliation": {
            "strategy_selection_input_rows": sequence_input_count,
            "sequenced_trade_count": sequence_count,
            "portfolio_usable_trade_count": sequence_usable_count,
            "position_sizing_input_rows": sizing_input_count,
            "sized_trade_count": sized_trade_count,
            "skipped_position_sizing_rows": sizing_skipped_count,
            "equity_input_position_sizing_rows": equity_input_count,
            "equity_sized_trade_count": equity_sized_trade_count,
            "equity_curve_row_count": equity_curve_row_count,
            "metrics_trade_count": metrics_trade_count,
            "metrics_sized_trade_count": metrics_sized_trade_count,
            "metrics_equity_curve_row_count": metrics_equity_curve_row_count,
        },
        "performance_summary": {
            "starting_equity": starting_equity,
            "ending_equity": ending_equity,
            "total_return_pct": total_return_pct,
            "cagr": cagr,
            "max_drawdown_pct": max_drawdown_pct,
            "max_drawdown_date": metrics_report.get("risk_metrics", {}).get(
                "max_drawdown_date"
            ),
            "profit_factor": profit_factor,
            "win_rate": win_rate,
            "annualized_sharpe": annualized_sharpe,
            "annualized_sortino": annualized_sortino,
            "trade_count": metrics_trade_count,
        },
        "data_quality": {
            "non_positive_equity_row_count": non_positive_equity_row_count,
            "leakage_flag_counts": leakage_flag_counts,
            "return_bound_violation_counts": return_bound_violation_counts,
            "sizing_skip_reason_counts": metrics_report.get("data_quality", {}).get(
                "sizing_skip_reason_counts", {}
            ),
            "equity_recognition_policy": equity_recognition_policy,
            "equity_realization_date_source_counts": equity_realization_sources,
        },
        "source_readiness": {
            "selected_trade_sequence_ready": selected_trade_sequence_summary.get(
                "is_ready"
            ),
            "position_sizing_ready": position_sizing_summary.get("is_ready"),
            "equity_reconstruction_ready": equity_reconstruction_summary.get(
                "is_ready"
            ),
            "metrics_report_ready": metrics_report.get("is_ready"),
        },
        "depends_on": {
            "selected_trade_sequence_summary": "portfolio_selected_trade_sequence_summary",
            "position_sizing_summary": "portfolio_position_sizing_replay_summary",
            "equity_reconstruction_summary": "portfolio_equity_reconstruction_summary",
            "metrics_report": "portfolio_metrics_report",
        },
        "paths": {
            "manifest_path": str(manifest_path),
        },
        "explicit_exclusions": [
            "new_strategy_selection_logic",
            "new_expectancy_calculation",
            "parameter_optimization",
            "broker_execution",
            "live_orders",
            "slippage_modeling",
            "open_position_overlap_modeling",
            "mark_to_market_open_positions",
            "calendar_day_gap_fill",
            "cash_interest",
            "fees_and_commissions",
            "taxes",
            "live_broker_reconciliation",
        ],
    }

    write_json(manifest_path, manifest)

    return Phase6PortfolioReconstructionQcManifestResult(manifest=manifest)


def build_from_paths(
    *,
    selected_trade_sequence_summary_path: str | Path,
    position_sizing_summary_path: str | Path,
    equity_reconstruction_summary_path: str | Path,
    metrics_report_path: str | Path,
    output_dir: str | Path,
) -> Phase6PortfolioReconstructionQcManifestResult:
    return build_phase6_portfolio_reconstruction_qc_manifest(
        selected_trade_sequence_summary=read_json(selected_trade_sequence_summary_path),
        position_sizing_summary=read_json(position_sizing_summary_path),
        equity_reconstruction_summary=read_json(equity_reconstruction_summary_path),
        metrics_report=read_json(metrics_report_path),
        output_dir=output_dir,
    )
