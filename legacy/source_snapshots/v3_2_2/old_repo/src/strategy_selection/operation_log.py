from __future__ import annotations

import json
from collections.abc import Mapping
from os import PathLike
from pathlib import Path
from typing import Any

from src.signalforge.engines.strategy_selection.operation_record import (
    STRATEGY_SELECTION_OPERATION_RECORD_SCHEMA_VERSION,
    STRATEGY_SELECTION_OPERATION_TYPE,
    StrategySelectionOperationRecord,
)


class StrategySelectionOperationLogError(ValueError):
    """Raised when strategy-selection operation log persistence fails."""


def append_strategy_selection_operation_record(
    record: StrategySelectionOperationRecord | Mapping[str, Any],
    log_path: str | PathLike[str],
) -> Path:
    """
    Append a strategy-selection operation record to a JSONL operation log.

    This only persists the record. It does not audit, enforce health, optimize,
    or trigger downstream execution.
    """
    payload = _record_to_dict(record)
    _validate_log_payload(payload)

    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, sort_keys=True))
        file.write("\n")

    return path


def read_strategy_selection_operation_log(
    log_path: str | PathLike[str],
) -> list[dict[str, Any]]:
    path = Path(log_path)

    if not path.exists():
        return []

    records: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            raw_line = line.strip()

            if not raw_line:
                continue

            try:
                payload = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                raise StrategySelectionOperationLogError(
                    f"invalid JSONL at line {line_number}: {exc.msg}"
                ) from exc

            if not isinstance(payload, dict):
                raise StrategySelectionOperationLogError(
                    f"operation log line {line_number} is not a JSON object"
                )

            records.append(payload)

    return records


def _record_to_dict(
    record: StrategySelectionOperationRecord | Mapping[str, Any],
) -> dict[str, Any]:
    if hasattr(record, "to_dict"):
        return record.to_dict()

    if isinstance(record, Mapping):
        return dict(record)

    raise StrategySelectionOperationLogError(
        "record must be a StrategySelectionOperationRecord or mapping"
    )


def _validate_log_payload(payload: Mapping[str, Any]) -> None:
    operation_type = payload.get("operation_type")
    schema_version = payload.get("schema_version")

    if operation_type != STRATEGY_SELECTION_OPERATION_TYPE:
        raise StrategySelectionOperationLogError(
            f"invalid operation_type for strategy-selection log: {operation_type!r}"
        )

    if schema_version != STRATEGY_SELECTION_OPERATION_RECORD_SCHEMA_VERSION:
        raise StrategySelectionOperationLogError(
            f"invalid schema_version for strategy-selection log: {schema_version!r}"
        )

    if not payload.get("operation_id"):
        raise StrategySelectionOperationLogError(
            "strategy-selection operation log payload missing operation_id"
        )
