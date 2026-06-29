"""Historical replay matrix metadata contract.

This module defines the required metadata envelope that historical replay outcomes
must carry before SignalForge can attribute edge to exact strategy-matrix cells.

It intentionally does not backfill data, score strategies, select candidates,
connect to brokers, request quotes, route orders, or submit orders.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "signalforge_historical_replay_matrix_metadata_contract.v1"
ARTIFACT_TYPE = "signalforge_historical_replay_matrix_metadata_contract"
SUMMARY_SCHEMA_VERSION = "signalforge_historical_replay_matrix_metadata_contract_summary.v1"

RECOMMENDED_NEXT_ADAPTER = "historical_replay_matrix_metadata_backfill_adapter"

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
    "score",
    "outcome",
]

FIELD_DEFINITIONS: dict[str, dict[str, Any]] = {
    "regime_state": {
        "dimension": "regime",
        "type": "string",
        "required": True,
        "description": "Regime classification active at the historical replay decision timestamp.",
        "accepted_aliases": ["regime", "market_regime", "regime_label"],
        "normalization_rule": "trim_lower_snake_case",
        "missing_policy": "block_exact_matrix_cell_mapping",
    },
    "asset_behavior_state": {
        "dimension": "asset_behavior",
        "type": "string",
        "required": True,
        "description": "Asset behavior classification for the underlying at the replay decision timestamp.",
        "accepted_aliases": ["asset_behavior", "asset_behavior_label", "underlying_behavior_state"],
        "normalization_rule": "trim_lower_snake_case",
        "missing_policy": "block_exact_matrix_cell_mapping",
    },
    "option_behavior_state": {
        "dimension": "option_behavior",
        "type": "string",
        "required": True,
        "description": "Option behavior classification for the underlying option chain at the replay decision timestamp.",
        "accepted_aliases": ["option_behavior", "options_behavior", "option_behavior_label"],
        "normalization_rule": "trim_lower_snake_case",
        "missing_policy": "block_exact_matrix_cell_mapping",
    },
    "strategy_id": {
        "dimension": "strategy",
        "type": "string",
        "required": True,
        "description": "Exact strategy-matrix strategy identifier, such as bull_call_debit_spread or iron_condor.",
        "accepted_aliases": ["strategy", "strategy_name", "setup_id", "option_strategy_id"],
        "normalization_rule": "trim_lower_snake_case",
        "missing_policy": "block_exact_matrix_cell_mapping",
    },
    "strategy_family": {
        "dimension": "strategy",
        "type": "string",
        "required": True,
        "description": "Higher-level strategy family used for grouping and portfolio attribution.",
        "accepted_aliases": ["family", "strategy_family_name", "setup_family"],
        "normalization_rule": "trim_lower_snake_case",
        "missing_policy": "block_exact_matrix_cell_mapping",
    },
    "symbol": {
        "dimension": "symbol",
        "type": "string",
        "required": True,
        "description": "Underlying symbol for the historical replay outcome.",
        "accepted_aliases": ["ticker", "underlying", "underlying_symbol"],
        "normalization_rule": "trim_uppercase_symbol",
        "missing_policy": "block_exact_matrix_cell_mapping",
    },
    "horizon_days": {
        "dimension": "horizon",
        "type": "integer",
        "required": True,
        "description": "Replay horizon in calendar or strategy-defined days, normalized to integer days.",
        "accepted_aliases": ["horizon", "window_days", "selected_window_days", "target_horizon_days"],
        "normalization_rule": "coerce_positive_integer_days",
        "missing_policy": "block_exact_matrix_cell_mapping",
    },
    "asset_class": {
        "dimension": "asset_class",
        "type": "string",
        "required": False,
        "description": "Asset class of the candidate, for example equity_option.",
        "accepted_aliases": ["asset_type", "instrument_class"],
        "normalization_rule": "trim_lower_snake_case",
        "missing_policy": "allow_cell_mapping_with_warning",
    },
    "strategy_direction": {
        "dimension": "direction",
        "type": "string",
        "required": False,
        "description": "Directional bias of the strategy, for example bullish, bearish, neutral, or defensive.",
        "accepted_aliases": ["direction", "bias", "strategy_bias"],
        "normalization_rule": "trim_lower_snake_case",
        "missing_policy": "allow_cell_mapping_with_warning",
    },
    "risk_structure": {
        "dimension": "risk_structure",
        "type": "string",
        "required": False,
        "description": "Risk structure for attribution, for example defined_risk, capped, debit, or credit.",
        "accepted_aliases": ["risk_profile", "risk_type"],
        "normalization_rule": "trim_lower_snake_case",
        "missing_policy": "allow_cell_mapping_with_warning",
    },
    "replay_window_id": {
        "dimension": "window",
        "type": "string",
        "required": False,
        "description": "Historical replay window or batch identifier.",
        "accepted_aliases": ["window", "window_id", "batch_id"],
        "normalization_rule": "trim_string",
        "missing_policy": "allow_cell_mapping_with_warning",
    },
    "edge_score": {
        "dimension": "score",
        "type": "number",
        "required": False,
        "description": "Normalized edge or score associated with the outcome record when available.",
        "accepted_aliases": ["historical_edge_score", "risk_adjusted_edge_score", "score"],
        "normalization_rule": "coerce_number",
        "missing_policy": "allow_cell_mapping_with_warning",
    },
    "outcome_state": {
        "dimension": "outcome",
        "type": "string",
        "required": False,
        "description": "Outcome classification, for example win, loss, ready, blocked, or needs_review.",
        "accepted_aliases": ["outcome", "result_state", "historical_edge_state"],
        "normalization_rule": "trim_lower_snake_case",
        "missing_policy": "allow_cell_mapping_with_warning",
    },
}

DIMENSION_TO_REQUIRED_FIELDS = {
    "regime": ["regime_state"],
    "asset_behavior": ["asset_behavior_state"],
    "option_behavior": ["option_behavior_state"],
    "strategy": ["strategy_id", "strategy_family"],
    "symbol": ["symbol"],
    "horizon": ["horizon_days"],
}

DIMENSION_TO_OPTIONAL_FIELDS = {
    "asset_class": ["asset_class"],
    "direction": ["strategy_direction"],
    "risk_structure": ["risk_structure"],
    "window": ["replay_window_id"],
    "score": ["edge_score"],
    "outcome": ["outcome_state"],
}


def build_signalforge_historical_replay_matrix_metadata_contract(
    *,
    historical_edge_matrix_backfill_plan_source: Mapping[str, Any],
    strategy_matrix_edge_inventory_source: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a metadata contract for exact strategy-matrix edge validation."""

    plan_summary = _extract_plan_summary(historical_edge_matrix_backfill_plan_source)
    inventory_summary = _extract_inventory_summary(strategy_matrix_edge_inventory_source or {})

    blocked_reasons: list[str] = []
    warnings: list[str] = []

    if not plan_summary:
        blocked_reasons.append("historical_edge_matrix_backfill_plan_source_required")

    matrix_mapping_state = str(plan_summary.get("matrix_mapping_state") or "unknown")
    records_requiring_mapping_count = _as_int(plan_summary.get("records_requiring_mapping_count"), default=0)
    exact_matrix_cell_ready_record_count = _as_int(
        plan_summary.get("exact_matrix_cell_ready_record_count"), default=0
    )

    required_backfill_dimensions = _ordered_unique(
        _as_text_list(plan_summary.get("required_backfill_dimensions"))
    )
    required_normalization_dimensions = _ordered_unique(
        _as_text_list(plan_summary.get("required_normalization_dimensions"))
    )

    if not required_backfill_dimensions and not required_normalization_dimensions:
        # Contract is still useful even if the plan is a summary-shaped fixture. Use the
        # canonical exact matrix dimensions as the baseline contract.
        required_contract_dimensions = list(REQUIRED_EXACT_MATRIX_DIMENSIONS)
    else:
        required_contract_dimensions = _ordered_unique(
            [*required_backfill_dimensions, *required_normalization_dimensions]
        )

    missing_contract_dimensions = [
        dimension
        for dimension in required_contract_dimensions
        if dimension not in REQUIRED_EXACT_MATRIX_DIMENSIONS
    ]
    for dimension in missing_contract_dimensions:
        blocked_reasons.append(f"unsupported_required_matrix_dimension:{dimension}")

    required_fields = _build_required_fields(required_contract_dimensions)
    optional_fields = _build_optional_fields()
    normalization_rules = _build_normalization_rules(required_fields, optional_fields)
    validation_rules = _build_validation_rules(required_contract_dimensions)
    matrix_cell_key_fields = _matrix_cell_key_fields(required_contract_dimensions)

    if "strategy" in required_contract_dimensions:
        warnings.append("strategy_dimension_requires_exact_strategy_id_and_strategy_family")
    if records_requiring_mapping_count > 0:
        warnings.append("historical_replay_outcomes_require_metadata_contract_backfill")
    if matrix_mapping_state == "portfolio_level_edge_requires_matrix_dimension_backfill":
        warnings.append("portfolio_level_edge_evidence_requires_exact_matrix_metadata")

    if blocked_reasons:
        contract_state = "blocked"
    else:
        contract_state = "ready"

    result = {
        "artifact_type": ARTIFACT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "contract_id": _contract_id(required_fields, optional_fields, validation_rules),
        "contract_state": contract_state,
        "status": contract_state,
        "is_ready": contract_state == "ready",
        "created_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "matrix_mapping_state": matrix_mapping_state,
        "recommended_next_adapter": RECOMMENDED_NEXT_ADAPTER,
        "ready_to_build_exact_matrix_edge_summary": False,
        "ready_to_build_metadata_backfill_adapter": contract_state == "ready",
        "records_requiring_mapping_count": records_requiring_mapping_count,
        "exact_matrix_cell_ready_record_count": exact_matrix_cell_ready_record_count,
        "expected_matrix_cell_count": _as_int(
            plan_summary.get("expected_matrix_cell_count")
            or inventory_summary.get("expected_matrix_cell_count"),
            default=0,
        ),
        "required_matrix_dimensions": required_contract_dimensions,
        "required_backfill_dimensions": required_backfill_dimensions,
        "required_normalization_dimensions": required_normalization_dimensions,
        "matrix_cell_key_fields": matrix_cell_key_fields,
        "required_fields": required_fields,
        "optional_fields": optional_fields,
        "normalization_rules": normalization_rules,
        "validation_rules": validation_rules,
        "source_requirements": _build_source_requirements(required_contract_dimensions),
        "backfill_output_requirements": _build_backfill_output_requirements(),
        "manual_review_rules": _build_manual_review_rules(),
        "blocked_reasons": _ordered_unique(blocked_reasons),
        "warnings": _ordered_unique(warnings),
        "automatic_action": None,
        "automatic_strategy_change": None,
        "order_intent": None,
        "requires_manual_approval": True,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }
    result["contract_summary"] = build_historical_replay_matrix_metadata_contract_summary(result)
    return result


