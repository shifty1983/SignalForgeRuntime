# src/backtesting/historical_records_file_final_review_cli.py

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.backtesting.historical_records_file_final_review_runner import (
    run_historical_records_file_final_review,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        forward_windows = _parse_int_csv(args.forward_windows, argument_name="forward-windows")
        neutral_bands = _parse_float_csv(args.neutral_bands, argument_name="neutral-bands")

        candidate_read_options = _parse_json_mapping(
            args.candidate_read_options_json,
            argument_name="candidate-read-options-json",
        )
        price_read_options = _parse_json_mapping(
            args.price_read_options_json,
            argument_name="price-read-options-json",
        )
        candidate_field_map = _parse_json_mapping(
            args.candidate_field_map_json,
            argument_name="candidate-field-map-json",
        )
        price_field_map = _parse_json_mapping(
            args.price_field_map_json,
            argument_name="price-field-map-json",
        )
        metadata = _parse_json_mapping(args.metadata_json, argument_name="metadata-json")
    except ValueError as error:
        print(json.dumps({"error": str(error)}, sort_keys=True), file=sys.stderr)
        return 2

    result = run_historical_records_file_final_review(
        args.candidate_file,
        args.price_file,
        candidate_format=args.candidate_format,
        price_format=args.price_format,
        candidate_read_options=candidate_read_options,
        price_read_options=price_read_options,
        forward_windows=forward_windows,
        neutral_bands=neutral_bands,
        candidate_field_map=candidate_field_map,
        price_field_map=price_field_map,
        operation_name=args.operation_name,
        actual_final_review_operation_name=args.actual_final_review_operation_name,
        actual_validation_operation_name=args.actual_validation_operation_name,
        adapter_operation_name=args.adapter_operation_name,
        validation_operation_name=args.validation_operation_name,
        promotion_operation_name=args.promotion_operation_name,
        summary_export_name=args.summary_export_name,
        review_queue_operation_name=args.review_queue_operation_name,
        review_snapshot_name=args.review_snapshot_name,
        priority_operation_name=args.priority_operation_name,
        priority_report_name=args.priority_report_name,
        handoff_operation_name=args.handoff_operation_name,
        handoff_bundle_name=args.handoff_bundle_name,
        planning_operation_name=args.planning_operation_name,
        planning_queue_name=args.planning_queue_name,
        plan_snapshot_name=args.plan_snapshot_name,
        plan_export_operation_name=args.plan_export_operation_name,
        plan_export_name=args.plan_export_name,
        review_artifact_operation_name=args.review_artifact_operation_name,
        review_artifact_name=args.review_artifact_name,
        final_review_pipeline_operation_name=args.final_review_pipeline_operation_name,
        final_review_pipeline_name=args.final_review_pipeline_name,
        final_summary_operation_name=args.final_summary_operation_name,
        final_summary_name=args.final_summary_name,
        final_export_operation_name=args.final_export_operation_name,
        final_export_name=args.final_export_name,
        metadata=metadata,
        adapter_log_path=args.adapter_log_path,
        final_summary_log_path=args.final_summary_log_path,
        final_export_log_path=args.final_export_log_path,
        final_pipeline_operation_log_path=args.final_pipeline_operation_log_path,
    )

    _write_result(result, output_file=args.output_file)

    return 1 if result.get("is_blocked") is True else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the file-based actual historical final review pipeline from "
            "candidate and price files."
        )
    )

    parser.add_argument("--candidate-file", required=True)
    parser.add_argument("--price-file", required=True)

    parser.add_argument("--candidate-format", default=None)
    parser.add_argument("--price-format", default=None)

    parser.add_argument("--candidate-read-options-json", default=None)
    parser.add_argument("--price-read-options-json", default=None)

    parser.add_argument("--candidate-field-map-json", default=None)
    parser.add_argument("--price-field-map-json", default=None)

    parser.add_argument("--forward-windows", default="1")
    parser.add_argument("--neutral-bands", default="0.01")

    parser.add_argument(
        "--operation-name",
        default="historical_records_file_final_review_runner",
    )

    parser.add_argument("--actual-final-review-operation-name", default=None)
    parser.add_argument("--actual-validation-operation-name", default=None)
    parser.add_argument("--adapter-operation-name", default=None)
    parser.add_argument("--validation-operation-name", default=None)
    parser.add_argument("--promotion-operation-name", default=None)
    parser.add_argument("--summary-export-name", default=None)
    parser.add_argument("--review-queue-operation-name", default=None)
    parser.add_argument("--review-snapshot-name", default=None)
    parser.add_argument("--priority-operation-name", default=None)
    parser.add_argument("--priority-report-name", default=None)
    parser.add_argument("--handoff-operation-name", default=None)
    parser.add_argument("--handoff-bundle-name", default=None)
    parser.add_argument("--planning-operation-name", default=None)
    parser.add_argument("--planning-queue-name", default=None)
    parser.add_argument("--plan-snapshot-name", default=None)
    parser.add_argument("--plan-export-operation-name", default=None)
    parser.add_argument("--plan-export-name", default=None)
    parser.add_argument("--review-artifact-operation-name", default=None)
    parser.add_argument("--review-artifact-name", default=None)
    parser.add_argument("--final-review-pipeline-operation-name", default=None)
    parser.add_argument("--final-review-pipeline-name", default=None)
    parser.add_argument("--final-summary-operation-name", default=None)
    parser.add_argument("--final-summary-name", default=None)
    parser.add_argument("--final-export-operation-name", default=None)
    parser.add_argument("--final-export-name", default=None)

    parser.add_argument("--metadata-json", default=None)

    parser.add_argument("--adapter-log-path", default=None)
    parser.add_argument("--final-summary-log-path", default=None)
    parser.add_argument("--final-export-log-path", default=None)
    parser.add_argument("--final-pipeline-operation-log-path", default=None)

    parser.add_argument(
        "--output-file",
        default=None,
        help="Optional JSON output path. If omitted, JSON is printed to stdout.",
    )

    return parser


