from __future__ import annotations

from collections.abc import Mapping, Sequence
from os import PathLike
from pathlib import Path
from typing import Any

from src.options_portfolio.control_report import SECTION_DEFINITIONS


EXPLICIT_EXCLUSIONS = (
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
)

EXPECTED_FILENAMES = {
    "weekly_trade_plan": ("weekly_option_trade_plan.json",),
    "position_risk_monitor": ("options_position_risk_monitor.json",),
    "manual_action_queue": ("options_manual_action_queue.json",),
    "manual_action_review": ("options_manual_action_review.json",),
    "manual_execution_record": ("options_manual_execution_record.json",),
    "manual_action_outcome_record": ("options_manual_action_outcome_record.json",),
    "edge_validation_summary": ("options_edge_validation_summary.json",),
    "edge_validation_review": ("options_edge_validation_review.json",),
    "strategy_improvement_queue": ("options_strategy_improvement_queue.json",),
    "strategy_improvement_review": ("options_strategy_improvement_review.json",),
    "strategy_decision_log": ("options_strategy_decision_log.json",),
}


def build_options_portfolio_control_report_artifact_manifest(
    source: Mapping[str, Any],
    *,
    base_dir: str | PathLike[str] | None = None,
) -> dict[str, Any]:
    """Build an artifact-path manifest for the control report source assembler.

    This builder only scans local files and emits a manifest. It does not call
    brokers, route orders, submit orders, model fills, perform live execution,
    model slippage, create automatic close/roll/defense orders, change strategy
    logic automatically, update parameters automatically, or pause strategies
    automatically.
    """

    if not isinstance(source, Mapping):
        return _blocked_result("source must be a mapping")

    root = Path(base_dir) if base_dir is not None else Path.cwd()
    report_date = _string_or_none(
        source.get("report_date")
        or source.get("control_date")
        or source.get("as_of_date")
        or source.get("run_date")
    )

    preferred_paths = _as_mapping(source.get("preferred_paths"))
    search_dirs, search_dir_blocks = _search_dirs(source, root)

    if search_dir_blocks:
        manifest_summary = _manifest_summary(
            found_artifacts=[],
            missing_artifacts=[],
            ambiguous_artifacts=[],
            blocked_items=search_dir_blocks,
        )
        return {
            "artifact_type": "options_portfolio_control_report_artifact_manifest",
            "schema_version": "1.0",
            "status": "blocked",
            "is_ready": False,
            "requires_manual_approval": True,
            "order_intent": None,
            "broker_order_id": None,
            "automatic_action": None,
            "automatic_strategy_change": None,
            "automatic_parameter_change": None,
            "automatic_pause_action": None,
            "report_date": report_date,
            "manifest": {"report_date": report_date, "artifact_paths": {}}
            if report_date is not None
            else {"artifact_paths": {}},
            "manifest_summary": manifest_summary,
            "found_artifacts": [],
            "missing_artifacts": [],
            "ambiguous_artifacts": [],
            "blocked_items": _sorted_by_section(search_dir_blocks),
            "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
        }

    if not preferred_paths and not search_dirs:
        return _blocked_result("missing_manifest_search_inputs", report_date=report_date)

    artifact_paths: dict[str, str] = {}
    found_artifacts: list[dict[str, Any]] = []
    missing_artifacts: list[dict[str, Any]] = []
    ambiguous_artifacts: list[dict[str, Any]] = []
    blocked_items: list[dict[str, Any]] = list(search_dir_blocks)

    for definition in SECTION_DEFINITIONS:
        section = str(definition["section"])
        canonical_key = str(definition["keys"][0])
        preferred_path = _find_preferred_path(
            preferred_paths,
            section=section,
            keys=definition["keys"],
        )

        if preferred_path is not None:
            resolved = _resolve_path(preferred_path, root)
            if not resolved.exists():
                blocked_items.append(
                    {
                        "section": section,
                        "reason": "preferred_artifact_file_not_found",
                        "path": _display_path(resolved, root),
                    }
                )
                continue

            artifact_paths[section] = _display_path(resolved, root)
            found_artifacts.append(
                {
                    "section": section,
                    "canonical_key": canonical_key,
                    "source_type": "preferred_path",
                    "path": _display_path(resolved, root),
                }
            )
            continue

        candidates = _candidate_files(
            search_dirs,
            expected_filenames=EXPECTED_FILENAMES.get(section, (f"{canonical_key}.json",)),
        )

        if len(candidates) == 1:
            selected = candidates[0]
            artifact_paths[section] = _display_path(selected, root)
            found_artifacts.append(
                {
                    "section": section,
                    "canonical_key": canonical_key,
                    "source_type": "discovered_path",
                    "path": _display_path(selected, root),
                }
            )
            continue

        if len(candidates) > 1:
            ambiguous_artifacts.append(
                {
                    "section": section,
                    "reason": "multiple_candidate_artifacts_found",
                    "candidate_paths": [_display_path(candidate, root) for candidate in candidates],
                }
            )
            continue

        missing_artifacts.append(
            {
                "section": section,
                "reason": "expected_artifact_file_not_found",
                "expected_filenames": list(EXPECTED_FILENAMES.get(section, (f"{canonical_key}.json",))),
            }
        )

    manifest = {
        "report_date": report_date,
        "artifact_paths": artifact_paths,
    }
    if report_date is None:
        manifest.pop("report_date")

    manifest_summary = _manifest_summary(
        found_artifacts=found_artifacts,
        missing_artifacts=missing_artifacts,
        ambiguous_artifacts=ambiguous_artifacts,
        blocked_items=blocked_items,
    )
    status = _status(manifest_summary)

    return {
        "artifact_type": "options_portfolio_control_report_artifact_manifest",
        "schema_version": "1.0",
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "report_date": report_date,
        "manifest": manifest,
        "manifest_summary": manifest_summary,
        "found_artifacts": _sorted_by_section(found_artifacts),
        "missing_artifacts": _sorted_by_section(missing_artifacts),
        "ambiguous_artifacts": _sorted_by_section(ambiguous_artifacts),
        "blocked_items": _sorted_by_section(blocked_items),
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _search_dirs(source: Mapping[str, Any], root: Path) -> tuple[list[Path], list[dict[str, Any]]]:
    search_dirs: list[Path] = []
    blocked_items: list[dict[str, Any]] = []

    artifact_root = _string_or_none(source.get("artifact_root"))
    if artifact_root:
        search_dirs.append(_resolve_path(artifact_root, root))

    raw_search_dirs = source.get("search_dirs")
    if isinstance(raw_search_dirs, Sequence) and not isinstance(raw_search_dirs, (str, bytes, bytearray)):
        for item in raw_search_dirs:
            text = _string_or_none(item)
            if text:
                search_dirs.append(_resolve_path(text, root))

    unique_dirs = []
    seen = set()
    for path in search_dirs:
        key = str(path.resolve()) if path.exists() else str(path)
        if key not in seen:
            seen.add(key)
            unique_dirs.append(path)

    existing_dirs = []
    for path in unique_dirs:
        if path.exists() and path.is_dir():
            existing_dirs.append(path)
        else:
            blocked_items.append(
                {
                    "reason": "search_dir_not_found",
                    "path": _display_path(path, root),
                }
            )

    return existing_dirs, blocked_items


def _find_preferred_path(
    preferred_paths: Mapping[str, Any],
    *,
    section: str,
    keys: Sequence[str],
) -> str | None:
    for key in (section, *keys):
        value = _string_or_none(preferred_paths.get(key))
        if value:
            return value
    return None


def _candidate_files(
    search_dirs: Sequence[Path],
    *,
    expected_filenames: Sequence[str],
) -> list[Path]:
    candidates: list[Path] = []
    for search_dir in search_dirs:
        for filename in expected_filenames:
            candidates.extend(path for path in search_dir.rglob(filename) if path.is_file())

    return sorted(set(candidates), key=lambda path: str(path))


def _manifest_summary(
    *,
    found_artifacts: Sequence[Mapping[str, Any]],
    missing_artifacts: Sequence[Mapping[str, Any]],
    ambiguous_artifacts: Sequence[Mapping[str, Any]],
    blocked_items: Sequence[Mapping[str, Any]],
) -> dict[str, int]:
    return {
        "control_section_count": len(SECTION_DEFINITIONS),
        "found_artifact_count": len(found_artifacts),
        "preferred_artifact_count": sum(
            1 for item in found_artifacts if item.get("source_type") == "preferred_path"
        ),
        "discovered_artifact_count": sum(
            1 for item in found_artifacts if item.get("source_type") == "discovered_path"
        ),
        "missing_artifact_count": len(missing_artifacts),
        "ambiguous_artifact_count": len(ambiguous_artifacts),
        "blocked_item_count": len(blocked_items),
    }


def _status(summary: Mapping[str, Any]) -> str:
    if _safe_int(summary.get("blocked_item_count")) > 0:
        return "blocked"
    if _safe_int(summary.get("found_artifact_count")) <= 0 and _safe_int(summary.get("ambiguous_artifact_count")) <= 0:
        return "blocked"
    if (
        _safe_int(summary.get("missing_artifact_count")) > 0
        or _safe_int(summary.get("ambiguous_artifact_count")) > 0
    ):
        return "needs_review"
    return "ready"


def _blocked_result(reason: str, *, report_date: str | None = None) -> dict[str, Any]:
    return {
        "artifact_type": "options_portfolio_control_report_artifact_manifest",
        "schema_version": "1.0",
        "status": "blocked",
        "is_ready": False,
        "requires_manual_approval": True,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "report_date": report_date,
        "manifest": {"artifact_paths": {}},
        "manifest_summary": {
            "control_section_count": len(SECTION_DEFINITIONS),
            "found_artifact_count": 0,
            "preferred_artifact_count": 0,
            "discovered_artifact_count": 0,
            "missing_artifact_count": len(SECTION_DEFINITIONS),
            "ambiguous_artifact_count": 0,
            "blocked_item_count": 1,
        },
        "found_artifacts": [],
        "missing_artifacts": [],
        "ambiguous_artifacts": [],
        "blocked_items": [{"reason": reason}],
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _resolve_path(path_value: str, root: Path) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return root / path


def _display_path(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _sorted_by_section(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [dict(item) for item in items],
        key=lambda item: (
            str(item.get("section", "")),
            str(item.get("reason", "")),
            str(item.get("path", "")),
        ),
    )


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0

