"""Options strategy setup matcher matrix metadata bridge.

This module stamps the strategy/setup-matcher layer with SignalForge's shared
historical replay ``matrix_metadata`` envelope. The setup matcher can legitimately
contribute exact strategy identifiers when they are explicit on the setup record.
It does not infer regime, asset behavior, option behavior, symbol, or horizon.

No broker calls, order routing, order submission, fills, live execution, or
slippage modeling are performed here.
"""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Mapping, Sequence

from src.signalforge.engines.strategy_selection.historical_replay_matrix_metadata_stamp import (
    MATRIX_CELL_KEY_KEY,
    MATRIX_METADATA_KEY,
    MATRIX_METADATA_MISSING_FIELDS_KEY,
    MATRIX_METADATA_SOURCE_REFS_KEY,
    MATRIX_METADATA_STATE_KEY,
    build_matrix_cell_key,
    matrix_metadata_coverage,
    merge_matrix_metadata,
    normalize_horizon_days,
    normalize_matrix_metadata,
    normalize_symbol,
    stamp_matrix_metadata,
)

SCHEMA_VERSION = "signalforge_options_strategy_setup_matcher_matrix_metadata.v1"
SUMMARY_SCHEMA_VERSION = "signalforge_options_strategy_setup_matcher_matrix_metadata_summary.v1"
ARTIFACT_TYPE = "signalforge_options_strategy_setup_matcher_matrix_metadata"

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

SETUP_MATCH_COLLECTION_KEYS = [
    "setup_matches",
    "matched_setups",
    "strategy_setups",
    "strategy_matches",
    "available_strategies",
    "eligible_strategies",
    "candidate_setups",
    "strategy_candidates",
    "candidates",
    "items",
    "records",
]

STRATEGY_ID_KEYS = [
    "strategy_id",
    "option_strategy_id",
    "setup_id",
    "setup_name",
    "strategy",
    "strategy_name",
    "catalog_strategy_id",
    "strategy_template_id",
    "id",
]

STRATEGY_FAMILY_KEYS = [
    "strategy_family",
    "option_strategy_family",
    "family",
    "strategy_type",
    "setup_family",
    "catalog_strategy_family",
]

OPTIONAL_EXPLICIT_KEYS = {
    "regime_state": ["regime_state", "regime", "market_regime"],
    "asset_behavior_state": ["asset_behavior_state", "asset_behavior", "behavior_state"],
    "option_behavior_state": ["option_behavior_state", "option_behavior", "options_behavior_state"],
    "symbol": ["symbol", "ticker", "underlying_symbol", "underlying"],
    "horizon_days": ["horizon_days", "horizon", "target_horizon_days", "window_days"],
    "asset_class": ["asset_class", "instrument_type", "security_type"],
    "strategy_direction": ["strategy_direction", "direction", "bias"],
    "risk_structure": ["risk_structure", "risk_profile", "defined_risk_state"],
    "replay_window_id": ["replay_window_id", "window_id", "window"],
    "edge_score": ["edge_score", "historical_edge_score", "score"],
    "outcome_state": ["outcome_state", "outcome", "result_state"],
}


def stamp_options_strategy_setup_match(
    setup_match: Mapping[str, Any],
    *,
    source_ref: str | None = None,
    preserve_existing: bool = True,
) -> dict[str, Any]:
    """Stamp one setup matcher record with matrix metadata.

    Only explicit fields are copied. In particular, a bullish/bearish setup name
    is not converted into a strategy family unless the record has an explicit
    strategy identifier/family field.
    """

    metadata = extract_options_strategy_setup_match_matrix_metadata(setup_match)
    source_refs = _source_refs(metadata, source_ref=source_ref or "options_strategy_setup_matcher")
    return stamp_matrix_metadata(
        setup_match,
        metadata=metadata,
        source_refs=source_refs,
        preserve_existing=preserve_existing,
    )


def stamp_options_strategy_setup_matches(
    setup_matches: Sequence[Mapping[str, Any]],
    *,
    source_ref: str | None = None,
    preserve_existing: bool = True,
) -> list[dict[str, Any]]:
    """Stamp a sequence of setup matcher records."""

    stamped: list[dict[str, Any]] = []
    for index, setup_match in enumerate(setup_matches):
        stamped.append(
            stamp_options_strategy_setup_match(
                setup_match,
                source_ref=f"{source_ref or 'options_strategy_setup_matcher'}[{index}]",
                preserve_existing=preserve_existing,
            )
        )
    return stamped


