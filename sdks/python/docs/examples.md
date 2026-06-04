# Examples

Recipes for common usage patterns. Every snippet assumes:

```python
BASE_URL = "http://localhost:8000"
PERSONAL_KEY = "xag_personal_..."     # control plane
RUNTIME_KEY  = "xag_agent_..."        # data plane (one specific agent)
```

## Multi-turn conversation

```python
from xagent_sdk import XagentClient

with XagentClient(base_url=BASE_URL, api_key=RUNTIME_KEY) as data:
    task = data.tasks.create(
        agent_id=AGENT_ID,
        message="I'd like to plan a trip to Tokyo.",
    )
    print(data.tasks.wait_for_completion(task.task_id).output)

    data.tasks.append_message(
        task.task_id, agent_id=AGENT_ID,
        message="Make it a 5-day itinerary.",
    )
    print(data.tasks.wait_for_completion(task.task_id).output)

    data.tasks.append_message(
        task.task_id, agent_id=AGENT_ID,
        message="What's the budget range?",
    )
    print(data.tasks.wait_for_completion(task.task_id).output)
```

`append_message` extends the same `task_id` — there is no "conversation
id" separate from the task. See [Tasks API → lifecycle](./tasks.md#task-lifecycle)
for the state machine.

## Async pipeline

```python
import asyncio
from xagent_sdk import AsyncXagentClient

async def run(prompts: list[str]) -> list[str]:
    async with AsyncXagentClient(base_url=BASE_URL, api_key=RUNTIME_KEY) as data:
        # Fire all tasks concurrently...
        creates = await asyncio.gather(*[
            data.tasks.create(agent_id=AGENT_ID, message=p)
            for p in prompts
        ])
        # ...then wait for each to terminate.
        results = await asyncio.gather(*[
            data.tasks.wait_for_completion(c.task_id) for c in creates
        ])
        return [r.output or "" for r in results]

asyncio.run(run(["Summarise X", "Translate Y", "Explain Z"]))
```

## Polling vs `wait_for_completion`

`wait_for_completion` is a thin polling loop. If you need progress
updates between polls (status, latest step), poll yourself:

```python
import time
from xagent_sdk import XagentClient

with XagentClient(base_url=BASE_URL, api_key=RUNTIME_KEY) as data:
    task = data.tasks.create(agent_id=AGENT_ID, message="long-running query")

    while True:
        info = data.tasks.get(task.task_id)
        steps = data.tasks.get_steps(task.task_id).steps
        print(info.status, f"({len(steps)} steps)")
        if info.is_terminal:
            break
        time.sleep(1.0)

    print("final output:", info.output)
```

## Tool & step inspection

Iterate over the public timeline to see what tools the agent invoked:

```python
steps = data.tasks.get_steps(task_id).steps
for s in steps:
    if s.type == "tool_call":
        print(f"  → {s.data['name']}({s.data.get('args')!r})")
        if s.status == "completed":
            print(f"     ← {s.data.get('result')!r}")
        elif s.status == "failed":
            print(f"     ✗ {s.data.get('error')!r}")
```

## Round-trip your own correlation ids

`metadata` is a free-form dict the server stores but does not interpret
— ideal for trace ids, request ids, or any client-side bookkeeping you
want to find later in logs:

```python
task = data.tasks.create(
    agent_id=AGENT_ID,
    message="reset my password",
    metadata={
        "trace_id": "trace-abc-123",
        "incoming_request_id": "req-987",
        "user_segment": "premium",
    },
)
```

> `metadata` does not appear in any of the SDK response models today —
> the value is opaque to the SDK. To inspect it, use the server's web
> UI or query the database directly.

## Use one shared `httpx.Client` across SDK clients

If you instantiate two SDK clients (one with the personal key, one with
the runtime key), they each open their own `httpx.Client` by default.
For a hot path with connection pooling concerns, share one:

```python
import httpx
from xagent_sdk import XagentClient

shared = httpx.Client(base_url=BASE_URL, timeout=30.0)

ctrl = XagentClient(base_url=BASE_URL, api_key=PERSONAL_KEY, httpx_client=shared)
data = XagentClient(base_url=BASE_URL, api_key=RUNTIME_KEY, httpx_client=shared)

try:
    ctrl.agents.me()
    data.tasks.get(some_task_id)
finally:
    # The SDK does NOT close httpx clients you passed in.
    shared.close()
```

The auth header is set per-request, so two SDK clients sharing one
underlying `httpx.Client` don't bleed credentials across calls.

## Hot-swap a rotated runtime key

```python
import time
from xagent_sdk import InvalidApiKeyError, XagentClient

def with_auto_reload(call):
    """Retry once if the cached key was revoked under us."""
    api_key = secrets.get("xagent_runtime_key")
    while True:
        with XagentClient(base_url=BASE_URL, api_key=api_key) as c:
            try:
                return call(c)
            except InvalidApiKeyError:
                fresh = secrets.reload("xagent_runtime_key")
                if fresh == api_key:
                    raise           # really revoked, not just stale cache
                api_key = fresh
                time.sleep(0.1)

with_auto_reload(lambda c: c.tasks.create(agent_id=AGENT_ID, message="hi"))
```

## Create-then-run, in one script

End-to-end from "nothing" to "task result":

```python
from xagent_sdk import XagentClient

with XagentClient(base_url=BASE_URL, api_key=PERSONAL_KEY) as ctrl:
    created = ctrl.agents.create(
        name="example-agent",
        instructions="You answer concisely.",
    )
    agent_id = created.agent.id
    runtime_key = created.api_key.full_key  # persist this in real code

with XagentClient(base_url=BASE_URL, api_key=runtime_key) as data:
    task = data.tasks.create(agent_id=agent_id, message="Why is the sky blue?")
    result = data.tasks.wait_for_completion(task.task_id)
    print(result.output)
```
