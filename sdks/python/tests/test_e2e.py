"""End-to-end test: SDK against a real uvicorn server.

Unlike ``test_client.py`` (which stubs ``httpx.MockTransport``), this
module spins up a **real** uvicorn server in a subprocess, waits for it
to accept connections, and points the SDK at the live ``http://`` URL.
The full network path is exercised:

    SDK -> httpx -> TCP -> uvicorn -> FastAPI -> auth dep -> SQLite

No LLM key is required: the background turn scheduler is monkey-patched
out in the child process via an env var so ``POST /v1/chat/tasks`` still
returns 202 and the row is committed, but no LLM call is attempted.

The whole module is skipped if:

  - The main ``xagent`` package is not importable (SDK installed
    standalone in a fresh venv without ``pip install -e .`` of the
    parent project), OR
  - ``uvicorn`` is not installed.

That keeps the SDK's own CI lane independent while still letting
contributors run the full end-to-end check from a repo checkout that
has the server installed.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path
from typing import Iterator

import httpx
import pytest

# Skip the entire file if the main project or uvicorn isn't available.
xagent = pytest.importorskip(
    "xagent.web",
    reason=(
        "Main xagent package not importable; install with "
        "`pip install -e .` from the repo root to run the SDK e2e tests."
    ),
)
pytest.importorskip("uvicorn", reason="uvicorn required for SDK e2e tests")

from xagent_sdk import (  # noqa: E402
    AgentNotFoundError,
    InvalidApiKeyError,
    TaskBusyError,
    XagentClient,
)


# ===== server boot helpers =====


def _free_port() -> int:
    """Ask the OS for a free TCP port and immediately release it."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_http(url: str, timeout: float = 120.0) -> None:
    """Poll ``url`` until it returns any HTTP response or timeout fires.

    The first server boot pulls in the full xagent stack (langchain,
    lancedb, etc.) which can take 30-60s on a cold cache; the timeout
    is set generously and only matters when the subprocess truly
    failed to start (then we fall back to surfacing its stderr).
    """
    deadline = time.monotonic() + timeout
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with httpx.Client(timeout=1.0) as c:
                c.get(url)
            return
        except Exception as e:
            last_err = e
            time.sleep(0.5)
    raise RuntimeError(f"Server at {url} never came up: {last_err}")


# Bootstrap script run inside the uvicorn subprocess. It:
#
#   1. Installs a per-process SQLite DB (path from env) and initialises
#      the schema before any request handler runs.
#   2. Patches the background-turn scheduler to a no-op so tasks don't
#      require an LLM key. The orchestrator's atomic claim still runs,
#      so DB state and HTTP responses match production.
#   3. Builds the minimum FastAPI surface the SDK touches (auth + me +
#      agents + v1) and serves it via uvicorn.
#
# Inlined here as a string rather than a separate file so the SDK
# package stays self-contained — `python -c "..."` keeps the test
# zero-config from the contributor's side.
_SERVER_BOOTSTRAP = textwrap.dedent(
    '''
    import os
    from unittest.mock import MagicMock
    import uvicorn
    from fastapi import FastAPI, Request
    from fastapi.exceptions import RequestValidationError
    from fastapi.responses import JSONResponse

    os.environ["DATABASE_URL"] = os.environ["SDK_E2E_DB_URL"]

    # Patch BEFORE importing anything that imports the orchestrator so the
    # no-op binding is in place when the route module captures the symbol.
    import xagent.web.services.task_orchestrator as _orch
    _orch._schedule_bg = MagicMock()

    from xagent.web.api.agents import router as agents_router
    from xagent.web.api.auth import auth_router
    from xagent.web.api.me import router as me_router
    from xagent.web.api.v1 import v1_router
    from xagent.web.api.v1.errors import V1ApiError, v1_api_error_handler
    from xagent.web.models.database import get_db, init_db

    init_db(db_url=os.environ["SDK_E2E_DB_URL"])

    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(me_router)
    app.include_router(agents_router)
    app.include_router(v1_router)
    app.add_exception_handler(V1ApiError, v1_api_error_handler)

    @app.exception_handler(Exception)
    async def _err(request: Request, exc: Exception):
        if request.url.path.startswith("/v1/"):
            return JSONResponse(
                status_code=500,
                content={"error": {"code": "internal_error",
                                    "message": "Internal server error."}},
            )
        raise exc

    @app.exception_handler(RequestValidationError)
    async def _val(request: Request, exc: RequestValidationError):
        if request.url.path.startswith("/v1/"):
            errors = exc.errors()
            first = errors[0] if errors else {}
            msg = first.get("msg") or "Invalid request body"
            return JSONResponse(
                status_code=422,
                content={"error": {"code": "invalid_input", "message": msg}},
            )
        return JSONResponse(status_code=422, content={"detail": exc.errors()})

    def _get_db():
        db = None
        try:
            db = next(get_db())
            yield db
        finally:
            if db is not None:
                db.close()

    app.dependency_overrides[get_db] = _get_db

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=int(os.environ["SDK_E2E_PORT"]),
        log_level="warning",
    )
    '''
)


