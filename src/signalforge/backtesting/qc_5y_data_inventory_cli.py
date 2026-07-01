from __future__ import annotations

import argparse
import json
from pathlib import Path

from signalforge.backtesting.qc_5y_data_inventory import build_qc_5y_data_inventory


def _parse_expected_symbols(raw: str | None) -> list[str]:
    if not raw:
        return []

    return [
        item.strip().upper()
        for item in raw.split(",")
        if item.strip()
    ]


def _load_expected_symbols_file(path: str | None) -> list[str]:
    if not path:
        return []

    expected_path = Path(path)

    if not expected_path.exists():
        raise FileNotFoundError(f"expected symbols file does not exist: {expected_path}")

    text = expected_path.read_text(encoding="utf-8").strip()

    if not text:
        return []

    if expected_path.suffix.lower() == ".json":
        data = json.loads(text)

        if isinstance(data, list):
            return [str(item).strip().upper() for item in data if str(item).strip()]

        if isinstance(data, dict):
            for key in ["symbols", "universe", "tickers"]:
                value = data.get(key)
                if isinstance(value, list):
                    return [str(item).strip().upper() for item in value if str(item).strip()]

        raise ValueError("expected symbols JSON must be a list or contain symbols/universe/tickers")

    symbols: list[str] = []

    for line in text.splitlines():
        cleaned = line.strip()

        if not cleaned or cleaned.startswith("#"):
            continue

        cleaned = cleaned.replace("-", "").replace('"', "").replace("'", "").strip()

        if ":" in cleaned:
            continue

        if cleaned:
            symbols.append(cleaned.upper())

    return symbols


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build QuantConnect 5-year data inventory artifact."
    )

    parser.add_argument(
        "--source-root",
        required=True,
        help="Root folder containing QuantConnect pulled data/artifacts.",
    )

    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where inventory artifacts will be written.",
    )

    parser.add_argument(
        "--replay-start",
        default=None,
        help="Expected replay start date, e.g. 2021-06-01.",
    )

    parser.add_argument(
        "--replay-end",
        default=None,
        help="Expected replay end date, e.g. 2026-05-31.",
    )

    parser.add_argument(
        "--expected-symbols",
        default=None,
        help="Comma-separated expected symbols, e.g. SPY,QQQ,AAPL.",
    )

    parser.add_argument(
        "--expected-symbols-file",
        default=None,
        help="Optional JSON/text/yaml-ish file containing expected symbols.",
    )

    args = parser.parse_args()

    expected_symbols = []
    expected_symbols.extend(_parse_expected_symbols(args.expected_symbols))
    expected_symbols.extend(_load_expected_symbols_file(args.expected_symbols_file))

    artifact = build_qc_5y_data_inventory(
        source_root=args.source_root,
        output_dir=args.output_dir,
        replay_start=args.replay_start,
        replay_end=args.replay_end,
        expected_symbols=expected_symbols,
    )

    print(json.dumps({
        "adapter_type": artifact["adapter_type"],
        "artifact_type": artifact["artifact_type"],
        "contract": artifact["contract"],
        "is_ready": artifact["is_ready"],
        "readiness_state": artifact["readiness_state"],
        "blocker_count": artifact["blocker_count"],
        "blockers": artifact["blockers"],
        "warnings": artifact["warnings"],
        "file_summary": artifact["file_summary"],
        "coverage_summary": artifact["coverage_summary"],
    }, indent=2, sort_keys=True))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

