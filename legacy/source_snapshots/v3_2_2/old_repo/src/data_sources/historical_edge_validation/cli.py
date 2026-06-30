from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from src.signalforge.data_sources.historical_edge_validation.edge_validator import build_signalforge_historical_edge_validation
from src.signalforge.data_sources.historical_edge_validation.file_writer import write_historical_edge_validation_result
from src.signalforge.data_sources.quantconnect_replay_result_import_validator.validator import DEFAULT_RESULT_FILES


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure historical edge from validated compact QuantConnect replay result files."
    )
    parser.add_argument(
        "--quantconnect-replay-result-import-validation-source",
        required=True,
        help="Path to SignalForge QuantConnect replay result import validation JSON artifact.",
    )
    parser.add_argument(
        "--result-dir",
        required=True,
        help="Directory containing compact QuantConnect replay result JSON files.",
    )
    parser.add_argument("--output-dir", required=True, help="Directory for output artifacts.")
    parser.add_argument(
        "--result-files",
        default=",".join(DEFAULT_RESULT_FILES),
        help="Comma-separated replay result filenames. Defaults to the QuantConnect compact replay contract filenames.",
    )

    args = parser.parse_args(argv)

    import_validation_source = _read_json(args.quantconnect_replay_result_import_validation_source)
    result_file_names = _parse_result_files(args.result_files)
    replay_result_sources = _read_result_files(Path(args.result_dir), result_file_names)

    result = build_signalforge_historical_edge_validation(
        import_validation_source=import_validation_source,
        replay_result_sources=replay_result_sources,
    )

    summary = write_historical_edge_validation_result(result, args.output_dir)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0 if result.get("is_ready") else 1


def _read_json(path_text: str | Path) -> Any:
    path = Path(path_text)
    if not path.exists():
        raise SystemExit(f"input file does not exist: {path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _parse_result_files(value: str) -> list[str]:
    values: list[str] = []
    for part in str(value or "").split(","):
        text = part.strip()
        if text:
            values.append(text)
    return values or list(DEFAULT_RESULT_FILES)


def _read_result_files(result_dir: Path, result_file_names: Sequence[str]) -> dict[str, Any]:
    if not result_dir.exists():
        raise SystemExit(f"result directory does not exist: {result_dir}")
    results: dict[str, Any] = {}
    for filename in result_file_names:
        path = result_dir / filename
        if path.exists():
            results[filename] = json.loads(path.read_text(encoding="utf-8-sig"))
    return results


if __name__ == "__main__":
    raise SystemExit(main())