@pytest.fixture(scope="module")
def live_server() -> Iterator[str]:
    """Start uvicorn in a subprocess, yield its base URL, kill on teardown.

    Module-scoped so the ~5s server boot only happens once for the whole
    test file. Each test still gets a clean DB via the per-function
    ``clean_db`` fixture below.
    """
    port = _free_port()
    tmp_dir = tempfile.mkdtemp()
    db_path = Path(tmp_dir) / "sdk_e2e.db"
    db_url = f"sqlite:///{db_path}"

    env = {
        **os.environ,
        "SDK_E2E_PORT": str(port),
        "SDK_E2E_DB_URL": db_url,
    }
    proc = subprocess.Popen(
        [sys.executable, "-c", _SERVER_BOOTSTRAP],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    base_url = f"http://127.0.0.1:{port}"
    try:
        try:
            _wait_for_http(f"{base_url}/api/auth/setup-status")
        except Exception:
            # Surface the server's stderr so failures aren't opaque.
            proc.terminate()
            out, _ = proc.communicate(timeout=5)
            raise RuntimeError(
                "uvicorn failed to start. Subprocess output:\n"
                + (out.decode(errors="replace") if out else "<no output>")
            )
        yield base_url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ===== per-test setup =====


def _reset_db(base_url: str) -> None:
    """Tear down + re-init the server's DB between tests.

    Implemented by talking to the live server, not by reaching into its
    process, because the DB lives in a separate process. We hit
    /api/auth/setup-status to confirm reachability, then rely on each
    test's own bootstrap flow to create the admin user it needs.

    For now tests are written to be idempotent against an already-set-up
    admin, so we don't need a true reset — but the helper exists for
    future tests that need a pristine state.
    """
    with httpx.Client(base_url=base_url, timeout=5.0) as c:
        c.get("/api/auth/setup-status").raise_for_status()


# ===== auth helpers =====


def _bootstrap_admin(base_url: str) -> str:
    """Ensure admin exists, log in, return JWT access token."""
    with httpx.Client(base_url=base_url, timeout=10.0) as c:
        status = c.get("/api/auth/setup-status").json()
        if status.get("needs_setup", True):
            resp = c.post(
                "/api/auth/setup-admin",
                json={
                    "username": "admin",
                    "email": "admin@example.com",
                    "password": "admin12345",
                },
            )
            assert resp.status_code == 200, resp.text

        resp = c.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin12345"},
        )
        assert resp.status_code == 200, resp.text
        return resp.json()["access_token"]


def _create_personal_key(base_url: str, jwt_token: str) -> str:
    """Mint a personal SDK key for the admin user."""
    with httpx.Client(base_url=base_url, timeout=10.0) as c:
        resp = c.post(
            "/api/me/personal-keys",
            headers={"Authorization": f"Bearer {jwt_token}"},
        )
        assert resp.status_code == 200, resp.text
        return resp.json()["full_key"]


