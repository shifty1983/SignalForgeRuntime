from __future__ import annotations

import json
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


def assemble_options_portfolio_control_report_source(
    source: Mapping[str, Any],
    *,
    base_dir: str | PathLike[str] | None = None,
) -> dict[str, Any]:
    """Assemble a control-report source from direct artifacts and artifact paths.

    This assembler reads local JSON artifact files and combines them into the
    source shape expected by the options portfolio control report. It is local
    and advisory only. It does not call brokers, route orders, submit orders,
    model fills, perform live execution, model slippage, or apply automatic
    strategy/parameter/pause changes.
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

    assembled_source: dict[str, Any] = {}
    if report_date is not None:
        assembled_source["report_date"] = report_date

    loaded_artifacts: list[dict[str, Any]] = []
    missing_artifacts: list[dict[str, Any]] = []
    blocked_items: list[dict[str, Any]] = []

    for definition in SECTION_DEFINITIONS:
        section = str(definition["section"])
        canonical_key = str(definition["keys"][0])

        direct_artifact = _find_direct_artifact(source, definition["keys"])
        if direct_artifact:
            assembled_source[canonical_key] = dict(direct_artifact)
            loaded_artifacts.append(
                {
                    "section": section,
                    "source_type": "direct",
                    "source_key": _matched_direct_key(source, definition["keys"]),
                    "artifact_type": direct_artifact.get("artifact_type"),
                    "status": _normalized(direct_artifact.get("status")) or None,
                }
            )
            continue

        path_value = _find_artifact_path(source, section=section, keys=definition["keys"])
        if path_value is None:
            missing_artifacts.append(
                {
                    "section": section,
                    "reason": "missing_artifact_path_or_direct_artifact",
                }
            )
            continue

        artifact_path = _resolve_path(path_value, root)
        try:
            artifact = _read_json_mapping(artifact_path)
        except FileNotFoundError:
            blocked_items.append(
                {
                    "section": section,
                    "reason": "artifact_file_not_found",
                    "path": str(artifact_path),
                }
            )
            continue
        except json.JSONDecodeError as error:
            blocked_items.append(
                {
                    "section": section,
                    "reason": "artifact_file_invalid_json",
                    "path": str(artifact_path),
                    "error": str(error),
                }
            )
            continue
        except ValueError:
            blocked_items.append(
                {
                    "section": section,
                    "reason": "artifact_file_json_not_mapping",
                    "path": str(artifact_path),
                }
            )
            continue

        assembled_source[canonical_key] = artifact
        loaded_artifacts.append(
            {
                "section": section,
                "source_type": "file",
                "path": str(artifact_path),
                "artifact_type": artifact.get("artifact_type"),
                "status": _normalized(artifact.get("status")) or None,
            }
        )

    source_summary = _source_summary(
        loaded_artifacts=loaded_artifacts,
        missing_artifacts=missing_artifacts,
        blocked_items=blocked_items,
    )
    status = _status(source_summary)

    return {
        "artifact_type": "options_portfolio_control_report_source",
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
        "assembled_source": assembled_source,
        "source_summary": source_summary,
        "loaded_artifacts": _sorted_by_section(loaded_artifacts),
        "missing_artifacts": _sorted_by_section(missing_artifacts),
        "blocked_items": _sorted_by_section(blocked_items),
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _find_direct_artifact(source: Mapping[str, Any], keys: Sequence[str]) -> Mapping[str, Any]:
    for key in keys:
        value = source.get(key)
        if isinstance(value, Mapping):
            return value

    for nested_key in ("artifacts", "source_artifacts", "control_sources"):
        nested = source.get(nested_key)
        if isinstance(nested, Mapping):
            for key in keys:
                value = nested.get(key)
                if isinstance(value, Mapping):
                    return value

    return {}


def _matched_direct_key(source: Mapping[str, Any], keys: Sequence[str]) -> str | None:
    for key in keys:
        if isinstance(source.get(key), Mapping):
            return key

    for nested_key in ("artifacts", "source_artifacts", "control_sources"):
        nested = source.get(nested_key)
        if isinstance(nested, Mapping):
            for key in keys:
                if isinstance(nested.get(key), Mapping):
                    return f"{nested_key}.{key}"

    return None


def _find_artifact_path(
    source: Mapping[str, Any],
    *,
    section: str,
    keys: Sequence[str],
) -> str | None:
    artifact_paths = source.get("artifact_paths")
    if isinstance(artifact_paths, Mapping):
        for key in (section, *keys):
            value = _string_or_none(artifact_paths.get(key))
            if value:
                return value

    for key in (f"{section}_path", *(f"{item}_path" for item in keys)):
        value = _string_or_none(source.get(key))
        if value:
            return value

    return None


def _resolve_path(path_value: str, root: Path) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return root / path


def _read_json_mapping(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file:
        payload = json.load(file)

    if not isinstance(payload, Mapping):
        raise ValueError("artifact JSON payload must be a mapping")

    return dict(payload)


def _source_summary(
    *,
    loaded_artifacts: Sequence[Mapping[str, Any]],
    missing_artifacts: Sequence[Mapping[str, Any]],
    blocked_items: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    file_count = sum(1 for item in loaded_artifacts if item.get("source_type") == "file")
    direct_count = sum(1 for item in loaded_artifacts if item.get("source_type") == "direct")

    return {
        "control_section_count": len(SECTION_DEFINITIONS),
        "loaded_artifact_count": len(loaded_artifacts),
        "file_artifact_count": file_count,
        "direct_artifact_count": direct_count,
        "missing_artifact_count": len(missing_artifacts),
        "blocked_item_count": len(blocked_items),
        "ready_artifact_count": sum(1 for item in loaded_artifacts if item.get("status") == "ready"),
        "needs_review_artifact_count": sum(
            1 for item in loaded_artifacts if item.get("status") == "needs_review"
        ),
        "blocked_artifact_count": sum(
            1 for item in loaded_artifacts if item.get("status") == "blocked"
        ),
    }


def _status(source_summary: Mapping[str, Any]) -> str:
    if _safe_int(source_summary.get("blocked_item_count")) > 0:
        return "blocked"
    if _safe_int(source_summary.get("loaded_artifact_count")) <= 0:
        return "blocked"
    if _safe_int(source_summary.get("missing_artifact_count")) > 0:
        return "needs_review"
    if _safe_int(source_summary.get("blocked_artifact_count")) > 0:
        return "blocked"
    if _safe_int(source_summary.get("needs_review_artifact_count")) > 0:
        return "needs_review"
    return "ready"


def _blocked_result(reason: str) -> dict[str, Any]:
    return {
        "artifact_type": "options_portfolio_control_report_source",
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
        "report_date": None,
        "assembled_source": {},
        "source_summary": {
            "control_section_count": len(SECTION_DEFINITIONS),
            "loaded_artifact_count": 0,
            "file_artifact_count": 0,
            "direct_artifact_count": 0,
            "missing_artifact_count": len(SECTION_DEFINITIONS),
            "blocked_item_count": 1,
            "ready_artifact_count": 0,
            "needs_review_artifact_count": 0,
            "blocked_artifact_count": 0,
        },
        "loaded_artifacts": [],
        "missing_artifacts": [],
        "blocked_items": [{"reason": reason}],
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }


def _sorted_by_section(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [dict(item) for item in items],
        key=lambda item: (
            str(item.get("section", "")),
            str(item.get("reason", "")),
            str(item.get("path", "")),
        ),
    )


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalized(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0

