from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from src.signalforge.data_sources.quantconnect_cloud_replay_batch_runner.file_writer import (
    write_signalforge_quantconnect_cloud_replay_batch_runner_plan,
)
from src.signalforge.data_sources.quantconnect_cloud_replay_batch_runner.runner import (
    build_signalforge_quantconnect_cloud_replay_batch_runner_plan,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run or plan QuantConnect Cloud replay batch operations."
    )
    parser.add_argument("--scaleout-plan", default="")
    parser.add_argument("--backtest-execution-source", default="")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--mode",
        choices=[
            "dry_run",
            "execute_compile_only",
            "execute_backtest_only",
            "download_object_store_only",
        ],
        default="dry_run",
    )
    parser.add_argument("--quantconnect-project-id", default=os.environ.get("QC_PROJECT_ID", ""))
    parser.add_argument("--quantconnect-organization-id", default=os.environ.get("QC_ORGANIZATION_ID", ""))
    parser.add_argument("--quantconnect-project-file-name", default="main.py")
    parser.add_argument("--compile-batch-limit", type=int, default=1)
    parser.add_argument("--backtest-batch-limit", type=int, default=1)
    parser.add_argument("--download-batch-limit", type=int, default=1)
    parser.add_argument(
        "--delete-object-store-after-local-validation",
        action="store_true",
        help="Plan delete operations after local six-file validation. Dry-run only for now.",
    )

    args = parser.parse_args()

    if args.mode == "download_object_store_only":
        if not args.backtest_execution_source:
            raise SystemExit("--backtest-execution-source is required for download_object_store_only")

        backtest_execution = _read_json(Path(args.backtest_execution_source))

        from src.signalforge.data_sources.quantconnect_cloud_api.client import (
            QuantConnectCloudClient,
            QuantConnectCloudCredentials,
        )
        from src.signalforge.data_sources.quantconnect_cloud_replay_batch_runner.object_store_downloader import (
            execute_signalforge_quantconnect_cloud_object_store_download_only,
        )
        from src.signalforge.data_sources.quantconnect_cloud_replay_batch_runner.object_store_download_file_writer import (
            write_signalforge_quantconnect_cloud_object_store_download,
        )

        credentials = QuantConnectCloudCredentials.from_env()
        client = QuantConnectCloudClient(credentials)

        result = execute_signalforge_quantconnect_cloud_object_store_download_only(
            backtest_execution,
            client=client,
            quantconnect_organization_id=args.quantconnect_organization_id,
            output_dir=args.output_dir,
            batch_limit=args.download_batch_limit,
        )

        summary = write_signalforge_quantconnect_cloud_object_store_download(
            result,
            args.output_dir,
        )

        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0 if result.get("is_ready") else 1

    if not args.scaleout_plan:
        raise SystemExit("--scaleout-plan is required for this mode")

    scaleout_plan = _read_json(Path(args.scaleout_plan))

    if args.mode == "dry_run":
        result = build_signalforge_quantconnect_cloud_replay_batch_runner_plan(
            scaleout_plan,
            quantconnect_project_id=args.quantconnect_project_id,
            quantconnect_organization_id=args.quantconnect_organization_id,
            output_dir=args.output_dir,
            mode=args.mode,
            quantconnect_project_file_name=args.quantconnect_project_file_name,
            delete_object_store_after_local_validation=args.delete_object_store_after_local_validation,
        )

        summary = write_signalforge_quantconnect_cloud_replay_batch_runner_plan(
            result,
            args.output_dir,
        )

        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0 if result.get("is_ready") else 1

    from src.signalforge.data_sources.quantconnect_cloud_api.client import (
        QuantConnectCloudClient,
        QuantConnectCloudCredentials,
    )

    credentials = QuantConnectCloudCredentials.from_env()
    client = QuantConnectCloudClient(credentials)

    if args.mode == "execute_compile_only":
        from src.signalforge.data_sources.quantconnect_cloud_replay_batch_runner.compile_executor import (
            execute_signalforge_quantconnect_cloud_replay_compile_only,
        )
        from src.signalforge.data_sources.quantconnect_cloud_replay_batch_runner.compile_file_writer import (
            write_signalforge_quantconnect_cloud_replay_compile_execution,
        )

        result = execute_signalforge_quantconnect_cloud_replay_compile_only(
            scaleout_plan,
            client=client,
            quantconnect_project_id=args.quantconnect_project_id,
            quantconnect_organization_id=args.quantconnect_organization_id,
            output_dir=args.output_dir,
            quantconnect_project_file_name=args.quantconnect_project_file_name,
            batch_limit=args.compile_batch_limit,
        )

        summary = write_signalforge_quantconnect_cloud_replay_compile_execution(
            result,
            args.output_dir,
        )

        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0 if result.get("is_ready") else 1

    from src.signalforge.data_sources.quantconnect_cloud_replay_batch_runner.backtest_executor import (
        execute_signalforge_quantconnect_cloud_replay_backtest_only,
    )
    from src.signalforge.data_sources.quantconnect_cloud_replay_batch_runner.backtest_file_writer import (
        write_signalforge_quantconnect_cloud_replay_backtest_execution,
    )

    result = execute_signalforge_quantconnect_cloud_replay_backtest_only(
        scaleout_plan,
        client=client,
        quantconnect_project_id=args.quantconnect_project_id,
        quantconnect_organization_id=args.quantconnect_organization_id,
        output_dir=args.output_dir,
        quantconnect_project_file_name=args.quantconnect_project_file_name,
        batch_limit=args.backtest_batch_limit,
    )

    summary = write_signalforge_quantconnect_cloud_replay_backtest_execution(
        result,
        args.output_dir,
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if result.get("is_ready") else 1


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"source does not exist: {path}")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise SystemExit(f"source is not a JSON object: {path}")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
