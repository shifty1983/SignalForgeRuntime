from __future__ import annotations

import argparse
import json

from src.data_sources.quantconnect_cloud_api.client import (
    QuantConnectCloudClient,
    QuantConnectCloudCredentials,
    QuantConnectCloudApiError,
    redact_quantconnect_payload,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Minimal QuantConnect Cloud API client checks for SignalForge."
    )
    parser.add_argument(
        "--operation",
        choices=["authenticate", "list-object-store"],
        default="authenticate",
    )
    parser.add_argument("--object-store-path", default="")
    args = parser.parse_args()

    try:
        credentials = QuantConnectCloudCredentials.from_env()
        client = QuantConnectCloudClient(credentials)

        if args.operation == "authenticate":
            result = client.authenticate()
        elif args.operation == "list-object-store":
            result = client.list_object_store_files(path=args.object_store_path)
        else:
            raise QuantConnectCloudApiError(f"Unsupported operation: {args.operation}")

        print(json.dumps(redact_quantconnect_payload(result), indent=2, sort_keys=True))
        return 0

    except QuantConnectCloudApiError as exc:
        print(json.dumps({"success": False, "error": str(exc)}, indent=2, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
