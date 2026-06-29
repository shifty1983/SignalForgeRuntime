from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from src.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS


HISTORICAL_EDGE_MATRIX_COVERAGE_AUDIT_SCHEMA_VERSION = (
    "signalforge_historical_edge_matrix_coverage_audit.v1"
)

COVERED_CAPABILITIES = [
    "historical_edge_matrix_coverage_audit",
    "historical_evidence_mapping_dimension_review",
    "portfolio_edge_to_strategy_matrix_gap_detection",
    "matrix_cell_edge_validation_readiness_check",
]

DEPENDS_ON_CAPABILITIES = [
    "strategy_matrix_edge_inventory",
    "historical_edge_validation",
    "historical_edge_diagnostics",
    "portfolio_candidate_selection",
    "quantconnect_historical_replay_plan",
]

REQUIRED_EXACT_MATRIX_DIMENSIONS = [
    "regime",
    "asset_behavior",
    "option_behavior",
    "strategy",
    "symbol",
    "horizon",
]

OPTIONAL_USEFUL_DIMENSIONS = [
    "asset_class",
    "direction",
    "risk_structure",
    "window",
    "outcome",
    "score",
]

DIMENSION_KEYS: dict[str, tuple[str, ...]] = {
    "regime": (
        "regime",
        "regime_state",
        "regime_label",
        "market_regime",
        "regime_classification",
        "regime_bucket",
    ),
    "asset_behavior": (
        "asset_behavior",
        "asset_behavior_state",
        "asset_behavior_label",
        "behavior_state",
        "asset_setup",
        "trend_behavior",
        "price_behavior",
    ),
    "option_behavior": (
        "option_behavior",
        "option_behavior_state",
        "option_behavior_label",
        "iv_behavior",
        "implied_volatility_behavior",
        "volatility_behavior",
        "skew_behavior",
        "term_structure_behavior",
        "liquidity_state",
        "option_liquidity_state",
    ),
    "strategy": (
        "strategy",
        "strategy_id",
        "strategy_family",
        "strategy_name",
        "option_strategy",
        "option_strategy_id",
        "setup_strategy",
    ),
    "symbol": (
        "symbol",
        "underlying_symbol",
        "ticker",
        "asset_symbol",
    ),
    "horizon": (
        "horizon",
        "horizon_days",
        "target_horizon_days",
        "holding_period_days",
        "fixed_horizon_days",
    ),
    "asset_class": (
        "asset_class",
        "instrument_type",
        "security_type",
    ),
    "direction": (
        "direction",
        "strategy_direction",
        "bias",
        "market_bias",
        "setup_direction",
    ),
    "risk_structure": (
        "risk_structure",
        "risk_profile",
        "defined_risk",
        "variant_id",
        "scenario_id",
    ),
    "window": (
        "window",
        "window_id",
        "period_id",
        "batch_id",
    ),
    "outcome": (
        "strategy_adjusted_return",
        "contract_return",
        "total_return",
        "win_rate",
        "is_favorable",
        "historical_edge_state",
    ),
    "score": (
        "historical_edge_score",
        "risk_adjusted_edge_score",
        "primary_score",
        "score",
        "conservative_score",
        "aggressive_score",
    ),
}

RECORD_CONTAINER_KEYS = (
    "strategy_edge_items",
    "historical_edge_items",
    "edge_items",
    "candidate_rows",
    "portfolio_candidate_rows",
    "window_summaries",
    "window_outcome_summaries",
    "horizon_sensitivity_summary",
    "best_outcomes",
    "worst_outcomes",
    "top_positive_symbols",
    "top_negative_symbols",
    "rows",
    "items",
    "data",
)

POSITIVE_EDGE_STATES = {
    "historical_positive_edge_candidate",
    "positive_edge_candidate",
    "validated_positive_edge",
    "edge_validated",
    "ready",
}

PORTFOLIO_EDGE_ARTIFACT_TYPES = {
    "signalforge_portfolio_candidate_selection_summary",
    "signalforge_portfolio_equity_reconstruction_summary",
    "signalforge_historical_edge_validation_multi_window_summary",
}


