from __future__ import annotations

from base64 import b64encode
from dataclasses import dataclass
from hashlib import sha256
from time import time
from typing import Any, Callable, Mapping

import requests

BASE_URL = "https://www.quantconnect.com/api/v2"


@dataclass(frozen=True)
class QuantConnectCredentials:
    user_id: str
    api_token: str
    organization_id: str | None = None


def build_auth_headers(
    *,
    user_id: str | int,
    api_token: str,
    timestamp: int | str | None = None,
) -> dict[str, str]:
    """Build QuantConnect REST API headers.

    QuantConnect's REST examples hash ``API_TOKEN:timestamp`` with SHA-256,
    then base64 encode ``USER_ID:hashed_token`` for Basic auth.
    """

    stamp = str(int(time()) if timestamp is None else timestamp)
    token_hash = sha256(f"{api_token}:{stamp}".encode("utf-8")).hexdigest()
    auth = b64encode(f"{user_id}:{token_hash}".encode("utf-8")).decode("ascii")
    return {
        "Authorization": f"Basic {auth}",
        "Timestamp": stamp,
    }


class QuantConnectRestClient:
    """Small QuantConnect REST client used by SignalForge automation scripts.

    The class intentionally exposes data/project/object-store operations only.
    It does not provide live-trading helpers.
    """

    def __init__(
        self,
        credentials: QuantConnectCredentials,
        *,
        base_url: str = BASE_URL,
        request_post: Callable[..., Any] | None = None,
        request_get: Callable[..., Any] | None = None,
    ) -> None:
        self.credentials = credentials
        self.base_url = base_url.rstrip("/")
        self._post = request_post or requests.post
        self._get = request_get or requests.get

    def headers(self) -> dict[str, str]:
        return build_auth_headers(user_id=self.credentials.user_id, api_token=self.credentials.api_token)

    def authenticate(self) -> dict[str, Any]:
        return self._json(self._post(f"{self.base_url}/authenticate", headers=self.headers()))

    def list_object_store(self, *, path: str = "") -> dict[str, Any]:
        organization_id = self._require_organization_id()
        return self._json(
            self._post(
                f"{self.base_url}/object/list",
                headers=self.headers(),
                json={"organizationId": organization_id, "path": path},
            )
        )

    def get_object_store(self, *, keys: list[str]) -> dict[str, Any]:
        organization_id = self._require_organization_id()
        return self._json(
            self._post(
                f"{self.base_url}/object/get",
                headers=self.headers(),
                json={"organizationId": organization_id, "keys": keys},
            )
        )

    def create_project(self, *, name: str, language: str = "Py") -> dict[str, Any]:
        return self._json(
            self._post(
                f"{self.base_url}/projects/create",
                headers=self.headers(),
                json={"name": name, "language": language},
            )
        )

    def create_file(self, *, project_id: int, name: str, content: str) -> dict[str, Any]:
        return self._json(
            self._post(
                f"{self.base_url}/files/create",
                headers=self.headers(),
                json={"projectId": project_id, "name": name, "content": content},
            )
        )

    def compile_project(self, *, project_id: int) -> dict[str, Any]:
        return self._json(
            self._post(
                f"{self.base_url}/compile/create",
                headers=self.headers(),
                json={"projectId": project_id},
            )
        )

    def create_backtest(self, *, project_id: int, compile_id: str, name: str) -> dict[str, Any]:
        return self._json(
            self._post(
                f"{self.base_url}/backtests/create",
                headers=self.headers(),
                json={"projectId": project_id, "compileId": compile_id, "backtestName": name},
            )
        )

    def read_backtest(self, *, project_id: int, backtest_id: str) -> dict[str, Any]:
        return self._json(
            self._post(
                f"{self.base_url}/backtests/read",
                headers=self.headers(),
                json={"projectId": project_id, "backtestId": backtest_id},
            )
        )

    def _require_organization_id(self) -> str:
        if not self.credentials.organization_id:
            raise ValueError("organization_id is required for QuantConnect Object Store operations")
        return self.credentials.organization_id

    @staticmethod
    def _json(response: Any) -> dict[str, Any]:
        if hasattr(response, "raise_for_status"):
            response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, Mapping):
            raise ValueError("QuantConnect REST response was not a JSON object")
        return dict(payload)
