"""Xagent Python SDK.

A thin, typed Python client for the Xagent public ``/v1/*`` HTTP API
(see ``src/xagent/web/api/v1`` in the main repo). The SDK ships two
parallel client trees that share request shaping, auth, and error
translation:

  - :class:`XagentClient` -- synchronous, backed by ``httpx.Client``
  - :class:`AsyncXagentClient` -- asyncio, backed by ``httpx.AsyncClient``

Both clients expose the same surface area split into two namespaces
that mirror the two server-side auth schemes:

  - ``client.agents`` -- personal management key (``xag_<...>``,
    ``PERSONAL`` kind). Lists / creates / rotates agents under the
    calling user, plus ``client.me()`` for the identity probe.
  - ``client.tasks`` -- agent runtime key (``xag_<...>``, ``AGENT``
    kind). Creates / appends / polls SDK-owned tasks against the
    bound agent.

Both auth kinds are bearer tokens, so SDK callers usually instantiate
two clients side by side -- one with their personal key for control
plane work, one with an agent runtime key for the data plane.

Error envelope (``{"error": {"code": ..., "message": ...}}``) is
translated into the typed exceptions exported below so callers can
``except AgentNotFoundError:`` instead of string-matching.

Example (sync):

    from xagent_sdk import XagentClient

    with XagentClient(base_url="http://localhost:8000",
                      api_key="xag_abc123_...") as client:
        task = client.tasks.create(agent_id=42, message="Hello")
        info = client.tasks.wait_for_completion(task.task_id)
        print(info.output)

Example (async):

    import asyncio
    from xagent_sdk import AsyncXagentClient

    async def main():
        async with AsyncXagentClient(
            base_url="http://localhost:8000",
            api_key="xag_abc123_...",
        ) as client:
            task = await client.tasks.create(agent_id=42, message="Hi")
            info = await client.tasks.wait_for_completion(task.task_id)
            print(info.output)

    asyncio.run(main())
"""

from .client import AsyncXagentClient, XagentClient
from .errors import (
    AgentNotFoundError,
    InternalServerError,
    InvalidApiKeyError,
    InvalidInputError,
    RateLimitedError,
    TaskBusyError,
    TaskNotFoundError,
    TemplateNotFoundError,
    XagentApiError,
    XagentError,
)
from .models import (
    Agent,
    AgentSummary,
    AppendMessageResponse,
    CreateAgentResult,
    CreateTaskResponse,
    Me,
    PublicStep,
    RuntimeKey,
    StepsResponse,
    TaskInfo,
)

__version__ = "0.1.0"

__all__ = [
    "__version__",
    # Clients
    "XagentClient",
    "AsyncXagentClient",
    # Errors
    "XagentError",
    "XagentApiError",
    "InvalidApiKeyError",
    "AgentNotFoundError",
    "TaskNotFoundError",
    "TemplateNotFoundError",
    "TaskBusyError",
    "InvalidInputError",
    "RateLimitedError",
    "InternalServerError",
    # Models
    "Me",
    "RuntimeKey",
    "Agent",
    "AgentSummary",
    "CreateAgentResult",
    "CreateTaskResponse",
    "AppendMessageResponse",
    "TaskInfo",
    "PublicStep",
    "StepsResponse",
]
