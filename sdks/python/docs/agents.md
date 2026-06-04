# Agents API

`client.agents.*` is the **control plane** namespace — manage agents
under the calling user. All methods here require a **personal API key**.

```python
from xagent_sdk import XagentClient

with XagentClient(base_url=BASE_URL, api_key="xag_personal_...") as client:
    ...
```

The async counterpart is `AsyncXagentClient.agents.*`; every method
below has an awaitable mirror with identical arguments.

## `client.me()` / `client.agents.me()`

Identity probe — confirm a personal key works and see who it belongs to.

```python
me = client.agents.me()
# Me(principal_type='user', user_id=7, username='alice',
#    email='alice@example.com', key_prefix='abc123')
```

| Returns | `Me` |
| --- | --- |

## `client.agents.list()`

List every agent the calling user owns (summary only — no instructions
or model config).

```python
agents = client.agents.list()
for a in agents:
    print(a.id, a.name, a.status)
```

| Returns | `list[AgentSummary]` |
| --- | --- |

## `client.agents.create(...)`

Create a new agent. Optionally returns a fresh runtime key in the same
response (see [Authentication](./authentication.md#a-generated-at-agent-creation)).

```python
result = client.agents.create(
    name="support-bot",
    description="Triages support tickets.",
    instructions="You are a calm, accurate support agent.",
    execution_mode="balanced",          # "flash" | "balanced" | "think" | "auto"
    models={...},                       # optional model overrides
    knowledge_bases=["kb_support"],     # optional KB ids
    skills=[],                          # optional skill ids
    tool_categories=["web"],            # optional tool category names
    suggested_prompts=["Reset my password"],
    generate_runtime_key=True,          # default: mint a runtime key too
)

agent_id = result.agent.id
runtime_key = result.api_key.full_key   # None if generate_runtime_key=False
```

| Required | `name: str` |
| --- | --- |
| Returns | `CreateAgentResult(agent: Agent, api_key: RuntimeKey \| None)` |
| Raises | `InvalidInputError` (duplicate name, bad models config, unknown KB), `XagentApiError` |

## `client.agents.create_from_template(...)`

Same as `create`, but inherits defaults from a server-side template.
Only `template_id` is required; everything else, when omitted, comes
from the template.

```python
result = client.agents.create_from_template(
    template_id="template-customer-support",
    name="my-custom-support-bot",        # optional override
)
```

| Required | `template_id: str` |
| --- | --- |
| Returns | `CreateAgentResult` |
| Raises | `TemplateNotFoundError`, `InvalidInputError`, `XagentApiError` |

## `client.agents.rotate_runtime_key(agent_id)`

Mint a new runtime key for an existing agent. The old key (if any)
remains valid until you separately revoke it via the web management
endpoint — this gives you a window for hot-swap deploys.

```python
new_key = client.agents.rotate_runtime_key(agent_id)
# RuntimeKey(full_key='xag_agent_xyz...', key_prefix='xyz...', created_at=...)
```

| Returns | `RuntimeKey` |
| --- | --- |
| Raises | `AgentNotFoundError`, `XagentApiError` |

> Like all key responses, `full_key` is returned **only this once**.
> Persist it before the function returns to your caller.

## Return models — at a glance

```python
class Me:
    principal_type: str       # always "user"
    user_id: int
    username: str
    email: str | None
    key_prefix: str           # public-safe lookup handle of the presented key

class AgentSummary:
    id: int
    name: str
    description: str | None
    logo_url: str | None
    status: str
    created_at: str
    updated_at: str
    widget_enabled: bool
    allowed_domains: list[str]

class Agent(AgentSummary):
    # ...plus full config:
    user_id: int
    instructions: str | None
    execution_mode: str
    models: dict | None
    knowledge_bases: list[str]
    skills: list[str]
    tool_categories: list[str]
    suggested_prompts: list[str]
    published_at: str | None

class RuntimeKey:
    full_key: str
    key_prefix: str
    created_at: datetime

class CreateAgentResult:
    agent: Agent
    api_key: RuntimeKey | None
```

All models tolerate unknown fields (`model_config = ConfigDict(extra="ignore")`),
so a newer server can add response fields without breaking the SDK.
