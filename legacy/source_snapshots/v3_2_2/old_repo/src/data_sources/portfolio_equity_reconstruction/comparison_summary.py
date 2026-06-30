from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable
import json
import re

from src.signalforge.engines.strategy_selection.historical_replay_matrix_metadata_stamp import (
    MATRIX_METADATA_KEY,
    REQUIRED_MATRIX_METADATA_FIELDS,
    matrix_metadata_coverage,
    stamp_matrix_metadata,
    validate_matrix_metadata_record,
)


EXPLICIT_EXCLUSIONS = [
    "broker_api_calls",
    "order_routing",
    "order_submission",
    "fills",
    "live_execution",
    "slippage_modeling",
    "automatic_close_orders",
    "automatic_roll_orders",
    "automatic_defense_orders",
    "automatic_strategy_changes",
    "automatic_parameter_changes",
    "automatic_pause_actions",
]


RECONSTRUCTION_FILE = "signalforge_portfolio_equity_reconstruction.json"


def read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def discover_reconstruction_sources(paths: Iterable[str | Path]) -> list[Path]:
    discovered: list[Path] = []

    for raw_path in paths:
        path = Path(raw_path)

        if not path.exists():
            continue

        if path.is_file():
            discovered.append(path)
            continue

        if path.is_dir():
            direct = path / RECONSTRUCTION_FILE
            if direct.exists():
                discovered.append(direct)
            else:
                discovered.extend(sorted(path.rglob(RECONSTRUCTION_FILE)))

    return sorted(dict.fromkeys(discovered), key=lambda item: str(item))



def _metadata_from_scenario(
    *,
    reconstruction: dict[str, Any],
    scenario: dict[str, Any],
) -> dict[str, Any]:
    metadata: dict[str, Any] = {}

    reconstruction_metadata = reconstruction.get(MATRIX_METADATA_KEY)
    if isinstance(reconstruction_metadata, dict):
        metadata.update(reconstruction_metadata)

    scenario_metadata = scenario.get(MATRIX_METADATA_KEY)
    if isinstance(scenario_metadata, dict):
        metadata.update(scenario_metadata)

    if scenario.get("horizon") not in (None, ""):
        metadata.setdefault("horizon_days", scenario.get("horizon"))

    return metadata


def _matrix_metadata_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    coverage = matrix_metadata_coverage(records)
    missing_field_counts: dict[str, int] = {field: 0 for field in REQUIRED_MATRIX_METADATA_FIELDS}
    matrix_cell_counts: dict[str, int] = {}
    blocked_reasons: list[str] = []

    for record in records:
        validation = validate_matrix_metadata_record(record)
        matrix_cell_key = validation.get("matrix_cell_key")
        if matrix_cell_key:
            matrix_cell_counts[str(matrix_cell_key)] = matrix_cell_counts.get(str(matrix_cell_key), 0) + 1
        for field in validation.get("matrix_metadata_missing_fields") or []:
            missing_field_counts[str(field)] = missing_field_counts.get(str(field), 0) + 1
        blocked_reasons.extend(str(reason) for reason in validation.get("blocked_reasons") or [])

    ready_to_build = bool(coverage.get("ready_to_build_exact_matrix_edge_summary"))
    if not records:
        state = "blocked"
        recommended_next_step = "provide_portfolio_reconstruction_scenarios"
    elif ready_to_build:
        state = "ready"
        recommended_next_step = "patch_portfolio_candidate_selection_summary_matrix_metadata"
    else:
        state = "needs_review"
        recommended_next_step = "populate_matrix_metadata_before_portfolio_candidate_selection"

    return {
        "matrix_metadata_envelope_key": MATRIX_METADATA_KEY,
        "matrix_cell_key_fields": list(REQUIRED_MATRIX_METADATA_FIELDS),
        "matrix_metadata_state": state,
        "total_record_count": len(records),
        "exact_matrix_cell_ready_record_count": int(coverage.get("exact_matrix_cell_ready_record_count") or 0),
        "needs_review_record_count": int(coverage.get("needs_review_record_count") or 0),
        "ready_to_build_exact_matrix_edge_summary": ready_to_build,
        "mapped_required_field_counts": coverage.get("mapped_required_field_counts") or {},
        "missing_required_field_counts": coverage.get("missing_required_field_counts") or {},
        "missing_field_counts": {k: v for k, v in sorted(missing_field_counts.items()) if v},
        "matrix_cell_count": len(matrix_cell_counts),
        "matrix_cell_counts": dict(sorted(matrix_cell_counts.items())),
        "blocked_reasons": sorted(dict.fromkeys(blocked_reasons)),
        "recommended_next_step": recommended_next_step,
    }

