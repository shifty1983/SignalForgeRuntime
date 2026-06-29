from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from src.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS
from src.strategy_selection.historical_replay_matrix_metadata_stamp import (
    MATRIX_METADATA_KEY,
    REQUIRED_MATRIX_METADATA_FIELDS,
    matrix_metadata_coverage,
    stamp_matrix_metadata,
    validate_matrix_metadata_record,
)


QUANTCONNECT_REPLAY_RESULT_IMPORT_VALIDATION_SCHEMA_VERSION = (
    "signalforge_quantconnect_replay_result_import_validation.v1"
)

COVERED_CAPABILITIES = [
    "quantconnect_replay_result_import_validator",
    "compact_quantconnect_replay_result_validation",
    "historical_market_option_replay_result_contract",
    "position_maintenance_replay_result_import",
    "quantconnect_replay_result_import_not_order_intent_or_execution",
    "historical_replay_matrix_metadata_import_validation",
]

DEPENDS_ON_CAPABILITIES = [
    "quantconnect_historical_replay_handoff",
    "position_maintenance_policy",
    "portfolio_construction_optimizer",
    "position_sizing_recommendation",
]

DEFAULT_RESULT_FILES = [
    "signalforge_qc_replay_manifest.json",
    "signalforge_qc_market_price_snapshots.json",
    "signalforge_qc_filtered_option_rows.json",
    "signalforge_qc_contract_outcome_snapshots.json",
    "signalforge_qc_maintenance_trigger_snapshots.json",
    "signalforge_qc_portfolio_replay_snapshots.json",
]

REPLAY_MANIFEST_REQUIRED_KEYS = [
    "artifact_type",
    "schema_version",
    "request_id",
    "as_of_run_time",
    "symbol_count",
    "candidate_count",
    "status",
]

TABLE_CONTRACTS: dict[str, dict[str, Any]] = {
    "signalforge_qc_market_price_snapshots.json": {
        "table_name": "market_price_snapshots",
        "allow_empty": False,
        "required_fields": ["symbol", "date", "open", "high", "low", "close", "volume"],
    },
    "signalforge_qc_filtered_option_rows.json": {
        "table_name": "filtered_option_rows",
        "allow_empty": False,
        "required_fields": [
            "underlying_symbol",
            "quote_date",
            "expiration",
            "strike",
            "option_right",
            "bid",
            "ask",
            "implied_volatility",
            "delta",
            "gamma",
            "theta",
            "vega",
            "open_interest",
            "volume",
            "underlying_price",
        ],
    },
    "signalforge_qc_contract_outcome_snapshots.json": {
        "table_name": "contract_outcome_snapshots",
        "allow_empty": False,
        "required_fields": [
            "symbol",
            "candidate_id",
            "quote_date",
            "horizon_days",
            "underlying_forward_return",
            "contract_mark_return",
            "max_adverse_excursion",
            "max_favorable_excursion",
        ],
    },
    "signalforge_qc_maintenance_trigger_snapshots.json": {
        "table_name": "maintenance_trigger_snapshots",
        "allow_empty": True,
        "required_fields": ["symbol", "candidate_id", "date", "trigger_type", "trigger_state", "trigger_value"],
    },
    "signalforge_qc_portfolio_replay_snapshots.json": {
        "table_name": "portfolio_replay_snapshots",
        "allow_empty": False,
        "required_fields": [
            "date",
            "candidate_count",
            "net_delta",
            "gross_abs_delta",
            "gross_abs_gamma",
            "gross_abs_vega",
            "net_theta",
        ],
    },
}

MATRIX_METADATA_REQUIRED_TABLES = {
    "contract_outcome_snapshots",
}

MATRIX_METADATA_OBSERVED_TABLES = {
    "market_price_snapshots",
    "filtered_option_rows",
    "contract_outcome_snapshots",
    "maintenance_trigger_snapshots",
    "portfolio_replay_snapshots",
}