def build_historical_replay_matrix_metadata_contract_summary(
    contract: Mapping[str, Any]
) -> dict[str, Any]:
    """Build a compact summary for CLI/file-writer output."""

    return {
        "artifact_type": "signalforge_historical_replay_matrix_metadata_contract_summary",
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "contract_state": str(contract.get("contract_state") or "blocked"),
        "status": str(contract.get("status") or contract.get("contract_state") or "blocked"),
        "is_ready": bool(contract.get("is_ready")),
        "matrix_mapping_state": str(contract.get("matrix_mapping_state") or "unknown"),
        "recommended_next_adapter": str(
            contract.get("recommended_next_adapter") or RECOMMENDED_NEXT_ADAPTER
        ),
        "ready_to_build_metadata_backfill_adapter": bool(
            contract.get("ready_to_build_metadata_backfill_adapter")
        ),
        "ready_to_build_exact_matrix_edge_summary": bool(
            contract.get("ready_to_build_exact_matrix_edge_summary")
        ),
        "records_requiring_mapping_count": _as_int(
            contract.get("records_requiring_mapping_count"), default=0
        ),
        "expected_matrix_cell_count": _as_int(contract.get("expected_matrix_cell_count"), default=0),
        "required_matrix_dimension_count": len(_as_text_list(contract.get("required_matrix_dimensions"))),
        "required_field_count": len(_as_sequence(contract.get("required_fields"))),
        "optional_field_count": len(_as_sequence(contract.get("optional_fields"))),
        "normalization_rule_count": len(_as_sequence(contract.get("normalization_rules"))),
        "validation_rule_count": len(_as_sequence(contract.get("validation_rules"))),
        "matrix_cell_key_fields": _as_text_list(contract.get("matrix_cell_key_fields")),
        "blocked_reasons": _as_text_list(contract.get("blocked_reasons")),
        "warnings": _as_text_list(contract.get("warnings")),
        "explicit_exclusions": _as_text_list(contract.get("explicit_exclusions")),
        "order_intent": contract.get("order_intent"),
        "automatic_action": contract.get("automatic_action"),
        "automatic_strategy_change": contract.get("automatic_strategy_change"),
        "requires_manual_approval": bool(contract.get("requires_manual_approval", True)),
    }


