"""HTTP-level tests for the SDK client.

We use ``httpx.MockTransport`` (a built-in ``httpx`` feature, no extra
dependency) to stub responses so the tests exercise the real request
shaping (URL, headers, JSON body) without needing a live server.

The goal is to pin:

  - Auth header is always ``Bearer <api_key>``.
  - URLs are composed against the configured ``base_url`` without
    accidental double slashes.
  - Request bodies match the documented v1 contract.
  - 2xx bodies hydrate the right Pydantic model.
  - Non-2xx bodies surface the right typed exception.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Callable, List, Tuple

import httpx
import pytest

from xagent_sdk import (
    AsyncXagentClient,
    InvalidApiKeyError,
    TaskBusyError,
    XagentClient,
)

BASE_URL = "https://xagent.example.com"
API_KEY = "xag_testpfx_secrettokenhere"


# ===== helpers =====


def _make_sync_client(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    base_url: str = BASE_URL,
) -> Tuple[XagentClient, List[httpx.Request]]:
    """Build a sync client whose transport records every request."""
    captured: List[httpx.Request] = []

    def _wrapped(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return handler(request)

    transport = httpx.MockTransport(_wrapped)
    httpx_client = httpx.Client(base_url=base_url.rstrip("/"), transport=transport)
    return (
        XagentClient(base_url=base_url, api_key=API_KEY, httpx_client=httpx_client),
        captured,
    )


def _make_async_client(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    base_url: str = BASE_URL,
) -> Tuple[AsyncXagentClient, List[httpx.Request]]:
    """Build an async client whose transport records every request."""
    captured: List[httpx.Request] = []

    def _wrapped(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return handler(request)

    transport = httpx.MockTransport(_wrapped)
    httpx_client = httpx.AsyncClient(base_url=base_url.rstrip("/"), transport=transport)
    return (
        AsyncXagentClient(
            base_url=base_url, api_key=API_KEY, httpx_client=httpx_client
        ),
        captured,
    )


def _ok(payload: dict | list, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=payload)


def _err(status: int, code: str, message: str) -> httpx.Response:
    return httpx.Response(status, json={"error": {"code": code, "message": message}})


# ===== sync =====


def test_sync_me_sends_bearer_and_parses_response() -> None:
    payload = {
        "principal_type": "user",
        "user_id": 7,
        "username": "alice",
        "email": "alice@example.com",
        "key_prefix": "testpfx",
    }
    client, captured = _make_sync_client(lambda req: _ok(payload))

    with client:
        me = client.agents.me()

    assert me.user_id == 7
    assert me.username == "alice"

    assert len(captured) == 1
    req = captured[0]
    assert req.method == "GET"
    assert req.url.path == "/v1/me"
    assert req.headers["authorization"] == f"Bearer {API_KEY}"
    assert req.headers["accept"] == "application/json"


def test_sync_create_task_posts_expected_body() -> None:
    payload = {
        "task_id": 100,
        "agent_id": 42,
        "status": "running",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    client, captured = _make_sync_client(lambda req: _ok(payload, status=202))

    with client:
        result = client.tasks.create(agent_id=42, message="hello")

    assert result.task_id == 100
    assert result.agent_id == 42
    assert result.status == "running"

    req = captured[0]
    assert req.method == "POST"
    assert req.url.path == "/v1/chat/tasks"
    body = json.loads(req.content.decode())
    assert body == {
        "agent_id": 42,
        "message": {"role": "user", "content": "hello"},
    }


def test_sync_create_task_includes_metadata_when_provided() -> None:
    payload = {
        "task_id": 1,
        "agent_id": 1,
        "status": "running",
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    client, captured = _make_sync_client(lambda req: _ok(payload, status=202))

    with client:
        client.tasks.create(
            agent_id=1, message="hi", metadata={"trace_id": "abc"}
        )

    body = json.loads(captured[0].content.decode())
    assert body["metadata"] == {"trace_id": "abc"}


def test_sync_invalid_api_key_raises_typed_exception() -> None:
    client, _ = _make_sync_client(
        lambda req: _err(401, "invalid_api_key", "Invalid or revoked API key.")
    )

    with client:
        with pytest.raises(InvalidApiKeyError) as excinfo:
            client.agents.me()

    assert excinfo.value.status_code == 401
    assert excinfo.value.code == "invalid_api_key"


def test_sync_append_message_task_busy_raises_typed_exception() -> None:
    client, captured = _make_sync_client(
        lambda req: _err(409, "task_busy", "Task is currently running.")
    )

    with client:
        with pytest.raises(TaskBusyError):
            client.tasks.append_message(9, agent_id=1, message="next")

    # Verify the URL still went where we expected even on failure.
    assert captured[0].url.path == "/v1/chat/tasks/9/messages"


def test_sync_get_task_is_terminal_flag() -> None:
    payload = {
        "task_id": 5,
        "agent_id": 1,
        "status": "completed",
        "input": "hi",
        "output": "hello!",
        "error": None,
        "created_at": "2026-01-01T00:00:00+00:00",
        "completed_at": "2026-01-01T00:00:05+00:00",
    }
    client, _ = _make_sync_client(lambda req: _ok(payload))

    with client:
        info = client.tasks.get(5)

    assert info.is_terminal is True
    assert info.output == "hello!"


def test_sync_base_url_trailing_slash_does_not_double_slash() -> None:
    payload = {
        "principal_type": "user",
        "user_id": 1,
        "username": "bob",
        "email": None,
        "key_prefix": "abcdef",
    }
    client, captured = _make_sync_client(
        lambda req: _ok(payload), base_url=f"{BASE_URL}/"
    )

    with client:
        client.agents.me()

    assert str(captured[0].url) == f"{BASE_URL}/v1/me"


def test_sync_list_agents_returns_typed_summaries() -> None:
    payload = [
        {
            "id": 1,
            "name": "agent-a",
            "description": None,
            "logo_url": None,
            "status": "draft",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "widget_enabled": False,
            "allowed_domains": [],
        }
    ]
    client, captured = _make_sync_client(lambda req: _ok(payload))

    with client:
        agents = client.agents.list()

    assert len(agents) == 1
    assert agents[0].name == "agent-a"
    assert captured[0].url.path == "/v1/agents"


# ===== async =====
#
# We avoid a hard pytest-asyncio dependency by driving the coroutine
# from the sync test body via ``asyncio.run``. This keeps the test
# matrix simple (just pytest itself), and the goal here is to pin the
# wire shape, not to exercise the event loop integration -- the
# AsyncXagentClient logic is a thin mirror of the sync one and shares
# all the request shaping through ``_AsyncTransport``.


def test_async_me_round_trip() -> None:
    import asyncio

    payload = {
        "principal_type": "user",
        "user_id": 11,
        "username": "carol",
        "email": None,
        "key_prefix": "asyncpfx",
    }
    client, captured = _make_async_client(lambda req: _ok(payload))

    async def _run() -> None:
        async with client:
            me = await client.agents.me()
        assert me.user_id == 11
        assert me.username == "carol"
        assert captured[0].headers["authorization"] == f"Bearer {API_KEY}"

    asyncio.run(_run())


def test_async_create_task_round_trip() -> None:
    import asyncio

    payload = {
        "task_id": 77,
        "agent_id": 3,
        "status": "running",
        "created_at": "2026-02-02T00:00:00+00:00",
    }
    client, captured = _make_async_client(lambda req: _ok(payload, status=202))

    async def _run() -> None:
        async with client:
            result = await client.tasks.create(agent_id=3, message="hi")
        assert result.task_id == 77
        body = json.loads(captured[0].content.decode())
        assert body["agent_id"] == 3

    asyncio.run(_run())
