from __future__ import annotations

import json
from collections.abc import Mapping
from os import PathLike
from pathlib import Path
from typing import Any

from src.options_portfolio.control_report_manifest_builder_file_writer import (
    DEFAULT_FILENAMES as MANIFEST_BUILDER_FILENAMES,
    write_options_portfolio_control_report_manifest_builder_operation_files,
)
from src.options_portfolio.control_report_pipeline_operation_file_writer import (
    DEFAULT_FILENAMES as PIPELINE_OPERATION_FILENAMES,
    write_options_portfolio_control_report_pipeline_operation_files,
)


AUTODISCOVERY_PIPELINE_SCHEMA_VERSION = "options_portfolio_control_report_autodiscovery_pipeline_files.v1"
AUTODISCOVERY_PIPELINE_TYPE = "options_portfolio_control_report_autodiscovery_pipeline"
AUTODISCOVERY_PIPELINE_SUMMARY_FILENAME = "options_portfolio_control_report_autodiscovery_pipeline_summary.json"

MANIFEST_BUILDER_DIRNAME = "manifest_builder"
PIPELINE_OPERATION_DIRNAME = "pipeline_operation"


def write_options_portfolio_control_report_autodiscovery_pipeline_files(
    source: Any,
    *,
    output_dir: str | PathLike[str],
    base_dir: str | PathLike[str] | None = None,
    report_date: str | None = None,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    manifest_builder_output_dir = output_path / MANIFEST_BUILDER_DIRNAME
    pipeline_operation_output_dir = output_path / PIPELINE_OPERATION_DIRNAME
    manifest_builder_output_dir.mkdir(parents=True, exist_ok=True)
    pipeline_operation_output_dir.mkdir(parents=True, exist_ok=True)

    manifest_builder_result = write_options_portfolio_control_report_manifest_builder_operation_files(
        source,
        output_dir=manifest_builder_output_dir,
        base_dir=base_dir,
        report_date=report_date,
    )

    pipeline_operation_result: dict[str, Any] | None = None
    generated_manifest_path = (
        manifest_builder_output_dir / MANIFEST_BUILDER_FILENAMES["manifest"]
    )

    if manifest_builder_result.get("status") != "blocked":
        generated_manifest = _read_json_mapping(generated_manifest_path)
        pipeline_operation_result = write_options_portfolio_control_report_pipeline_operation_files(
            generated_manifest,
            output_dir=pipeline_operation_output_dir,
            base_dir=base_dir,
            report_date=report_date,
        )

    status = _classify_status(
        manifest_builder_status=str(manifest_builder_result.get("status", "needs_review")),
        pipeline_operation_status=(
            str(pipeline_operation_result.get("status", "needs_review"))
            if pipeline_operation_result is not None
            else None
        ),
    )

    summary = {
        "schema_version": AUTODISCOVERY_PIPELINE_SCHEMA_VERSION,
        "pipeline_type": AUTODISCOVERY_PIPELINE_TYPE,
        "status": status,
        "output_dir": str(output_path),
        "base_dir": str(base_dir) if base_dir is not None else None,
        "report_date": report_date,
        "manifest_builder_output_dir": str(manifest_builder_output_dir),
        "pipeline_operation_output_dir": (
            str(pipeline_operation_output_dir) if pipeline_operation_result is not None else None
        ),
        "generated_manifest_path": str(generated_manifest_path),
        "manifest_builder_status": manifest_builder_result.get("status"),
        "pipeline_operation_status": (
            pipeline_operation_result.get("status") if pipeline_operation_result is not None else None
        ),
        "manifest_summary": manifest_builder_result.get("manifest_summary", {}),
        "pipeline_operation_summary": (
            pipeline_operation_result.get("operation_summary", {})
            if pipeline_operation_result is not None
            else {}
        ),
        "files": {
            "autodiscovery_pipeline_summary": str(
                output_path / AUTODISCOVERY_PIPELINE_SUMMARY_FILENAME
            ),
            "manifest_builder": manifest_builder_result.get("files", {}),
            "pipeline_operation": (
                pipeline_operation_result.get("files", {})
                if pipeline_operation_result is not None
                else {}
            ),
        },
        "explicit_exclusions": _explicit_exclusions(
            manifest_builder_result=manifest_builder_result,
            pipeline_operation_result=pipeline_operation_result,
        ),
    }

    _write_json(output_path / AUTODISCOVERY_PIPELINE_SUMMARY_FILENAME, summary)
    return summary


def _classify_status(
    *,
    manifest_builder_status: str,
    pipeline_operation_status: str | None,
) -> str:
    statuses = {manifest_builder_status}
    if pipeline_operation_status is not None:
        statuses.add(pipeline_operation_status)

    if "blocked" in statuses:
        return "blocked"
    if "needs_review" in statuses:
        return "needs_review"
    return "ready"


def _explicit_exclusions(
    *,
    manifest_builder_result: Mapping[str, Any],
    pipeline_operation_result: Mapping[str, Any] | None,
) -> list[str]:
    exclusions = set(_as_list(manifest_builder_result.get("explicit_exclusions")))
    if pipeline_operation_result is not None:
        exclusions.update(_as_list(pipeline_operation_result.get("explicit_exclusions")))
    return sorted(exclusions)


def _read_json_mapping(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file:
        payload = json.load(file)

    if not isinstance(payload, Mapping):
        raise ValueError("generated manifest JSON must be a mapping")

    return dict(payload)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []

