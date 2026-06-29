"""Historical replay source metadata backfill requirements.

This module turns the matrix metadata backfill adapter result into a source-level
repair plan. It does not infer missing matrix dimensions, mutate historical
records, score strategies, select candidates, connect to brokers, request
quotes, route orders, submit orders, or alter strategy availability rules.

The purpose is to identify exactly which upstream historical replay/export
sources must stamp matrix metadata before exact strategy-matrix edge summaries
can be built.
"""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "signalforge_historical_replay_source_metadata_backfill.v1"
SUMMARY_SCHEMA_VERSION = "signalforge_historical_replay_source_metadata_backfill_summary.v1"
ARTIFACT_TYPE = "signalforge_historical_replay_source_metadata_backfill"
RECOMMENDED_NEXT_WHEN_NEEDS_REVIEW = "historical_replay_export_matrix_metadata_envelope"
RECOMMENDED_NEXT_WHEN_READY = "exact_matrix_edge_summary"

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

DIMENSION_TO_FIELDS = {
    "regime": ["regime_state"],
    "asset_behavior": ["asset_behavior_state"],
    "option_behavior": ["option_behavior_state"],
    "strategy": ["strategy_id", "strategy_family"],
    "symbol": ["symbol"],
    "horizon": ["horizon_days"],
}

DIMENSION_SOURCE_REQUIREMENTS = {
    "regime": {
        "source_requirement": "Historical replay outcomes must carry the regime classification active at the decision timestamp.",
        "candidate_source_artifacts": [
            "regime_decision_export",
            "historical_regime_snapshot",
            "regime_asset_options_alignment",
        ],
        "join_keys": ["decision_timestamp", "window_start", "window_end"],
        "upstream_action": "stamp_regime_state_when_replay_candidate_is_created",
    },
    "asset_behavior": {
        "source_requirement": "Historical replay outcomes must carry the asset behavior classification for the underlying at the decision timestamp.",
        "candidate_source_artifacts": [
            "asset_behavior_decision_export",
            "historical_asset_behavior_export",
            "regime_asset_options_alignment",
        ],
        "join_keys": ["symbol", "decision_timestamp", "window_start", "window_end"],
        "upstream_action": "stamp_asset_behavior_state_when_symbol_candidate_is_created",
    },
    "option_behavior": {
        "source_requirement": "Historical replay outcomes must carry the option behavior classification for the option chain at the decision timestamp.",
        "candidate_source_artifacts": [
            "option_behavior_decision_export",
            "historical_option_behavior_export",
            "regime_asset_options_alignment",
        ],
        "join_keys": ["symbol", "expiration", "decision_timestamp", "window_start", "window_end"],
        "upstream_action": "stamp_option_behavior_state_when_contract_candidate_is_created",
    },
    "strategy": {
        "source_requirement": "Historical replay outcomes must carry the exact strategy matrix strategy_id and strategy_family used to create the outcome.",
        "candidate_source_artifacts": [
            "strategy_family_eligibility",
            "options_strategy_catalog",
            "options_strategy_setup_matcher",
            "candidate_selection_review",
        ],
        "join_keys": ["strategy_id", "strategy_family", "symbol", "decision_timestamp"],
        "upstream_action": "stamp_exact_strategy_id_and_family_before_replay_outcome_is_written",
    },
    "symbol": {
        "source_requirement": "Historical replay outcomes must carry the normalized underlying symbol.",
        "candidate_source_artifacts": [
            "quantconnect_replay_window_plan",
            "historical_replay_candidate_export",
            "contract_outcome_snapshot",
        ],
        "join_keys": ["symbol", "underlying_symbol", "ticker"],
        "upstream_action": "normalize_symbol_on_every_replay_outcome_record",
    },
    "horizon": {
        "source_requirement": "Historical replay outcomes must carry normalized integer horizon_days.",
        "candidate_source_artifacts": [
            "quantconnect_replay_window_plan",
            "historical_edge_validation_multi_window_summary",
            "portfolio_candidate_selection_summary",
        ],
        "join_keys": ["horizon", "window_days", "selected_window_days", "target_horizon_days"],
        "upstream_action": "normalize_horizon_days_on_every_replay_outcome_record",
    },
}

