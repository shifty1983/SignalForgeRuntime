from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


ADAPTER_TYPE = "primary_strategy_candidate_profile_export"
ARTIFACT_TYPE = "signalforge_primary_strategy_candidate_profile_export"
SUMMARY_ARTIFACT_TYPE = "signalforge_primary_strategy_candidate_profile_export_summary"

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

WINDOW_KEYS = [
    "selected_window_days",
    "window_days",
    "profile_window_days",
    "holding_period_days",
    "horizon_days",
    "horizon",
    "lookback_days",
    "candidate_window_days",
    "strategy_window_days",
    "days",
    "scenario_id",
    "profile_name",
    "portfolio_name",
    "reconstruction_name",
    "scenario_name",
    "run_name",
    "artifact_name",
    "artifact_path",
    "source_path",
    "output_dir",
    "file",
    "filename",
    "name",
    "label",
]

IDENTITY_KEYS = [
    "candidate_id",
    "profile_id",
    "strategy_candidate_id",
    "strategy_id",
    "id",
    "scenario_id",
    "run_id",
    "portfolio_id",
    "reconstruction_id",
    "profile_name",
    "portfolio_name",
    "reconstruction_name",
    "scenario_name",
    "run_name",
    "name",
]

SYMBOL_KEYS = [
    "symbol",
    "ticker",
    "underlying",
    "asset",
]

STRATEGY_FAMILY_KEYS = [
    "strategy_family",
    "strategy_type",
    "strategy_name",
    "strategy",
    "model_family",
    "portfolio_strategy",
    "risk_model",
    "risk_profile",
    "variant_id",
]

RANK_KEYS = [
    "selection_rank",
    "rank",
    "candidate_rank",
    "portfolio_rank",
]

SCORE_KEYS = [
    "risk_adjusted_edge_score",
    "historical_edge_score",
    "edge_score",
    "candidate_score",
    "selection_score",
    "primary_score",
    "conservative_score",
    "aggressive_score",
    "expected_value",
    "expected_value_score",
    "return_score",
    "quality_score",
]

SELECTED_KEYS = [
    "is_primary",
    "primary",
    "is_selected",
    "selected",
    "is_winner",
    "winner",
    "chosen",
]

CANDIDATE_MARKER_KEYS = set(
    IDENTITY_KEYS
    + SYMBOL_KEYS
    + STRATEGY_FAMILY_KEYS
    + RANK_KEYS
    + SCORE_KEYS
    + SELECTED_KEYS
    + WINDOW_KEYS
)

PROFILE_SECTION_KEYS = [
    "profile",
    "candidate_profile",
    "strategy_profile",
    "selected_profile",
    "primary_profile",
    "edge_profile",
    "return_profile",
    "risk_profile",
]

BLOCKED_REASON_KEYS = [
    "blocked_reasons",
    "blockers",
    "blocking_reasons",
    "reasons_blocked",
]

WARNING_KEYS = [
    "warnings",
    "review_warnings",
    "needs_review_reasons",
]


def load_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, sort_keys=True)
        file.write("\n")


