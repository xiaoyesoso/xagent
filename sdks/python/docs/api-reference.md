# API Reference

Quick lookup for every public symbol exported from `xagent_sdk`.

Conceptual guides live in [Agents](./agents.md), [Tasks](./tasks.md),
[Authentication](./authentication.md), and [Error Handling](./errors.md).

## Top-level exports

```python
from xagent_sdk import (
    # Clients
    XagentClient, AsyncXagentClient,

    # Errors
    XagentError, XagentApiError,
    InvalidApiKeyError, AgentNotFoundError, TaskNotFoundError,
    TemplateNotFoundError, TaskBusyError, InvalidInputError,
    RateLimitedError, InternalServerError,

    # Models
    Me, RuntimeKey, Agent, AgentSummary, CreateAgentResult,
    CreateTaskResponse, AppendMessageResponse,
    TaskInfo, PublicStep, StepsResponse,
)
```

`__version__` is exposed on the package: `xagent_sdk.__version__`.

---

## Clients

### `XagentClient(*, base_url, api_key, timeout=30.0, httpx_client=None)`

Synchronous client.

| Argument | Type | Default | Notes |
| --- | --- | --- | --- |
| `base_url` | `str` | — | Server root, e.g. `"http://localhost:8000"`. Trailing slash is normalised. |
| `api_key` | `str` | — | Bearer token (`xag_<kind>_<prefix>_<secret>`). |
| `timeout` | `float` | `30.0` | Per-request timeout, in seconds. |
| `httpx_client` | `httpx.Client \| None` | `None` | Inject your own. When provided, **you** own its lifecycle. |

Attributes / methods:

| | |
| --- | --- |
| `.agents: AgentsAPI` | Personal-key control plane. |
| `.tasks: TasksAPI` | Agent runtime-key data plane. |
| `.me() -> Me` | Shortcut for `.agents.me()`. |
| `.close() -> None` | Close the underlying `httpx.Client` (only if owned). |
| `__enter__` / `__exit__` | Context-manager closes on exit. |

### `AsyncXagentClient(...)`

Same constructor signature as `XagentClient`. Differences:

| | |
| --- | --- |
| `.agents: AsyncAgentsAPI` | All methods are awaitable. |
| `.tasks: AsyncTasksAPI` | All methods are awaitable. |
| `await .me() -> Me` | Awaitable shortcut. |
| `await .aclose()` | Async close. |
| `__aenter__` / `__aexit__` | `async with` support. |

---

## `client.agents` (sync) / `client.agents` on `AsyncXagentClient` (async)

| Method | Returns | Raises (typed) |
| --- | --- | --- |
| `me()` | `Me` | `InvalidApiKeyError` |
| `list()` | `list[AgentSummary]` | `InvalidApiKeyError` |
| `create(*, name, description=None, instructions=None, execution_mode="balanced", models=None, knowledge_bases=None, skills=None, tool_categories=None, suggested_prompts=None, generate_runtime_key=True)` | `CreateAgentResult` | `InvalidInputError`, `InvalidApiKeyError` |
| `create_from_template(*, template_id, name=None, description=None, instructions=None, execution_mode=None, models=None, knowledge_bases=None, skills=None, tool_categories=None, suggested_prompts=None, generate_runtime_key=True)` | `CreateAgentResult` | `TemplateNotFoundError`, `InvalidInputError`, `InvalidApiKeyError` |
| `rotate_runtime_key(agent_id: int)` | `RuntimeKey` | `AgentNotFoundError`, `InvalidApiKeyError` |

All methods may additionally raise `InternalServerError`, the generic
`XagentApiError` (unknown future code), or an `httpx.HTTPError` for
network failures.

---

## `client.tasks` (sync) / `client.tasks` on `AsyncXagentClient` (async)

