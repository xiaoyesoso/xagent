# Error Handling

Every non-2xx response from `/v1/*` follows a stable envelope:

```json
{"error": {"code": "<V1ErrorCode>", "message": "<text>"}}
```

The SDK translates each `code` into a typed exception so callers can
`except TaskBusyError:` instead of string-matching. The full hierarchy:

```
XagentError                       # base for everything the SDK raises
├── XagentApiError                # any non-2xx HTTP response (fallback)
│   ├── InvalidApiKeyError        # 401  invalid_api_key
│   ├── AgentNotFoundError        # 404  agent_not_found
│   ├── TaskNotFoundError         # 404  task_not_found
│   ├── TemplateNotFoundError     # 404  template_not_found
│   ├── TaskBusyError             # 409  task_busy
│   ├── InvalidInputError         # 400/422  invalid_input
│   ├── RateLimitedError          # 429  rate_limited (reserved)
│   └── InternalServerError       # 5xx  internal_error
└── (network errors, JSON decode errors -> XagentError)
```

Each exception carries:

| Attribute | Type | Meaning |
| --- | --- | --- |
| `status_code` | `int` | HTTP status returned by the server. |
| `code` | `str` | Stable `V1ErrorCode` value. `"unknown"` if the body didn't match the envelope. |
| `message` | `str \| None` | Human-readable text. May change without notice. |
| `response_body` | `Any` | Raw decoded body for debugging. |

## Forward compatibility

If the server adds a new error code, old SDK versions surface it as
`XagentApiError` (the base class) — your `except` for known codes
still fires correctly, and unknown ones don't crash:

```python
try:
    client.tasks.create(agent_id=42, message="hi")
except TaskBusyError:
    ...      # handle 409
except XagentApiError as e:
    # New code from a future server release, or one you don't handle.
    log.warning("api error %s: %s", e.code, e.message)
```

## Recipes

### `InvalidApiKeyError` — refresh & retry

Triggers when the key is missing, malformed, **or revoked**. The right
response is almost never "retry the same call":

```python
from xagent_sdk import InvalidApiKeyError, XagentClient

def call_with_key_reload():
    api_key = secret_manager.get("xagent_runtime_key")
    try:
        with XagentClient(base_url=BASE, api_key=api_key) as c:
            return c.tasks.get(task_id)
    except InvalidApiKeyError:
        # Refresh from secret manager in case ops rotated.
        api_key = secret_manager.reload("xagent_runtime_key")
        with XagentClient(base_url=BASE, api_key=api_key) as c:
            return c.tasks.get(task_id)
```

### `TaskBusyError`

Returned when you call `append_message` while the previous turn is
still running. The fix is to poll the snapshot until the task leaves
`running`:

```python
import time
from xagent_sdk import TaskBusyError

def append_when_ready(client, task_id, agent_id, message, *, max_wait=120):
    deadline = time.monotonic() + max_wait
    while True:
        try:
            return client.tasks.append_message(
                task_id, agent_id=agent_id, message=message
            )
        except TaskBusyError:
            if time.monotonic() >= deadline:
                raise
            # Give the previous turn time to finish.
            info = client.tasks.get(task_id)
            if info.is_terminal:
                continue            # retry immediately
            time.sleep(1.0)
```

Or simpler — just `wait_for_completion` first:

```python
client.tasks.wait_for_completion(task_id)
client.tasks.append_message(task_id, agent_id=agent_id, message=message)
```

### `RateLimitedError` — exponential backoff

Reserved for future use; the server doesn't emit it yet, but you can
already wire the handler:

```python
import time
from xagent_sdk import RateLimitedError

def with_backoff(fn, *, attempts=5):
    delay = 1.0
    for attempt in range(attempts):
        try:
            return fn()
        except RateLimitedError:
            if attempt == attempts - 1:
                raise
            time.sleep(delay)
            delay *= 2
```

### `AgentNotFoundError` / `TaskNotFoundError`

Both are returned as **404** intentionally (never 403) so the existence
of other tenants' resources isn't leaked. If you're sure the id is
correct, the most likely cause is "this key isn't bound to that agent" —
i.e. you're using the wrong runtime key.

### `InternalServerError`

The server has a bug or an upstream dependency failed. The exception
message is sanitized — to debug, check the server's logs (the raw
exception stays on the server side, never in the response).

Retry sparingly; in the worst case treat it as terminal for the task
and surface the failure to the end user.

### Network / timeout errors

These come from `httpx` and propagate as their original type
(`httpx.ConnectError`, `httpx.ReadTimeout`, …). They subclass
`httpx.HTTPError`, not `XagentError`. If you want to catch both:

```python
import httpx
from xagent_sdk import XagentError

try:
    client.tasks.get(task_id)
except (XagentError, httpx.HTTPError) as e:
    ...
```

## Customising timeouts

`XagentClient` accepts a `timeout=` (seconds) or a pre-configured
`httpx_client=` for fine control:

```python
import httpx
from xagent_sdk import XagentClient

httpx_client = httpx.Client(
    base_url=BASE,
    timeout=httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0),
    transport=httpx.HTTPTransport(retries=2),
)
client = XagentClient(base_url=BASE, api_key="...", httpx_client=httpx_client)
```

When you pass an `httpx_client`, the SDK does **not** close it — you
remain responsible for `httpx_client.close()` / `aclose()`.