SourceInput = tuple[str, Mapping[str, Any] | Sequence[Any] | None]


def build_signalforge_historical_edge_matrix_coverage_audit(
    *,
    strategy_matrix_edge_inventory_source: Mapping[str, Any] | Sequence[Any] | None = None,
    historical_edge_source: Mapping[str, Any] | Sequence[Any] | None = None,
    historical_edge_diagnostics_source: Mapping[str, Any] | Sequence[Any] | None = None,
    portfolio_candidate_selection_source: Mapping[str, Any] | Sequence[Any] | None = None,
    quantconnect_replay_window_plan_source: Mapping[str, Any] | Sequence[Any] | None = None,
    additional_sources: Mapping[str, Any] | Sequence[Any] | None = None,
) -> dict[str, Any]:
    """Audit whether historical evidence can be mapped to strategy matrix cells.

    The audit answers what the historical replay actually carried as evidence:
    regime, asset behavior, option behavior, strategy, symbol, horizon, and
    outcome fields. It does not promote portfolio-level edge to strategy-matrix
    edge. It only reports coverage and the next mapping requirements.
    """

    source_inputs: list[SourceInput] = [
        ("strategy_matrix_edge_inventory", strategy_matrix_edge_inventory_source),
        ("historical_edge", historical_edge_source),
        ("historical_edge_diagnostics", historical_edge_diagnostics_source),
        ("portfolio_candidate_selection", portfolio_candidate_selection_source),
        ("quantconnect_replay_window_plan", quantconnect_replay_window_plan_source),
        ("additional_sources", additional_sources),
    ]

    matrix_summary = _matrix_inventory_summary(strategy_matrix_edge_inventory_source)
    source_audits = [
        _audit_source(source_name=name, source=source)
        for name, source in source_inputs
        if source is not None
    ]

    if not source_audits:
        return _blocked_result(
            blocked_reasons=["missing_historical_edge_sources"],
            matrix_summary=matrix_summary,
        )

    coverage_by_dimension = _coverage_by_dimension(source_audits)
    summary = _coverage_summary(
        matrix_summary=matrix_summary,
        source_audits=source_audits,
        coverage_by_dimension=coverage_by_dimension,
    )
    warnings = _warnings(summary)
    blocked_reasons = _blocked_reasons(summary)
    status = _status(summary=summary, blocked_reasons=blocked_reasons)

    return {
        "artifact_type": "signalforge_historical_edge_matrix_coverage_audit",
        "schema_version": HISTORICAL_EDGE_MATRIX_COVERAGE_AUDIT_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "contract": "historical_edge_matrix_coverage_audit",
        "adapter_type": "historical_edge_matrix_coverage_audit_builder",
        "review_scope": "historical_edge_evidence_mapping_not_contract_selection_or_execution",
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "required_exact_matrix_dimensions": list(REQUIRED_EXACT_MATRIX_DIMENSIONS),
        "optional_useful_dimensions": list(OPTIONAL_USEFUL_DIMENSIONS),
        "matrix_inventory_summary": matrix_summary,
        "source_audits": source_audits,
        "coverage_by_dimension": coverage_by_dimension,
        "coverage_summary": summary,
        "warnings": warnings,
        "blocked_reasons": blocked_reasons,
        "next_build_recommendations": _next_build_recommendations(summary),
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
    matrix_summary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "artifact_type": "signalforge_historical_edge_matrix_coverage_audit",
        "schema_version": HISTORICAL_EDGE_MATRIX_COVERAGE_AUDIT_SCHEMA_VERSION,
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "contract": "historical_edge_matrix_coverage_audit",
        "adapter_type": "historical_edge_matrix_coverage_audit_builder",
        "review_scope": "historical_edge_evidence_mapping_not_contract_selection_or_execution",
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "required_exact_matrix_dimensions": list(REQUIRED_EXACT_MATRIX_DIMENSIONS),
        "optional_useful_dimensions": list(OPTIONAL_USEFUL_DIMENSIONS),
        "matrix_inventory_summary": dict(matrix_summary or {}),
        "source_audits": [],
        "coverage_by_dimension": {},
        "coverage_summary": {
            "source_count": 0,
            "total_record_count": 0,
            "exact_matrix_cell_ready_record_count": 0,
            "portfolio_level_edge_source_count": 0,
            "matrix_mapping_state": "blocked_missing_sources",
        },
        "warnings": [],
        "blocked_reasons": list(blocked_reasons),
        "next_build_recommendations": [
            "provide_historical_edge_or_portfolio_candidate_selection_artifacts_for_coverage_audit",
        ],
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _audit_source(
    *,
    source_name: str,
    source: Mapping[str, Any] | Sequence[Any],
) -> dict[str, Any]:
    source_artifact_type = _source_artifact_type(source)
    source_level_dimensions = _dimensions_present(source if isinstance(source, Mapping) else {})
    records = _extract_records(source)
    record_audits = [_audit_record(record, index=index) for index, record in enumerate(records)]

    record_count = len(record_audits)
    exact_ready_count = sum(1 for record in record_audits if record["exact_matrix_cell_ready"])
    portfolio_edge_evidence_present = _has_positive_portfolio_edge(source)
    source_mapping_state = _source_mapping_state(
        record_count=record_count,
        exact_ready_count=exact_ready_count,
        portfolio_edge_evidence_present=portfolio_edge_evidence_present,
        source_level_dimensions=source_level_dimensions,
    )

    dimension_record_counts = {
        dimension: sum(1 for record in record_audits if dimension in record["present_dimensions"])
        for dimension in list(REQUIRED_EXACT_MATRIX_DIMENSIONS) + list(OPTIONAL_USEFUL_DIMENSIONS)
    }

    return {
        "source_name": source_name,
        "artifact_type": source_artifact_type,
        "record_count": record_count,
        "record_sample_limit": min(record_count, 25),
        "source_level_present_dimensions": sorted(source_level_dimensions),
        "dimension_record_counts": dimension_record_counts,
        "exact_matrix_cell_ready_record_count": exact_ready_count,
        "portfolio_edge_evidence_present": portfolio_edge_evidence_present,
        "positive_edge_state": _positive_edge_state(source),
        "source_mapping_state": source_mapping_state,
        "records_requiring_mapping_count": record_count - exact_ready_count,
        "record_audit_samples": record_audits[:25],
    }


def _audit_record(record: Mapping[str, Any], *, index: int) -> dict[str, Any]:
    present = _dimensions_present(record)
    missing_required = [
        dimension for dimension in REQUIRED_EXACT_MATRIX_DIMENSIONS if dimension not in present
    ]
    exact_ready = not missing_required
    values = {
        dimension: _first_dimension_value(record, dimension)
        for dimension in list(REQUIRED_EXACT_MATRIX_DIMENSIONS) + list(OPTIONAL_USEFUL_DIMENSIONS)
        if dimension in present
    }

    return {
        "record_index": index,
        "present_dimensions": sorted(present),
        "missing_required_dimensions": missing_required,
        "exact_matrix_cell_ready": exact_ready,
        "mapping_state": "exact_matrix_cell_mapping_available"
        if exact_ready
        else "missing_required_matrix_dimensions",
        "dimension_values": values,
    }


def _extract_records(source: Mapping[str, Any] | Sequence[Any]) -> list[Mapping[str, Any]]:
    records: list[Mapping[str, Any]] = []

    if isinstance(source, Mapping):
        for key in RECORD_CONTAINER_KEYS:
            value = source.get(key)
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                records.extend(item for item in value if isinstance(item, Mapping))
        if isinstance(source.get("primary_candidate"), Mapping):
            records.append(source["primary_candidate"])
        if not records:
            records.append(source)
        return records

    if isinstance(source, Sequence) and not isinstance(source, (str, bytes)):
        return [item for item in source if isinstance(item, Mapping)]

    return []


def _dimensions_present(record: Mapping[str, Any]) -> set[str]:
    present: set[str] = set()
    flattened = _flatten_mapping(record)
    for dimension, keys in DIMENSION_KEYS.items():
        if any(key in flattened and _has_value(flattened[key]) for key in keys):
            present.add(dimension)
    return present


def _first_dimension_value(record: Mapping[str, Any], dimension: str) -> Any:
    flattened = _flatten_mapping(record)
    for key in DIMENSION_KEYS.get(dimension, ()):
        if key in flattened and _has_value(flattened[key]):
            return flattened[key]
    return None


def _flatten_mapping(record: Mapping[str, Any]) -> dict[str, Any]:
    flattened: dict[str, Any] = {}

    def visit(value: Any, *, prefix: str = "") -> None:
        if isinstance(value, Mapping):
            for key, nested_value in value.items():
                key_text = str(key)
                normalized_key = key_text.lower().strip()
                flattened.setdefault(normalized_key, nested_value)
                if prefix:
                    flattened.setdefault(f"{prefix}.{normalized_key}", nested_value)
                visit(nested_value, prefix=normalized_key)

    visit(record)
    return flattened


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and len(value) == 0:
        return False
    if isinstance(value, Mapping) and len(value) == 0:
        return False
    return True


def _coverage_by_dimension(source_audits: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    dimensions = list(REQUIRED_EXACT_MATRIX_DIMENSIONS) + list(OPTIONAL_USEFUL_DIMENSIONS)
    total_records = sum(int(source.get("record_count", 0) or 0) for source in source_audits)
    coverage: dict[str, Any] = {}
    for dimension in dimensions:
        source_count = sum(
            1
            for source in source_audits
            if int(source.get("dimension_record_counts", {}).get(dimension, 0) or 0) > 0
        )
        record_count = sum(
            int(source.get("dimension_record_counts", {}).get(dimension, 0) or 0)
            for source in source_audits
        )
        coverage_ratio = record_count / total_records if total_records else 0.0
        coverage[dimension] = {
            "source_count_with_dimension": source_count,
            "record_count_with_dimension": record_count,
            "record_coverage_ratio": round(coverage_ratio, 6),
            "dimension_required_for_exact_matrix_mapping": dimension
            in REQUIRED_EXACT_MATRIX_DIMENSIONS,
            "coverage_state": _dimension_coverage_state(
                total_records=total_records,
                record_count=record_count,
                required=dimension in REQUIRED_EXACT_MATRIX_DIMENSIONS,
            ),
        }
    return coverage


def _dimension_coverage_state(*, total_records: int, record_count: int, required: bool) -> str:
    if total_records == 0:
        return "no_records"
    if record_count == total_records:
        return "complete"
    if record_count > 0:
        return "partial"
    return "missing_required" if required else "missing_optional"


def _coverage_summary(
    *,
    matrix_summary: Mapping[str, Any],
    source_audits: Sequence[Mapping[str, Any]],
    coverage_by_dimension: Mapping[str, Any],
) -> dict[str, Any]:
    total_records = sum(int(source.get("record_count", 0) or 0) for source in source_audits)
    exact_ready_records = sum(
        int(source.get("exact_matrix_cell_ready_record_count", 0) or 0)
        for source in source_audits
    )
    portfolio_edge_source_count = sum(
        1 for source in source_audits if source.get("portfolio_edge_evidence_present") is True
    )
    required_missing_dimensions = [
        dimension
        for dimension in REQUIRED_EXACT_MATRIX_DIMENSIONS
        if coverage_by_dimension.get(dimension, {}).get("record_count_with_dimension", 0) == 0
    ]
    required_partial_dimensions = [
        dimension
        for dimension in REQUIRED_EXACT_MATRIX_DIMENSIONS
        if 0
        < int(coverage_by_dimension.get(dimension, {}).get("record_count_with_dimension", 0) or 0)
        < total_records
    ]

    source_mapping_counts = Counter(
        str(source.get("source_mapping_state") or "unknown") for source in source_audits
    )

    mapping_state = _matrix_mapping_state(
        total_records=total_records,
        exact_ready_records=exact_ready_records,
        portfolio_edge_source_count=portfolio_edge_source_count,
        required_missing_dimensions=required_missing_dimensions,
        required_partial_dimensions=required_partial_dimensions,
    )

    return {
        "source_count": len(source_audits),
        "total_record_count": total_records,
        "exact_matrix_cell_ready_record_count": exact_ready_records,
        "records_requiring_mapping_count": max(total_records - exact_ready_records, 0),
        "portfolio_level_edge_source_count": portfolio_edge_source_count,
        "required_missing_dimensions": required_missing_dimensions,
        "required_partial_dimensions": required_partial_dimensions,
        "source_mapping_state_counts": dict(sorted(source_mapping_counts.items())),
        "matrix_mapping_state": mapping_state,
        "expected_matrix_cell_count": int(matrix_summary.get("catalog_strategy_count", 0) or 0),
        "inventory_ready_matrix_cell_count": int(
            matrix_summary.get("ready_matrix_cell_count", 0) or 0
        ),
        "inventory_review_required_matrix_cell_count": int(
            matrix_summary.get("review_required_matrix_cell_count", 0) or 0
        ),
    }


def _matrix_mapping_state(
    *,
    total_records: int,
    exact_ready_records: int,
    portfolio_edge_source_count: int,
    required_missing_dimensions: Sequence[str],
    required_partial_dimensions: Sequence[str],
) -> str:
    if total_records == 0:
        return "blocked_no_records"
    if exact_ready_records > 0 and not required_missing_dimensions:
        if exact_ready_records == total_records and not required_partial_dimensions:
            return "exact_matrix_cell_mapping_available"
        return "partial_exact_matrix_cell_mapping_available"
    if portfolio_edge_source_count > 0:
        return "portfolio_level_edge_requires_matrix_dimension_backfill"
    return "insufficient_for_exact_matrix_cell_edge_mapping"


def _source_mapping_state(
    *,
    record_count: int,
    exact_ready_count: int,
    portfolio_edge_evidence_present: bool,
    source_level_dimensions: set[str],
) -> str:
    if record_count == 0:
        if portfolio_edge_evidence_present:
            return "portfolio_level_edge_without_row_records"
        return "no_records"
    if exact_ready_count == record_count:
        return "all_records_have_exact_matrix_dimensions"
    if exact_ready_count > 0:
        return "partial_records_have_exact_matrix_dimensions"
    if portfolio_edge_evidence_present:
        return "portfolio_level_edge_requires_matrix_dimension_backfill"
    if REQUIRED_EXACT_MATRIX_DIMENSIONS and source_level_dimensions:
        return "source_level_dimensions_not_sufficient_for_row_mapping"
    return "records_missing_required_matrix_dimensions"


def _warnings(summary: Mapping[str, Any]) -> list[str]:
    warnings: list[str] = []
    if summary.get("portfolio_level_edge_source_count", 0) and summary.get(
        "matrix_mapping_state"
    ) == "portfolio_level_edge_requires_matrix_dimension_backfill":
        warnings.append("portfolio_level_edge_evidence_requires_matrix_dimension_backfill")
    for dimension in summary.get("required_missing_dimensions", []):
        warnings.append(f"missing_required_matrix_dimension:{dimension}")
    for dimension in summary.get("required_partial_dimensions", []):
        warnings.append(f"partial_required_matrix_dimension:{dimension}")
    if int(summary.get("inventory_ready_matrix_cell_count", 0) or 0) == 0:
        warnings.append("no_strategy_matrix_cells_have_exact_edge_mapping_yet")
    return _dedupe(warnings)


def _blocked_reasons(summary: Mapping[str, Any]) -> list[str]:
    if int(summary.get("total_record_count", 0) or 0) == 0:
        return ["no_historical_edge_records_detected"]
    return []


def _status(*, summary: Mapping[str, Any], blocked_reasons: Sequence[str]) -> str:
    if blocked_reasons:
        return "blocked"
    if summary.get("matrix_mapping_state") == "exact_matrix_cell_mapping_available":
        return "ready"
    return "needs_review"


def _next_build_recommendations(summary: Mapping[str, Any]) -> list[str]:
    recommendations: list[str] = []
    state = summary.get("matrix_mapping_state")
    if state == "exact_matrix_cell_mapping_available":
        recommendations.append("use_exact_matrix_cell_edge_records_to_promote_ready_strategy_matrix_cells")
    else:
        recommendations.extend(
            [
                "add_matrix_cell_metadata_to_historical_replay_outcome_records",
                "include_regime_asset_behavior_option_behavior_strategy_symbol_and_horizon_on_each_outcome",
                "build_matrix_cell_edge_validation_summary_after_metadata_backfill",
            ]
        )
    if summary.get("portfolio_level_edge_source_count", 0):
        recommendations.append("preserve_portfolio_level_edge_as_supporting_evidence_not_exact_cell_validation")
    return _dedupe(recommendations)


def _matrix_inventory_summary(
    source: Mapping[str, Any] | Sequence[Any] | None,
) -> dict[str, Any]:
    if not isinstance(source, Mapping):
        return {
            "matrix_inventory_source_present": False,
            "catalog_strategy_count": 0,
            "ready_matrix_cell_count": 0,
            "review_required_matrix_cell_count": 0,
            "portfolio_level_mapping_required_count": 0,
        }

    summary = source.get("strategy_matrix_edge_inventory_summary")
    if isinstance(summary, Mapping):
        return {
            "matrix_inventory_source_present": True,
            "catalog_strategy_count": int(summary.get("catalog_strategy_count", 0) or 0),
            "ready_matrix_cell_count": int(summary.get("ready_matrix_cell_count", 0) or 0),
            "review_required_matrix_cell_count": int(
                summary.get("review_required_matrix_cell_count", 0) or 0
            ),
            "portfolio_level_mapping_required_count": int(
                summary.get("portfolio_level_mapping_required_count", 0) or 0
            ),
            "inventory_status": source.get("status"),
        }

    items = source.get("strategy_matrix_edge_inventory_items")
    item_count = len(items) if isinstance(items, Sequence) and not isinstance(items, (str, bytes)) else 0
    return {
        "matrix_inventory_source_present": True,
        "catalog_strategy_count": item_count,
        "ready_matrix_cell_count": 0,
        "review_required_matrix_cell_count": item_count,
        "portfolio_level_mapping_required_count": item_count,
        "inventory_status": source.get("status"),
    }


def _has_positive_portfolio_edge(source: Mapping[str, Any] | Sequence[Any]) -> bool:
    if not isinstance(source, Mapping):
        return False
    artifact_type = str(source.get("artifact_type") or "")
    edge_state = str(
        source.get("historical_edge_state")
        or source.get("multi_window_edge_state")
        or source.get("portfolio_edge_evidence_state")
        or ""
    )
    if edge_state in POSITIVE_EDGE_STATES:
        return artifact_type in PORTFOLIO_EDGE_ARTIFACT_TYPES or bool(
            source.get("candidate_rows") or source.get("window_summaries")
        )
    portfolio = source.get("portfolio_level_edge_evidence")
    if isinstance(portfolio, Mapping):
        return str(portfolio.get("portfolio_edge_evidence_state") or "") in {
            "portfolio_level_positive_edge_candidate",
            "positive_edge_candidate",
        }
    return False


def _positive_edge_state(source: Mapping[str, Any] | Sequence[Any]) -> str | None:
    if not isinstance(source, Mapping):
        return None
    for key in (
        "historical_edge_state",
        "multi_window_edge_state",
        "portfolio_edge_evidence_state",
        "status",
    ):
        value = source.get(key)
        if isinstance(value, str) and value in POSITIVE_EDGE_STATES:
            return value
    return None


def _source_artifact_type(source: Mapping[str, Any] | Sequence[Any]) -> str | None:
    if isinstance(source, Mapping):
        artifact_type = source.get("artifact_type")
        return str(artifact_type) if artifact_type is not None else None
    if isinstance(source, Sequence) and not isinstance(source, (str, bytes)):
        return "sequence"
    return None


def _dedupe(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result