def _build_required_fields(required_dimensions: Sequence[str]) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    for dimension in REQUIRED_EXACT_MATRIX_DIMENSIONS:
        if dimension not in required_dimensions:
            continue
        for field_name in DIMENSION_TO_REQUIRED_FIELDS.get(dimension, []):
            field = deepcopy(FIELD_DEFINITIONS[field_name])
            field["field_name"] = field_name
            field["contract_role"] = "required_exact_matrix_dimension"
            fields.append(field)
    return fields


def _build_optional_fields() -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    for dimension in OPTIONAL_USEFUL_DIMENSIONS:
        for field_name in DIMENSION_TO_OPTIONAL_FIELDS.get(dimension, []):
            field = deepcopy(FIELD_DEFINITIONS[field_name])
            field["field_name"] = field_name
            field["contract_role"] = "optional_enrichment_dimension"
            fields.append(field)
    return fields


def _build_normalization_rules(
    required_fields: Sequence[Mapping[str, Any]],
    optional_fields: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for field in [*required_fields, *optional_fields]:
        field_name = str(field.get("field_name") or "")
        rule = str(field.get("normalization_rule") or "")
        if not field_name or not rule:
            continue
        key = (field_name, rule)
        if key in seen:
            continue
        seen.add(key)
        rules.append(
            {
                "field_name": field_name,
                "dimension": str(field.get("dimension") or ""),
                "normalization_rule": rule,
                "accepted_aliases": _as_text_list(field.get("accepted_aliases")),
            }
        )
    return rules


def _build_validation_rules(required_dimensions: Sequence[str]) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    for dimension in required_dimensions:
        fields = DIMENSION_TO_REQUIRED_FIELDS.get(dimension, [])
        if not fields:
            continue
        rules.append(
            {
                "rule_id": f"required_dimension_present:{dimension}",
                "dimension": dimension,
                "required_fields": fields,
                "failure_state": "needs_review",
                "failure_reason": f"missing_or_unmapped_matrix_dimension:{dimension}",
            }
        )
    rules.append(
        {
            "rule_id": "exact_matrix_cell_key_must_be_deterministic",
            "dimension": "matrix_cell_key",
            "required_fields": _matrix_cell_key_fields(required_dimensions),
            "failure_state": "needs_review",
            "failure_reason": "non_deterministic_matrix_cell_key",
        }
    )
    return rules


def _matrix_cell_key_fields(required_dimensions: Sequence[str]) -> list[str]:
    fields: list[str] = []
    for dimension in REQUIRED_EXACT_MATRIX_DIMENSIONS:
        if dimension not in required_dimensions:
            continue
        fields.extend(DIMENSION_TO_REQUIRED_FIELDS.get(dimension, []))
    return fields


def _build_source_requirements(required_dimensions: Sequence[str]) -> list[dict[str, Any]]:
    requirements: list[dict[str, Any]] = []
    for dimension in required_dimensions:
        requirements.append(
            {
                "dimension": dimension,
                "required_fields": DIMENSION_TO_REQUIRED_FIELDS.get(dimension, []),
                "source_requirement": _source_requirement_for_dimension(dimension),
                "unavailable_policy": "emit_needs_review_record_do_not_guess",
            }
        )
    return requirements


def _source_requirement_for_dimension(dimension: str) -> str:
    requirements = {
        "regime": "join historical replay timestamp and symbol to regime classification artifact",
        "asset_behavior": "join historical replay timestamp and symbol to asset behavior artifact",
        "option_behavior": "join historical replay timestamp and symbol to option behavior artifact",
        "strategy": "map replay setup/contract outcome to strategy catalog or strategy matrix row",
        "symbol": "normalize from replay outcome, contract outcome, or underlying field",
        "horizon": "normalize from replay horizon, window, selected_window_days, or target_horizon_days",
    }
    return requirements.get(dimension, "source mapping required")


def _build_backfill_output_requirements() -> list[dict[str, Any]]:
    return [
        {
            "requirement_id": "preserve_original_replay_outcome",
            "description": "Backfilled records must retain the original source outcome payload or source reference.",
        },
        {
            "requirement_id": "emit_mapping_confidence",
            "description": "Each mapped dimension must include mapped, partial, missing, or inferred confidence state.",
        },
        {
            "requirement_id": "do_not_promote_inferred_records_to_ready",
            "description": "Records requiring inference or manual mapping must remain needs_review for exact matrix edge.",
        },
        {
            "requirement_id": "preserve_no_execution_boundary",
            "description": "Backfill artifacts must not create order intent, broker calls, fills, or execution actions.",
        },
    ]


def _build_manual_review_rules() -> list[dict[str, Any]]:
    return [
        {
            "rule_id": "missing_required_dimension_requires_review",
            "review_reason": "missing_required_matrix_dimension",
            "automatic_promotion_allowed": False,
        },
        {
            "rule_id": "partial_symbol_or_horizon_requires_normalization_review",
            "review_reason": "partial_required_matrix_dimension",
            "automatic_promotion_allowed": False,
        },
        {
            "rule_id": "strategy_alias_mapping_requires_catalog_match",
            "review_reason": "strategy_dimension_alias_requires_catalog_match",
            "automatic_promotion_allowed": False,
        },
    ]


def _extract_plan_summary(source: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(source, Mapping):
        return {}

    for key in (
        "backfill_plan_summary",
        "plan_summary",
        "summary",
        "coverage_summary",
        "contract_summary",
    ):
        value = source.get(key)
        if isinstance(value, Mapping):
            merged = dict(value)
            for passthrough_key in (
                "matrix_mapping_state",
                "records_requiring_mapping_count",
                "exact_matrix_cell_ready_record_count",
                "expected_matrix_cell_count",
                "required_backfill_dimensions",
                "required_normalization_dimensions",
            ):
                if passthrough_key in source and passthrough_key not in merged:
                    merged[passthrough_key] = source[passthrough_key]
            return merged

    if any(
        key in source
        for key in (
            "required_backfill_dimensions",
            "required_normalization_dimensions",
            "matrix_mapping_state",
            "records_requiring_mapping_count",
        )
    ):
        return dict(source)

    return {}


def _extract_inventory_summary(source: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(source, Mapping):
        return {}
    for key in ("inventory_summary", "summary", "matrix_inventory_summary"):
        value = source.get(key)
        if isinstance(value, Mapping):
            return dict(value)
    return dict(source)


def _contract_id(
    required_fields: Sequence[Mapping[str, Any]],
    optional_fields: Sequence[Mapping[str, Any]],
    validation_rules: Sequence[Mapping[str, Any]],
) -> str:
    material = {
        "required_fields": [field.get("field_name") for field in required_fields],
        "optional_fields": [field.get("field_name") for field in optional_fields],
        "validation_rules": [rule.get("rule_id") for rule in validation_rules],
    }
    digest = sha256(repr(material).encode("utf-8")).hexdigest()[:16]
    return f"historical_replay_matrix_metadata_contract_{digest}"


def _as_sequence(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _as_text_list(value: Any) -> list[str]:
    values = _as_sequence(value)
    result: list[str] = []
    for item in values:
        if item is None:
            continue
        text = str(item).strip()
        if text:
            result.append(text)
    return result


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


def _as_int(value: Any, *, default: int) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default