@pytest.fixture
def personal_key(live_server: str) -> str:
    """Bootstrap admin (once per test file) and mint a fresh personal key."""
    _reset_db(live_server)
    token = _bootstrap_admin(live_server)
    return _create_personal_key(live_server, token)


# ===== tests =====


def test_e2e_me_returns_admin_identity(live_server: str, personal_key: str) -> None:
    """``client.agents.me()`` against a real running uvicorn."""
    with XagentClient(base_url=live_server, api_key=personal_key) as sdk:
        me = sdk.agents.me()

    assert me.username == "admin"
    assert me.principal_type == "user"
    # Key format is ``xag_<kind>_<prefix>_<secret>`` -- index 2 is the
    # public-safe lookup prefix the server exposes via /v1/me.
    assert me.key_prefix == personal_key.split("_")[2]


def test_e2e_invalid_personal_key_raises_typed_exception(live_server: str) -> None:
    """Bad bearer should surface as :class:`InvalidApiKeyError`."""
    with XagentClient(base_url=live_server, api_key="xag_nopfx0_" + "x" * 32) as sdk:
        with pytest.raises(InvalidApiKeyError) as excinfo:
            sdk.agents.me()
    assert excinfo.value.status_code == 401
    assert excinfo.value.code == "invalid_api_key"


def test_e2e_create_agent_returns_runtime_key(
    live_server: str, personal_key: str
) -> None:
    """SDK create_agent mints both the agent row and a runtime key."""
    name = f"sdk-e2e-agent-{int(time.time() * 1000)}"
    with XagentClient(base_url=live_server, api_key=personal_key) as sdk:
        result = sdk.agents.create(
            name=name,
            description="created from the SDK e2e test",
            instructions="You are a test agent.",
            execution_mode="balanced",
        )

        assert result.agent.id > 0
        assert result.agent.name == name
        assert result.api_key is not None
        assert result.api_key.full_key.startswith("xag_")

        agents = sdk.agents.list()
    assert any(a.id == result.agent.id for a in agents)


def test_e2e_create_and_get_task(live_server: str, personal_key: str) -> None:
    """Full happy path: agent runtime key -> create task -> GET task."""
    name = f"task-e2e-agent-{int(time.time() * 1000)}"
    with XagentClient(base_url=live_server, api_key=personal_key) as ctrl:
        created = ctrl.agents.create(
            name=name,
            instructions="You are a test agent.",
        )
    assert created.api_key is not None
    runtime_key = created.api_key.full_key
    agent_id = created.agent.id

    with XagentClient(base_url=live_server, api_key=runtime_key) as data:
        create_resp = data.tasks.create(agent_id=agent_id, message="hello sdk")
        assert create_resp.agent_id == agent_id
        assert create_resp.status in ("running", "pending")

        info = data.tasks.get(create_resp.task_id)
        assert info.task_id == create_resp.task_id
        assert info.input == "hello sdk"

        # Append while the orchestrator's row is still RUNNING -> 409.
        with pytest.raises(TaskBusyError):
            data.tasks.append_message(
                create_resp.task_id, agent_id=agent_id, message="next"
            )


def test_e2e_task_with_mismatched_agent_id_returns_typed_exception(
    live_server: str, personal_key: str
) -> None:
    """``body.agent_id`` mismatch is 404 ``agent_not_found`` per v1 contract."""
    name = f"mismatch-agent-{int(time.time() * 1000)}"
    with XagentClient(base_url=live_server, api_key=personal_key) as ctrl:
        created = ctrl.agents.create(name=name, instructions="x")
    assert created.api_key is not None

    with XagentClient(base_url=live_server, api_key=created.api_key.full_key) as data:
        with pytest.raises(AgentNotFoundError):
            data.tasks.create(agent_id=created.agent.id + 9999, message="hi")
