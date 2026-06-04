# Xagent Python SDK — Documentation

A typed Python client for the Xagent public `/v1/*` HTTP API.

If you've never used Xagent or the SDK before, start with the
**[Quickstart](./quickstart.md)** — five minutes from `pip install` to a
running task.

## Contents

| Guide | What it covers |
| --- | --- |
| **[Quickstart](./quickstart.md)** | Install, get a key, create an agent, run a task. |
| **[Authentication](./authentication.md)** | The two key kinds (`personal` / `agent`), how to get them, how to rotate. |
| **[Agents API](./agents.md)** | `client.agents.*` — manage agents under your account. |
| **[Tasks API](./tasks.md)** | `client.tasks.*` — drive an agent's task lifecycle. |
| **[Error Handling](./errors.md)** | Typed exceptions and recommended retry patterns. |
| **[Examples](./examples.md)** | Multi-turn chat, async usage, polling, metadata round-trip. |
| **[API Reference](./api-reference.md)** | Method signatures, parameters, return types. |

## Versioning & compatibility

| | |
| --- | --- |
| SDK package | `xagent-sdk` (name reserved; **not yet released to PyPI** — install from repo, see [Quickstart](./quickstart.md#1-install)) |
| Tracks server API | `/v1/*` (stable contract, see [`web/api/v1/`](../../../src/xagent/web/api/v1/)) |
| Forward compatibility | Unknown response fields → ignored. Unknown error codes → fall back to `XagentApiError`. |
| Python | 3.10+ |
| Runtime dependencies | `httpx`, `pydantic` |

## Getting help

- Bugs & feature requests: open an issue on [github.com/xorbitsai/xagent](https://github.com/xorbitsai/xagent/issues).
- Roadmap item this SDK tracks: [issue #82 — Python SDK (P2)](https://github.com/xorbitsai/xagent/issues/82).