def _parse_int_csv(value: str, *, argument_name: str) -> tuple[int, ...]:
    parsed_values: list[int] = []

    for item in value.split(","):
        text = item.strip()
        if not text:
            continue

        try:
            parsed_value = int(text)
        except ValueError as error:
            raise ValueError(f"{argument_name} must be comma-separated integers") from error

        if parsed_value <= 0:
            raise ValueError(f"{argument_name} values must be positive integers")

        parsed_values.append(parsed_value)

    if not parsed_values:
        raise ValueError(f"{argument_name} must contain at least one integer")

    return tuple(parsed_values)


def _parse_float_csv(value: str, *, argument_name: str) -> tuple[float, ...]:
    parsed_values: list[float] = []

    for item in value.split(","):
        text = item.strip()
        if not text:
            continue

        try:
            parsed_value = float(text)
        except ValueError as error:
            raise ValueError(f"{argument_name} must be comma-separated numbers") from error

        parsed_values.append(parsed_value)

    if not parsed_values:
        raise ValueError(f"{argument_name} must contain at least one number")

    return tuple(parsed_values)


def _parse_json_mapping(
    value: str | None,
    *,
    argument_name: str,
) -> dict[str, Any] | None:
    if value is None:
        return None

    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError(f"{argument_name} must be valid JSON") from error

    if not isinstance(parsed, Mapping):
        raise ValueError(f"{argument_name} must decode to a JSON object")

    return dict(parsed)


def _write_result(result: Mapping[str, Any], *, output_file: str | None) -> None:
    encoded_result = json.dumps(result, sort_keys=True, indent=2, default=str)

    if output_file is None:
        print(encoded_result)
        return

    path = Path(output_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{encoded_result}\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