def patch_options_strategy_setup_matcher_result(
    result: Mapping[str, Any],
    *,
    preserve_existing: bool = True,
) -> dict[str, Any]:
    """Return a copy of a setup matcher result with stamped setup records.

    The function searches common collection keys and patches every list of
    mapping-shaped setup/candidate records it finds. It leaves unrelated fields
    unchanged.
    """

    patched = dict(result)
    patched_collections: list[str] = []
    stamped_records: list[dict[str, Any]] = []

    for key in SETUP_MATCH_COLLECTION_KEYS:
        value = patched.get(key)
        if not _is_mapping_sequence(value):
            continue
        stamped = stamp_options_strategy_setup_matches(
            value,  # type: ignore[arg-type]
            source_ref=f"options_strategy_setup_matcher.{key}",
            preserve_existing=preserve_existing,
        )
        patched[key] = stamped
        patched_collections.append(key)
        stamped_records.extend(stamped)

    # Some matcher implementations return a single selected setup at top-level.
    selected_setup = patched.get("selected_setup") or patched.get("primary_setup")
    if isinstance(selected_setup, Mapping):
        stamped_selected = stamp_options_strategy_setup_match(
            selected_setup,
            source_ref="options_strategy_setup_matcher.selected_setup",
            preserve_existing=preserve_existing,
        )
        if "selected_setup" in patched:
            patched["selected_setup"] = stamped_selected
        else:
            patched["primary_setup"] = stamped_selected
        stamped_records.append(stamped_selected)
        patched_collections.append("selected_setup")

    summary = build_options_strategy_setup_matcher_matrix_metadata_summary(stamped_records)
    patched["matrix_metadata_setup_matcher_summary"] = summary
    patched["matrix_metadata_envelope_key"] = MATRIX_METADATA_KEY
    patched["matrix_cell_key_fields"] = list(summary["matrix_cell_key_fields"])
    patched["exact_matrix_cell_ready_record_count"] = summary["exact_matrix_cell_ready_record_count"]
    patched["matrix_metadata_needs_review_record_count"] = summary["needs_review_record_count"]
    patched["ready_to_build_exact_matrix_edge_summary"] = summary[
        "ready_to_build_exact_matrix_edge_summary"
    ]
    patched["options_strategy_setup_matcher_matrix_metadata_collections"] = patched_collections
    patched["recommended_next_step"] = (
        "patch_quantconnect_replay_scaleout_plan_matrix_metadata"
        if summary["exact_matrix_cell_ready_record_count"] > 0
        else "ensure_setup_matcher_receives_regime_asset_option_symbol_horizon_metadata"
    )
    patched.setdefault("explicit_exclusions", list(EXPLICIT_EXCLUSIONS))
    patched.setdefault("automatic_action", None)
    patched.setdefault("automatic_strategy_change", None)
    patched.setdefault("order_intent", None)
    patched.setdefault("requires_manual_approval", True)
    return patched


