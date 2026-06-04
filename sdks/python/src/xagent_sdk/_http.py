"""Internal HTTP plumbing shared by sync and async clients.

Centralises:
  - URL composition (base_url + path, no accidental ``//``)
  - Bearer auth header injection
  - Response decoding + error envelope translation

The two transport classes (``_SyncTransport`` and ``_AsyncTransport``)
wrap ``httpx.Client`` / ``httpx.AsyncClient`` respectively. They both
return parsed JSON for 2xx responses and raise the appropriate
:class:`XagentApiError` subclass for non-2xx, so the public client
modules can stay focused on shaping requests and parsing models.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

import httpx

from .errors import XagentError, raise_for_error

DEFAULT_TIMEOUT_SECONDS = 30.0
USER_AGENT = "xagent-python-sdk"


def _build_headers(api_key: str, extra: Optional[Mapping[str, str]] = None) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    if extra:
        headers.update(extra)
    return headers


def _decode(response: httpx.Response) -> Any:
    """Parse the response body, treating empty / non-JSON as ``None``."""
    if not response.content:
        return None
    try:
        return response.json()
    except ValueError:
        # Non-JSON body on an error response is still useful to surface.
        return response.text


def _handle(response: httpx.Response) -> Any:
    """Return parsed body on 2xx, raise typed exception otherwise."""
    body = _decode(response)
    if 200 <= response.status_code < 300:
        return body
    raise_for_error(response.status_code, body)
    # ``raise_for_error`` always raises; this is unreachable but keeps
    # the type checker happy.
    raise XagentError("unreachable")


class _SyncTransport:
    """Thin wrapper around ``httpx.Client``.

    Owns the underlying client when ``close()`` is called via the
    context manager; if the caller passes a pre-built ``httpx.Client``
    they remain responsible for closing it.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        httpx_client: Optional[httpx.Client] = None,
    ) -> None:
        self._api_key = api_key
        self._owns_client = httpx_client is None
        self._client = httpx_client or httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: Optional[Mapping[str, Any]] = None,
    ) -> Any:
        response = self._client.request(
            method,
            path,
            json=json,
            params=params,
            headers=_build_headers(self._api_key),
        )
        return _handle(response)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


class _AsyncTransport:
    """Async counterpart of :class:`_SyncTransport`."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        httpx_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self._api_key = api_key
        self._owns_client = httpx_client is None
        self._client = httpx_client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
        )

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: Optional[Mapping[str, Any]] = None,
    ) -> Any:
        response = await self._client.request(
            method,
            path,
            json=json,
            params=params,
            headers=_build_headers(self._api_key),
        )
        return _handle(response)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
