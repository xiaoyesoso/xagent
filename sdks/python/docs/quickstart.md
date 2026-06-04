# Quickstart

From zero to a running task in five minutes.

## 1. Install

> ⚠️ **Not yet on PyPI.** While roadmap [issue #82](https://github.com/xorbitsai/xagent/issues/82)
> is still in review, install from a checkout of the repo:

```bash
# From the repo root
pip install -e sdks/python
```

Once a release ships the install will be `pip install xagent-sdk` — but
that name returns 404 on PyPI today, so don't try it yet.

The SDK pulls in only `httpx` and `pydantic` — it does **not** drag in
the server runtime.

## 2. Get your API keys

You need **two** bearer tokens (both shaped like `xag_<kind>_<prefix>_<secret>`):

| Key | Used for | How to get it |
| --- | --- | --- |
| Personal | `client.agents.*`, `client.me()` | Web UI → **Settings → Personal API Keys → Create**, or `POST /api/me/personal-keys` with a JWT session. |
| Agent runtime | `client.tasks.*` | Created automatically when you `client.agents.create(...)` (default `generate_runtime_key=True`); or rotate with `client.agents.rotate_runtime_key(agent_id)`. |

Full details, including rotation and revocation: [Authentication](./authentication.md).

> Each `full_key` is returned **only once** at create/rotate time. Persist it
> immediately; lost keys must be rotated.

## 3. Create an agent and grab its runtime key

```python
from xagent_sdk import XagentClient

PERSONAL_KEY = "xag_personal_..."   # from step 2
BASE_URL = "http://localhost:8000"  # your Xagent server

with XagentClient(base_url=BASE_URL, api_key=PERSONAL_KEY) as ctrl:
    result = ctrl.agents.create(
        name="quickstart-agent",
        instructions="You are a helpful assistant.",
    )

agent_id = result.agent.id
runtime_key = result.api_key.full_key     # <-- persist this now
print(f"agent_id={agent_id}, runtime_key={runtime_key}")
```

## 4. Run a task and wait for the result

```python
from xagent_sdk import XagentClient

with XagentClient(base_url=BASE_URL, api_key=runtime_key) as data:
    task = data.tasks.create(agent_id=agent_id, message="Say hi in three languages.")
    info = data.tasks.wait_for_completion(task.task_id)
    print(info.status, "\n", info.output)
```

`wait_for_completion` polls `GET /v1/chat/tasks/{id}` (default every 1 s,
timeout 300 s). Tune with `poll_interval=` / `timeout=`.

## 5. Async variant

Every method has an async counterpart on `AsyncXagentClient`:

```python
import asyncio
from xagent_sdk import AsyncXagentClient

async def main():
    async with AsyncXagentClient(base_url=BASE_URL, api_key=runtime_key) as data:
        task = await data.tasks.create(agent_id=agent_id, message="hi")
        info = await data.tasks.wait_for_completion(task.task_id)
        print(info.output)

asyncio.run(main())
```

## Next steps

- [Agents API](./agents.md) — list, create, rotate keys.
- [Tasks API](./tasks.md) — create, append turns, inspect steps.
- [Error Handling](./errors.md) — typed exceptions and retry recipes.
- [Examples](./examples.md) — multi-turn chat, metadata, custom httpx clients.
