from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from src.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS
from src.options_strategy.catalog import (
    OptionStrategyDefinition,
    build_option_strategy_catalog,
)


STRATEGY_MATRIX_EDGE_INVENTORY_SCHEMA_VERSION = "signalforge_strategy_matrix_edge_inventory.v1"

COVERED_CAPABILITIES = [
    "strategy_matrix_edge_inventory",
    "regime_asset_option_behavior_matrix_review",
    "strategy_catalog_to_edge_evidence_mapping",
    "matrix_available_strategy_evidence_gap_detection",
    "paper_fixture_separation_from_strategy_selection",
]

DEPENDS_ON_CAPABILITIES = [
    "options_strategy_catalog",
    "regime_asset_options_alignment",
    "strategy_family_eligibility",
    "option_strategy_candidate_generation",
    "historical_edge_validation",
    "portfolio_candidate_selection",
]

OPTION_CANDIDATE_KEYS = (
    "candidates",
    "ready_candidates",
    "needs_review_candidates",
    "blocked_candidates",
    "option_strategy_candidates",
    "strategy_candidates",
    "items",
    "data",
    "rows",
)

ELIGIBILITY_ITEM_KEYS = (
    "strategy_family_eligibility_items",
    "eligibility_items",
    "items",
    "data",
    "rows",
)

HISTORICAL_EDGE_ITEM_KEYS = (
    "strategy_edge_items",
    "historical_edge_items",
    "edge_items",
    "candidate_rows",
    "scenario_rows",
    "items",
    "data",
    "rows",
)

PORTFOLIO_SELECTION_ITEM_KEYS = (
    "candidate_rows",
    "portfolio_candidate_rows",
    "items",
    "data",
    "rows",
)

POSITIVE_EDGE_STATES = {
    "historical_positive_edge_candidate",
    "positive_edge_candidate",
    "validated_positive_edge",
    "edge_validated",
    "ready",
}

CURRENT_AVAILABLE_FAMILY_STATUSES = {
    "favored",
    "favored_constrained",
    "allowed",
    "allowed_constrained",
    "ready",
    "constrained",
}

CURRENT_REVIEW_FAMILY_STATUSES = {
    "review_required",
    "manual_review_only",
    "needs_review",
    "data_review_required",
}

CURRENT_BLOCKED_FAMILY_STATUSES = {
    "blocked",
    "hard_blocked",
    "not_allowed",
}

STRATEGY_TO_ELIGIBILITY_FAMILIES: dict[str, list[str]] = {
    "bull_call_debit_spread": ["debit_spread", "directional_long_premium"],
    "bear_put_debit_spread": ["debit_spread", "directional_long_premium"],
    "put_credit_spread": ["credit_spread", "defined_risk_short_premium"],
    "call_credit_spread": ["credit_spread", "defined_risk_short_premium"],
    "iron_condor": ["defined_risk_neutral", "defined_risk_short_premium"],
    "iron_butterfly": ["defined_risk_neutral", "defined_risk_short_premium"],
    "calendar_spread": ["defined_risk_neutral", "debit_spread"],
    "diagonal_spread": ["debit_spread", "directional_long_premium"],
    "long_call": ["directional_long_premium", "long_gamma"],
    "long_put": ["directional_long_premium", "long_gamma"],
    "protective_put": ["protective_put_spread", "defined_risk_only"],
    "collar": ["protective_put_spread", "defined_risk_only"],
    "covered_call": ["defined_risk_short_premium", "defined_risk_only"],
}


