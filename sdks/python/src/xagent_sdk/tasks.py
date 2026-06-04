"""``client.tasks`` namespace -- agent runtime-key data plane.

Endpoints covered (all require an ``AGENT`` API key bound to the
target agent):

  - ``POST /v1/chat/tasks``                  (create)
  - ``POST /v1/chat/tasks/{id}/messages``    (append)
  - ``GET  /v1/chat/tasks/{id}``             (snapshot)
  - ``GET  /v1/chat/tasks/{id}/steps``       (timeline)

Convenience helper :meth:`TasksAPI.wait_for_completion` polls the
snapshot endpoint until the task reaches a terminal state -- there is
no WebSocket transport in this initial SDK cut, so polling is the
documented way to wait for a result.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

from ._http import _AsyncTransport, _SyncTransport
from .errors import XagentError
from .models import (
    AppendMessageResponse,
    CreateTaskResponse,
    StepsResponse,
    TaskInfo,
)

DEFAULT_POLL_INTERVAL = 1.0
DEFAULT_POLL_TIMEOUT = 300.0


class TaskTimeoutError(XagentError):
    """Raised when :meth:`wait_for_completion` exceeds its timeout.

    Distinct from :class:`xagent_sdk.errors.XagentApiError` because no
    HTTP error occurred -- the task was simply slower than the
    caller's deadline. The latest snapshot is attached so callers can
    keep polling out-of-band or report progress.
    """

    def __init__(self, task_id: int, last_snapshot: Optional[TaskInfo]) -> None:
        super().__init__(
            f"Task {task_id} did not reach a terminal state in time."
        )
        self.task_id = task_id
        self.last_snapshot = last_snapshot


def _create_body(agent_id: int, message: str, metadata: Optional[dict[str, Any]]) -> dict[str, Any]:
    body: dict[str, Any] = {
        "agent_id": agent_id,
        "message": {"role": "user", "content": message},
    }
    if metadata is not None:
        body["metadata"] = metadata
    return body


class TasksAPI:
    """Synchronous tasks namespace exposed as ``client.tasks``."""

    def __init__(self, transport: _SyncTransport) -> None:
        self._t = transport

    def create(
        self,
        *,
        agent_id: int,
        message: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> CreateTaskResponse:
        """Create a new SDK task and queue its first turn."""
        return CreateTaskResponse.model_validate(
            self._t.request(
                "POST",
                "/v1/chat/tasks",
                json=_create_body(agent_id, message, metadata),
            )
        )

    def append_message(
        self,
        task_id: int,
        *,
        agent_id: int,
        message: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> AppendMessageResponse:
        """Append the next user message to an existing task."""
        return AppendMessageResponse.model_validate(
            self._t.request(
                "POST",
                f"/v1/chat/tasks/{task_id}/messages",
                json=_create_body(agent_id, message, metadata),
            )
        )

    def get(self, task_id: int) -> TaskInfo:
        """Return the current snapshot of a task."""
        return TaskInfo.model_validate(
            self._t.request("GET", f"/v1/chat/tasks/{task_id}")
        )

    def get_steps(self, task_id: int) -> StepsResponse:
        """Return the public-timeline steps for a task."""
        return StepsResponse.model_validate(
            self._t.request("GET", f"/v1/chat/tasks/{task_id}/steps")
        )

    def wait_for_completion(
        self,
        task_id: int,
        *,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        timeout: Optional[float] = DEFAULT_POLL_TIMEOUT,
    ) -> TaskInfo:
        """Block until the task reaches a terminal status.

        Args:
            task_id: Target task primary key.
            poll_interval: Seconds between snapshot polls.
            timeout: Maximum seconds to wait before raising
                :class:`TaskTimeoutError`. ``None`` means wait forever.

        Returns:
            The terminal :class:`TaskInfo` snapshot.

        Raises:
            TaskTimeoutError: If the task did not terminate in time.
            XagentApiError: Propagated from the underlying snapshot call.
        """
        deadline = None if timeout is None else time.monotonic() + timeout
        info: Optional[TaskInfo] = None
        while True:
            info = self.get(task_id)
            if info.is_terminal:
                return info
            if deadline is not None and time.monotonic() >= deadline:
                raise TaskTimeoutError(task_id, info)
            time.sleep(poll_interval)


class AsyncTasksAPI:
    """Async counterpart of :class:`TasksAPI`."""

    def __init__(self, transport: _AsyncTransport) -> None:
        self._t = transport

    async def create(
        self,
        *,
        agent_id: int,
        message: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> CreateTaskResponse:
        return CreateTaskResponse.model_validate(
            await self._t.request(
                "POST",
                "/v1/chat/tasks",
                json=_create_body(agent_id, message, metadata),
            )
        )

    async def append_message(
        self,
        task_id: int,
        *,
        agent_id: int,
        message: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> AppendMessageResponse:
        return AppendMessageResponse.model_validate(
            await self._t.request(
                "POST",
                f"/v1/chat/tasks/{task_id}/messages",
                json=_create_body(agent_id, message, metadata),
            )
        )

    async def get(self, task_id: int) -> TaskInfo:
        return TaskInfo.model_validate(
            await self._t.request("GET", f"/v1/chat/tasks/{task_id}")
        )

    async def get_steps(self, task_id: int) -> StepsResponse:
        return StepsResponse.model_validate(
            await self._t.request("GET", f"/v1/chat/tasks/{task_id}/steps")
        )

    async def wait_for_completion(
        self,
        task_id: int,
        *,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        timeout: Optional[float] = DEFAULT_POLL_TIMEOUT,
    ) -> TaskInfo:
        """Async version of :meth:`TasksAPI.wait_for_completion`."""
        deadline = None if timeout is None else asyncio.get_event_loop().time() + timeout
        info: Optional[TaskInfo] = None
        while True:
            info = await self.get(task_id)
            if info.is_terminal:
                return info
            if deadline is not None and asyncio.get_event_loop().time() >= deadline:
                raise TaskTimeoutError(task_id, info)
            await asyncio.sleep(poll_interval)
