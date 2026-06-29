from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from src.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS


HISTORICAL_EDGE_MATRIX_BACKFILL_PLAN_SCHEMA_VERSION = (
    "signalforge_historical_edge_matrix_backfill_plan.v1"
)

COVERED_CAPABILITIES = [
    "historical_edge_matrix_backfill_plan",
    "matrix_dimension_gap_to_build_task_translation",
    "historical_replay_metadata_contract_planning",
    "portfolio_edge_to_matrix_cell_backfill_planning",
]

DEPENDS_ON_CAPABILITIES = [
    "historical_edge_matrix_coverage_audit",
    "strategy_matrix_edge_inventory",
    "quantconnect_historical_replay",
    "historical_edge_validation",
    "regime_classification",
    "asset_behavior_classification",
    "option_behavior_classification",
    "strategy_availability_matrix",
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

DIMENSION_BACKFILL_RULES: dict[str, dict[str, Any]] = {
    "regime": {
        "source_of_truth": "regime decision artifact aligned to replay outcome timestamp/window",
        "target_fields": ["regime_state", "regime_label", "market_regime"],
        "target_artifact_contract": "historical_replay_contract_outcome",
        "build_action": "join_regime_state_onto_each_historical_outcome",
    },
    "asset_behavior": {
        "source_of_truth": "asset behavior decision artifact aligned by symbol and replay outcome timestamp/window",
        "target_fields": ["asset_behavior_state", "asset_behavior_label"],
        "target_artifact_contract": "historical_replay_contract_outcome",
        "build_action": "join_asset_behavior_state_onto_each_historical_outcome",
    },
    "option_behavior": {
        "source_of_truth": "option behavior decision artifact aligned by symbol, expiration/contract, and replay outcome timestamp/window",
        "target_fields": [
            "option_behavior_state",
            "iv_behavior",
            "vol_premium_behavior",
            "skew_behavior",
            "term_structure_behavior",
            "liquidity_behavior",
        ],
        "target_artifact_contract": "historical_replay_contract_outcome",
        "build_action": "join_option_behavior_state_onto_each_historical_outcome",
    },
    "strategy": {
        "source_of_truth": "strategy availability matrix / option strategy candidate match that generated the replay candidate",
        "target_fields": ["strategy", "strategy_id", "strategy_family", "option_strategy_id"],
        "target_artifact_contract": "historical_replay_contract_outcome",
        "build_action": "persist_strategy_matrix_row_id_on_each_historical_outcome",
    },
    "symbol": {
        "source_of_truth": "replay candidate or contract outcome symbol field",
        "target_fields": ["symbol", "underlying_symbol"],
        "target_artifact_contract": "historical_replay_contract_outcome",
        "build_action": "normalize_symbol_field_across_historical_sources",
    },
    "horizon": {
        "source_of_truth": "fixed horizon/scenario id/replay plan metadata",
        "target_fields": ["horizon", "horizon_days", "target_horizon_days", "fixed_horizon_days"],
        "target_artifact_contract": "historical_replay_contract_outcome",
        "build_action": "normalize_horizon_field_across_historical_sources",
    },
    "asset_class": {
        "source_of_truth": "strategy matrix row or instrument metadata",
        "target_fields": ["asset_class", "instrument_type", "security_type"],
        "target_artifact_contract": "historical_replay_contract_outcome",
        "build_action": "optionally_attach_asset_class_metadata",
    },
    "direction": {
        "source_of_truth": "strategy catalog / strategy matrix row",
        "target_fields": ["direction", "strategy_direction", "bias"],
        "target_artifact_contract": "historical_replay_contract_outcome",
        "build_action": "optionally_attach_strategy_direction_metadata",
    },
    "risk_structure": {
        "source_of_truth": "strategy catalog / scenario id / variant id",
        "target_fields": ["risk_structure", "risk_profile", "defined_risk", "variant_id"],
        "target_artifact_contract": "historical_replay_contract_outcome",
        "build_action": "optionally_attach_risk_structure_metadata",
    },
    "window": {
        "source_of_truth": "replay window plan / batch id",
        "target_fields": ["window_id", "period_id", "batch_id"],
        "target_artifact_contract": "historical_replay_contract_outcome",
        "build_action": "optionally_normalize_replay_window_metadata",
    },
    "outcome": {
        "source_of_truth": "historical replay outcome / edge validation result",
        "target_fields": ["strategy_adjusted_return", "contract_return", "win_rate", "historical_edge_state"],
        "target_artifact_contract": "historical_replay_contract_outcome",
        "build_action": "optionally_normalize_outcome_metric_fields",
    },
    "score": {
        "source_of_truth": "historical edge validation / portfolio candidate selection",
        "target_fields": ["historical_edge_score", "risk_adjusted_edge_score", "primary_score", "score"],
        "target_artifact_contract": "historical_replay_contract_outcome",
        "build_action": "optionally_normalize_edge_score_fields",
    },
}


def build_signalforge_historical_edge_matrix_backfill_plan(
    *,
    historical_edge_matrix_coverage_audit_source: Mapping[str, Any] | None = None,
    strategy_matrix_edge_inventory_source: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic plan to backfill matrix dimensions into historical edge records.

    The plan does not backfill data and does not promote portfolio-level edge to
    strategy-matrix edge. It converts coverage-audit gaps into explicit build
    tasks so the historical replay/export layer can be corrected first.
    """

    if not isinstance(historical_edge_matrix_coverage_audit_source, Mapping):
        return _blocked_result(["missing_historical_edge_matrix_coverage_audit_source"])

    audit_summary = _coverage_summary(historical_edge_matrix_coverage_audit_source)
    coverage_by_dimension = _coverage_by_dimension(historical_edge_matrix_coverage_audit_source)
    matrix_summary = _matrix_summary(
        historical_edge_matrix_coverage_audit_source,
        strategy_matrix_edge_inventory_source=strategy_matrix_edge_inventory_source,
    )

    tasks = _build_backfill_tasks(
        audit_summary=audit_summary,
        coverage_by_dimension=coverage_by_dimension,
    )
    summary = _plan_summary(
        tasks=tasks,
        audit_summary=audit_summary,
        matrix_summary=matrix_summary,
    )
    warnings = _warnings(summary=summary, audit_summary=audit_summary)
    blocked_reasons = _blocked_reasons(summary)
    status = _status(summary=summary, blocked_reasons=blocked_reasons)

    return {
        "artifact_type": "signalforge_historical_edge_matrix_backfill_plan",
        "schema_version": HISTORICAL_EDGE_MATRIX_BACKFILL_PLAN_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "contract": "historical_edge_matrix_backfill_plan",
        "adapter_type": "historical_edge_matrix_backfill_plan_builder",
        "review_scope": "historical_replay_metadata_backfill_plan_not_execution_or_edge_promotion",
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "source_artifacts": {
            "historical_edge_matrix_coverage_audit_source": _source_artifact_type(
                historical_edge_matrix_coverage_audit_source
            ),
            "strategy_matrix_edge_inventory_source": _source_artifact_type(
                strategy_matrix_edge_inventory_source
            ),
        },
        "audit_summary": audit_summary,
        "matrix_summary": matrix_summary,
        "required_exact_matrix_dimensions": list(REQUIRED_EXACT_MATRIX_DIMENSIONS),
        "optional_useful_dimensions": list(OPTIONAL_USEFUL_DIMENSIONS),
        "backfill_tasks": tasks,
        "backfill_plan_summary": summary,
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


def _blocked_result(blocked_reasons: Sequence[str]) -> dict[str, Any]:
    return {
        "artifact_type": "signalforge_historical_edge_matrix_backfill_plan",
        "schema_version": HISTORICAL_EDGE_MATRIX_BACKFILL_PLAN_SCHEMA_VERSION,
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "contract": "historical_edge_matrix_backfill_plan",
        "adapter_type": "historical_edge_matrix_backfill_plan_builder",
        "review_scope": "historical_replay_metadata_backfill_plan_not_execution_or_edge_promotion",
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "source_artifacts": {},
        "audit_summary": {},
        "matrix_summary": {},
        "required_exact_matrix_dimensions": list(REQUIRED_EXACT_MATRIX_DIMENSIONS),
        "optional_useful_dimensions": list(OPTIONAL_USEFUL_DIMENSIONS),
        "backfill_tasks": [],
        "backfill_plan_summary": {
            "task_count": 0,
            "required_backfill_task_count": 0,
            "required_normalization_task_count": 0,
            "optional_enrichment_task_count": 0,
            "ready_to_build_exact_matrix_edge_summary": False,
            "recommended_next_contract": "historical_replay_matrix_metadata_contract",
        },
        "warnings": [],
        "blocked_reasons": list(blocked_reasons),
        "next_build_recommendations": [
            "run_historical_edge_matrix_coverage_audit_before_building_backfill_plan",
        ],
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _coverage_summary(source: Mapping[str, Any]) -> dict[str, Any]:
    summary = source.get("coverage_summary")
    if isinstance(summary, Mapping):
        return dict(summary)

    return {
        "source_count": source.get("source_count", 0),
        "total_record_count": source.get("total_record_count", 0),
        "exact_matrix_cell_ready_record_count": source.get(
            "exact_matrix_cell_ready_record_count", 0
        ),
        "records_requiring_mapping_count": source.get("records_requiring_mapping_count", 0),
        "portfolio_level_edge_source_count": source.get("portfolio_level_edge_source_count", 0),
        "matrix_mapping_state": source.get("matrix_mapping_state"),
        "required_missing_dimensions": list(source.get("required_missing_dimensions", []) or []),
        "required_partial_dimensions": list(source.get("required_partial_dimensions", []) or []),
    }


def _coverage_by_dimension(source: Mapping[str, Any]) -> dict[str, Any]:
    detail = source.get("coverage_by_dimension")
    if isinstance(detail, Mapping):
        return {str(key): dict(value) for key, value in detail.items() if isinstance(value, Mapping)}

    states = source.get("dimension_coverage_states")
    if isinstance(states, Mapping):
        return {
            str(dimension): {"coverage_state": state}
            for dimension, state in states.items()
        }

    return {}


def _matrix_summary(
    audit_source: Mapping[str, Any],
    *,
    strategy_matrix_edge_inventory_source: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if isinstance(strategy_matrix_edge_inventory_source, Mapping):
        inventory_summary = strategy_matrix_edge_inventory_source.get(
            "strategy_matrix_edge_inventory_summary"
        )
        if isinstance(inventory_summary, Mapping):
            return dict(inventory_summary)

    matrix_summary = audit_source.get("matrix_inventory_summary")
    if isinstance(matrix_summary, Mapping):
        return dict(matrix_summary)

    return {
        "catalog_strategy_count": audit_source.get("expected_matrix_cell_count", 0),
        "ready_matrix_cell_count": audit_source.get("inventory_ready_matrix_cell_count", 0),
    }


def _build_backfill_tasks(
    *,
    audit_summary: Mapping[str, Any],
    coverage_by_dimension: Mapping[str, Any],
) -> list[dict[str, Any]]:
    missing_required = set(_as_text_list(audit_summary.get("required_missing_dimensions")))
    partial_required = set(_as_text_list(audit_summary.get("required_partial_dimensions")))
    tasks: list[dict[str, Any]] = []

    explicit_required_dimensions = set(missing_required) | set(partial_required)

    for dimension in REQUIRED_EXACT_MATRIX_DIMENSIONS:
        detail = coverage_by_dimension.get(dimension)
        if not isinstance(detail, Mapping):
            continue

        coverage_state = str(detail.get("coverage_state") or "")
        if coverage_state and coverage_state not in {"complete"}:
            explicit_required_dimensions.add(dimension)

    # If the source gives no explicit missing/partial dimensions and no coverage
    # details, plan a review task for all required dimensions. Otherwise, only
    # build tasks for dimensions the audit actually identified.
    if not explicit_required_dimensions and not coverage_by_dimension:
        explicit_required_dimensions = set(REQUIRED_EXACT_MATRIX_DIMENSIONS)

    for dimension in REQUIRED_EXACT_MATRIX_DIMENSIONS:
        if dimension not in explicit_required_dimensions:
            continue

        coverage_state = _dimension_state(
            dimension=dimension,
            coverage_by_dimension=coverage_by_dimension,
            missing_required=missing_required,
            partial_required=partial_required,
            required=True,
        )
        if coverage_state in {"complete"}:
            continue

        if dimension in missing_required or coverage_state == "missing_required":
            task_type = "required_backfill"
            priority = 1
        elif dimension in partial_required or coverage_state == "partial":
            task_type = "required_normalization"
            priority = 2
        else:
            task_type = "required_review"
            priority = 3

        tasks.append(
            _task_for_dimension(
                dimension,
                task_type=task_type,
                priority=priority,
                coverage_state=coverage_state,
            )
        )

    if coverage_by_dimension:
        for dimension in OPTIONAL_USEFUL_DIMENSIONS:
            coverage_state = _dimension_state(
                dimension=dimension,
                coverage_by_dimension=coverage_by_dimension,
                missing_required=set(),
                partial_required=set(),
                required=False,
            )
            if coverage_state in {"complete", "partial"}:
                continue

            # Only create optional enrichment tasks when the audit explicitly
            # reported that optional dimension. This keeps small summary-shaped
            # fixtures from producing unrelated optional tasks.
            if dimension not in coverage_by_dimension:
                continue

            tasks.append(
                _task_for_dimension(
                    dimension,
                    task_type="optional_enrichment",
                    priority=4,
                    coverage_state=coverage_state,
                )
            )

    return sorted(tasks, key=lambda item: (int(item["priority"]), str(item["dimension"])))


def _dimension_state(
    *,
    dimension: str,
    coverage_by_dimension: Mapping[str, Any],
    missing_required: set[str],
    partial_required: set[str],
    required: bool,
) -> str:
    if dimension in missing_required:
        return "missing_required"
    if dimension in partial_required:
        return "partial"
    detail = coverage_by_dimension.get(dimension)
    if isinstance(detail, Mapping):
        state = detail.get("coverage_state")
        if isinstance(state, str) and state:
            return state
    return "missing_required" if required else "missing_optional"


def _task_for_dimension(
    dimension: str,
    *,
    task_type: str,
    priority: int,
    coverage_state: str,
) -> dict[str, Any]:
    rule = DIMENSION_BACKFILL_RULES.get(dimension, {})
    return {
        "task_id": f"{task_type}:{dimension}",
        "dimension": dimension,
        "task_type": task_type,
        "priority": priority,
        "current_coverage_state": coverage_state,
        "required_for_exact_matrix_cell_edge": dimension in REQUIRED_EXACT_MATRIX_DIMENSIONS,
        "source_of_truth": rule.get("source_of_truth"),
        "target_artifact_contract": rule.get("target_artifact_contract"),
        "target_fields": list(rule.get("target_fields", [])),
        "build_action": rule.get("build_action"),
        "automatic_action": None,
        "automatic_strategy_change": None,
    }


def _plan_summary(
    *,
    tasks: Sequence[Mapping[str, Any]],
    audit_summary: Mapping[str, Any],
    matrix_summary: Mapping[str, Any],
) -> dict[str, Any]:
    required_backfill = [task for task in tasks if task.get("task_type") == "required_backfill"]
    required_normalization = [
        task for task in tasks if task.get("task_type") == "required_normalization"
    ]
    optional_enrichment = [task for task in tasks if task.get("task_type") == "optional_enrichment"]
    exact_ready_count = int(audit_summary.get("exact_matrix_cell_ready_record_count", 0) or 0)
    records_requiring_mapping = int(audit_summary.get("records_requiring_mapping_count", 0) or 0)
    ready_for_exact_summary = (
        not required_backfill
        and not required_normalization
        and exact_ready_count > 0
        and records_requiring_mapping == 0
    )

    return {
        "task_count": len(tasks),
        "required_backfill_task_count": len(required_backfill),
        "required_normalization_task_count": len(required_normalization),
        "optional_enrichment_task_count": len(optional_enrichment),
        "records_requiring_mapping_count": records_requiring_mapping,
        "exact_matrix_cell_ready_record_count": exact_ready_count,
        "expected_matrix_cell_count": int(matrix_summary.get("catalog_strategy_count", 0) or 0),
        "required_backfill_dimensions": [str(task.get("dimension")) for task in required_backfill],
        "required_normalization_dimensions": [
            str(task.get("dimension")) for task in required_normalization
        ],
        "optional_enrichment_dimensions": [
            str(task.get("dimension")) for task in optional_enrichment
        ],
        "ready_to_build_exact_matrix_edge_summary": ready_for_exact_summary,
        "recommended_next_contract": "historical_replay_matrix_metadata_contract"
        if not ready_for_exact_summary
        else "strategy_matrix_exact_edge_summary",
    }


def _warnings(*, summary: Mapping[str, Any], audit_summary: Mapping[str, Any]) -> list[str]:
    warnings: list[str] = []
    if int(summary.get("required_backfill_task_count", 0) or 0) > 0:
        warnings.append("historical_replay_outcomes_require_missing_matrix_dimension_backfill")
    if int(summary.get("required_normalization_task_count", 0) or 0) > 0:
        warnings.append("historical_replay_outcomes_require_partial_matrix_dimension_normalization")
    if str(audit_summary.get("matrix_mapping_state") or "") == "portfolio_level_edge_requires_matrix_dimension_backfill":
        warnings.append("portfolio_level_edge_evidence_still_requires_matrix_dimension_backfill")
    for dimension in _as_text_list(summary.get("required_backfill_dimensions")):
        warnings.append(f"required_backfill_dimension:{dimension}")
    for dimension in _as_text_list(summary.get("required_normalization_dimensions")):
        warnings.append(f"required_normalization_dimension:{dimension}")
    return _dedupe_preserve_order(warnings)


def _blocked_reasons(summary: Mapping[str, Any]) -> list[str]:
    if int(summary.get("required_backfill_task_count", 0) or 0) > 0:
        return []
    if int(summary.get("required_normalization_task_count", 0) or 0) > 0:
        return []
    return []


def _status(*, summary: Mapping[str, Any], blocked_reasons: Sequence[str]) -> str:
    if blocked_reasons:
        return "blocked"
    if summary.get("ready_to_build_exact_matrix_edge_summary") is True:
        return "ready"
    return "needs_review"


def _next_build_recommendations(summary: Mapping[str, Any]) -> list[str]:
    if summary.get("ready_to_build_exact_matrix_edge_summary") is True:
        return [
            "build_strategy_matrix_exact_edge_summary_from_exact_matrix_records",
            "map_ready_matrix_cells_into_strategy_selection_candidate_review",
        ]
    recommendations = [
        "build_historical_replay_matrix_metadata_contract",
        "backfill_regime_asset_option_strategy_metadata_onto_historical_replay_outcomes",
        "rerun_historical_edge_matrix_coverage_audit_after_backfill",
    ]
    if int(summary.get("required_normalization_task_count", 0) or 0) > 0:
        recommendations.append("normalize_partial_symbol_and_horizon_fields_across_historical_sources")
    return recommendations


def _source_artifact_type(source: Mapping[str, Any] | None) -> str | None:
    if not isinstance(source, Mapping):
        return None
    artifact_type = source.get("artifact_type")
    return str(artifact_type) if artifact_type is not None else None


def _as_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [str(item) for item in value if item is not None and str(item).strip()]
    return [str(value)]


def _dedupe_preserve_order(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
