from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from src.backtesting.quantconnect_manual_backtest_evidence_pipeline.file_writer import (
    write_quantconnect_manual_backtest_evidence_pipeline_files,
)
from src.backtesting.quantconnect_manual_result_decision_marker_normalizer import (
    build_quantconnect_manual_result_decision_marker_normalization,
)
from src.backtesting.quantconnect_manual_result_source_validator.file_writer import (
    write_quantconnect_manual_result_source_validation_files,
)


CLI_SUMMARY_SCHEMA_VERSION = "quantconnect_manual_import_workflow_cli_summary.v1"
DEFAULT_VALIDATION_DIRNAME = "validation"
DEFAULT_PIPELINE_DIRNAME = "pipeline"
DEFAULT_WORKFLOW_SUMMARY_FILENAME = "quantconnect_manual_import_workflow_summary.json"
DEFAULT_NORMALIZATION_FILENAME = (
    "quantconnect_manual_import_workflow_normalization.json"
)
DEFAULT_NORMALIZED_SOURCE_FILENAME = (
    "quantconnect_manual_import_workflow_normalized_source.json"
)

WriterFunction = Callable[..., dict[str, Any]]


def main(
    argv: Sequence[str] | None = None,
    *,
    normalizer: Callable[[Any], dict[str, Any]] = (
        build_quantconnect_manual_result_decision_marker_normalization
    ),
    validation_writer: WriterFunction = (
        write_quantconnect_manual_result_source_validation_files
    ),
    pipeline_writer: WriterFunction = (
        write_quantconnect_manual_backtest_evidence_pipeline_files
    ),
) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        source = _read_json(args.source)
    except FileNotFoundError:
        print(f"source file not found: {args.source}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as error:
        print(f"source file is not valid JSON: {error}", file=sys.stderr)
        return 2

    output_path = Path(args.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    normalization_result = normalizer(source)
    normalized_source = _as_mapping(
        normalization_result.get("normalized_source")
    )

    normalization_path = output_path / DEFAULT_NORMALIZATION_FILENAME
    normalized_source_path = output_path / DEFAULT_NORMALIZED_SOURCE_FILENAME
    summary_path = output_path / DEFAULT_WORKFLOW_SUMMARY_FILENAME

    _write_json(normalization_path, normalization_result)
    _write_json(normalized_source_path, normalized_source)

    normalization_status = str(
        normalization_result.get("status", "needs_review")
    )

    if normalization_status == "blocked":
        summary = _build_cli_summary(
            workflow_status="blocked",
            output_dir=output_path,
            validation_output_dir=None,
            normalization_result=normalization_result,
            normalization_path=normalization_path,
            normalized_source_path=normalized_source_path,
            pipeline_output_dir=None,
            validation_result={},
            validation_payload={},
            validation_summary={},
            pipeline_result={},
            pipeline_payload={},
            pipeline_ran=False,
            allow_needs_review=args.allow_needs_review,
            workflow_summary_path=summary_path,
        )

        _write_json(summary_path, summary)
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 1

    validation_output_dir = output_path / DEFAULT_VALIDATION_DIRNAME
    pipeline_output_dir = output_path / DEFAULT_PIPELINE_DIRNAME

    validation_result = validation_writer(
        normalized_source,
        output_dir=validation_output_dir,
    )

    validation_payload = _extract_validation(validation_result)
    validation_status = str(validation_result.get("status", "needs_review"))
    validation_summary = _as_mapping(validation_payload.get("summary"))

    pipeline_result: dict[str, Any] = {}
    pipeline_ran = False

    if _should_run_pipeline(
        validation_status=validation_status,
        allow_needs_review=args.allow_needs_review,
    ):
        pipeline_result = pipeline_writer(
            normalized_source,
            output_dir=pipeline_output_dir,
        )
        pipeline_ran = True

    pipeline_payload = _extract_pipeline_result(pipeline_result)
    pipeline_status = (
        str(pipeline_result.get("status", "not_run"))
        if pipeline_ran
        else "not_run"
    )

    workflow_status = _classify_workflow_status(
        validation_status=validation_status,
        pipeline_status=pipeline_status,
        pipeline_ran=pipeline_ran,
    )

    summary = _build_cli_summary(
        workflow_status=workflow_status,
        output_dir=output_path,
        validation_output_dir=validation_output_dir,
        normalization_result=normalization_result,
        normalization_path=normalization_path,
        normalized_source_path=normalized_source_path,
        pipeline_output_dir=pipeline_output_dir if pipeline_ran else None,
        validation_result=validation_result,
        validation_payload=validation_payload,
        validation_summary=validation_summary,
        pipeline_result=pipeline_result,
        pipeline_payload=pipeline_payload,
        pipeline_ran=pipeline_ran,
        allow_needs_review=args.allow_needs_review,
        workflow_summary_path=summary_path,
    )

    _write_json(summary_path, summary)
    print(json.dumps(summary, indent=2, sort_keys=True))

    if workflow_status == "blocked":
        return 1

    if not pipeline_ran and validation_status != "ready":
        return 1

    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a local manual QuantConnect result source and, when "
            "validation is ready, run the local 12-stage manual backtest "
            "evidence pipeline. This command writes local files only and does "
            "not call QuantConnect, brokers, market-data APIs, order-routing "
            "systems, live execution systems, fill engines, slippage engines, "
            "or external data warehouses."
        )
    )

    parser.add_argument(
        "--source",
        required=True,
        help="Path to filled manual QuantConnect result source JSON.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where workflow artifacts should be written.",
    )
    parser.add_argument(
        "--allow-needs-review",
        action="store_true",
        help=(
            "Allow the pipeline to run when source validation returns "
            "needs_review. Blocked validation never runs the pipeline."
        ),
    )

    return parser