def build_signalforge_strategy_matrix_edge_inventory(
    *,
    strategy_family_eligibility_source: Mapping[str, Any] | Sequence[Any] | None = None,
    option_strategy_candidate_source: Mapping[str, Any] | Sequence[Any] | None = None,
    historical_edge_source: Mapping[str, Any] | Sequence[Any] | None = None,
    portfolio_candidate_selection_source: Mapping[str, Any] | Sequence[Any] | None = None,
    strategy_catalog_source: Mapping[str, Any] | Sequence[Any] | None = None,
) -> dict[str, Any]:
    """Inventory the strategy matrix and map it to available edge evidence.

    This artifact reconciles the intended strategy-selection architecture:
    regime + asset behavior + option behavior determine available strategy
    families, while historical edge evidence determines which matrix cells are
    validated enough to continue downstream.

    It does not generate contracts, request broker data, submit orders, model
    fills, infer slippage, or authorize automatic strategy changes.
    """

    source_artifacts = {
        "strategy_catalog_source": _source_artifact_type(strategy_catalog_source) or "src.options_strategy.catalog",
        "strategy_family_eligibility_source": _source_artifact_type(strategy_family_eligibility_source),
        "option_strategy_candidate_source": _source_artifact_type(option_strategy_candidate_source),
        "historical_edge_source": _source_artifact_type(historical_edge_source),
        "portfolio_candidate_selection_source": _source_artifact_type(portfolio_candidate_selection_source),
    }

    catalog_definitions = _catalog_definitions(strategy_catalog_source)
    if not catalog_definitions:
        return _blocked_result(
            ["missing_strategy_catalog"],
            source_artifacts=source_artifacts,
        )

    eligibility_index = _build_eligibility_index(strategy_family_eligibility_source)
    option_candidate_index = _build_option_candidate_index(option_strategy_candidate_source)
    historical_exact_index = _build_historical_exact_index(historical_edge_source)
    historical_portfolio_evidence = _portfolio_level_edge_evidence(
        historical_edge_source=historical_edge_source,
        portfolio_candidate_selection_source=portfolio_candidate_selection_source,
    )

    items = [
        _build_inventory_item(
            definition=definition,
            eligibility_index=eligibility_index,
            option_candidate_index=option_candidate_index,
            historical_exact_index=historical_exact_index,
            historical_portfolio_evidence=historical_portfolio_evidence,
        )
        for definition in catalog_definitions
    ]

    summary = _summary(items)
    warnings = _warnings(summary=summary, historical_portfolio_evidence=historical_portfolio_evidence)
    status = _status(summary=summary, warnings=warnings)

    return {
        "artifact_type": "signalforge_strategy_matrix_edge_inventory",
        "schema_version": STRATEGY_MATRIX_EDGE_INVENTORY_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "contract": "strategy_matrix_edge_inventory",
        "adapter_type": "strategy_matrix_edge_inventory_builder",
        "review_scope": "strategy_matrix_edge_mapping_not_contract_selection_or_execution",
        "source_artifacts": source_artifacts,
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "strategy_matrix_edge_inventory_items": items,
        "strategy_matrix_edge_inventory_summary": summary,
        "portfolio_level_edge_evidence": historical_portfolio_evidence,
        "warnings": warnings,
        "blocked_reasons": [],
        "next_build_recommendations": _next_build_recommendations(summary),
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _catalog_definitions(
    strategy_catalog_source: Mapping[str, Any] | Sequence[Any] | None,
) -> list[OptionStrategyDefinition | Mapping[str, Any]]:
    if strategy_catalog_source is None:
        return list(build_option_strategy_catalog())

    if isinstance(strategy_catalog_source, Mapping):
        items = _extract_items(
            strategy_catalog_source,
            ("strategies", "strategy_catalog", "catalog", "items", "data", "rows"),
        )
        return [item for item in items if isinstance(item, Mapping)]

    if isinstance(strategy_catalog_source, Sequence) and not isinstance(strategy_catalog_source, (str, bytes)):
        return [item for item in strategy_catalog_source if isinstance(item, Mapping)]

    return []


def _build_inventory_item(
    *,
    definition: OptionStrategyDefinition | Mapping[str, Any],
    eligibility_index: Mapping[str, list[dict[str, Any]]],
    option_candidate_index: Mapping[str, list[dict[str, Any]]],
    historical_exact_index: Mapping[str, list[dict[str, Any]]],
    historical_portfolio_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    definition_dict = _definition_to_dict(definition)
    strategy = _clean_text(definition_dict.get("strategy")) or "unknown_strategy"
    eligibility_families = _strategy_eligibility_families(strategy, definition_dict)

    current_availability = _current_availability(
        strategy=strategy,
        eligibility_families=eligibility_families,
        eligibility_index=eligibility_index,
        option_candidate_index=option_candidate_index,
    )
    edge_mapping = _edge_mapping(
        strategy=strategy,
        eligibility_families=eligibility_families,
        historical_exact_index=historical_exact_index,
        historical_portfolio_evidence=historical_portfolio_evidence,
    )

    matrix_cell_state = _matrix_cell_state(
        definition_dict=definition_dict,
        current_availability=current_availability,
        edge_mapping=edge_mapping,
    )

    return {
        "strategy": strategy,
        "display_name": definition_dict.get("display_name"),
        "direction": definition_dict.get("direction"),
        "setup_families": list(_strings(definition_dict.get("setup_families"))),
        "defined_risk": bool(definition_dict.get("defined_risk")),
        "risk_profile": definition_dict.get("risk_profile"),
        "eligibility_families": eligibility_families,
        "preferred_regimes": list(_strings(definition_dict.get("preferred_regimes"))),
        "preferred_asset_behaviors": list(_strings(definition_dict.get("preferred_asset_behaviors"))),
        "preferred_option_behaviors": _preferred_option_behaviors(definition_dict.get("preferred_option_behaviors")),
        "required_context": list(_strings(definition_dict.get("required_context"))),
        "blocked_when": list(_strings(definition_dict.get("blocked_when"))),
        "current_availability": current_availability,
        "historical_edge_mapping": edge_mapping,
        "matrix_cell_state": matrix_cell_state,
        "next_validation_action": _next_validation_action(matrix_cell_state, edge_mapping),
    }


def _current_availability(
    *,
    strategy: str,
    eligibility_families: Sequence[str],
    eligibility_index: Mapping[str, list[dict[str, Any]]],
    option_candidate_index: Mapping[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    ready_symbols: list[str] = []
    needs_review_symbols: list[str] = []
    blocked_symbols: list[str] = []
    evidence_records: list[dict[str, Any]] = []

    for candidate in option_candidate_index.get(strategy, []):
        symbol = _clean_symbol(candidate.get("symbol"))
        status = _clean_text(candidate.get("status") or candidate.get("candidate_state") or candidate.get("coverage_status")) or "ready"
        if not symbol:
            continue
        if status == "ready":
            ready_symbols.append(symbol)
        elif status == "blocked":
            blocked_symbols.append(symbol)
        else:
            needs_review_symbols.append(symbol)
        evidence_records.append(
            {
                "source": "option_strategy_candidate_source",
                "symbol": symbol,
                "status": status,
                "score": _safe_float(candidate.get("score") or candidate.get("full_options_view_score")),
            }
        )

    for family in eligibility_families:
        for record in eligibility_index.get(family, []):
            symbol = _clean_symbol(record.get("symbol"))
            family_status = _clean_text(record.get("family_status"))
            if not symbol or not family_status:
                continue
            if family_status in CURRENT_AVAILABLE_FAMILY_STATUSES:
                ready_symbols.append(symbol)
            elif family_status in CURRENT_BLOCKED_FAMILY_STATUSES:
                blocked_symbols.append(symbol)
            else:
                needs_review_symbols.append(symbol)
            evidence_records.append(
                {
                    "source": "strategy_family_eligibility_source",
                    "symbol": symbol,
                    "eligibility_family": family,
                    "family_status": family_status,
                    "coverage_status": record.get("coverage_status"),
                }
            )

    ready_symbols = _dedupe_strings(ready_symbols)
    needs_review_symbols = [symbol for symbol in _dedupe_strings(needs_review_symbols) if symbol not in ready_symbols]
    blocked_symbols = [symbol for symbol in _dedupe_strings(blocked_symbols) if symbol not in ready_symbols and symbol not in needs_review_symbols]

    if ready_symbols:
        status = "currently_available"
    elif needs_review_symbols:
        status = "current_availability_needs_review"
    elif blocked_symbols:
        status = "currently_blocked"
    else:
        status = "not_observed_in_current_sources"

    return {
        "current_availability_state": status,
        "ready_symbols": ready_symbols,
        "needs_review_symbols": needs_review_symbols,
        "blocked_symbols": blocked_symbols,
        "evidence_record_count": len(evidence_records),
        "evidence_records": evidence_records[:25],
    }


def _edge_mapping(
    *,
    strategy: str,
    eligibility_families: Sequence[str],
    historical_exact_index: Mapping[str, list[dict[str, Any]]],
    historical_portfolio_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    exact_records = list(historical_exact_index.get(strategy, []))
    family_records: list[dict[str, Any]] = []
    for family in eligibility_families:
        family_records.extend(historical_exact_index.get(family, []))

    positive_exact = [record for record in exact_records if _is_positive_edge_record(record)]
    positive_family = [record for record in family_records if _is_positive_edge_record(record)]

    portfolio_state = _clean_text(historical_portfolio_evidence.get("portfolio_edge_evidence_state"))
    has_portfolio_evidence = portfolio_state in {
        "portfolio_level_positive_edge_candidate",
        "portfolio_level_edge_evidence_present",
    }

    if positive_exact:
        mapping_state = "exact_strategy_edge_validated"
    elif positive_family:
        mapping_state = "family_edge_evidence_present"
    elif has_portfolio_evidence:
        mapping_state = "portfolio_level_edge_evidence_requires_matrix_mapping"
    else:
        mapping_state = "missing_historical_edge_evidence"

    return {
        "edge_mapping_state": mapping_state,
        "exact_strategy_evidence_count": len(exact_records),
        "positive_exact_strategy_evidence_count": len(positive_exact),
        "family_evidence_count": len(family_records),
        "positive_family_evidence_count": len(positive_family),
        "portfolio_level_edge_evidence_state": portfolio_state,
        "portfolio_level_primary_candidate": historical_portfolio_evidence.get("primary_candidate"),
        "evidence_records": [*_compact_records(positive_exact), *_compact_records(positive_family)][:25],
    }


def _matrix_cell_state(
    *,
    definition_dict: Mapping[str, Any],
    current_availability: Mapping[str, Any],
    edge_mapping: Mapping[str, Any],
) -> str:
    if not bool(definition_dict.get("defined_risk")):
        return "blocked_undefined_or_unapproved_risk"

    edge_state = _clean_text(edge_mapping.get("edge_mapping_state"))
    availability_state = _clean_text(current_availability.get("current_availability_state"))

    if edge_state == "exact_strategy_edge_validated" and availability_state == "currently_available":
        return "matrix_cell_ready_for_ev_or_candidate_selection"
    if edge_state == "exact_strategy_edge_validated":
        return "edge_validated_but_not_currently_available"
    if edge_state == "family_edge_evidence_present" and availability_state == "currently_available":
        return "available_with_family_edge_review_required"
    if edge_state == "portfolio_level_edge_evidence_requires_matrix_mapping":
        return "portfolio_edge_present_matrix_mapping_required"
    if availability_state == "currently_available":
        return "available_but_missing_edge_mapping"
    return "matrix_cell_requires_edge_inventory_review"


def _next_validation_action(matrix_cell_state: str, edge_mapping: Mapping[str, Any]) -> str:
    if matrix_cell_state == "matrix_cell_ready_for_ev_or_candidate_selection":
        return "eligible_for_downstream_ev_scoring_or_candidate_selection"
    if matrix_cell_state == "edge_validated_but_not_currently_available":
        return "wait_for_regime_asset_option_behavior_availability"
    if matrix_cell_state == "available_with_family_edge_review_required":
        return "map_family_edge_evidence_to_specific_strategy_before_promotion"
    if matrix_cell_state == "portfolio_edge_present_matrix_mapping_required":
        return "reconcile_portfolio_level_edge_artifact_to_strategy_matrix_cell"
    if matrix_cell_state == "available_but_missing_edge_mapping":
        return "run_historical_edge_validation_for_available_matrix_cell"
    if _clean_text(edge_mapping.get("edge_mapping_state")) == "missing_historical_edge_evidence":
        return "no_trade_promotion_until_edge_evidence_exists"
    return "manual_review_required"


def _build_eligibility_index(source: Mapping[str, Any] | Sequence[Any] | None) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in _extract_items(source, ELIGIBILITY_ITEM_KEYS):
        if not isinstance(item, Mapping):
            continue
        symbol = _clean_symbol(item.get("symbol"))
        coverage_status = _clean_text(item.get("coverage_status"))
        statuses = item.get("strategy_family_statuses")
        if isinstance(statuses, Mapping):
            for family, status in statuses.items():
                family_key = _clean_text(family)
                if not family_key:
                    continue
                index[family_key].append(
                    {
                        "symbol": symbol,
                        "family_status": _clean_text(status),
                        "coverage_status": coverage_status,
                    }
                )
        else:
            for family in _strings(item.get("favored_strategy_families")):
                index[family].append({"symbol": symbol, "family_status": "favored", "coverage_status": coverage_status})
            for family in _strings(item.get("allowed_strategy_families")):
                index[family].append({"symbol": symbol, "family_status": "allowed", "coverage_status": coverage_status})
            for family in _strings(item.get("blocked_strategy_families")):
                index[family].append({"symbol": symbol, "family_status": "blocked", "coverage_status": coverage_status})
    return dict(index)


def _build_option_candidate_index(source: Mapping[str, Any] | Sequence[Any] | None) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in _extract_items(source, OPTION_CANDIDATE_KEYS):
        if not isinstance(item, Mapping):
            continue
        strategy = _clean_text(item.get("strategy") or item.get("strategy_id") or item.get("selected_strategy"))
        if strategy:
            index[strategy].append(dict(item))
    return dict(index)


def _build_historical_exact_index(source: Mapping[str, Any] | Sequence[Any] | None) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in _extract_items(source, HISTORICAL_EDGE_ITEM_KEYS):
        if not isinstance(item, Mapping):
            continue
        keys = [
            item.get("strategy"),
            item.get("strategy_id"),
            item.get("strategy_family"),
            item.get("selected_strategy_family"),
            item.get("variant_id"),
            item.get("scenario_id"),
        ]
        for key in keys:
            clean_key = _clean_text(key)
            if clean_key:
                index[clean_key].append(dict(item))
    return dict(index)


def _portfolio_level_edge_evidence(
    *,
    historical_edge_source: Mapping[str, Any] | Sequence[Any] | None,
    portfolio_candidate_selection_source: Mapping[str, Any] | Sequence[Any] | None,
) -> dict[str, Any]:
    portfolio_source = portfolio_candidate_selection_source if isinstance(portfolio_candidate_selection_source, Mapping) else None
    historical_source = historical_edge_source if isinstance(historical_edge_source, Mapping) else None

    primary_candidate = None
    if portfolio_source is not None:
        primary_candidate = portfolio_source.get("primary_candidate")

    historical_edge_state = None
    historical_edge_score = None
    strategy_adjusted_win_rate = None
    if portfolio_source is not None:
        historical_edge_state = portfolio_source.get("historical_edge_state")
        historical_edge_score = portfolio_source.get("historical_edge_score")
        strategy_adjusted_win_rate = portfolio_source.get("strategy_adjusted_win_rate")
    elif historical_source is not None:
        historical_edge_state = historical_source.get("historical_edge_state") or historical_source.get("edge_state")
        historical_edge_score = historical_source.get("historical_edge_score") or historical_source.get("edge_score")

    candidate_rows = _extract_items(portfolio_candidate_selection_source, PORTFOLIO_SELECTION_ITEM_KEYS)
    if not candidate_rows:
        candidate_rows = _extract_items(historical_edge_source, HISTORICAL_EDGE_ITEM_KEYS)

    positive_state = _clean_text(historical_edge_state) in POSITIVE_EDGE_STATES
    has_candidate_rows = bool(candidate_rows)
    has_primary = isinstance(primary_candidate, Mapping)

    if positive_state or has_primary:
        evidence_state = "portfolio_level_positive_edge_candidate"
    elif has_candidate_rows:
        evidence_state = "portfolio_level_edge_evidence_present"
    else:
        evidence_state = "missing_portfolio_level_edge_evidence"

    return {
        "portfolio_edge_evidence_state": evidence_state,
        "historical_edge_state": historical_edge_state,
        "historical_edge_score": _safe_float(historical_edge_score),
        "strategy_adjusted_win_rate": _safe_float(strategy_adjusted_win_rate),
        "primary_candidate": _compact_candidate(primary_candidate),
        "candidate_row_count": len(candidate_rows),
        "candidate_rows": [_compact_candidate(row) for row in candidate_rows[:25] if isinstance(row, Mapping)],
        "evidence_scope": "portfolio_or_scenario_level_not_specific_strategy_cell",
    }


def _is_positive_edge_record(record: Mapping[str, Any]) -> bool:
    state = _clean_text(
        record.get("historical_edge_state")
        or record.get("edge_state")
        or record.get("status")
        or record.get("coverage_status")
    )
    if state in POSITIVE_EDGE_STATES:
        return True
    score = _safe_float(record.get("historical_edge_score") or record.get("edge_score") or record.get("primary_score"))
    return score is not None and score > 0


def _summary(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    state_counts = Counter(str(item.get("matrix_cell_state") or "unknown") for item in items)
    edge_counts = Counter(
        str((item.get("historical_edge_mapping") or {}).get("edge_mapping_state") or "unknown")
        for item in items
    )
    availability_counts = Counter(
        str((item.get("current_availability") or {}).get("current_availability_state") or "unknown")
        for item in items
    )
    return {
        "catalog_strategy_count": len(items),
        "defined_risk_strategy_count": sum(1 for item in items if item.get("defined_risk") is True),
        "matrix_cell_state_counts": dict(sorted(state_counts.items())),
        "edge_mapping_state_counts": dict(sorted(edge_counts.items())),
        "current_availability_state_counts": dict(sorted(availability_counts.items())),
        "exact_strategy_edge_validated_count": edge_counts.get("exact_strategy_edge_validated", 0),
        "family_edge_evidence_present_count": edge_counts.get("family_edge_evidence_present", 0),
        "portfolio_level_mapping_required_count": edge_counts.get("portfolio_level_edge_evidence_requires_matrix_mapping", 0),
        "missing_historical_edge_evidence_count": edge_counts.get("missing_historical_edge_evidence", 0),
        "currently_available_strategy_count": availability_counts.get("currently_available", 0),
        "ready_matrix_cell_count": state_counts.get("matrix_cell_ready_for_ev_or_candidate_selection", 0),
        "review_required_matrix_cell_count": sum(
            count for state, count in state_counts.items() if state != "matrix_cell_ready_for_ev_or_candidate_selection"
        ),
    }


def _warnings(*, summary: Mapping[str, Any], historical_portfolio_evidence: Mapping[str, Any]) -> list[str]:
    warnings: list[str] = []
    if int(summary.get("portfolio_level_mapping_required_count") or 0) > 0:
        warnings.append("portfolio_level_edge_evidence_requires_mapping_to_strategy_matrix_cells")
    if int(summary.get("missing_historical_edge_evidence_count") or 0) > 0:
        warnings.append("one_or_more_strategy_matrix_cells_missing_historical_edge_evidence")
    if _clean_text(historical_portfolio_evidence.get("portfolio_edge_evidence_state")) == "missing_portfolio_level_edge_evidence":
        warnings.append("missing_portfolio_level_edge_evidence_source")
    return warnings


def _status(*, summary: Mapping[str, Any], warnings: Sequence[str]) -> str:
    if int(summary.get("catalog_strategy_count") or 0) == 0:
        return "blocked"
    if warnings or int(summary.get("review_required_matrix_cell_count") or 0) > 0:
        return "needs_review"
    return "ready"


def _next_build_recommendations(summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    recommendations = [
        {
            "capability": "strategy_matrix_edge_reconciliation",
            "priority": "high",
            "recommendation": "Map historical edge artifacts back to regime + asset behavior + option behavior + strategy-family matrix cells before promoting paper-trading candidates.",
        }
    ]
    if int(summary.get("portfolio_level_mapping_required_count") or 0) > 0:
        recommendations.append(
            {
                "capability": "historical_edge_matrix_key_export",
                "priority": "high",
                "recommendation": "Export strategy matrix keys from historical replay outcomes so portfolio-level evidence can be tied to exact strategy cells instead of only scenario-level results.",
            }
        )
    return recommendations


def _definition_to_dict(definition: OptionStrategyDefinition | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(definition, OptionStrategyDefinition):
        return definition.to_dict()
    return dict(definition)


def _strategy_eligibility_families(strategy: str, definition_dict: Mapping[str, Any]) -> list[str]:
    families = list(STRATEGY_TO_ELIGIBILITY_FAMILIES.get(strategy, []))
    risk_profile = _clean_text(definition_dict.get("risk_profile"))
    if risk_profile == "defined_debit":
        families.append("debit_spread")
    elif risk_profile == "defined_credit":
        families.append("credit_spread")
        families.append("defined_risk_short_premium")
    elif risk_profile and risk_profile.startswith("defensive"):
        families.append("protective_put_spread")
        families.append("defined_risk_only")
    return _dedupe_strings(families)


def _preferred_option_behaviors(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): list(_strings(values)) for key, values in value.items()}


def _extract_items(source: Mapping[str, Any] | Sequence[Any] | None, keys: Sequence[str]) -> list[Any]:
    if source is None:
        return []
    if isinstance(source, Mapping):
        for key in keys:
            value = source.get(key)
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                return list(value)
        return []
    if isinstance(source, Sequence) and not isinstance(source, (str, bytes)):
        return list(source)
    return []


def _source_artifact_type(source: Any) -> str | None:
    if isinstance(source, Mapping):
        artifact_type = source.get("artifact_type") or source.get("operation_type")
        return str(artifact_type) if artifact_type is not None else "mapping"
    if isinstance(source, Sequence) and not isinstance(source, (str, bytes)):
        return "sequence"
    return None


def _compact_records(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [_compact_candidate(record) for record in records]


def _compact_candidate(candidate: Any) -> dict[str, Any] | None:
    if not isinstance(candidate, Mapping):
        return None
    keys = (
        "strategy",
        "strategy_id",
        "strategy_family",
        "selected_strategy_family",
        "scenario_id",
        "variant_id",
        "horizon",
        "historical_edge_state",
        "historical_edge_score",
        "primary_score",
        "total_return",
        "win_rate",
        "tail_stress_wipeout_horizon",
        "status",
        "symbol",
    )
    return {key: candidate.get(key) for key in keys if key in candidate}


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    return text or None


def _clean_symbol(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    return text or None


def _strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        return [str(key) for key in value.keys()]
    if isinstance(value, Sequence):
        return [str(item) for item in value if item is not None]
    return [str(value)]


def _dedupe_strings(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _blocked_result(blocked_reasons: Sequence[str], *, source_artifacts: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "artifact_type": "signalforge_strategy_matrix_edge_inventory",
        "schema_version": STRATEGY_MATRIX_EDGE_INVENTORY_SCHEMA_VERSION,
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "contract": "strategy_matrix_edge_inventory",
        "adapter_type": "strategy_matrix_edge_inventory_builder",
        "review_scope": "strategy_matrix_edge_mapping_not_contract_selection_or_execution",
        "source_artifacts": dict(source_artifacts),
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "strategy_matrix_edge_inventory_items": [],
        "strategy_matrix_edge_inventory_summary": _summary([]),
        "portfolio_level_edge_evidence": {},
        "warnings": [],
        "blocked_reasons": list(blocked_reasons),
        "next_build_recommendations": [],
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }
