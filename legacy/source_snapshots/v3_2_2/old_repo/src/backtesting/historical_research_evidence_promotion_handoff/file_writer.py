from __future__ import annotations

import json
from os import PathLike
from pathlib import Path
from typing import Any, Mapping

from src.backtesting.historical_research_evidence_promotion_handoff.operation import (
    run_historical_research_evidence_promotion_handoff_operation,
)


FILE_WRITER_SCHEMA_VERSION = (
    "historical_research_evidence_promotion_handoff_files.v1"
)

OPERATION_TYPE = (
    "historical_research_evidence_promotion_handoff_file_writer"
)

DEFAULT_FILENAMES = {
    "promotion_handoff": (
        "historical_research_evidence_promotion_handoff.json"
    ),
    "operation_result": (
        "historical_research_evidence_promotion_handoff_operation.json"
    ),
    "audit_report": (
        "historical_research_evidence_promotion_handoff_audit.json"
    ),
    "health_report": (
        "historical_research_evidence_promotion_handoff_health.json"
    ),
    "promoted_items": (
        "historical_research_evidence_promoted_items.json"
    ),
    "strategy_ids": (
        "historical_research_evidence_promoted_strategy_ids.json"
    ),
    "symbols": (
        "historical_research_evidence_promoted_symbols.json"
    ),
    "backtest_ids": (
        "historical_research_evidence_promoted_backtest_ids.json"
    ),
    "evidence_ids": (
        "historical_research_evidence_promoted_evidence_ids.json"
    ),
    "event_log": (
        "historical_research_evidence_promotion_handoff_operation.jsonl"
    ),
}


def write_historical_research_evidence_promotion_handoff_files(
    source: Any,
    *,
    output_dir: str | PathLike[str],
) -> dict[str, Any]:
    """Write deterministic promotion handoff artifacts.

    This writer does not call QuantConnect, brokers, market-data services,
    order-routing systems, live-trading APIs, fill engines, slippage engines,
    or external data warehouses.
    """

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    event_log_path = output_path / DEFAULT_FILENAMES["event_log"]

    operation_result = (
        run_historical_research_evidence_promotion_handoff_operation(
            source,
            event_log_path=event_log_path,
        )
    )

    promotion_handoff = _as_mapping(
        operation_result.get("promotion_handoff")
    )
    audit_report = _as_mapping(
        operation_result.get("audit_report")
    )
    health_report = _as_mapping(
        operation_result.get("health_report")
    )

    files = {
        "promotion_handoff": (
            output_path / DEFAULT_FILENAMES["promotion_handoff"]
        ),
        "operation_result": (
            output_path / DEFAULT_FILENAMES["operation_result"]
        ),
        "audit_report": (
            output_path / DEFAULT_FILENAMES["audit_report"]
        ),
        "health_report": (
            output_path / DEFAULT_FILENAMES["health_report"]
        ),
        "promoted_items": (
            output_path / DEFAULT_FILENAMES["promoted_items"]
        ),
        "strategy_ids": (
            output_path / DEFAULT_FILENAMES["strategy_ids"]
        ),
        "symbols": (
            output_path / DEFAULT_FILENAMES["symbols"]
        ),
        "backtest_ids": (
            output_path / DEFAULT_FILENAMES["backtest_ids"]
        ),
        "evidence_ids": (
            output_path / DEFAULT_FILENAMES["evidence_ids"]
        ),
        "event_log": event_log_path,
    }

    _write_json(
        files["promotion_handoff"],
        promotion_handoff,
    )
    _write_json(
        files["operation_result"],
        operation_result,
    )
    _write_json(
        files["audit_report"],
        audit_report,
    )
    _write_json(
        files["health_report"],
        health_report,
    )
    _write_json(
        files["promoted_items"],
        _as_list(promotion_handoff.get("promoted_items")),
    )
    _write_json(
        files["strategy_ids"],
        _as_list(promotion_handoff.get("strategy_ids")),
    )
    _write_json(
        files["symbols"],
        _as_list(promotion_handoff.get("symbols")),
    )
    _write_json(
        files["backtest_ids"],
        _as_list(promotion_handoff.get("backtest_ids")),
    )
    _write_json(
        files["evidence_ids"],
        _as_list(promotion_handoff.get("evidence_ids")),
    )

    return {
        "schema_version": FILE_WRITER_SCHEMA_VERSION,
        "operation_type": OPERATION_TYPE,
        "status": operation_result.get("status", "needs_review"),
        "output_dir": str(output_path),
        "files": {
            key: str(path)
            for key, path in files.items()
        },
        "file_summary": _build_file_summary(files),
        "operation_result": operation_result,
        "explicit_exclusions": list(
            operation_result.get("explicit_exclusions", [])
        ),
    }


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _build_file_summary(
    files: Mapping[str, Path],
) -> dict[str, Any]:
    return {
        "file_count": len(files),
        "written_files": sorted(files.keys()),
        "missing_files": sorted(
            key
            for key, path in files.items()
            if not path.exists()
        ),
        "empty_files": sorted(
            key
            for key, path in files.items()
            if path.exists() and path.stat().st_size == 0
        ),
    }


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)

    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value

    return []
