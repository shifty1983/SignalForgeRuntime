from __future__ import annotations

import argparse
import base64
import json
import os
import time
from hashlib import sha256
from typing import Any

import requests


BASE_URL = "https://www.quantconnect.com/api/v2"


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def get_headers() -> dict[str, str]:
    user_id = require_env("QC_USER_ID")
    api_token = require_env("QC_API_TOKEN")

    timestamp = f"{int(time.time())}"
    token_hash = sha256(f"{api_token}:{timestamp}".encode("utf-8")).hexdigest()
    auth = base64.b64encode(f"{user_id}:{token_hash}".encode("utf-8")).decode("ascii")

    return {
        "Authorization": f"Basic {auth}",
        "Timestamp": timestamp,
    }


def qc_post(endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = requests.post(
        f"{BASE_URL}{endpoint}",
        headers=get_headers(),
        json=payload,
        timeout=120,
    )

    data = response.json()

    if response.status_code >= 400 or data.get("success") is False:
        raise RuntimeError(f"QC API failure from {endpoint}: {data}")

    return data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", type=int, default=int(os.environ.get("QC_PROJECT_ID", "0")))
    parser.add_argument("--compile-id", required=True)
    parser.add_argument("--backtest-name", required=True)
    args = parser.parse_args()

    if not args.project_id:
        raise RuntimeError("Provide --project-id or set QC_PROJECT_ID.")

    result = qc_post(
        "/backtests/create",
        {
            "projectId": args.project_id,
            "compileId": args.compile_id,
            "backtestName": args.backtest_name,
        },
    )

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