def build_primary_strategy_candidate_profile_export(
    source_payload: Any,
    *,
    selected_window_days: int = 21,
    source_path: Optional[str] = None,
) -> Dict[str, Any]:
    warnings: List[str] = []
    blocked_reasons: List[str] = []

    if not isinstance(source_payload, Mapping):
        return _blocked_export(
            selected_window_days=selected_window_days,
            source_path=source_path,
            blocked_reasons=[
                "source_payload_invalid_shape",
                "source_payload_must_be_json_object",
            ],
        )

    candidates = _find_candidate_dicts(source_payload)
    window_candidates = [
        candidate
        for candidate in candidates
        if _extract_window_days(candidate) == selected_window_days
    ]

    if not candidates:
        blocked_reasons.append("no_candidate_profiles_found")

    if candidates and not window_candidates:
        blocked_reasons.append(f"no_{selected_window_days}_day_candidate_profile_found")

    if len(window_candidates) > 1:
        warnings.append(
            f"multiple_{selected_window_days}_day_candidate_profiles_found_primary_selected_by_rank_and_score"
        )

    sorted_candidates = sorted(
        window_candidates,
        key=lambda candidate: _candidate_sort_key(candidate),
        reverse=True,
    )

    primary_candidate = sorted_candidates[0] if sorted_candidates else None
    candidate_profiles = [
        _normalize_candidate_profile(
            candidate,
            selected_window_days=selected_window_days,
            source_index=index,
        )
        for index, candidate in enumerate(sorted_candidates)
    ]

    primary_profile = (
        _normalize_candidate_profile(
            primary_candidate,
            selected_window_days=selected_window_days,
            source_index=0,
        )
        if primary_candidate is not None
        else None
    )

    candidate_warnings = _collect_list_values(primary_candidate or {}, WARNING_KEYS)
    candidate_blocked_reasons = _collect_list_values(
        primary_candidate or {}, BLOCKED_REASON_KEYS
    )

    warnings.extend(candidate_warnings)
    blocked_reasons.extend(candidate_blocked_reasons)

    profile_export_state = _classify_state(
        blocked_reasons=blocked_reasons,
        warnings=warnings,
        primary_profile=primary_profile,
    )

    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": ARTIFACT_TYPE,
        "profile_export_state": profile_export_state,
        "selected_window_days": selected_window_days,
        "source_path": source_path,
        "candidate_profile_count": len(candidate_profiles),
        "primary_candidate_id": (
            primary_profile.get("candidate_id") if primary_profile else None
        ),
        "primary_symbol": primary_profile.get("symbol") if primary_profile else None,
        "primary_strategy_family": (
            primary_profile.get("strategy_family") if primary_profile else None
        ),
        "primary_profile": primary_profile,
        "candidate_profiles": candidate_profiles,
        "warnings": _dedupe_strings(warnings),
        "blocked_reasons": _dedupe_strings(blocked_reasons),
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def export_primary_strategy_candidate_profile(
    *,
    source_path: str | Path,
    output_dir: str | Path,
    selected_window_days: int = 21,
) -> Dict[str, Any]:
    source_path_obj = Path(source_path)
    output_dir_obj = Path(output_dir)

    source_payload = load_json(source_path_obj)

    export_payload = build_primary_strategy_candidate_profile_export(
        source_payload,
        selected_window_days=selected_window_days,
        source_path=str(source_path_obj),
    )

    export_path = output_dir_obj / "signalforge_primary_strategy_candidate_profile_export.json"
    summary_path = (
        output_dir_obj / "signalforge_primary_strategy_candidate_profile_export_summary.json"
    )

    summary_payload = build_primary_strategy_candidate_profile_export_summary(
        export_payload,
        export_path=export_path,
        summary_path=summary_path,
    )

    write_json(export_path, export_payload)
    write_json(summary_path, summary_payload)

    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": "primary_strategy_candidate_profile_export_write_result",
        "profile_export_state": export_payload["profile_export_state"],
        "selected_window_days": selected_window_days,
        "source_path": str(source_path_obj),
        "output_dir": str(output_dir_obj),
        "export_path": str(export_path),
        "summary_path": str(summary_path),
        "primary_candidate_id": export_payload.get("primary_candidate_id"),
        "primary_symbol": export_payload.get("primary_symbol"),
        "primary_strategy_family": export_payload.get("primary_strategy_family"),
        "candidate_profile_count": export_payload.get("candidate_profile_count", 0),
        "blocked_reasons": export_payload.get("blocked_reasons", []),
        "warnings": export_payload.get("warnings", []),
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def build_primary_strategy_candidate_profile_export_summary(
    export_payload: Mapping[str, Any],
    *,
    export_path: str | Path | None = None,
    summary_path: str | Path | None = None,
) -> Dict[str, Any]:
    primary_profile = export_payload.get("primary_profile") or {}

    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": SUMMARY_ARTIFACT_TYPE,
        "profile_export_state": export_payload.get("profile_export_state"),
        "selected_window_days": export_payload.get("selected_window_days"),
        "candidate_profile_count": export_payload.get("candidate_profile_count", 0),
        "primary_candidate_id": export_payload.get("primary_candidate_id"),
        "primary_symbol": export_payload.get("primary_symbol"),
        "primary_strategy_family": export_payload.get("primary_strategy_family"),
        "risk_adjusted_edge_score": primary_profile.get("risk_adjusted_edge_score"),
        "historical_edge_score": primary_profile.get("historical_edge_score"),
        "selection_rank": primary_profile.get("selection_rank"),
        "blocked_reason_count": len(export_payload.get("blocked_reasons", [])),
        "warning_count": len(export_payload.get("warnings", [])),
        "blocked_reasons": export_payload.get("blocked_reasons", []),
        "warnings": export_payload.get("warnings", []),
        "output_files": {
            "export": str(export_path) if export_path is not None else None,
            "summary": str(summary_path) if summary_path is not None else None,
        },
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def _blocked_export(
    *,
    selected_window_days: int,
    source_path: Optional[str],
    blocked_reasons: Sequence[str],
) -> Dict[str, Any]:
    return {
        "adapter_type": ADAPTER_TYPE,
        "artifact_type": ARTIFACT_TYPE,
        "profile_export_state": "blocked",
        "selected_window_days": selected_window_days,
        "source_path": source_path,
        "candidate_profile_count": 0,
        "primary_candidate_id": None,
        "primary_symbol": None,
        "primary_strategy_family": None,
        "primary_profile": None,
        "candidate_profiles": [],
        "warnings": [],
        "blocked_reasons": _dedupe_strings(blocked_reasons),
        "explicit_exclusions": EXPLICIT_EXCLUSIONS,
    }


