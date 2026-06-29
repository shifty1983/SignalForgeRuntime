from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol

import requests


DEFAULT_BASE_URL = "https://www.quantconnect.com/api/v2"


class QuantConnectCloudApiError(RuntimeError):
    """Raised when QuantConnect Cloud API returns an error response."""


class SupportsPostGet(Protocol):
    def post(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        json: Mapping[str, Any] | None = None,
        data: Mapping[str, Any] | None = None,
        files: Mapping[str, Any] | None = None,
        timeout: int | float | None = None,
    ) -> Any:
        ...

    def get(
        self,
        url: str,
        *,
        timeout: int | float | None = None,
    ) -> Any:
        ...


@dataclass(frozen=True)
class QuantConnectCloudCredentials:
    user_id: str
    api_token: str
    organization_id: str | None = None

    @classmethod
    def from_env(cls) -> "QuantConnectCloudCredentials":
        user_id = os.environ.get("QC_USER_ID", "").strip()
        api_token = os.environ.get("QC_API_TOKEN", "").strip()
        organization_id = os.environ.get("QC_ORGANIZATION_ID", "").strip() or None

        missing = []
        if not user_id:
            missing.append("QC_USER_ID")
        if not api_token:
            missing.append("QC_API_TOKEN")

        if missing:
            raise QuantConnectCloudApiError(
                f"Missing QuantConnect API environment variables: {', '.join(missing)}"
            )

        return cls(
            user_id=user_id,
            api_token=api_token,
            organization_id=organization_id,
        )


