from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .rest_client import QuantConnectCredentials, QuantConnectRestClient


def _credentials_from_env() -> QuantConnectCredentials:
    user_id = os.environ.get("QUANTCONNECT_USER_ID", "").strip()
    api_token = os.environ.get("QUANTCONNECT_API_TOKEN", "").strip()
    organization_id = os.environ.get("QUANTCONNECT_ORGANIZATION_ID", "").strip()
    if not user_id or not api_token:
        raise SystemExit("Set QUANTCONNECT_USER_ID and QUANTCONNECT_API_TOKEN before using the REST CLI.")
    return QuantConnectCredentials(user_id=user_id, api_token=api_token, organization_id=organization_id or None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="QuantConnect REST Object Store helper for SignalForge data pulls.")
    parser.add_argument("--list", action="store_true", help="List object store keys.")
    parser.add_argument("--path", default="", help="Object Store path for --list.")
    parser.add_argument("--get", nargs="*", default=None, help="Object Store keys to retrieve.")
    parser.add_argument("--output", required=True, help="Output JSON path.")
    args = parser.parse_args(argv)

    client = QuantConnectRestClient(_credentials_from_env())
    if args.list:
        payload = client.list_object_store(path=args.path)
    elif args.get is not None:
        payload = client.get_object_store(keys=list(args.get))
    else:
        raise SystemExit("Pass --list or --get.")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(str(output))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
