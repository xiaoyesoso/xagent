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

URL composition: the transport stores its own normalised ``base_url``
and joins request paths against it explicitly, **not** via
``httpx.Client(base_url=...)``. That way the caller can inject a
pre-configured ``httpx.Client`` with an unrelated ``base_url`` (e.g.
pointing at a proxy or pinned to a different host) and we still send
the request to the right endpoint on the Xagent server.
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


def _join(base_url: str, path: str) -> str:
    """Compose an absolute URL from the SDK ``base_url`` and a path.

    ``base_url`` is the value the caller passed into ``XagentClient``,
    normalised once at transport construction (no trailing slash).
    ``path`` is the route the SDK code writes (always starts with
    ``/``). We concatenate explicitly instead of relying on
    ``httpx.Client(base_url=...)`` so callers that inject their own
    ``httpx_client`` with a different ``base_url`` (proxy, sidecar,
    test transport, …) still see requests land on the Xagent server.
    """
    return f"{base_url}{path}"


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
        self._base_url = base_url.rstrip("/")
        self._owns_client = httpx_client is None
        self._client = httpx_client or httpx.Client(timeout=timeout)

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
            _join(self._base_url, path),
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
        self._base_url = base_url.rstrip("/")
        self._owns_client = httpx_client is None
        self._client = httpx_client or httpx.AsyncClient(timeout=timeout)

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
            _join(self._base_url, path),
            json=json,
            params=params,
            headers=_build_headers(self._api_key),
        )
        return _handle(response)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