def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _integer(value: Any) -> int:
    number = _number(value)
    if number is None:
        return 0
    return int(number)


def _variant_id(source_path: str | Path, period_id: str | None = None) -> str:
    parent = Path(source_path).parent.name

    if period_id:
        prefix = f"portfolio_equity_reconstruction_{period_id}_"
        if parent.startswith(prefix):
            return parent.replace(prefix, "", 1)

    return parent


def _variant_type(variant_id: str, scenarios: list[dict[str, Any]]) -> str:
    lowered = variant_id.lower()

    if "uncapped" in lowered or "tail_stress" in lowered:
        return "tail_stress"

    for scenario in scenarios:
        min_cap = _number(scenario.get("min_return_cap"))
        max_cap = _number(scenario.get("max_return_cap"))
        if min_cap is not None and max_cap is not None and min_cap <= -999 and max_cap >= 999:
            return "tail_stress"

    if "ex_" in lowered or "exclude" in lowered or "overlay" in lowered:
        return "risk_overlay"

    return "baseline"


def _scenario_record(
    *,
    source_path: str | Path,
    period_id: str | None,
    reconstruction: dict[str, Any],
    scenario: dict[str, Any],
) -> dict[str, Any]:
    variant_id = _variant_id(source_path, period_id)
    variant_type = _variant_type(variant_id, reconstruction.get("scenario_summaries") or [])

    max_drawdown = _number(scenario.get("max_drawdown"))
    annualized_return = _number(scenario.get("annualized_return"))
    sharpe_ratio = _number(scenario.get("sharpe_ratio"))
    sortino_ratio = _number(scenario.get("sortino_ratio"))
    total_return = _number(scenario.get("total_return"))

    # Balanced score is only a comparison heuristic. It is not a trading signal.
    balanced_score = None
    if annualized_return is not None:
        balanced_score = annualized_return
        if sharpe_ratio is not None:
            balanced_score += 0.10 * sharpe_ratio
        if max_drawdown is not None:
            balanced_score += max_drawdown

    record = {
        "variant_id": variant_id,
        "variant_type": variant_type,
        "source_path": str(source_path),
        "period_id": reconstruction.get("period_id") or period_id,
        "scenario_id": scenario.get("scenario_id"),
        "horizon": str(scenario.get("horizon")),
        "starting_equity": _number(scenario.get("starting_equity")),
        "ending_equity": _number(scenario.get("ending_equity")),
        "total_return": total_return,
        "annualized_return": annualized_return,
        "max_drawdown": max_drawdown,
        "sortino_ratio": sortino_ratio,
        "sharpe_ratio": sharpe_ratio,
        "calmar_ratio": _number(scenario.get("calmar_ratio")),
        "trade_count": _integer(scenario.get("trade_count")),
        "exit_day_count": _integer(scenario.get("exit_day_count")),
        "win_rate": _number(scenario.get("win_rate")),
        "profit_factor": _number(scenario.get("profit_factor")),
        "tail_capped_trade_count": _integer(scenario.get("tail_capped_trade_count")),
        "max_active_trade_count": _integer(scenario.get("max_active_trade_count")),
        "max_active_risk_fraction": _number(scenario.get("max_active_risk_fraction")),
        "max_active_risk_date": scenario.get("max_active_risk_date"),
        "average_active_risk_fraction": _number(scenario.get("average_active_risk_fraction")),
        "min_return_cap": _number(scenario.get("min_return_cap")),
        "max_return_cap": _number(scenario.get("max_return_cap")),
        "excluded_symbols": scenario.get("excluded_symbols") or [],
        "balanced_score": round(balanced_score, 6) if balanced_score is not None else None,
        "is_investable_model": variant_type != "tail_stress",
    }

    return stamp_matrix_metadata(
        record,
        metadata=_metadata_from_scenario(reconstruction=reconstruction, scenario=scenario),
        source_refs={
            "horizon_days": "portfolio_equity_reconstruction.scenario_summaries.horizon",
        },
    )


def _rank(
    records: list[dict[str, Any]],
    field: str,
    *,
    descending: bool = True,
    investable_only: bool = True,
    limit: int = 10,
) -> list[dict[str, Any]]:
    candidates = records

    if investable_only:
        candidates = [record for record in candidates if record.get("is_investable_model")]

    candidates = [
        record
        for record in candidates
        if record.get(field) is not None
    ]

    return sorted(
        candidates,
        key=lambda record: record[field],
        reverse=descending,
    )[:limit]