def _find_candidate_dicts(payload: Mapping[str, Any]) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for candidate in _walk_candidate_like_dicts(payload):
        canonical = json.dumps(candidate, sort_keys=True, default=str)
        if canonical not in seen:
            seen.add(canonical)
            candidates.append(deepcopy(candidate))

    return candidates


def _walk_candidate_like_dicts(value: Any, *, depth: int = 0) -> Iterable[Dict[str, Any]]:
    if depth > 7:
        return

    if isinstance(value, Mapping):
        if _is_candidate_like(value):
            yield dict(value)

        for nested_value in value.values():
            yield from _walk_candidate_like_dicts(nested_value, depth=depth + 1)

    elif isinstance(value, list):
        for item in value:
            yield from _walk_candidate_like_dicts(item, depth=depth + 1)


def _is_candidate_like(value: Mapping[str, Any]) -> bool:
    keys = set(value.keys())

    has_candidate_marker = bool(keys & CANDIDATE_MARKER_KEYS)
    has_score = bool(keys & set(SCORE_KEYS))
    has_window = _extract_window_days(value) is not None
    has_identity = bool(keys & set(IDENTITY_KEYS + SYMBOL_KEYS + STRATEGY_FAMILY_KEYS))
    has_selected_flag = any(_is_truthy(value.get(key)) for key in SELECTED_KEYS)

    return has_candidate_marker and (
        has_window
        or has_score
        or has_identity
        or has_selected_flag
    )


def _extract_window_days(candidate: Mapping[str, Any]) -> Optional[int]:
    for key in WINDOW_KEYS:
        parsed = _parse_days(candidate.get(key))
        if parsed is not None:
            return parsed

    for key in PROFILE_SECTION_KEYS:
        section = candidate.get(key)
        if isinstance(section, Mapping):
            parsed = _extract_window_days(section)
            if parsed is not None:
                return parsed

    return None


def _parse_days(value: Any) -> Optional[int]:
    if value is None:
        return None

    if isinstance(value, bool):
        return None

    if isinstance(value, int):
        return value

    if isinstance(value, float) and value.is_integer():
        return int(value)

    if isinstance(value, str):
        stripped = value.strip().lower()

        if stripped.isdigit():
            return int(stripped)

        patterns = [
            r"(\d+)\s*[-_ ]?\s*d(?:ay|ays)?\b",
            r"(?:fixed[_-]?horizon|horizon|window|profile|holding[_-]?period)[_-]?(\d+)\b",
            r"\b(\d+)[_-]?(?:defined[_-]?risk|uncapped|capped|cap)\b",
        ]

        for pattern in patterns:
            match = re.search(pattern, stripped)
            if match:
                return int(match.group(1))

    return None


