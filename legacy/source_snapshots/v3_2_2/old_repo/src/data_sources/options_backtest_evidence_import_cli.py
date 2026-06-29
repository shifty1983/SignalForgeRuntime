from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, Sequence

from src.data_sources.options_backtest_evidence_import_file_writer import (
    write_signalforge_options_backtest_evidence_import_files,
)


CLI_SUMMARY_SCHEMA_VERSION = "signalforge_options_backtest_evidence_import_cli_summary.v1"
DEFAULT_CLI_SUMMARY_FILENAME = "signalforge_options_backtest_evidence_import_cli_summary.json"

WriterFunction = Callable[..., dict[str, Any]]


def main(
    argv: Sequence[str] | None = None,
    *,
    writer: WriterFunction = write_signalforge_options_backtest_evidence_import_files,
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

    writer_result = writer(source, output_dir=output_path)

    cli_summary_path = output_path / DEFAULT_CLI_SUMMARY_FILENAME
    cli_summary = _build_cli_summary(
        writer_result=writer_result,
        summary_path=cli_summary_path,
    )
    _write_json(cli_summary_path, cli_summary)

    print(json.dumps(cli_summary, indent=2, sort_keys=True))

    return 1 if cli_summary["status"] == "blocked" else 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Normalize a local QuantConnect/manual options backtest result into "
            "SignalForge backtest evidence. This command reads local JSON only. "
            "It does not call QuantConnect, call brokers, route orders, submit "
            "orders, model fills, perform live execution, model slippage, create "
            "automatic close/roll/defense orders, change strategy logic "
            "automatically, update parameters automatically, or pause strategies "
            "automatically."
        )
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Path to local JSON source containing quantconnect_result, backtest_result, payload, or flat fields.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where options backtest evidence import artifacts should be written.",
    )
    return parser


def _read_json(path: str) -> Any:
    with Path(path).open(encoding="utf-8") as file:
        return json.load(file)


def _build_cli_summary(
    *,
    writer_result: dict[str, Any],
    summary_path: Path,
) -> dict[str, Any]:
    summary = writer_result.get("summary", {})
    import_result = writer_result.get("import_result", {})

    return {
        "schema_version": CLI_SUMMARY_SCHEMA_VERSION,
        "operation_type": "signalforge_options_backtest_evidence_import_cli",
        "status": writer_result.get("status", "needs_review"),
        "output_dir": writer_result.get("output_dir"),
        "summary_path": str(summary_path),
        "files": writer_result.get("files", {}),
        "file_summary": writer_result.get("file_summary", {}),
        "contract": summary.get("contract"),
        "adapter_type": summary.get("adapter_type"),
        "source_kind": summary.get("source_kind"),
        "validation_status": summary.get("validation_status"),
        "normalized_payload_summary": summary.get("normalized_payload_summary", {}),
        "backtest_summary": summary.get("backtest_summary", {}),
        "missing_required_field_count": summary.get("missing_required_field_count"),
        "missing_preferred_field_count": summary.get("missing_preferred_field_count"),
        "blocker_count": summary.get("blocker_count"),
        "warning_count": summary.get("warning_count"),
        "requires_manual_approval": import_result.get("requires_manual_approval") is True,
        "order_intent": import_result.get("order_intent"),
        "broker_order_id": import_result.get("broker_order_id"),
        "automatic_action": import_result.get("automatic_action"),
        "automatic_strategy_change": import_result.get("automatic_strategy_change"),
        "automatic_parameter_change": import_result.get("automatic_parameter_change"),
        "automatic_pause_action": import_result.get("automatic_pause_action"),
        "explicit_exclusions": list(writer_result.get("explicit_exclusions", [])),
    }


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())