def build_signalforge_quantconnect_replay_result_import_validation(
    handoff_source: Mapping[str, Any] | None,
    replay_result_sources: Mapping[str, Any] | None,
    *,
    result_file_names: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Validate compact QuantConnect replay results before SignalForge edge analysis.

    This validates files created by a QuantConnect research/backtest job against
    the handoff/result contract. It does not call QuantConnect, create orders,
    model fills/slippage, or execute anything live.
    """

    expected_files = _expected_files(handoff_source, result_file_names)
    replay_sources = replay_result_sources or {}
    blocked_reasons: list[str] = []
    file_validations: list[dict[str, Any]] = []
    table_row_counts: dict[str, int] = {}
    table_missing_field_counts: Counter[str] = Counter()
    matrix_metadata_table_summaries: dict[str, dict[str, Any]] = {}

    expected_request_id = _expected_request_id(handoff_source)
    replay_manifest_payload = replay_sources.get("signalforge_qc_replay_manifest.json")
    provided_request_id = _payload_request_id(replay_manifest_payload)

    if not isinstance(handoff_source, Mapping):
        blocked_reasons.append("missing_quantconnect_historical_replay_handoff_source")
    if expected_request_id and provided_request_id and expected_request_id != provided_request_id:
        blocked_reasons.append("request_id_mismatch")
    elif expected_request_id and not provided_request_id:
        blocked_reasons.append("missing_result_request_id")

    for filename in expected_files:
        payload = replay_sources.get(filename)
        validation = _validate_file(filename, payload)
        file_validations.append(validation)
        blocked_reasons.extend(validation.get("blocked_reasons", []))

        table_name = validation.get("table_name")
        if table_name:
            table_row_counts[str(table_name)] = int(validation.get("row_count") or 0)
            for field_name, count in (validation.get("missing_field_counts") or {}).items():
                table_missing_field_counts[str(field_name)] += int(count)
            matrix_summary = validation.get("matrix_metadata_summary")
            if isinstance(matrix_summary, Mapping):
                matrix_metadata_table_summaries[str(table_name)] = dict(matrix_summary)
                if int(matrix_summary.get("blocked_record_count") or 0) > 0:
                    blocked_reasons.append(f"blocked_matrix_metadata:{table_name}")

    summary = _summary(
        handoff_source=handoff_source,
        expected_files=expected_files,
        file_validations=file_validations,
        blocked_reasons=blocked_reasons,
        table_row_counts=table_row_counts,
        table_missing_field_counts=table_missing_field_counts,
        matrix_metadata_table_summaries=matrix_metadata_table_summaries,
        expected_request_id=expected_request_id,
        provided_request_id=provided_request_id,
    )
    status = "ready" if not blocked_reasons else "blocked"

    return {
        "artifact_type": "signalforge_quantconnect_replay_result_import_validation",
        "schema_version": QUANTCONNECT_REPLAY_RESULT_IMPORT_VALIDATION_SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "contract": "quantconnect_replay_result_import_validator",
        "adapter_type": "quantconnect_replay_result_import_validator_builder",
        "review_scope": "quantconnect_replay_result_import_validation_not_order_intent_or_execution",
        "source_artifacts": {
            "quantconnect_historical_replay_handoff_source": _source_artifact_type(handoff_source),
        },
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "next_build_recommendations": [
            {
                "capability": "historical_edge_validation",
                "priority": "high",
                "recommendation": "Use validated QuantConnect replay results to measure model edge, drawdown, and maintenance-policy impact historically.",
            }
        ],
        "expected_result_files": expected_files,
        "quantconnect_replay_result_file_validations": file_validations,
        "quantconnect_replay_result_import_validation_summary": summary,
        "matrix_metadata_envelope_key": MATRIX_METADATA_KEY,
        "matrix_cell_key_fields": list(REQUIRED_MATRIX_METADATA_FIELDS),
        "matrix_metadata_import_summary": summary.get("matrix_metadata_import_summary", {}),
        "ready_to_build_exact_matrix_edge_summary": bool(
            summary.get("matrix_metadata_import_summary", {}).get("ready_to_build_exact_matrix_edge_summary")
        ),
        "recommended_next_step": (
            "patch_historical_edge_validation_matrix_metadata"
            if summary.get("matrix_metadata_import_summary", {}).get("ready_to_build_exact_matrix_edge_summary")
            else "ensure_quantconnect_replay_results_include_matrix_metadata_envelope"
        ),
        "blocked_reasons": list(dict.fromkeys(blocked_reasons)),
        "portfolio_action": None,
        "position_size": None,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "automatic_close_order": None,
        "automatic_roll_order": None,
        "automatic_defense_order": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _validate_file(filename: str, payload: Any) -> dict[str, Any]:
    if payload is None:
        return {
            "file_name": filename,
            "status": "blocked",
            "is_valid": False,
            "blocked_reasons": [f"missing_result_file:{filename}"],
            "row_count": 0,
            "missing_field_counts": {},
        }

    if filename == "signalforge_qc_replay_manifest.json":
        return _validate_replay_manifest(filename, payload)

    table_contract = TABLE_CONTRACTS.get(filename)
    if not table_contract:
        return {
            "file_name": filename,
            "status": "ready",
            "is_valid": True,
            "blocked_reasons": [],
            "row_count": 0,
            "missing_field_counts": {},
        }

    table_name = str(table_contract["table_name"])
    rows = _extract_rows(payload, table_name)
    blocked_reasons: list[str] = []
    missing_field_counts: Counter[str] = Counter()

    if rows is None:
        blocked_reasons.append(f"missing_table_rows:{table_name}")
        rows = []
    if not rows and not bool(table_contract.get("allow_empty")):
        blocked_reasons.append(f"empty_required_table:{table_name}")

    required_fields = list(table_contract.get("required_fields") or [])
    for row in rows:
        if not isinstance(row, Mapping):
            blocked_reasons.append(f"invalid_row_shape:{table_name}")
            continue
        for field in required_fields:
            if field not in row or row.get(field) is None:
                missing_field_counts[field] += 1

    if missing_field_counts:
        blocked_reasons.append(f"missing_required_fields:{table_name}")

    matrix_metadata_summary = _matrix_metadata_summary_for_rows(table_name=table_name, rows=rows)

    return {
        "file_name": filename,
        "table_name": table_name,
        "status": "ready" if not blocked_reasons else "blocked",
        "is_valid": not blocked_reasons,
        "blocked_reasons": blocked_reasons,
        "row_count": len(rows),
        "required_fields": required_fields,
        "missing_field_counts": dict(sorted(missing_field_counts.items())),
        "matrix_metadata_summary": matrix_metadata_summary,
    }


def _validate_replay_manifest(filename: str, payload: Any) -> dict[str, Any]:
    blocked_reasons: list[str] = []
    missing_keys: list[str] = []
    if not isinstance(payload, Mapping):
        blocked_reasons.append("invalid_replay_manifest_shape")
    else:
        for key in REPLAY_MANIFEST_REQUIRED_KEYS:
            if key not in payload or payload.get(key) is None:
                missing_keys.append(key)
        if missing_keys:
            blocked_reasons.append("missing_replay_manifest_required_keys")

    return {
        "file_name": filename,
        "table_name": "replay_manifest",
        "status": "ready" if not blocked_reasons else "blocked",
        "is_valid": not blocked_reasons,
        "blocked_reasons": blocked_reasons,
        "row_count": 1 if isinstance(payload, Mapping) else 0,
        "required_fields": list(REPLAY_MANIFEST_REQUIRED_KEYS),
        "missing_field_counts": {key: 1 for key in missing_keys},
    }


def _summary(
    *,
    handoff_source: Mapping[str, Any] | None,
    expected_files: Sequence[str],
    file_validations: Sequence[Mapping[str, Any]],
    blocked_reasons: Sequence[str],
    table_row_counts: Mapping[str, int],
    table_missing_field_counts: Mapping[str, int],
    matrix_metadata_table_summaries: Mapping[str, Mapping[str, Any]],
    expected_request_id: str,
    provided_request_id: str,
) -> dict[str, Any]:
    valid_files = [item for item in file_validations if item.get("is_valid") is True]
    missing_files = [
        str(item.get("file_name"))
        for item in file_validations
        if any(str(reason).startswith("missing_result_file:") for reason in item.get("blocked_reasons", []))
    ]
    invalid_files = [
        str(item.get("file_name"))
        for item in file_validations
        if item.get("is_valid") is not True and str(item.get("file_name")) not in missing_files
    ]

    handoff_summary = {}
    if isinstance(handoff_source, Mapping):
        handoff_summary = handoff_source.get("quantconnect_historical_replay_handoff_summary") or {}

    matrix_metadata_import_summary = _matrix_metadata_import_summary(matrix_metadata_table_summaries)

    return {
        "covered_capabilities": list(COVERED_CAPABILITIES),
        "depends_on_capabilities": list(DEPENDS_ON_CAPABILITIES),
        "expected_result_file_count": len(expected_files),
        "provided_result_file_count": len(file_validations) - len(missing_files),
        "valid_result_file_count": len(valid_files),
        "missing_result_file_count": len(missing_files),
        "invalid_result_file_count": len(invalid_files),
        "missing_result_files": missing_files,
        "invalid_result_files": invalid_files,
        "validated_table_count": len([item for item in file_validations if item.get("is_valid") is True]),
        "required_table_count": len(file_validations),
        "request_id": expected_request_id or provided_request_id,
        "expected_request_id": expected_request_id,
        "provided_request_id": provided_request_id,
        "request_id_matches": bool(expected_request_id and provided_request_id and expected_request_id == provided_request_id),
        "symbol_count": _safe_int(handoff_summary.get("symbol_count")),
        "replay_candidate_count": _safe_int(handoff_summary.get("replay_candidate_count")),
        "replay_start": handoff_summary.get("replay_start"),
        "replay_end": handoff_summary.get("replay_end"),
        "table_row_counts": dict(sorted(table_row_counts.items())),
        "table_missing_field_counts": dict(sorted(table_missing_field_counts.items())),
        "matrix_metadata_import_summary": matrix_metadata_import_summary,
        "blocked_reason_counts": dict(sorted(Counter(blocked_reasons).items())),
    }


def _matrix_metadata_summary_for_rows(*, table_name: str, rows: Sequence[Any]) -> dict[str, Any]:
    if table_name not in MATRIX_METADATA_OBSERVED_TABLES:
        return {
            "table_name": table_name,
            "row_count": len(rows),
            "matrix_metadata_observed": False,
            "exact_matrix_cell_ready_record_count": 0,
            "needs_review_record_count": 0,
            "blocked_record_count": 0,
            "ready_to_build_exact_matrix_edge_summary": False,
            "mapped_required_field_counts": {},
            "missing_required_field_counts": {},
        }

    stamped_records: list[dict[str, Any]] = []
    blocked_record_count = 0
    matrix_cell_key_count = 0

    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            continue
        stamped = stamp_matrix_metadata(
            row,
            source_refs={
                "symbol": f"{table_name}[{index}]",
                "horizon_days": f"{table_name}[{index}]",
                "strategy_id": f"{table_name}[{index}]",
                "strategy_family": f"{table_name}[{index}]",
                "regime_state": f"{table_name}[{index}]",
                "asset_behavior_state": f"{table_name}[{index}]",
                "option_behavior_state": f"{table_name}[{index}]",
            },
        )
        validation = validate_matrix_metadata_record(stamped)
        if validation.get("matrix_metadata_state") == "blocked":
            blocked_record_count += 1
        if stamped.get("matrix_cell_key"):
            matrix_cell_key_count += 1
        stamped_records.append(stamped)

    coverage = matrix_metadata_coverage(stamped_records)
    ready_count = int(coverage.get("exact_matrix_cell_ready_record_count") or 0)
    needs_review_count = int(coverage.get("needs_review_record_count") or 0)
    row_count = len(stamped_records)

    return {
        "table_name": table_name,
        "row_count": row_count,
        "matrix_metadata_observed": True,
        "exact_matrix_cell_ready_record_count": ready_count,
        "needs_review_record_count": needs_review_count,
        "blocked_record_count": blocked_record_count,
        "matrix_cell_key_count": matrix_cell_key_count,
        "ready_to_build_exact_matrix_edge_summary": (
            table_name in MATRIX_METADATA_REQUIRED_TABLES and row_count > 0 and ready_count == row_count and blocked_record_count == 0
        ),
        "mapped_required_field_counts": dict(coverage.get("mapped_required_field_counts") or {}),
        "missing_required_field_counts": dict(coverage.get("missing_required_field_counts") or {}),
    }


def _matrix_metadata_import_summary(
    table_summaries: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    required_table_summaries = {
        name: summary
        for name, summary in table_summaries.items()
        if name in MATRIX_METADATA_REQUIRED_TABLES
    }

    required_record_count = sum(
        int(summary.get("row_count") or 0) for summary in required_table_summaries.values()
    )
    required_ready_count = sum(
        int(summary.get("exact_matrix_cell_ready_record_count") or 0)
        for summary in required_table_summaries.values()
    )
    required_needs_review_count = sum(
        int(summary.get("needs_review_record_count") or 0)
        for summary in required_table_summaries.values()
    )
    required_blocked_count = sum(
        int(summary.get("blocked_record_count") or 0)
        for summary in required_table_summaries.values()
    )

    aggregate_mapped = Counter()
    aggregate_missing = Counter()
    for summary in table_summaries.values():
        for field, count in (summary.get("mapped_required_field_counts") or {}).items():
            aggregate_mapped[str(field)] += int(count)
        for field, count in (summary.get("missing_required_field_counts") or {}).items():
            aggregate_missing[str(field)] += int(count)

    ready_to_build_exact = (
        bool(required_table_summaries)
        and required_record_count > 0
        and required_ready_count == required_record_count
        and required_needs_review_count == 0
        and required_blocked_count == 0
    )

    return {
        "matrix_metadata_envelope_key": MATRIX_METADATA_KEY,
        "matrix_cell_key_fields": list(REQUIRED_MATRIX_METADATA_FIELDS),
        "observed_table_count": len(table_summaries),
        "required_matrix_metadata_tables": sorted(MATRIX_METADATA_REQUIRED_TABLES),
        "required_outcome_record_count": required_record_count,
        "exact_matrix_cell_ready_record_count": required_ready_count,
        "needs_review_record_count": required_needs_review_count,
        "blocked_record_count": required_blocked_count,
        "mapped_required_field_counts": dict(sorted(aggregate_mapped.items())),
        "missing_required_field_counts": dict(sorted(aggregate_missing.items())),
        "table_summaries": dict(sorted((str(key), dict(value)) for key, value in table_summaries.items())),
        "ready_to_build_exact_matrix_edge_summary": ready_to_build_exact,
    }


def _expected_files(
    handoff_source: Mapping[str, Any] | None,
    result_file_names: Sequence[str] | None,
) -> list[str]:
    if result_file_names:
        return [str(name) for name in result_file_names if str(name).strip()]
    if isinstance(handoff_source, Mapping):
        contract = handoff_source.get("quantconnect_result_contract")
        if isinstance(contract, Mapping):
            expected = contract.get("expected_result_files")
            if isinstance(expected, Sequence) and not isinstance(expected, (str, bytes, bytearray)):
                values = [str(name) for name in expected if str(name).strip()]
                if values:
                    return values
    return list(DEFAULT_RESULT_FILES)


def _expected_request_id(handoff_source: Mapping[str, Any] | None) -> str:
    if not isinstance(handoff_source, Mapping):
        return ""
    manifest = handoff_source.get("quantconnect_replay_request_manifest")
    if isinstance(manifest, Mapping) and manifest.get("request_id"):
        return str(manifest.get("request_id"))
    if handoff_source.get("request_id"):
        return str(handoff_source.get("request_id"))
    return ""


def _payload_request_id(payload: Any) -> str:
    if isinstance(payload, Mapping) and payload.get("request_id"):
        return str(payload.get("request_id"))
    return ""


def _extract_rows(payload: Any, table_name: str) -> list[Any] | None:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, Mapping):
        return None
    for key in (table_name, "rows", "data", "items"):
        value = payload.get(key)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return list(value)
    return None


def _source_artifact_type(source: Any) -> str:
    if isinstance(source, Mapping):
        return str(source.get("artifact_type") or "provided_unknown_artifact")
    if source is None:
        return "missing"
    return type(source).__name__


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