def _by_horizon_comparison(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    horizons = sorted(
        {record["horizon"] for record in records},
        key=lambda value: int(value) if str(value).isdigit() else 999999,
    )

    rows: list[dict[str, Any]] = []

    for horizon in horizons:
        horizon_records = [
            record for record in records if str(record.get("horizon")) == str(horizon)
        ]

        baseline = next(
            (
                record
                for record in horizon_records
                if record["variant_type"] == "baseline"
            ),
            None,
        )

        for record in sorted(horizon_records, key=lambda item: item["variant_id"]):
            delta_vs_baseline = {}

            if baseline and record is not baseline:
                for field in [
                    "ending_equity",
                    "total_return",
                    "annualized_return",
                    "max_drawdown",
                    "sharpe_ratio",
                    "sortino_ratio",
                    "win_rate",
                    "trade_count",
                ]:
                    left = _number(record.get(field))
                    right = _number(baseline.get(field))
                    delta_vs_baseline[field] = (
                        round(left - right, 6)
                        if left is not None and right is not None
                        else None
                    )

            rows.append(
                {
                    **record,
                    "delta_vs_baseline": delta_vs_baseline,
                }
            )

    return rows


def _stress_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    stress_records = [record for record in records if record["variant_type"] == "tail_stress"]

    wiped_out = [
        record
        for record in stress_records
        if record.get("ending_equity") is not None and record["ending_equity"] <= 0
    ]

    return {
        "tail_stress_scenario_count": len(stress_records),
        "tail_stress_wipeout_count": len(wiped_out),
        "tail_stress_wipeouts": wiped_out,
        "stress_interpretation": (
            "Tail-stress variants are diagnostic only. They are not the defined-risk "
            "portfolio model when min/max return caps are disabled."
        ),
    }


def build_portfolio_equity_reconstruction_comparison_summary(
    reconstructions: list[dict[str, Any]],
    *,
    source_paths: list[str | Path],
    period_id: str | None = None,
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []

    for index, reconstruction in enumerate(reconstructions):
        source_path = source_paths[index]

        for scenario in reconstruction.get("scenario_summaries") or []:
            records.append(
                _scenario_record(
                    source_path=source_path,
                    period_id=period_id,
                    reconstruction=reconstruction,
                    scenario=scenario,
                )
            )

    investable_records = [record for record in records if record["is_investable_model"]]
    matrix_metadata_comparison_summary = _matrix_metadata_summary(records)

    return {
        "adapter_type": "portfolio_equity_reconstruction_comparison_summary_builder",
        "artifact_type": "signalforge_portfolio_equity_reconstruction_comparison_summary",
        "schema_version": "signalforge_portfolio_equity_reconstruction_comparison_summary.v1",
        "period_id": period_id,
        "status": "ready" if records else "blocked",
        "is_ready": bool(records),
        "reconstruction_source_count": len(reconstructions),
        "scenario_count": len(records),
        "investable_scenario_count": len(investable_records),
        "variant_ids": sorted({record["variant_id"] for record in records}),
        "variant_types": sorted({record["variant_type"] for record in records}),
        "best_by_total_return": _rank(records, "total_return", descending=True),
        "best_by_annualized_return": _rank(records, "annualized_return", descending=True),
        "best_by_sharpe": _rank(records, "sharpe_ratio", descending=True),
        "best_by_sortino": _rank(records, "sortino_ratio", descending=True),
        "best_by_lowest_drawdown": _rank(records, "max_drawdown", descending=True),
        "best_by_balanced_score": _rank(records, "balanced_score", descending=True),
        "by_horizon_comparison": _by_horizon_comparison(records),
        "tail_stress_summary": _stress_summary(records),
        "scenario_records": records,
        "matrix_metadata_comparison_summary": matrix_metadata_comparison_summary,
        "exact_matrix_cell_ready_record_count": matrix_metadata_comparison_summary.get("exact_matrix_cell_ready_record_count", 0),
        "matrix_metadata_needs_review_record_count": matrix_metadata_comparison_summary.get("needs_review_record_count", 0),
        "ready_to_build_exact_matrix_edge_summary": matrix_metadata_comparison_summary.get("ready_to_build_exact_matrix_edge_summary", False),
        "recommended_next_step": matrix_metadata_comparison_summary.get("recommended_next_step"),
        "selection_guidance": {
            "return_leader": _rank(records, "annualized_return", descending=True, limit=1),
            "risk_adjusted_leader": _rank(records, "sharpe_ratio", descending=True, limit=1),
            "drawdown_leader": _rank(records, "max_drawdown", descending=True, limit=1),
            "interpretation": (
                "Use the comparison summary as a ranking aid, not as final approval. "
                "Portfolio reconstruction is realized exit-date synthetic performance and "
                "does not model broker fills, slippage, or intraperiod mark-to-market."
            ),
        },
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
        "automatic_action": None,
        "automatic_close_order": None,
        "automatic_defense_order": None,
        "automatic_roll_order": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
    }
