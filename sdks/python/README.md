# Xagent Python SDK

Official Python client for the Xagent public `/v1/*` HTTP API.

> Status: **Alpha**. Tracks roadmap [issue #82](https://github.com/xorbitsai/xagent/issues/82) → *Python SDK (P2)*. Surface area is intentionally limited to the v1 contract documented in `src/xagent/web/api/v1/`.

## Documentation

Full user guide lives under [`docs/`](./docs/index.md):

| | |
| --- | --- |
| [Quickstart](./docs/quickstart.md) | Install → key → first task in five minutes. |
| [Authentication](./docs/authentication.md) | Personal vs agent runtime keys, rotation, revocation. |
| [Agents API](./docs/agents.md) | `client.agents.*` — manage agents. |
| [Tasks API](./docs/tasks.md) | `client.tasks.*` — drive task lifecycle. |
| [Error Handling](./docs/errors.md) | Typed exceptions and retry recipes. |
| [Examples](./docs/examples.md) | Multi-turn, async pipeline, polling, metadata. |
| [API Reference](./docs/api-reference.md) | Method signatures, models, exception hierarchy. |

The README below is a condensed overview; the docs are authoritative.

## Install

> ⚠️ **Not yet published to PyPI.** The `xagent-sdk` name is reserved
> for this package but no release has been cut while the surface is
> still in review against [issue #82](https://github.com/xorbitsai/xagent/issues/82).
> Install from a checkout of the repo for now:

```bash
# From the repo root
pip install -e sdks/python
```

Once a release ships, install will be:

```bash
pip install xagent-sdk    # not available yet
```

## Authentication

The SDK uses bearer tokens. Two kinds exist on the server side, both
shaped like `xag_<6-char prefix>_<32-char secret>`:

| Kind         | Bound to     | Used for                                                                 |
| ------------ | ------------ | ------------------------------------------------------------------------ |
| **Personal** | A user       | Manage agents under the calling user (`client.agents.*`, `client.me()`)  |
| **Agent**    | One agent    | Drive a specific agent's task lifecycle (`client.tasks.*`)               |

Pass whichever key matches the surface you intend to call as `api_key=...`.
The two kinds look identical on the wire — the server picks the right
auth path from the key prefix — so callers usually hold one of each and
instantiate two clients.

> The server returns each `full_key` **only once** (at create / rotate
> time) and stores a bcrypt hash thereafter. Persist it as soon as you
> see it; lost keys must be rotated.

### Getting a Personal key

Personal keys are created against the logged-in web session (JWT
cookie), not via the SDK itself. From the Xagent web UI, open
**Settings → Personal API Keys → Create**, or call the underlying
endpoint directly:

```bash
# Authenticated with the web session (JWT cookie / Authorization header)
curl -X POST https://<your-host>/api/me/personal-keys
# -> {"full_key": "xag_abc123_...", "key_prefix": "abc123", "created_at": "..."}
```

Companion endpoints:

- `GET    /api/me/personal-keys`             — list (metadata only)
- `DELETE /api/me/personal-keys/{key_id}`    — revoke

### Getting an Agent runtime key

You can get an agent runtime key in two ways.

**(a) Create the agent through the SDK** with `generate_runtime_key=True`
(the default) and read it from the response:

```python
from xagent_sdk import XagentClient

with XagentClient(base_url="http://localhost:8000",
                  api_key="xag_<personal key>") as client:
    result = client.agents.create(
        name="my-agent",
        instructions="You are a helpful assistant.",
    )
    runtime_key = result.api_key.full_key   # <-- persist this now
    agent_id = result.agent.id
```

**(b) Rotate / create against an existing agent** via the SDK:

```python
new_key = client.agents.rotate_runtime_key(agent_id).full_key
```

Or with the raw endpoints (web session auth):

```bash
curl -X POST   https://<your-host>/api/agents/<agent_id>/api-key   # create / rotate
curl -X GET    https://<your-host>/api/agents/<agent_id>/api-key   # metadata
curl -X DELETE https://<your-host>/api/agents/<agent_id>/api-key   # revoke
```

## Sync example

```python
from xagent_sdk import XagentClient

with XagentClient(
    base_url="http://localhost:8000",
    api_key="xag_<agent runtime key>",
) as client:
    task = client.tasks.create(agent_id=42, message="Summarise today's news.")
    info = client.tasks.wait_for_completion(task.task_id)
    print(info.status, info.output)
```

## Async example

```python
import asyncio
from xagent_sdk import AsyncXagentClient

async def main():
    async with AsyncXagentClient(
        base_url="http://localhost:8000",
        api_key="xag_<agent runtime key>",
    ) as client:
        task = await client.tasks.create(agent_id=42, message="hi")
        info = await client.tasks.wait_for_completion(task.task_id)
        print(info.output)

asyncio.run(main())
```

## Error handling

All non-2xx responses are translated into typed exceptions whose names
mirror the server-side `V1ErrorCode` enum:

```python
from xagent_sdk import TaskBusyError, InvalidApiKeyError

try:
    client.tasks.append_message(task_id, agent_id=42, message="next turn")
except TaskBusyError:
    ...  # poll get() until the task leaves the running state
except InvalidApiKeyError:
    ...  # refresh / rotate the key
```

Unknown error codes (added later on the server) fall back to the
`XagentApiError` base class so the SDK stays forward compatible.

## Testing

```bash
cd sdks/python
pip install -e ".[dev]"
pytest
```

Tests use [`httpx.MockTransport`](https://www.python-httpx.org/advanced/transports/#mock-transports)
to stub responses so no server is required and `pytest` is the only
test dependency.