| Method | Returns | Raises (typed) |
| --- | --- | --- |
| `create(*, agent_id: int, message: str, metadata: dict \| None = None)` | `CreateTaskResponse` | `AgentNotFoundError`, `InvalidInputError`, `InvalidApiKeyError` |
| `append_message(task_id: int, *, agent_id: int, message: str, metadata: dict \| None = None)` | `AppendMessageResponse` | `TaskNotFoundError`, `AgentNotFoundError`, `TaskBusyError`, `InvalidInputError`, `InvalidApiKeyError` |
| `get(task_id: int)` | `TaskInfo` | `TaskNotFoundError`, `InvalidApiKeyError` |
| `get_steps(task_id: int)` | `StepsResponse` | `TaskNotFoundError`, `InvalidApiKeyError` |
| `wait_for_completion(task_id: int, *, poll_interval: float = 1.0, timeout: float \| None = 300.0)` | terminal `TaskInfo` | `TaskTimeoutError`, plus anything `get` would raise |

`TaskTimeoutError` is importable from `xagent_sdk.tasks`. It subclasses
`XagentError`, **not** `XagentApiError`, because no HTTP failure
occurred.

---

## Models

All models are Pydantic v2, with `model_config = ConfigDict(extra="ignore")` —
unknown server fields are silently dropped so the SDK survives
forward-compatible server changes.

### `Me`
```python
principal_type: str       # always "user"
user_id: int
username: str
email: str | None
key_prefix: str           # public-safe handle of the presented key
```

### `RuntimeKey`
```python
full_key: str             # returned ONCE, persist it now
key_prefix: str
created_at: datetime
```

### `AgentSummary`
```python
id: int
name: str
description: str | None
logo_url: str | None
status: str
created_at: str
updated_at: str
widget_enabled: bool
allowed_domains: list[str]
```

### `Agent`
Superset of `AgentSummary`. Additional fields:
```python
user_id: int
instructions: str | None
execution_mode: str
models: dict | None
knowledge_bases: list[str]
skills: list[str]
tool_categories: list[str]
suggested_prompts: list[str]
published_at: str | None
```

### `CreateAgentResult`
```python
agent: Agent
api_key: RuntimeKey | None    # None if generate_runtime_key=False
```

### `CreateTaskResponse`
```python
task_id: int
agent_id: int
status: str                   # "running" on 202 Accepted
created_at: datetime
```

### `AppendMessageResponse`
```python
task_id: int
agent_id: int
status: str
accepted_at: datetime
```

### `TaskInfo`
```python
task_id: int
agent_id: int
status: str                   # pending | running | paused | completed | failed
input: str | None             # latest-turn user message
output: str | None            # latest-turn assistant reply (when completed)
error: str | None             # set when status == "failed"
created_at: datetime
completed_at: datetime | None
# Convenience:
is_terminal: bool             # property: status in {"completed", "failed"}
```

### `PublicStep`
```python
id: str                       # "tool_call:abc123" -- stable across re-polls
type: Literal["thinking", "tool_call", "agent_delegation", "message"]
status: Literal["running", "completed", "failed"]
started_at: datetime
completed_at: datetime | None
data: dict[str, Any]
```

`data` keys depend on `type`:

| `type` | `data` shape |
| --- | --- |
| `thinking` | `{"phase": "planning" \| "step" \| "action"}` |
| `tool_call` | `{"name": str, "args": Any, "result"?: Any, "error"?: str}` |
| `agent_delegation` | `{"sub_agent_name": str, "input"?: Any, "output"?: Any}` |
| `message` | `{"role": "user" \| "assistant", "content": str}` |

Treat unknown keys as forward-compat extensions; ignore them.

### `StepsResponse`
```python
task_id: int
agent_id: int
steps: list[PublicStep]       # started_at ascending
```

---

## Exception hierarchy

```
XagentError                                # base
├── XagentApiError                         # HTTP error envelope
│   ├── InvalidApiKeyError                 # 401
│   ├── AgentNotFoundError                 # 404
│   ├── TaskNotFoundError                  # 404
│   ├── TemplateNotFoundError              # 404
│   ├── TaskBusyError                      # 409
│   ├── InvalidInputError                  # 400 / 422
│   ├── RateLimitedError                   # 429 (reserved)
│   └── InternalServerError                # 5xx
└── TaskTimeoutError                       # wait_for_completion timed out
```

Common attributes on every `XagentApiError`:

```python
status_code: int
code: str            # stable V1ErrorCode, or "unknown"
message: str | None
response_body: Any   # parsed body, for debugging
```

Network and JSON-decode failures propagate as their underlying
`httpx.HTTPError` / `ValueError` types — not wrapped.