def _normalize_candidate_profile(
    candidate: Mapping[str, Any],
    *,
    selected_window_days: int,
    source_index: int,
) -> Dict[str, Any]:
    candidate_id = _first_present(candidate, IDENTITY_KEYS)
    symbol = _first_present(candidate, SYMBOL_KEYS)
    strategy_family = _first_present(candidate, STRATEGY_FAMILY_KEYS)

    risk_adjusted_edge_score = _first_numeric(
        candidate,
        [
            "risk_adjusted_edge_score",
            "primary_score",
            "edge_score",
            "candidate_score",
            "selection_score",
        ],
    )
    historical_edge_score = _first_numeric(
        candidate,
        [
            "historical_edge_score",
            "edge_score",
        ],
    )
    selection_rank = _first_numeric(candidate, RANK_KEYS)

    return {
        "candidate_id": candidate_id,
        "symbol": symbol,
        "strategy_family": strategy_family,
        "selected_window_days": selected_window_days,
        "source_index": source_index,
        "selection_rank": selection_rank,
        "risk_adjusted_edge_score": risk_adjusted_edge_score,
        "historical_edge_score": historical_edge_score,
        "edge_validation_summary": _first_mapping(
            candidate,
            [
                "edge_validation_summary",
                "historical_edge_validation",
                "historical_edge_summary",
                "validation_summary",
            ],
        ),
        "return_profile": _first_mapping(
            candidate,
            [
                "return_profile",
                "return_summary",
                "performance_profile",
                "performance_summary",
            ],
        ),
        "drawdown_profile": _first_mapping(
            candidate,
            [
                "drawdown_profile",
                "drawdown_summary",
                "risk_profile",
                "risk_summary",
            ],
        ),
        "adverse_excursion_profile": _first_mapping(
            candidate,
            [
                "adverse_excursion_profile",
                "mae_profile",
                "mae_summary",
                "max_adverse_excursion_profile",
            ],
        ),
        "tail_risk_notes": _first_present(
            candidate,
            [
                "tail_risk_notes",
                "tail_risk_summary",
                "tail_check",
                "tail_risk",
            ],
        ),
        "entry_exit_evidence": _first_mapping_or_list(
            candidate,
            [
                "entry_exit_evidence",
                "entry_exit_summary",
                "entry_logic_evidence",
                "exit_logic_evidence",
                "signal_evidence",
            ],
        ),
        "warnings": _dedupe_strings(_collect_list_values(candidate, WARNING_KEYS)),
        "blocked_reasons": _dedupe_strings(
            _collect_list_values(candidate, BLOCKED_REASON_KEYS)
        ),
        "source_candidate_snapshot": _json_safe(candidate),
    }


def _candidate_sort_key(candidate: Mapping[str, Any]) -> Tuple[float, float, float, str]:
    selected_score = 1.0 if any(_is_truthy(candidate.get(key)) for key in SELECTED_KEYS) else 0.0

    rank = _first_numeric(candidate, RANK_KEYS)
    rank_score = 0.0 if rank is None else -float(rank)

    score = _first_numeric(candidate, SCORE_KEYS)
    score_value = float(score) if score is not None else 0.0

    canonical = json.dumps(candidate, sort_keys=True, default=str)

    return selected_score, rank_score, score_value, canonical


def _classify_state(
    *,
    blocked_reasons: Sequence[str],
    warnings: Sequence[str],
    primary_profile: Optional[Mapping[str, Any]],
) -> str:
    if blocked_reasons:
        return "blocked"

    if primary_profile is None:
        return "blocked"

    if warnings:
        return "needs_review"

    return "ready"


def _first_present(candidate: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        value = candidate.get(key)
        if value not in (None, ""):
            return value

    for section_key in PROFILE_SECTION_KEYS:
        section = candidate.get(section_key)
        if isinstance(section, Mapping):
            value = _first_present(section, keys)
            if value not in (None, ""):
                return value

    return None


def _first_numeric(candidate: Mapping[str, Any], keys: Sequence[str]) -> Optional[float]:
    value = _first_present(candidate, keys)

    if value is None or isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None

    return None


def _first_mapping(candidate: Mapping[str, Any], keys: Sequence[str]) -> Optional[Dict[str, Any]]:
    for key in keys:
        value = candidate.get(key)
        if isinstance(value, Mapping):
            return _json_safe(value)

    return None


def _first_mapping_or_list(candidate: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        value = candidate.get(key)
        if isinstance(value, (Mapping, list)):
            return _json_safe(value)

    return None


def _collect_list_values(candidate: Mapping[str, Any], keys: Sequence[str]) -> List[str]:
    values: List[str] = []

    for key in keys:
        value = candidate.get(key)
        if isinstance(value, list):
            values.extend(str(item) for item in value if item not in (None, ""))
        elif isinstance(value, str) and value:
            values.append(value)

    return values


def _is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "y", "1", "selected", "primary"}

    if isinstance(value, (int, float)):
        return value == 1

    return False


def _dedupe_strings(values: Sequence[str]) -> List[str]:
    deduped: List[str] = []
    seen: set[str] = set()

    for value in values:
        clean_value = str(value).strip()
        if clean_value and clean_value not in seen:
            seen.add(clean_value)
            deduped.append(clean_value)

    return deduped


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))