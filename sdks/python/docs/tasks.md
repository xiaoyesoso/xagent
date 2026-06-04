# Tasks API

`client.tasks.*` is the **data plane** namespace — drive a single
agent's task lifecycle. All methods here require an **agent runtime
key** bound to the target agent.

```python
from xagent_sdk import XagentClient

with XagentClient(base_url=BASE_URL, api_key="xag_agent_...") as data:
    ...
```

The async counterpart is `AsyncXagentClient.tasks.*`; every method
below has an awaitable mirror with identical arguments.

## Task lifecycle

```
┌────────────┐  create   ┌────────────┐  bg turn ends  ┌────────────────────┐
│  (no row)  │ ────────▶ │  running   │ ─────────────▶ │ completed / failed │
└────────────┘           └────────────┘                └────────────────────┘
                            ▲    │
                  append    │    │  poll (snapshot / steps)
                            │    ▼
                       (another turn)
```

- `POST /v1/chat/tasks` returns **202 Accepted** with `status="running"` —
  the server has atomically claimed the row before responding.
- The task stays `running` while the background turn executes.
- `append_message` is only valid when the task is **not** running
  (otherwise 409 `task_busy`).
- Reaching `completed` or `failed` is terminal — `wait_for_completion`
  resolves at that point.

## `client.tasks.create(agent_id=..., message=..., metadata=...)`

Kick off a brand-new task and its first turn.

```python
task = client.tasks.create(
    agent_id=agent_id,
    message="Summarise yesterday's news.",
    metadata={"trace_id": "abc-123"},   # optional, free-form pass-through
)
# CreateTaskResponse(task_id=42, agent_id=..., status='running',
#                    created_at=datetime(..., tzinfo=utc))
```

| Required | `agent_id: int`, `message: str` |
| --- | --- |
| Optional | `metadata: dict \| None` — round-tripped, not interpreted server-side |
| Returns | `CreateTaskResponse` |
| Raises | `AgentNotFoundError`, `InvalidInputError`, `InvalidApiKeyError` |

> `agent_id` must match the agent bound to your runtime key. Server
> returns 404 `agent_not_found` (not 403) on mismatch — by design, so
> the existence of other agents isn't leaked.

## `client.tasks.append_message(task_id, agent_id=..., message=..., metadata=...)`

Continue an existing task with the next user message. Only valid after
the previous turn has terminated (`completed` / `failed`).

```python
turn = client.tasks.append_message(
    task_id=task.task_id,
    agent_id=agent_id,
    message="Translate that into Spanish.",
)
# AppendMessageResponse(task_id=..., agent_id=..., status='running',
#                       accepted_at=datetime(...))
```

| Returns | `AppendMessageResponse` |
| --- | --- |
| Raises | `TaskNotFoundError`, `AgentNotFoundError` (body `agent_id` mismatch), `TaskBusyError` (previous turn still running), `InvalidApiKeyError` |

See [Error Handling — task_busy retry pattern](./errors.md#taskbusyerror)
for a robust polling loop.

## `client.tasks.get(task_id)`

Snapshot of the task's current state. The fields reflect the **latest
turn**: `input` is its user message, `output` is the assistant reply
(set when status reaches `completed`), `error` is set when `failed`.

```python
info = client.tasks.get(task.task_id)
# TaskInfo(task_id=42, agent_id=..., status='completed',
#          input='Summarise yesterday\'s news.',
#          output='Here are the top three stories...',
#          error=None,
#          created_at=..., completed_at=...)

if info.is_terminal:
    print(info.output if info.status == "completed" else info.error)
```

| Returns | `TaskInfo` (has convenience `.is_terminal` property) |
| --- | --- |
| Raises | `TaskNotFoundError`, `InvalidApiKeyError` |

## `client.tasks.get_steps(task_id)`

The public-timeline view of what the agent did. Four stable step types:

| Type | `data` keys |
| --- | --- |
| `thinking` | `phase: "planning" \| "step" \| "action"` |
| `tool_call` | `name`, `args`, `result?`, `error?` |
| `agent_delegation` | `sub_agent_name`, `input?`, `output?` |
| `message` | `role: "user" \| "assistant"`, `content` |

```python
steps = client.tasks.get_steps(task.task_id)
for s in steps.steps:
    print(s.started_at, s.type, s.status, s.data)
```

Steps appear in `started_at` ascending order. In-flight steps have
`status="running"` and `completed_at=None`, so this endpoint is safe to
poll while the task is still running.

| Returns | `StepsResponse` |
| --- | --- |
| Raises | `TaskNotFoundError`, `InvalidApiKeyError` |

## `client.tasks.wait_for_completion(task_id, *, poll_interval=1.0, timeout=300.0)`

Convenience helper: polls `get(task_id)` until status is terminal.

```python
info = client.tasks.wait_for_completion(task.task_id, poll_interval=0.5, timeout=60)
```

| Returns | terminal `TaskInfo` |
| --- | --- |
| Raises | `TaskTimeoutError` (deadline reached), plus anything `get()` would raise |

`timeout=None` waits indefinitely.

Async version: `await async_client.tasks.wait_for_completion(...)`. It
uses `asyncio.sleep` between polls, so other coroutines keep running.

## Return models — at a glance

```python
class CreateTaskResponse:
    task_id: int
    agent_id: int
    status: str            # "running" on the 202 response
    created_at: datetime

class AppendMessageResponse:
    task_id: int
    agent_id: int
    status: str
    accepted_at: datetime

class TaskInfo:
    task_id: int
    agent_id: int
    status: str            # pending | running | paused | completed | failed
    input: str | None
    output: str | None
    error: str | None
    created_at: datetime
    completed_at: datetime | None
    is_terminal: bool      # property: status in {"completed", "failed"}

class PublicStep:
    id: str                # "tool_call:abc123" — type-prefixed, stable across re-polls
    type: Literal["thinking", "tool_call", "agent_delegation", "message"]
    status: Literal["running", "completed", "failed"]
    started_at: datetime
    completed_at: datetime | None
    data: dict[str, Any]

class StepsResponse:
    task_id: int
    agent_id: int
    steps: list[PublicStep]
```
