from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import requests


BASE_URL = "https://www.quantconnect.com/api/v2/"


def get_headers(user_id: str, api_token: str) -> dict[str, str]:
    timestamp = str(int(time.time()))
    hashed_token = hashlib.sha256(f"{api_token}:{timestamp}".encode("utf-8")).hexdigest()
    authentication = base64.b64encode(f"{user_id}:{hashed_token}".encode("utf-8")).decode("ascii")
    return {
        "Authorization": f"Basic {authentication}",
        "Timestamp": timestamp,
    }


def qc_post(endpoint: str, payload: dict[str, Any], *, user_id: str, api_token: str) -> dict[str, Any]:
    response = requests.post(
        BASE_URL + endpoint.lstrip("/"),
        headers=get_headers(user_id, api_token),
        json=payload,
        timeout=120,
    )
    response.raise_for_status()
    result = response.json()

    if not result.get("success", False):
        raise RuntimeError(f"QC API call failed: endpoint={endpoint} result={result}")

    return result


def list_object_store(
    *,
    organization_id: str,
    user_id: str,
    api_token: str,
    path: str,
) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    page = 0

    while True:
        payload = {
            "organizationId": organization_id,
            "path": path,
            "page": page,
        }

        result = qc_post("/object/list", payload, user_id=user_id, api_token=api_token)
        page_objects = result.get("objects") or []
        objects.extend(page_objects)

        total_pages = result.get("totalPages")
        current_page = result.get("page", page)

        if total_pages is None:
            break

        if int(current_page) + 1 >= int(total_pages):
            break

        page += 1

    return objects


def read_object_store_key(
    key: str,
    *,
    organization_id: str,
    user_id: str,
    api_token: str,
) -> str:
    payload = {
        "organizationId": organization_id,
        "keys": [key],
    }

    result = qc_post("/object/get", payload, user_id=user_id, api_token=api_token)

    # QC has returned different shapes over time. Handle the common possibilities.
    candidates = []

    if isinstance(result.get("objects"), list):
        candidates.extend(result["objects"])

    if isinstance(result.get("files"), list):
        candidates.extend(result["files"])

    candidates.append(result)

    for obj in candidates:
        if not isinstance(obj, dict):
            continue

        for field in ["objectData", "data", "content", "value", "text"]:
            value = obj.get(field)
            if value is None:
                continue
            if isinstance(value, bytes):
                return value.decode("utf-8")
            return str(value)

        url = obj.get("url")
        if url:
            download = requests.get(url, timeout=120)
            download.raise_for_status()
            return download.content.decode("utf-8")

    raise RuntimeError(f"Could not extract object text for key={key}. Result keys={list(result.keys())}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-export", required=True)
    parser.add_argument("--path", default="")
    parser.add_argument("--include-regex", default=None)
    parser.add_argument("--exclude-regex", default=r"(canonical|research_export|objectstore_export|decoded|manifest|failure)")
    parser.add_argument("--max-keys", type=int, default=0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    user_id = os.environ.get("QC_USER_ID")
    api_token = os.environ.get("QC_API_TOKEN")
    organization_id = os.environ.get("QC_ORGANIZATION_ID")

    if not user_id:
        raise RuntimeError("Set QC_USER_ID")
    if not api_token:
        raise RuntimeError("Set QC_API_TOKEN")
    if not organization_id:
        raise RuntimeError("Set QC_ORGANIZATION_ID")

    include_pattern = args.include_regex or re.escape(args.run_id)
    include_re = re.compile(include_pattern, re.IGNORECASE)
    exclude_re = re.compile(args.exclude_regex, re.IGNORECASE) if args.exclude_regex else None

    output_path = Path(args.output_export)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    objects = list_object_store(
        organization_id=organization_id,
        user_id=user_id,
        api_token=api_token,
        path=args.path,
    )

    keys = []
    for obj in objects:
        if not isinstance(obj, dict):
            continue

        if obj.get("folder") is True:
            continue

        key = str(obj.get("key") or "")
        if not key:
            continue

        if not include_re.search(key):
            continue

        if exclude_re and exclude_re.search(key):
            continue

        keys.append(key)

    keys = sorted(set(keys))

    if args.max_keys and args.max_keys > 0:
        keys = keys[: args.max_keys]

    summary = {
        "adapter_type": "qc_objectstore_v2_export_downloader",
        "artifact_type": "signalforge_qc_objectstore_v2_export_download_summary",
        "is_ready": len(keys) > 0,
        "run_id": args.run_id,
        "listed_object_count": len(objects),
        "matched_key_count": len(keys),
        "output_export": str(output_path),
        "sample_keys": keys[:10],
    }

    print(json.dumps(summary, indent=2))

    if not keys:
        return 1

    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for index, key in enumerate(keys, start=1):
            print(f"downloading {index}/{len(keys)} {key}")
            text = read_object_store_key(
                key,
                organization_id=organization_id,
                user_id=user_id,
                api_token=api_token,
            )
            handle.write(json.dumps({"key": key, "text": text}, sort_keys=True) + "\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
