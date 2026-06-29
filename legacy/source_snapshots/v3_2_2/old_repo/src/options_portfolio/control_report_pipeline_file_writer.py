from __future__ import annotations

import json
from collections.abc import Mapping
from os import PathLike
from pathlib import Path
from typing import Any

from src.options_portfolio.control_report_file_writer import (
    DEFAULT_FILENAMES as CONTROL_REPORT_FILENAMES,
    write_options_portfolio_control_report_operation_files,
)
from src.options_portfolio.control_report_source_assembler_file_writer import (
    DEFAULT_FILENAMES as SOURCE_ASSEMBLER_FILENAMES,
    write_options_portfolio_control_report_source_assembler_operation_files,
)


PIPELINE_SCHEMA_VERSION = "options_portfolio_control_report_pipeline_files.v1"
PIPELINE_TYPE = "options_portfolio_control_report_pipeline"
PIPELINE_SUMMARY_FILENAME = "options_portfolio_control_report_pipeline_summary.json"

SOURCE_ASSEMBLER_DIRNAME = "source_assembler"
CONTROL_REPORT_DIRNAME = "control_report"


def write_options_portfolio_control_report_pipeline_files(
    source: Any,
    *,
    output_dir: str | PathLike[str],
    base_dir: str | PathLike[str] | None = None,
    report_date: str | None = None,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    source_assembler_output_dir = output_path / SOURCE_ASSEMBLER_DIRNAME
    control_report_output_dir = output_path / CONTROL_REPORT_DIRNAME
    source_assembler_output_dir.mkdir(parents=True, exist_ok=True)
    control_report_output_dir.mkdir(parents=True, exist_ok=True)

    source_assembler_result = write_options_portfolio_control_report_source_assembler_operation_files(
        source,
        output_dir=source_assembler_output_dir,
        base_dir=base_dir,
        report_date=report_date,
    )

    control_report_result: dict[str, Any] | None = None
    assembled_source_path = (
        source_assembler_output_dir / SOURCE_ASSEMBLER_FILENAMES["assembled_source"]
    )

    if source_assembler_result.get("status") != "blocked":
        assembled_source = _read_json_mapping(assembled_source_path)
        control_report_result = write_options_portfolio_control_report_operation_files(
            assembled_source,
            output_dir=control_report_output_dir,
            report_date=report_date,
        )

    status = _classify_pipeline_status(
        source_assembler_status=str(source_assembler_result.get("status", "needs_review")),
        control_report_status=(
            str(control_report_result.get("status", "needs_review"))
            if control_report_result is not None
            else None
        ),
    )

    pipeline_summary = {
        "schema_version": PIPELINE_SCHEMA_VERSION,
        "pipeline_type": PIPELINE_TYPE,
        "status": status,
        "output_dir": str(output_path),
        "base_dir": str(base_dir) if base_dir is not None else None,
        "report_date": report_date,
        "source_assembler_output_dir": str(source_assembler_output_dir),
        "control_report_output_dir": (
            str(control_report_output_dir) if control_report_result is not None else None
        ),
        "assembled_source_path": str(assembled_source_path),
        "source_assembler_status": source_assembler_result.get("status"),
        "control_report_status": (
            control_report_result.get("status") if control_report_result is not None else None
        ),
        "source_assembler_summary": source_assembler_result.get("source_summary", {}),
        "control_report_summary": _control_report_operation_summary(control_report_result),
        "files": {
            "pipeline_summary": str(output_path / PIPELINE_SUMMARY_FILENAME),
            "source_assembler": source_assembler_result.get("files", {}),
            "control_report": (
                control_report_result.get("files", {}) if control_report_result is not None else {}
            ),
        },
        "explicit_exclusions": _explicit_exclusions(
            source_assembler_result=source_assembler_result,
            control_report_result=control_report_result,
        ),
    }

    _write_json(output_path / PIPELINE_SUMMARY_FILENAME, pipeline_summary)
    return pipeline_summary


def _classify_pipeline_status(
    *,
    source_assembler_status: str,
    control_report_status: str | None,
) -> str:
    statuses = {source_assembler_status}
    if control_report_status is not None:
        statuses.add(control_report_status)

    if "blocked" in statuses:
        return "blocked"
    if "needs_review" in statuses:
        return "needs_review"
    return "ready"


def _control_report_operation_summary(control_report_result: Mapping[str, Any] | None) -> dict[str, Any]:
    if control_report_result is None:
        return {}

    operation_result = _as_mapping(control_report_result.get("operation_result"))
    operation_record = _as_mapping(operation_result.get("operation_record"))
    return dict(_as_mapping(operation_record.get("operation_summary")))


def _explicit_exclusions(
    *,
    source_assembler_result: Mapping[str, Any],
    control_report_result: Mapping[str, Any] | None,
) -> list[str]:
    exclusions = set(_as_list(source_assembler_result.get("explicit_exclusions")))
    if control_report_result is not None:
        exclusions.update(_as_list(control_report_result.get("explicit_exclusions")))
    return sorted(exclusions)


def _read_json_mapping(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file:
        payload = json.load(file)

    if not isinstance(payload, Mapping):
        raise ValueError("assembled source JSON must be a mapping")

    return dict(payload)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []

