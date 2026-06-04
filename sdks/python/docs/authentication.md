# Authentication

The SDK uses bearer tokens. Two kinds exist on the server side, both
shaped like `xag_<kind>_<prefix>_<secret>`:

| Kind         | Bound to     | Used for                                                                 |
| ------------ | ------------ | ------------------------------------------------------------------------ |
| **Personal** | A user       | Manage agents under the calling user (`client.agents.*`, `client.me()`)  |
| **Agent**    | One agent    | Drive a specific agent's task lifecycle (`client.tasks.*`)               |

Pass whichever key matches the surface you intend to call as `api_key=...`.
The two kinds look identical on the wire — the server picks the right
auth path from the `kind` segment in the key — so callers usually hold
one of each and instantiate two clients.

## Security model

- Each `full_key` is returned **once**, at create or rotate time. The
  server only stores a bcrypt hash thereafter. **Persist immediately;
  lost keys must be rotated.**
- Both kinds support revocation. Revoked keys 401 with
  `invalid_api_key` (indistinguishable from "bad secret" by design —
  attackers cannot enumerate live prefixes by error code or timing).
- Personal keys belong to a user; agent runtime keys belong to one
  agent. Compromising an agent key only grants access to that agent's
  task surface, not to other agents or to agent management.

## Personal keys

Created against a logged-in web session (JWT). From the web UI, open
**Settings → Personal API Keys → Create**, or call the underlying
endpoint directly:

```bash
# Authenticated with the web session (JWT cookie / Authorization header)
curl -X POST https://<your-host>/api/me/personal-keys
# -> {"full_key": "xag_personal_abc123_...", "key_prefix": "abc123", "created_at": "..."}
```

Companion endpoints:

| Method | Path                                       | Purpose            |
| ------ | ------------------------------------------ | ------------------ |
| GET    | `/api/me/personal-keys`                    | List (metadata only — `key_prefix`, `created_at`, never `full_key`). |
| DELETE | `/api/me/personal-keys/{key_id}`           | Revoke.            |

### Identity probe

To confirm a personal key works:

```python
from xagent_sdk import XagentClient

with XagentClient(base_url=BASE_URL, api_key="xag_personal_...") as client:
    me = client.agents.me()
    print(me.user_id, me.username, me.key_prefix)
```

## Agent runtime keys

You have two ways to obtain one.

### (a) Generated at agent creation

`client.agents.create(..., generate_runtime_key=True)` (the default)
returns the agent **and** a runtime key in a single response:

```python
with XagentClient(base_url=BASE_URL, api_key="xag_personal_...") as ctrl:
    result = ctrl.agents.create(name="my-agent", instructions="...")
    runtime_key = result.api_key.full_key       # persist this now
    agent_id = result.agent.id
```

Set `generate_runtime_key=False` if you want to create the agent now
and mint the key separately later.

### (b) Rotate / mint an existing agent's key

```python
new_key = ctrl.agents.rotate_runtime_key(agent_id).full_key
```

Or via the raw endpoints (web session auth):

```bash
curl -X POST   https://<your-host>/api/agents/<agent_id>/api-key   # create / rotate
curl -X GET    https://<your-host>/api/agents/<agent_id>/api-key   # metadata
curl -X DELETE https://<your-host>/api/agents/<agent_id>/api-key   # revoke
```

## Recommended deployment pattern

For a server-side service that talks to Xagent:

1. **Create the personal key once**, store in your secret manager.
2. On first deploy, use the personal key to `client.agents.create(...)`
   for each agent you need and capture `result.api_key.full_key`.
3. Store the runtime keys in your secret manager keyed by `agent_id`.
4. Production code reads only the runtime key matching the agent it
   wants to drive — the personal key never has to be online in the
   request path.

## Rotation playbook

- **Routine rotation** (e.g. every 90 days): call
  `client.agents.rotate_runtime_key(agent_id)` to mint a new key.
  Push it into your secret manager, then revoke the old `key_id` via
  `DELETE /api/agents/{agent_id}/api-key`.
- **Compromise**: revoke first (DELETE), then mint a new one. The
  revoked key starts returning `InvalidApiKeyError` immediately.

See [Error Handling](./errors.md) for how `InvalidApiKeyError` is
surfaced and how to wire automatic key reload on detection.
