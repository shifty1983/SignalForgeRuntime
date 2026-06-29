from __future__ import annotations

import argparse
import json

from src.backtesting.research_build_report import (
    build_research_build_report,
    write_research_build_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a deterministic SignalForge research build report."
    )
    parser.add_argument(
        "--replay-result-dir",
        required=True,
        help="Replay result artifact directory.",
    )
    parser.add_argument(
        "--research-batch",
        default=None,
        help="Optional explicit research batch JSON/JSONL path. If omitted, the CLI tries to infer it.",
    )
    parser.add_argument(
        "--research-output",
        default=None,
        help="Optional explicit research output JSON/JSONL path. If omitted, the CLI tries to infer it.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Output directory for the research build report JSON and Markdown files.",
    )
    parser.add_argument(
        "--target-max-batch-bytes",
        type=int,
        default=10 * 1024 * 1024,
        help="Batch-size target used for utilization and expansion recommendations.",
    )
    parser.add_argument(
        "--object-store-size-kb",
        type=float,
        default=None,
        help="Optional QuantConnect Object Store source footprint in KB.",
    )

    args = parser.parse_args()

    report = build_research_build_report(
        replay_result_dir=args.replay_result_dir,
        research_batch_path=args.research_batch,
        research_output_path=args.research_output,
        target_max_batch_bytes=args.target_max_batch_bytes,
        object_store_size_kb=args.object_store_size_kb,
    )
    written = write_research_build_report(report, args.output_dir)

    cli_result = {
        "artifact_type": "signalforge_research_build_report_cli_result",
        "status": report["status"],
        "is_ready": report["is_ready"],
        "live_readiness_state": report["live_readiness_state"],
        "blocked_reasons": report["blocked_reasons"],
        "warnings": report["warnings"],
        "output_files": written,
    }

    print(json.dumps(cli_result, indent=2, sort_keys=True))

    return 0 if report["status"] != "blocked" else 2


if __name__ == "__main__":
    raise SystemExit(main())
