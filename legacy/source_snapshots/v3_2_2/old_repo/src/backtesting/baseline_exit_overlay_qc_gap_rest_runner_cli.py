from __future__ import annotations

import argparse
import json

from .baseline_exit_overlay_qc_gap_rest_runner import build_runner


def main() -> int:
    parser = argparse.ArgumentParser(description="Run QC backtests to fill baseline exit overlay daily quote gaps.")
    parser.add_argument("--batch-manifest", required=True)
    parser.add_argument("--template", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--qc-project-file-name", default="main.py")
    parser.add_argument("--max-batches", type=int, default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--include-completed", action="store_true")
    parser.add_argument("--continue-on-failure", action="store_true")
    parser.add_argument("--poll-seconds", type=int, default=20)
    parser.add_argument("--compile-timeout-seconds", type=int, default=600)
    parser.add_argument("--backtest-timeout-seconds", type=int, default=3600)
    parser.add_argument("--execute", action="store_true", help="Actually mutate QC project file, compile, and launch backtests.")
    args = parser.parse_args()

    summary = build_runner(
        batch_manifest=args.batch_manifest,
        template=args.template,
        output_dir=args.output_dir,
        qc_project_file_name=args.qc_project_file_name,
        max_batches=args.max_batches,
        resume=args.resume,
        skip_completed=not args.include_completed,
        stop_on_failure=not args.continue_on_failure,
        poll_seconds=args.poll_seconds,
        compile_timeout_seconds=args.compile_timeout_seconds,
        backtest_timeout_seconds=args.backtest_timeout_seconds,
        execute=args.execute,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary.get("is_ready") else 1


if __name__ == "__main__":
    raise SystemExit(main())