OPTIONAL_DIMENSION_SOURCE_REQUIREMENTS = {
    "asset_class": {
        "source_requirement": "Stamp asset class, such as equity_option, for cross-asset matrix aggregation.",
        "candidate_source_artifacts": ["strategy_catalog", "candidate_selection_review"],
        "join_keys": ["symbol", "instrument_type", "asset_class"],
        "upstream_action": "stamp_asset_class_when_candidate_is_created",
    },
    "direction": {
        "source_requirement": "Stamp strategy direction, such as bullish, bearish, neutral, or defensive.",
        "candidate_source_artifacts": ["strategy_catalog", "strategy_family_eligibility"],
        "join_keys": ["strategy_id", "strategy_family"],
        "upstream_action": "stamp_strategy_direction_from_strategy_catalog",
    },
    "risk_structure": {
        "source_requirement": "Stamp risk structure, such as defined_risk, capped, debit, or credit.",
        "candidate_source_artifacts": ["strategy_catalog", "candidate_selection_review"],
        "join_keys": ["strategy_id", "strategy_family"],
        "upstream_action": "stamp_risk_structure_from_strategy_catalog",
    },
    "window": {
        "source_requirement": "Stamp replay window or batch identifiers for traceability.",
        "candidate_source_artifacts": ["quantconnect_replay_window_plan"],
        "join_keys": ["window_id", "batch_id", "window_start", "window_end"],
        "upstream_action": "stamp_replay_window_id_on_outcome_records",
    },
    "score": {
        "source_requirement": "Carry source score fields when available for matrix attribution diagnostics.",
        "candidate_source_artifacts": ["historical_edge_validation", "portfolio_candidate_selection_summary"],
        "join_keys": ["record_id", "symbol", "horizon_days"],
        "upstream_action": "preserve_edge_score_fields_on_outcome_records",
    },
    "outcome": {
        "source_requirement": "Carry normalized outcome state and realized result fields for exact matrix edge aggregation.",
        "candidate_source_artifacts": ["contract_outcome_snapshot", "historical_edge_validation"],
        "join_keys": ["record_id", "symbol", "horizon_days"],
        "upstream_action": "preserve_outcome_state_on_replay_outcome_records",
    },
}