class QuantConnectCloudClient:
    def __init__(
        self,
        credentials: QuantConnectCloudCredentials,
        *,
        base_url: str = DEFAULT_BASE_URL,
        session: SupportsPostGet | None = None,
        timeout_seconds: int = 180,
        clock: Any = None,
    ) -> None:
        self.credentials = credentials
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self.timeout_seconds = timeout_seconds
        self.clock = clock or time.time

    def authenticate(self) -> dict[str, Any]:
        return self._post_json("/authenticate", {})

    def read_project_files(
        self,
        *,
        project_id: int,
        include_libraries: bool = True,
    ) -> dict[str, Any]:
        return self._post_json(
            "/files/read",
            {
                "projectId": int(project_id),
                "includeLibraries": bool(include_libraries),
            },
        )

    def create_project_file(
        self,
        *,
        project_id: int,
        name: str,
        content: str,
        code_source_id: str = "SignalForge Cloud Replay",
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "projectId": int(project_id),
            "name": name,
            "content": content,
            "codeSourceId": code_source_id,
        }
        return self._post_json("/files/create", payload)

    def update_project_file(
        self,
        *,
        project_id: int,
        name: str,
        content: str | None = None,
        new_name: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "projectId": int(project_id),
            "name": name,
        }
        if content is not None:
            payload["content"] = content
        if new_name is not None:
            payload["newName"] = new_name

        return self._post_json("/files/update", payload)

    def upsert_project_file(
        self,
        *,
        project_id: int,
        name: str,
        content: str,
        code_source_id: str = "SignalForge Cloud Replay",
    ) -> dict[str, Any]:
        files_result = self.read_project_files(project_id=project_id, include_libraries=False)
        files = files_result.get("files", [])
        existing_names = {
            str(file.get("name"))
            for file in files
            if isinstance(file, Mapping) and file.get("name") is not None
        }

        if name in existing_names:
            return self.update_project_file(
                project_id=project_id,
                name=name,
                content=content,
            )

        return self.create_project_file(
            project_id=project_id,
            name=name,
            content=content,
            code_source_id=code_source_id,
        )

    def create_compile(self, *, project_id: int) -> dict[str, Any]:
        return self._post_json("/compile/create", {"projectId": int(project_id)})

    def read_compile(self, *, project_id: int, compile_id: str) -> dict[str, Any]:
        return self._post_json(
            "/compile/read",
            {
                "projectId": int(project_id),
                "compileId": compile_id,
            },
        )

    def wait_for_compile(
        self,
        *,
        project_id: int,
        compile_id: str,
        poll_seconds: float = 5.0,
        timeout_seconds: float = 300.0,
    ) -> dict[str, Any]:
        start = float(self.clock())
        last_result: dict[str, Any] = {}

        while float(self.clock()) - start <= timeout_seconds:
            last_result = self.read_compile(project_id=project_id, compile_id=compile_id)
            state = str(last_result.get("state") or "")

            if state in {"BuildSuccess", "BuildError"}:
                return last_result

            time.sleep(poll_seconds)

        raise QuantConnectCloudApiError(
            f"Timed out waiting for QuantConnect compile result: compile_id={compile_id}"
        )

    def create_backtest(
        self,
        *,
        project_id: int,
        compile_id: str,
        backtest_name: str,
        parameters: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "projectId": int(project_id),
            "compileId": compile_id,
            "backtestName": backtest_name,
        }
        if parameters:
            payload["parameters"] = dict(parameters)

        return self._post_json("/backtests/create", payload)

    def read_backtest(self, *, project_id: int, backtest_id: str) -> dict[str, Any]:
        return self._post_json(
            "/backtests/read",
            {
                "projectId": int(project_id),
                "backtestId": backtest_id,
            },
        )

    def wait_for_backtest(
        self,
        *,
        project_id: int,
        backtest_id: str,
        poll_seconds: float = 10.0,
        timeout_seconds: float = 3600.0,
    ) -> dict[str, Any]:
        start = float(self.clock())
        last_result: dict[str, Any] = {}

        while float(self.clock()) - start <= timeout_seconds:
            last_result = self.read_backtest(project_id=project_id, backtest_id=backtest_id)
            backtest = last_result.get("backtest", {})
            if isinstance(backtest, Mapping) and bool(backtest.get("completed")):
                return last_result

            time.sleep(poll_seconds)

        raise QuantConnectCloudApiError(
            f"Timed out waiting for QuantConnect backtest result: backtest_id={backtest_id}"
        )

    def list_object_store_files(
        self,
        *,
        organization_id: str | None = None,
        path: str = "",
    ) -> dict[str, Any]:
        return self._post_json(
            "/object/list",
            {
                "organizationId": self._organization_id(organization_id),
                "path": path,
            },
        )

    def get_object_store_file(
        self,
        *,
        key: str,
        organization_id: str | None = None,
    ) -> dict[str, Any]:
        return self._post_json(
            "/object/get",
            {
                "organizationId": self._organization_id(organization_id),
                "keys": [key],
            },
        )

    def get_object_store_metadata(
        self,
        *,
        key: str,
        organization_id: str | None = None,
    ) -> dict[str, Any]:
        return self._post_json(
            "/object/properties",
            {
                "organizationId": self._organization_id(organization_id),
                "key": key,
            },
        )

    def delete_object_store_file(
        self,
        *,
        key: str,
        organization_id: str | None = None,
    ) -> dict[str, Any]:
        return self._post_json(
            "/object/delete",
            {
                "organizationId": self._organization_id(organization_id),
                "key": key,
            },
        )

    def download_object_store_file(
        self,
        *,
        key: str,
        output_path: str | Path,
        organization_id: str | None = None,
    ) -> dict[str, Any]:
        result = self.get_object_store_file(
            key=key,
            organization_id=organization_id,
        )

        url = str(result.get("url") or "")
        if not url:
            raise QuantConnectCloudApiError(f"Object Store get response did not include URL: key={key}")

        response = self.session.get(url, timeout=self.timeout_seconds)
        self._raise_for_http(response)

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        content = getattr(response, "content", None)
        if content is None:
            content = str(getattr(response, "text", "")).encode("utf-8")
        path.write_bytes(content)

        return {
            "success": True,
            "key": key,
            "output_path": str(path),
            "downloaded_bytes": path.stat().st_size,
            "object_get_response": result,
        }

    def _post_json(self, endpoint: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        response = self.session.post(
            f"{self.base_url}{endpoint}",
            headers=self._headers(),
            json=dict(payload),
            timeout=self.timeout_seconds,
        )
        self._raise_for_http(response)

        try:
            result = response.json()
        except Exception as exc:
            raise QuantConnectCloudApiError(f"QuantConnect API response was not JSON: {endpoint}") from exc

        if not isinstance(result, dict):
            raise QuantConnectCloudApiError(f"QuantConnect API response was not an object: {endpoint}")

        if result.get("success") is False:
            errors = result.get("errors", [])
            raise QuantConnectCloudApiError(
                f"QuantConnect API request failed: endpoint={endpoint}, errors={errors}"
            )

        return result

    def _headers(self) -> dict[str, str]:
        timestamp = f"{int(self.clock())}"
        time_stamped_token = f"{self.credentials.api_token}:{timestamp}".encode("utf-8")
        hashed_token = hashlib.sha256(time_stamped_token).hexdigest()
        authentication = f"{self.credentials.user_id}:{hashed_token}".encode("utf-8")
        encoded_authentication = base64.b64encode(authentication).decode("ascii")

        return {
            "Authorization": f"Basic {encoded_authentication}",
            "Timestamp": timestamp,
        }

    def _organization_id(self, organization_id: str | None) -> str:
        resolved = organization_id or self.credentials.organization_id
        if not resolved:
            raise QuantConnectCloudApiError(
                "organization_id is required. Set QC_ORGANIZATION_ID or pass organization_id."
            )
        return resolved

    @staticmethod
    def _raise_for_http(response: Any) -> None:
        status_code = int(getattr(response, "status_code", 200))
        if status_code >= 400:
            text = str(getattr(response, "text", ""))
            raise QuantConnectCloudApiError(
                f"QuantConnect HTTP request failed: status_code={status_code}, body={text[:500]}"
            )


def redact_quantconnect_payload(value: Mapping[str, Any]) -> dict[str, Any]:
    text = json.dumps(value, sort_keys=True, default=str)
    for env_name in ["QC_API_TOKEN", "QC_USER_ID"]:
        secret = os.environ.get(env_name)
        if secret:
            text = text.replace(secret, f"<redacted:{env_name}>")
    return json.loads(text)

