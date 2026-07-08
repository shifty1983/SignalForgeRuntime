from __future__ import annotations

import json
from collections.abc import Mapping
from os import PathLike
from pathlib import Path
from typing import Any

from src.portfolio_construction.operation_record import (
    PORTFOLIO_CONSTRUCTION_OPERATION_RECORD_SCHEMA_VERSION,
    PORTFOLIO_CONSTRUCTION_OPERATION_TYPE,
    PortfolioConstructionOperationRecord,
)


class PortfolioConstructionOperationLogError(ValueError):
    """Raised when portfolio construction operation log persistence fails."""


def append_portfolio_construction_operation_record(
    record: PortfolioConstructionOperationRecord | Mapping[str, Any],
    log_path: str | PathLike[str],
) -> Path:
    payload = _record_to_dict(record)
    _validate_log_payload(payload)

    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, sort_keys=True))
        file.write("\n")

    return path


def read_portfolio_construction_operation_log(
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
                raise PortfolioConstructionOperationLogError(
                    f"invalid JSONL at line {line_number}: {exc.msg}"
                ) from exc

            if not isinstance(payload, dict):
                raise PortfolioConstructionOperationLogError(
                    f"operation log line {line_number} is not a JSON object"
                )

            records.append(payload)

    return records


def _record_to_dict(
    record: PortfolioConstructionOperationRecord | Mapping[str, Any],
) -> dict[str, Any]:
    if hasattr(record, "to_dict"):
        return record.to_dict()

    if isinstance(record, Mapping):
        return dict(record)

    raise PortfolioConstructionOperationLogError(
        "record must be a PortfolioConstructionOperationRecord or mapping"
    )


def _validate_log_payload(payload: Mapping[str, Any]) -> None:
    operation_type = payload.get("operation_type")
    schema_version = payload.get("schema_version")

    if operation_type != PORTFOLIO_CONSTRUCTION_OPERATION_TYPE:
        raise PortfolioConstructionOperationLogError(
            f"invalid operation_type for portfolio-construction log: {operation_type!r}"
        )

    if schema_version != PORTFOLIO_CONSTRUCTION_OPERATION_RECORD_SCHEMA_VERSION:
        raise PortfolioConstructionOperationLogError(
            f"invalid schema_version for portfolio-construction log: {schema_version!r}"
        )

    if not payload.get("operation_id"):
        raise PortfolioConstructionOperationLogError(
            "portfolio-construction operation log payload missing operation_id"
        )