def build_signalforge_historical_replay_source_metadata_backfill(
    *,
    historical_replay_matrix_metadata_contract_source: Mapping[str, Any],
    historical_replay_matrix_metadata_backfill_adapter_source: Mapping[str, Any],
    historical_edge_matrix_backfill_plan_source: Mapping[str, Any] | None = None,
    strategy_matrix_edge_inventory_source: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build source-level metadata backfill requirements."""

    contract = _extract_contract(historical_replay_matrix_metadata_contract_source)
    adapter_summary = _extract_summary(historical_replay_matrix_metadata_backfill_adapter_source)
    plan_summary = _extract_summary(historical_edge_matrix_backfill_plan_source or {})
    inventory_summary = _extract_summary(strategy_matrix_edge_inventory_source or {})

    blocked_reasons: list[str] = []
    warnings: list[str] = []

    if not contract:
        blocked_reasons.append("historical_replay_matrix_metadata_contract_source_required")
    contract_state = str(contract.get("contract_state") or contract.get("status") or "unknown")
    if contract and contract_state != "ready":
        blocked_reasons.append("historical_replay_matrix_metadata_contract_not_ready")

    if not adapter_summary:
        blocked_reasons.append("historical_replay_matrix_metadata_backfill_adapter_source_required")

    required_missing_dimensions = _ordered_unique(
        _as_text_list(adapter_summary.get("required_missing_dimensions"))
    )
    required_partial_dimensions = _ordered_unique(
        _as_text_list(adapter_summary.get("required_partial_dimensions"))
    )
    missing_counts = _as_int_mapping(adapter_summary.get("missing_required_dimension_counts"))
    mapped_counts = _as_int_mapping(adapter_summary.get("mapped_required_dimension_counts"))
    partial_counts = _as_int_mapping(adapter_summary.get("partial_required_dimension_counts"))

    total_source_record_count = _as_int(adapter_summary.get("total_source_record_count"), default=0)
    records_requiring_mapping_count = _as_int(
        adapter_summary.get("records_requiring_mapping_count"),
        default=_as_int(plan_summary.get("records_requiring_mapping_count"), default=0),
    )
    exact_matrix_cell_ready_record_count = _as_int(
        adapter_summary.get("exact_matrix_cell_ready_record_count"), default=0
    )
    expected_matrix_cell_count = _as_int(
        adapter_summary.get("expected_matrix_cell_count")
        or inventory_summary.get("expected_matrix_cell_count"),
        default=0,
    )

    required_fields = _required_fields_from_contract(contract)
    optional_fields = _optional_fields_from_contract(contract)
    matrix_cell_key_fields = _as_text_list(
        contract.get("matrix_cell_key_fields")
        or adapter_summary.get("matrix_cell_key_fields")
        or [field.get("field_name") for field in required_fields]
    )

    required_source_tasks = _build_required_source_tasks(
        required_missing_dimensions=required_missing_dimensions,
        required_partial_dimensions=required_partial_dimensions,
        missing_counts=missing_counts,
        mapped_counts=mapped_counts,
        partial_counts=partial_counts,
        total_source_record_count=total_source_record_count,
        required_fields=required_fields,
    )
    optional_source_tasks = _build_optional_source_tasks(optional_fields=optional_fields)

    if required_missing_dimensions:
        warnings.append("historical_replay_source_exports_require_required_matrix_metadata_backfill")
    if required_partial_dimensions:
        warnings.append("historical_replay_source_exports_require_required_matrix_metadata_normalization")
    if exact_matrix_cell_ready_record_count == 0:
        warnings.append("exact_matrix_edge_summary_blocked_until_source_metadata_is_stamped")
    for dimension in required_missing_dimensions:
        warnings.append(f"source_backfill_required_dimension:{dimension}")
    for dimension in required_partial_dimensions:
        warnings.append(f"source_normalization_required_dimension:{dimension}")

    if blocked_reasons:
        backfill_state = "blocked"
        status = "blocked"
    elif not required_source_tasks and exact_matrix_cell_ready_record_count > 0:
        backfill_state = "ready"
        status = "ready"
    else:
        backfill_state = "needs_review"
        status = "needs_review"

    ready_to_build_exact_matrix_edge_summary = (
        status == "ready"
        and exact_matrix_cell_ready_record_count > 0
        and records_requiring_mapping_count == 0
    )
    ready_to_patch_historical_replay_exports = status != "blocked" and bool(required_source_tasks)

    source_backfill_contract = _build_source_backfill_contract(
        required_source_tasks=required_source_tasks,
        optional_source_tasks=optional_source_tasks,
        matrix_cell_key_fields=matrix_cell_key_fields,
    )

    result = {
        "artifact_type": ARTIFACT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "operation_type": "signalforge_historical_replay_source_metadata_backfill_builder",
        "source_metadata_backfill_id": _stable_id(
            contract.get("contract_id"),
            required_missing_dimensions,
            required_partial_dimensions,
            total_source_record_count,
        ),
        "source_metadata_backfill_state": backfill_state,
        "status": status,
        "is_ready": status == "ready",
        "created_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "matrix_mapping_state": _matrix_mapping_state(status, required_source_tasks),
        "recommended_next_step": (
            RECOMMENDED_NEXT_WHEN_READY
            if ready_to_build_exact_matrix_edge_summary
            else RECOMMENDED_NEXT_WHEN_NEEDS_REVIEW
        ),
        "ready_to_patch_historical_replay_exports": ready_to_patch_historical_replay_exports,
        "ready_to_build_exact_matrix_edge_summary": ready_to_build_exact_matrix_edge_summary,
        "contract_state": contract_state,
        "contract_id": str(contract.get("contract_id") or "unknown"),
        "adapter_state": str(
            adapter_summary.get("adapter_state")
            or adapter_summary.get("source_metadata_backfill_state")
            or adapter_summary.get("status")
            or "unknown"
        ),
        "total_source_record_count": total_source_record_count,
        "records_requiring_mapping_count": records_requiring_mapping_count,
        "exact_matrix_cell_ready_record_count": exact_matrix_cell_ready_record_count,
        "expected_matrix_cell_count": expected_matrix_cell_count,
        "matrix_cell_key_fields": matrix_cell_key_fields,
        "required_field_count": len(required_fields),
        "optional_field_count": len(optional_fields),
        "required_missing_dimensions": required_missing_dimensions,
        "required_partial_dimensions": required_partial_dimensions,
        "missing_required_dimension_counts": missing_counts,
        "mapped_required_dimension_counts": mapped_counts,
        "partial_required_dimension_counts": partial_counts,
        "required_source_backfill_task_count": len(
            [task for task in required_source_tasks if task.get("task_type") == "source_required_backfill"]
        ),
        "required_source_normalization_task_count": len(
            [task for task in required_source_tasks if task.get("task_type") == "source_required_normalization"]
        ),
        "optional_source_enrichment_task_count": len(optional_source_tasks),
        "source_backfill_task_count": len(required_source_tasks) + len(optional_source_tasks),
        "required_source_tasks": required_source_tasks,
        "optional_source_tasks": optional_source_tasks,
        "source_backfill_contract": source_backfill_contract,
        "source_patch_sequence": _build_patch_sequence(required_source_tasks),
        "upstream_artifact_requirements": _build_upstream_artifact_requirements(required_source_tasks),
        "blocked_reasons": _ordered_unique(blocked_reasons),
        "warnings": _ordered_unique(warnings),
        "automatic_action": None,
        "automatic_strategy_change": None,
        "order_intent": None,
        "requires_manual_approval": True,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }
    result["source_metadata_backfill_summary"] = build_historical_replay_source_metadata_backfill_summary(result)
    return result


def build_historical_replay_source_metadata_backfill_summary(
    result: Mapping[str, Any]
) -> dict[str, Any]:
    """Build a compact summary for the source metadata backfill artifact."""

    return {
        "artifact_type": "signalforge_historical_replay_source_metadata_backfill_summary",
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "source_metadata_backfill_state": str(result.get("source_metadata_backfill_state") or "blocked"),
        "status": str(result.get("status") or result.get("source_metadata_backfill_state") or "blocked"),
        "is_ready": bool(result.get("is_ready")),
        "matrix_mapping_state": str(result.get("matrix_mapping_state") or "unknown"),
        "recommended_next_step": str(result.get("recommended_next_step") or "unknown"),
        "ready_to_patch_historical_replay_exports": bool(
            result.get("ready_to_patch_historical_replay_exports")
        ),
        "ready_to_build_exact_matrix_edge_summary": bool(
            result.get("ready_to_build_exact_matrix_edge_summary")
        ),
        "contract_state": str(result.get("contract_state") or "unknown"),
        "contract_id": str(result.get("contract_id") or "unknown"),
        "adapter_state": str(result.get("adapter_state") or "unknown"),
        "total_source_record_count": _as_int(result.get("total_source_record_count"), default=0),
        "records_requiring_mapping_count": _as_int(result.get("records_requiring_mapping_count"), default=0),
        "exact_matrix_cell_ready_record_count": _as_int(
            result.get("exact_matrix_cell_ready_record_count"), default=0
        ),
        "expected_matrix_cell_count": _as_int(result.get("expected_matrix_cell_count"), default=0),
        "required_field_count": _as_int(result.get("required_field_count"), default=0),
        "optional_field_count": _as_int(result.get("optional_field_count"), default=0),
        "matrix_cell_key_fields": _as_text_list(result.get("matrix_cell_key_fields")),
        "required_missing_dimensions": _as_text_list(result.get("required_missing_dimensions")),
        "required_partial_dimensions": _as_text_list(result.get("required_partial_dimensions")),
        "missing_required_dimension_counts": _as_int_mapping(
            result.get("missing_required_dimension_counts")
        ),
        "mapped_required_dimension_counts": _as_int_mapping(
            result.get("mapped_required_dimension_counts")
        ),
        "partial_required_dimension_counts": _as_int_mapping(
            result.get("partial_required_dimension_counts")
        ),
        "required_source_backfill_task_count": _as_int(
            result.get("required_source_backfill_task_count"), default=0
        ),
        "required_source_normalization_task_count": _as_int(
            result.get("required_source_normalization_task_count"), default=0
        ),
        "optional_source_enrichment_task_count": _as_int(
            result.get("optional_source_enrichment_task_count"), default=0
        ),
        "source_backfill_task_count": _as_int(result.get("source_backfill_task_count"), default=0),
        "blocked_reasons": _as_text_list(result.get("blocked_reasons")),
        "warnings": _as_text_list(result.get("warnings")),
        "explicit_exclusions": _as_text_list(result.get("explicit_exclusions")),
        "order_intent": result.get("order_intent"),
        "automatic_action": result.get("automatic_action"),
        "automatic_strategy_change": result.get("automatic_strategy_change"),
        "requires_manual_approval": bool(result.get("requires_manual_approval", True)),
    }


def _extract_contract(source: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(source, Mapping):
        return {}
    if source.get("artifact_type") == "signalforge_historical_replay_matrix_metadata_contract":
        return dict(source)
    nested = source.get("contract") or source.get("metadata_contract") or source.get("result")
    if isinstance(nested, Mapping):
        return dict(nested)
    return dict(source)


def _extract_summary(source: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(source, Mapping):
        return {}
    for key in (
        "source_metadata_backfill_summary",
        "adapter_summary",
        "backfill_adapter_summary",
        "summary",
        "contract_summary",
        "backfill_plan_summary",
        "inventory_summary",
    ):
        value = source.get(key)
        if isinstance(value, Mapping):
            merged = dict(source)
            merged.update(dict(value))
            return merged
    return dict(source)


def _required_fields_from_contract(contract: Mapping[str, Any]) -> list[dict[str, Any]]:
    fields = contract.get("required_fields")
    if isinstance(fields, Sequence) and not isinstance(fields, (str, bytes, bytearray)):
        result = [dict(field) for field in fields if isinstance(field, Mapping)]
        if result:
            return result
    matrix_keys = _as_text_list(contract.get("matrix_cell_key_fields"))
    result = []
    for field_name in matrix_keys:
        dimension = _dimension_for_field(field_name)
        result.append({"field_name": field_name, "dimension": dimension, "required": True})
    return result


def _optional_fields_from_contract(contract: Mapping[str, Any]) -> list[dict[str, Any]]:
    fields = contract.get("optional_fields")
    if isinstance(fields, Sequence) and not isinstance(fields, (str, bytes, bytearray)):
        return [dict(field) for field in fields if isinstance(field, Mapping)]
    return []


def _build_required_source_tasks(
    *,
    required_missing_dimensions: Sequence[str],
    required_partial_dimensions: Sequence[str],
    missing_counts: Mapping[str, int],
    mapped_counts: Mapping[str, int],
    partial_counts: Mapping[str, int],
    total_source_record_count: int,
    required_fields: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    missing = set(required_missing_dimensions)
    partial = set(required_partial_dimensions)
    explicit_dimensions = _ordered_unique([*required_missing_dimensions, *required_partial_dimensions])

    for dimension in explicit_dimensions:
        requirement = DIMENSION_SOURCE_REQUIREMENTS.get(dimension, {})
        if dimension in missing:
            task_type = "source_required_backfill"
            priority = 1
        elif dimension in partial:
            task_type = "source_required_normalization"
            priority = 2
        else:
            task_type = "source_required_review"
            priority = 3

        tasks.append(
            {
                "dimension": dimension,
                "required_fields": _fields_for_dimension(dimension, required_fields),
                "task_type": task_type,
                "priority": priority,
                "missing_record_count": _as_int(missing_counts.get(dimension), default=0),
                "mapped_record_count": _as_int(mapped_counts.get(dimension), default=0),
                "partial_record_count": _as_int(partial_counts.get(dimension), default=0),
                "total_source_record_count": total_source_record_count,
                "source_requirement": str(requirement.get("source_requirement") or "source metadata required"),
                "candidate_source_artifacts": _as_text_list(requirement.get("candidate_source_artifacts")),
                "join_keys": _as_text_list(requirement.get("join_keys")),
                "upstream_action": str(requirement.get("upstream_action") or "stamp_dimension_on_replay_outcome"),
                "blocks_exact_matrix_edge_summary": True,
                "manual_review_required": True,
            }
        )

    return sorted(tasks, key=lambda item: (int(item["priority"]), str(item["dimension"])))


def _build_optional_source_tasks(*, optional_fields: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen_dimensions: list[str] = []
    for field in optional_fields:
        dimension = str(field.get("dimension") or "").strip()
        if dimension and dimension not in seen_dimensions:
            seen_dimensions.append(dimension)

    tasks: list[dict[str, Any]] = []
    for dimension in seen_dimensions:
        requirement = OPTIONAL_DIMENSION_SOURCE_REQUIREMENTS.get(dimension, {})
        tasks.append(
            {
                "dimension": dimension,
                "optional_fields": _fields_for_dimension(dimension, optional_fields),
                "task_type": "source_optional_enrichment",
                "priority": 4,
                "source_requirement": str(requirement.get("source_requirement") or "optional source metadata enrichment"),
                "candidate_source_artifacts": _as_text_list(requirement.get("candidate_source_artifacts")),
                "join_keys": _as_text_list(requirement.get("join_keys")),
                "upstream_action": str(requirement.get("upstream_action") or "optionally_stamp_dimension_on_replay_outcome"),
                "blocks_exact_matrix_edge_summary": False,
                "manual_review_required": False,
            }
        )
    return sorted(tasks, key=lambda item: (int(item["priority"]), str(item["dimension"])))


def _build_source_backfill_contract(
    *,
    required_source_tasks: Sequence[Mapping[str, Any]],
    optional_source_tasks: Sequence[Mapping[str, Any]],
    matrix_cell_key_fields: Sequence[str],
) -> dict[str, Any]:
    return {
        "contract_type": "historical_replay_source_metadata_backfill_contract",
        "matrix_metadata_envelope_field": "matrix_metadata",
        "matrix_cell_key_fields": list(matrix_cell_key_fields),
        "required_source_tasks": [dict(task) for task in required_source_tasks],
        "optional_source_tasks": [dict(task) for task in optional_source_tasks],
        "required_output_shape": {
            "matrix_metadata": {field: "required" for field in matrix_cell_key_fields},
            "source_trace": {
                "source_artifact_type": "required",
                "source_record_id": "required_when_available",
                "mapping_confidence": "required",
                "manual_review_required": "required",
            },
        },
        "forbidden_behaviors": list(EXPLICIT_EXCLUSIONS),
    }


def _build_patch_sequence(required_source_tasks: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not required_source_tasks:
        return []
    return [
        {
            "step": 1,
            "name": "stamp_matrix_metadata_at_candidate_creation",
            "description": "Attach regime, asset behavior, option behavior, strategy, symbol, and horizon metadata before replay outcomes are written.",
            "required_dimensions": _ordered_unique([str(task.get("dimension")) for task in required_source_tasks]),
        },
        {
            "step": 2,
            "name": "preserve_matrix_metadata_through_replay_results",
            "description": "Ensure QuantConnect replay results and imported contract outcomes preserve the matrix_metadata envelope.",
            "required_dimensions": _ordered_unique([str(task.get("dimension")) for task in required_source_tasks]),
        },
        {
            "step": 3,
            "name": "rerun_matrix_metadata_backfill_adapter",
            "description": "Rerun the backfill adapter and require exact_matrix_cell_ready_record_count to be greater than zero before matrix edge aggregation.",
            "required_dimensions": _ordered_unique([str(task.get("dimension")) for task in required_source_tasks]),
        },
    ]


def _build_upstream_artifact_requirements(
    required_source_tasks: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    by_artifact: dict[str, set[str]] = {}
    for task in required_source_tasks:
        dimension = str(task.get("dimension") or "")
        for artifact in _as_text_list(task.get("candidate_source_artifacts")):
            by_artifact.setdefault(artifact, set()).add(dimension)

    return [
        {
            "candidate_source_artifact": artifact,
            "required_dimensions": sorted(dimensions),
            "manual_review_required": True,
        }
        for artifact, dimensions in sorted(by_artifact.items())
    ]


def _fields_for_dimension(
    dimension: str,
    fields: Sequence[Mapping[str, Any]],
) -> list[str]:
    result = [
        str(field.get("field_name"))
        for field in fields
        if str(field.get("dimension") or "") == dimension and field.get("field_name")
    ]
    if result:
        return _ordered_unique(result)
    return list(DIMENSION_TO_FIELDS.get(dimension, []))


def _dimension_for_field(field_name: str) -> str:
    for dimension, fields in DIMENSION_TO_FIELDS.items():
        if field_name in fields:
            return dimension
    return field_name.replace("_state", "").replace("_days", "")


def _matrix_mapping_state(status: str, required_source_tasks: Sequence[Mapping[str, Any]]) -> str:
    if status == "blocked":
        return "source_metadata_backfill_blocked"
    if not required_source_tasks:
        return "source_metadata_backfill_not_required"
    return "historical_replay_source_metadata_backfill_required"


def _stable_id(*parts: Any) -> str:
    material = "|".join(str(part) for part in parts)
    digest = sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"historical_replay_source_metadata_backfill_{digest}"


def _as_int(value: Any, *, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value.strip()))
        except ValueError:
            return default
    return default


def _as_int_mapping(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): _as_int(item, default=0) for key, item in value.items()}


def _as_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, Mapping):
        return [str(key) for key in value.keys()]
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [str(item) for item in value if item is not None and str(item) != ""]
    return [str(value)]


def _ordered_unique(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result
