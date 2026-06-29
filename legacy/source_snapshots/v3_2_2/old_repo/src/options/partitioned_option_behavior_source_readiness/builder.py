from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from src.data_sources.data_source_inventory import EXPLICIT_EXCLUSIONS
from src.options.option_behavior_source_readiness import (
    build_signalforge_option_behavior_source_readiness,
)


ARTIFACT_TYPE = "signalforge_partitioned_option_behavior_source_readiness"
SCHEMA_VERSION = "signalforge_partitioned_option_behavior_source_readiness.v1"

SUMMARY_FILE = "signalforge_partitioned_option_behavior_source_readiness_summary.json"
COMBINED_FILE = "signalforge_partitioned_option_behavior_source_readiness.json"

OPTION_FILE = "signalforge_qc_filtered_option_rows.json"
MANIFEST_FILE = "signalforge_qc_replay_manifest.json"


def build_signalforge_partitioned_option_behavior_source_readiness(
    *,
    asset_behavior_decision_export: Mapping[str, Any] | None,
    inventory_source: Mapping[str, Any] | None,
    output_dir: str | Path,
    batch_limit: int | None = None,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    blocker_items: list[dict[str, Any]] = []
    warning_items: list[dict[str, Any]] = []

    if not isinstance(asset_behavior_decision_export, Mapping):
        asset_behavior_decision_export = {}
        blocker_items.append({"reason": "asset_behavior_decision_export_must_be_mapping"})

    if not isinstance(inventory_source, Mapping):
        inventory_source = {}
        blocker_items.append({"reason": "inventory_source_must_be_mapping"})

    result_dirs = _extract_result_dirs(inventory_source)
    if batch_limit is not None:
        result_dirs = result_dirs[: max(0, int(batch_limit))]

    if not result_dirs:
        blocker_items.append({"reason": "missing_inventory_result_dirs"})

    partition_items: list[dict[str, Any]] = []
    combined_ready_symbols: set[str] = set()
    combined_review_symbols: set[str] = set()
    combined_blocked_symbols: set[str] = set()
    total_option_rows = 0

    for batch_index, result_dir_text in enumerate(result_dirs):
        result_dir = Path(str(result_dir_text))
        partition_id = _partition_id(result_dir, batch_index)

        if not result_dir.exists():
            warning_items.append(
                {
                    "reason": "partition_result_dir_does_not_exist",
                    "partition_id": partition_id,
                    "result_dir": str(result_dir),
                }
            )
            continue

        try:
            manifest = _read_json(result_dir / MANIFEST_FILE)
            option_source = _read_json(result_dir / OPTION_FILE)
        except FileNotFoundError as exc:
            warning_items.append(
                {
                    "reason": "partition_missing_required_file",
                    "partition_id": partition_id,
                    "error": str(exc),
                }
            )
            continue
        except json.JSONDecodeError as exc:
            warning_items.append(
                {
                    "reason": "partition_invalid_json",
                    "partition_id": partition_id,
                    "error": str(exc),
                }
            )
            continue

        option_rows = _extract_option_rows(option_source)
        total_option_rows += len(option_rows)

        partition_result = build_signalforge_option_behavior_source_readiness(
            asset_behavior_decision_export,
            option_source,
        )

        partition_file = output_path / f"{partition_id}_option_behavior_source_readiness.json"
        partition_file.write_text(
            json.dumps(partition_result, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )

        summary = partition_result.get("option_behavior_source_readiness_summary") or {}
        ready_symbols = set(summary.get("ready_symbols") or [])
        review_symbols = set(summary.get("review_required_symbols") or [])
        blocked_symbols = set(summary.get("blocked_symbols") or [])

        combined_ready_symbols.update(str(symbol).upper() for symbol in ready_symbols)
        combined_review_symbols.update(str(symbol).upper() for symbol in review_symbols)
        combined_blocked_symbols.update(str(symbol).upper() for symbol in blocked_symbols)

        partition_items.append(
            {
                "artifact_type": "partitioned_option_behavior_source_readiness_item",
                "partition_id": partition_id,
                "partition_index": batch_index,
                "result_dir": str(result_dir),
                "request_id": manifest.get("request_id"),
                "partition_status": partition_result.get("status"),
                "partition_is_ready": partition_result.get("is_ready"),
                "option_row_count": len(option_rows),
                "ready_count": summary.get("ready_count"),
                "review_required_count": summary.get("review_required_count"),
                "blocked_count": summary.get("blocked_count"),
                "ready_symbols": sorted(ready_symbols),
                "review_required_symbols": sorted(review_symbols),
                "blocked_symbols": sorted(blocked_symbols),
                "output_file": str(partition_file),
            }
        )

    if not partition_items:
        blocker_items.append({"reason": "no_partition_readiness_items_produced"})

    partition_status_counts = Counter(
        str(item.get("partition_status") or "unknown") for item in partition_items
    )

    status = "blocked" if blocker_items else "needs_review" if warning_items else "ready"

    combined = {
        "artifact_type": ARTIFACT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "is_ready": status == "ready",
        "requires_manual_approval": True,
        "contract": "partitioned_option_behavior_source_readiness",
        "adapter_type": "partitioned_option_behavior_source_readiness_builder",
        "source_artifacts": {
            "asset_behavior_decision_export": asset_behavior_decision_export.get("artifact_type"),
            "inventory": inventory_source.get("artifact_type"),
        },
        "source_statuses": {
            "asset_behavior_decision_export": asset_behavior_decision_export.get("status"),
            "inventory": inventory_source.get("status"),
        },
        "macro_regime_label": asset_behavior_decision_export.get("macro_regime_label"),
        "policy_regime_label": asset_behavior_decision_export.get("policy_regime_label"),
        "weekly_planning_label": asset_behavior_decision_export.get("weekly_planning_label"),
        "market_confirmation": asset_behavior_decision_export.get("market_confirmation"),
        "partition_count": len(partition_items),
        "requested_partition_count": len(result_dirs),
        "total_option_row_count": total_option_rows,
        "partition_status_counts": dict(sorted(partition_status_counts.items())),
        "combined_ready_symbol_count": len(combined_ready_symbols),
        "combined_review_required_symbol_count": len(combined_review_symbols),
        "combined_blocked_symbol_count": len(combined_blocked_symbols),
        "combined_ready_symbols": sorted(combined_ready_symbols),
        "combined_review_required_symbols": sorted(combined_review_symbols),
        "combined_blocked_symbols": sorted(combined_blocked_symbols),
        "partition_items": partition_items,
        "blocker_items": blocker_items,
        "warning_items": warning_items,
        "order_intent": None,
        "broker_order_id": None,
        "automatic_action": None,
        "automatic_strategy_change": None,
        "automatic_parameter_change": None,
        "automatic_pause_action": None,
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }

    combined_path = output_path / COMBINED_FILE
    summary_path = output_path / SUMMARY_FILE

    combined_path.write_text(
        json.dumps(combined, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    summary = {
        "artifact_type": ARTIFACT_TYPE,
        "schema_version": f"{SCHEMA_VERSION}.summary",
        "status": status,
        "is_ready": status == "ready",
        "source_artifacts": combined["source_artifacts"],
        "source_statuses": combined["source_statuses"],
        "macro_regime_label": combined["macro_regime_label"],
        "policy_regime_label": combined["policy_regime_label"],
        "weekly_planning_label": combined["weekly_planning_label"],
        "partition_count": len(partition_items),
        "requested_partition_count": len(result_dirs),
        "total_option_row_count": total_option_rows,
        "partition_status_counts": dict(sorted(partition_status_counts.items())),
        "combined_ready_symbol_count": len(combined_ready_symbols),
        "combined_review_required_symbol_count": len(combined_review_symbols),
        "combined_blocked_symbol_count": len(combined_blocked_symbols),
        "blocker_count": len(blocker_items),
        "warning_count": len(warning_items),
        "files": {
            "combined": str(combined_path),
            "summary": str(summary_path),
        },
        "next_step": "run_partitioned_historical_option_behavior_or_build_option_behavior_classifier_runner",
        "explicit_exclusions": list(EXPLICIT_EXCLUSIONS),
    }

    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    return summary


def _extract_result_dirs(inventory_source: Mapping[str, Any]) -> list[str]:
    rows = inventory_source.get("results") or inventory_source.get("batches") or []
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)):
        return []

    result_dirs: list[str] = []
    for row in rows:
        if isinstance(row, Mapping):
            value = row.get("result_dir") or row.get("decoded_result_dir") or row.get("source_dir")
            if value:
                result_dirs.append(str(value))

    return sorted(dict.fromkeys(result_dirs))


def _extract_option_rows(option_source: Mapping[str, Any]) -> list[Any]:
    for key in ("filtered_option_rows", "option_rows", "rows", "data"):
        value = option_source.get(key)
        if isinstance(value, list):
            return value
    return []


def _partition_id(result_dir: Path, batch_index: int) -> str:
    batch_name = result_dir.name.replace(" ", "_")
    parent_name = result_dir.parent.name.replace(" ", "_")
    return f"{batch_index + 1:04d}_{parent_name}_{batch_name}"


def _read_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(str(path))
    return json.loads(path.read_text(encoding="utf-8-sig"))