def build_signalforge_options_strategy_setup_matcher_matrix_metadata(
    *,
    setup_matcher_result_source: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a standalone audit/bridge artifact for setup matcher metadata."""

    patched_result = patch_options_strategy_setup_matcher_result(setup_matcher_result_source)
    stamped_records = _collect_stamped_records(patched_result)
    summary = build_options_strategy_setup_matcher_matrix_metadata_summary(stamped_records)
    status = "ready" if stamped_records else "needs_review"
    warnings = [] if stamped_records else ["no_setup_match_records_found_to_stamp"]
    if summary["needs_review_record_count"]:
        warnings.append("setup_match_records_missing_required_matrix_metadata")

    return {
        "artifact_type": ARTIFACT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "operation_type": "signalforge_options_strategy_setup_matcher_matrix_metadata_builder",
        "metadata_bridge_id": f"options_strategy_setup_matcher_matrix_metadata_{_stable_id(summary)}",
        "created_at_utc": _utc_now_iso(),
        "status": status,
        "bridge_state": status,
        "is_ready": status == "ready",
        "matrix_metadata_envelope_key": MATRIX_METADATA_KEY,
        "matrix_cell_key_fields": list(summary["matrix_cell_key_fields"]),
        "setup_match_record_count": summary["total_record_count"],
        "exact_matrix_cell_ready_record_count": summary["exact_matrix_cell_ready_record_count"],
        "matrix_metadata_needs_review_record_count": summary["needs_review_record_count"],
        "mapped_required_field_counts": summary["mapped_required_field_counts"],
        "missing_required_field_counts": summary["missing_required_field_counts"],
        "ready_to_build_exact_matrix_edge_summary": summary[
            "ready_to_build_exact_matrix_edge_summary"
        ],
        "ready_to_patch_historical_replay_exports": True,
        "recommended_next_step": (
            "patch_quantconnect_replay_scaleout_plan_matrix_metadata"
            if summary["total_record_count"]
            else "wire_setup_matcher_matrix_metadata_bridge_into_setup_matcher_output"
        ),
        "patched_setup_matcher_result": patched_result,
        "matrix_metadata_setup_matcher_summary": summary,
        "blocked_reasons": [],
        "warnings": _ordered_unique(warnings),
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
        "automatic_action": None,
        "automatic_strategy_change": None,
        "order_intent": None,
        "requires_manual_approval": True,
    }


def extract_options_strategy_setup_match_matrix_metadata(record: Mapping[str, Any]) -> dict[str, Any]:
    """Extract explicit matrix metadata from one setup matcher record."""

    explicit: dict[str, Any] = {}
    existing = _as_mapping(record.get(MATRIX_METADATA_KEY))
    if existing:
        explicit.update(existing)

    strategy_id = _first_present(record, STRATEGY_ID_KEYS)
    if _has_value(strategy_id):
        explicit["strategy_id"] = strategy_id

    strategy_family = _first_present(record, STRATEGY_FAMILY_KEYS)
    if _has_value(strategy_family):
        explicit["strategy_family"] = strategy_family

    for field, aliases in OPTIONAL_EXPLICIT_KEYS.items():
        if _has_value(explicit.get(field)):
            continue
        value = _first_present(record, aliases)
        if not _has_value(value):
            continue
        if field == "symbol":
            value = normalize_symbol(value)
        elif field == "horizon_days":
            value = normalize_horizon_days(value)
        explicit[field] = value

    normalized = normalize_matrix_metadata(explicit)
    # Preserve an explicitly provided matrix cell key only if it matches the
    # normalized metadata. The shared stamper will rebuild the key when ready.
    explicit_key = record.get(MATRIX_CELL_KEY_KEY)
    if _has_value(explicit_key):
        expected_key = build_matrix_cell_key(normalized)
        if expected_key and str(explicit_key) == expected_key:
            normalized[MATRIX_CELL_KEY_KEY] = expected_key
    return normalized


def build_options_strategy_setup_matcher_matrix_metadata_summary(
    stamped_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Summarize setup matcher matrix metadata coverage."""

    coverage = matrix_metadata_coverage(stamped_records)
    return {
        "artifact_type": "signalforge_options_strategy_setup_matcher_matrix_metadata_summary",
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "matrix_metadata_envelope_key": MATRIX_METADATA_KEY,
        "matrix_cell_key_fields": [
            "regime_state",
            "asset_behavior_state",
            "option_behavior_state",
            "strategy_id",
            "strategy_family",
            "symbol",
            "horizon_days",
        ],
        "total_record_count": int(coverage.get("total_record_count") or 0),
        "exact_matrix_cell_ready_record_count": int(
            coverage.get("exact_matrix_cell_ready_record_count") or 0
        ),
        "needs_review_record_count": int(coverage.get("needs_review_record_count") or 0),
        "mapped_required_field_counts": dict(coverage.get("mapped_required_field_counts") or {}),
        "missing_required_field_counts": dict(coverage.get("missing_required_field_counts") or {}),
        "ready_to_build_exact_matrix_edge_summary": bool(
            coverage.get("ready_to_build_exact_matrix_edge_summary")
        ),
    }


def _collect_stamped_records(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for key in SETUP_MATCH_COLLECTION_KEYS:
        value = result.get(key)
        if not _is_mapping_sequence(value):
            continue
        records.extend(dict(item) for item in value if isinstance(item, Mapping))
    for key in ["selected_setup", "primary_setup"]:
        value = result.get(key)
        if isinstance(value, Mapping):
            records.append(dict(value))
    return records


def _source_refs(metadata: Mapping[str, Any], *, source_ref: str) -> dict[str, Any]:
    refs: dict[str, Any] = {}
    for field, value in metadata.items():
        if _has_value(value):
            refs[field] = source_ref
    return refs


def _first_present(record: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        value = _deep_get(record, key)
        if _has_value(value):
            return value
    return None


def _deep_get(record: Mapping[str, Any], key: str) -> Any:
    if key in record:
        return record.get(key)
    if "." not in key:
        return None
    current: Any = record
    for part in key.split("."):
        if not isinstance(current, Mapping):
            return None
        current = current.get(part)
    return current


def _is_mapping_sequence(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, Mapping) for item in value)


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    return True


def _ordered_unique(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value)
        if text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _stable_id(value: Any) -> str:
    import json

    return sha256(json.dumps(value, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