def _read_json(path: str) -> Any:
    source_path = Path(path)

    with source_path.open(encoding="utf-8") as file:
        return json.load(file)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _should_run_pipeline(
    *,
    validation_status: str,
    allow_needs_review: bool,
) -> bool:
    if validation_status == "ready":
        return True

    if validation_status == "needs_review" and allow_needs_review:
        return True

    return False


def _classify_workflow_status(
    *,
    validation_status: str,
    pipeline_status: str,
    pipeline_ran: bool,
) -> str:
    if validation_status == "blocked":
        return "blocked"

    if not pipeline_ran:
        return validation_status

    if pipeline_status == "blocked":
        return "blocked"

    if validation_status == "needs_review" or pipeline_status == "needs_review":
        return "needs_review"

    if validation_status == "ready" and pipeline_status == "ready":
        return "ready"

    return "needs_review"


def _build_cli_summary(
    *,
    workflow_status: str,
    output_dir: Path,
    validation_output_dir: Path | None,
    normalization_result: Mapping[str, Any],
    normalization_path: Path,
    normalized_source_path: Path,
    pipeline_output_dir: Path | None,
    validation_result: Mapping[str, Any],
    validation_payload: Mapping[str, Any],
    validation_summary: Mapping[str, Any],
    pipeline_result: Mapping[str, Any],
    pipeline_payload: Mapping[str, Any],
    pipeline_ran: bool,
    allow_needs_review: bool,
    workflow_summary_path: Path,
) -> dict[str, Any]:
    normalization_summary = _as_mapping(normalization_result.get("summary"))
    validation_operation_summary = _extract_operation_summary(
        validation_result
    )
    pipeline_operation_summary = _extract_operation_summary(pipeline_result)

    validation_health = _extract_health_report(validation_result)
    pipeline_health = _extract_health_report(pipeline_result)

    return {
        "schema_version": CLI_SUMMARY_SCHEMA_VERSION,
        "status": workflow_status,
        "output_dir": str(output_dir),
        "workflow_summary_path": str(workflow_summary_path),
        "allow_needs_review": allow_needs_review,
        "pipeline_ran": pipeline_ran,
        "normalization_status": normalization_result.get("status"),
        "normalization_path": str(normalization_path),
        "normalized_source_path": str(normalized_source_path),
        "normalization_summary": normalization_summary,
        "generated_decision_event_count": _safe_int(
            normalization_summary.get("generated_decision_event_count")
        ),
        "generated_log_marker_count": _safe_int(
            normalization_summary.get("generated_log_marker_count")
        ),
        "validation_status": (
            validation_result.get("status", "not_run")
            if validation_result
            else "not_run"
        ),
        "pipeline_status": (
            pipeline_result.get("status", "not_run")
            if pipeline_ran
            else "not_run"
        ),
        "validation_output_dir": (
            str(validation_output_dir) if validation_output_dir else None
        ),
        "pipeline_output_dir": (
            str(pipeline_output_dir) if pipeline_output_dir else None
        ),
        "validation_files": validation_result.get("files", {}),
        "pipeline_files": (
            pipeline_result.get("files", {})
            if pipeline_ran
            else {}
        ),
        "validation_file_summary": validation_result.get("file_summary", {}),
        "pipeline_file_summary": (
            pipeline_result.get("file_summary", {})
            if pipeline_ran
            else {}
        ),
        "validation_health_status": validation_health.get("status"),
        "pipeline_health_status": (
            pipeline_health.get("status") if pipeline_ran else None
        ),
        "validation_health_recommendations": validation_health.get(
            "recommendations",
            [],
        ),
        "pipeline_health_recommendations": (
            pipeline_health.get("recommendations", [])
            if pipeline_ran
            else []
        ),
        "validation_summary": validation_operation_summary,
        "pipeline_summary": (
            pipeline_operation_summary if pipeline_ran else {}
        ),
        "can_enter_manual_backtest_pipeline": bool(
            validation_summary.get("can_enter_manual_backtest_pipeline")
        ),
        "can_enter_expected_value_research": (
            bool(
                pipeline_operation_summary.get(
                    "can_enter_expected_value_research"
                )
            )
            if pipeline_ran
            else False
        ),
        "can_enter_strategy_selection": (
            bool(
                pipeline_operation_summary.get(
                    "can_enter_strategy_selection"
                )
            )
            if pipeline_ran
            else False
        ),
        "backtest_id": (
            pipeline_operation_summary.get("backtest_id")
            or validation_summary.get("backtest_id")
            or normalization_summary.get("backtest_id")
        ),
        "project_name": validation_summary.get("project_name"),
        "backtest_name": validation_summary.get("backtest_name"),
        "placeholder_count": _safe_int(
            validation_summary.get("placeholder_count")
        ),
        "sensitive_field_count": _safe_int(
            validation_summary.get("sensitive_field_count")
        ),
        "validation_blocked_reasons": validation_payload.get(
            "blocked_reasons",
            [],
        ),
        "validation_warnings": validation_payload.get("warnings", []),
        "pipeline_blocked_reasons": (
            pipeline_payload.get("blocked_reasons", [])
            if pipeline_ran
            else []
        ),
        "pipeline_warnings": (
            pipeline_payload.get("warnings", []) if pipeline_ran else []
        ),
        "explicit_exclusions": _choose_explicit_exclusions(
            normalization_result,
            validation_result,
            pipeline_result,
        ),
    }


