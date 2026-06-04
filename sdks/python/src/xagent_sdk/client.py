"""Top-level client classes -- sync and async.

A single ``api_key`` is used for both the agents namespace and the
tasks namespace because the server-side auth dependency picks the
correct branch based on the key's prefix kind (``personal`` vs
``agent``). In practice a caller will hold two keys and instantiate
two clients -- one per kind -- but the SDK doesn't enforce that
because there's no client-side way to tell the kinds apart without
calling the server.
"""

from __future__ import annotations

from types import TracebackType
from typing import Optional

import httpx

from ._http import DEFAULT_TIMEOUT_SECONDS, _AsyncTransport, _SyncTransport
from .agents import AgentsAPI, AsyncAgentsAPI
from .tasks import AsyncTasksAPI, TasksAPI


class XagentClient:
    """Synchronous client.

    Args:
        base_url: Server root, e.g. ``"http://localhost:8000"``.
        api_key: Bearer token (``xag_...``). Personal key for
            ``.agents`` calls, agent runtime key for ``.tasks`` calls.
        timeout: Per-request timeout in seconds.
        httpx_client: Optional pre-configured ``httpx.Client``. When
            provided, the SDK will NOT close it on ``__exit__`` --
            ownership stays with the caller.

    Usage:

        with XagentClient(base_url="...", api_key="xag_...") as client:
            client.agents.me()
            client.tasks.create(agent_id=1, message="hi")
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        httpx_client: Optional[httpx.Client] = None,
    ) -> None:
        self._transport = _SyncTransport(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
            httpx_client=httpx_client,
        )
        self.agents = AgentsAPI(self._transport)
        self.tasks = TasksAPI(self._transport)

    def me(self) -> "object":
        """Shortcut for :meth:`AgentsAPI.me`."""
        return self.agents.me()

    def close(self) -> None:
        """Close the underlying HTTP client (if owned)."""
        self._transport.close()

    def __enter__(self) -> "XagentClient":
        return self

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        self.close()


class AsyncXagentClient:
    """Asynchronous client.

    Mirrors :class:`XagentClient` but every method on ``.agents`` /
    ``.tasks`` is awaitable. Use ``async with`` to ensure the
    underlying ``httpx.AsyncClient`` is closed.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        httpx_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self._transport = _AsyncTransport(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
            httpx_client=httpx_client,
        )
        self.agents = AsyncAgentsAPI(self._transport)
        self.tasks = AsyncTasksAPI(self._transport)

    async def me(self) -> "object":
        return await self.agents.me()

    async def aclose(self) -> None:
        await self._transport.aclose()

    async def __aenter__(self) -> "AsyncXagentClient":
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        await self.aclose()