def _extract_validation(result: Mapping[str, Any]) -> dict[str, Any]:
    operation_result = result.get("operation_result")

    if isinstance(operation_result, Mapping):
        validation = operation_result.get("validation")

        if isinstance(validation, Mapping):
            return dict(validation)

    validation = result.get("validation")

    if isinstance(validation, Mapping):
        return dict(validation)

    return {}


def _extract_pipeline_result(result: Mapping[str, Any]) -> dict[str, Any]:
    operation_result = result.get("operation_result")

    if isinstance(operation_result, Mapping):
        pipeline_result = operation_result.get("pipeline_result")

        if isinstance(pipeline_result, Mapping):
            return dict(pipeline_result)

    pipeline_result = result.get("pipeline_result")

    if isinstance(pipeline_result, Mapping):
        return dict(pipeline_result)

    return {}


def _extract_operation_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    operation_result = result.get("operation_result")

    if not isinstance(operation_result, Mapping):
        return {}

    operation_record = operation_result.get("operation_record")

    if not isinstance(operation_record, Mapping):
        return {}

    summary = operation_record.get("summary")

    if isinstance(summary, Mapping):
        return dict(summary)

    return {}


def _extract_health_report(result: Mapping[str, Any]) -> dict[str, Any]:
    operation_result = result.get("operation_result")

    if not isinstance(operation_result, Mapping):
        return {}

    health_report = operation_result.get("health_report")

    if isinstance(health_report, Mapping):
        return dict(health_report)

    return {}


def _choose_explicit_exclusions(
    normalization_result: Mapping[str, Any],
    validation_result: Mapping[str, Any],
    pipeline_result: Mapping[str, Any],
) -> list[Any]:
    pipeline_exclusions = pipeline_result.get("explicit_exclusions")

    if isinstance(pipeline_exclusions, list) and pipeline_exclusions:
        return pipeline_exclusions

    validation_exclusions = validation_result.get("explicit_exclusions")

    if isinstance(validation_exclusions, list) and validation_exclusions:
        return validation_exclusions

    normalization_exclusions = normalization_result.get("explicit_exclusions")

    if isinstance(normalization_exclusions, list):
        return normalization_exclusions

    return []


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)

    return {}


def _safe_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0

    if isinstance(value, int):
        return value

    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

