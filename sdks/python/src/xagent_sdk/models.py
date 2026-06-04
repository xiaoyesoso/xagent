"""Response models for the SDK.

These mirror the server-side Pydantic schemas in
``src/xagent/web/schemas/v1.py`` but are re-declared here so the SDK
stays independent of the heavyweight web package import chain
(SQLAlchemy, FastAPI, etc.) -- importing the SDK should not pull in
the full server runtime.

We keep the shapes deliberately small and aligned 1:1 with the server
contract; new fields the server adds will simply be ignored on the
client side (``model_config = ConfigDict(extra="ignore")``) so old
SDKs keep working against newer servers.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# Mirrors ``PublicStepType`` and ``PublicStepStatus`` in
# ``schemas/v1.py``. Kept in sync manually -- they have not changed
# since the v1 surface was introduced and any new value would be a
# breaking change server-side too.
PublicStepType = Literal["thinking", "tool_call", "agent_delegation", "message"]
PublicStepStatus = Literal["running", "completed", "failed"]


class _SDKModel(BaseModel):
    """Base for SDK response models.

    ``extra="ignore"`` lets the server add fields without breaking
    existing SDK installs.
    """

    model_config = ConfigDict(extra="ignore")


class Me(_SDKModel):
    """``GET /v1/me`` -- identity probe response."""

    principal_type: str
    user_id: int
    username: str
    email: Optional[str] = None
    key_prefix: str


class RuntimeKey(_SDKModel):
    """One-time runtime key payload (created or rotated).

    ``full_key`` is only returned by the server on creation / rotation
    and is never retrievable again -- callers must persist it now.
    """

    full_key: str
    key_prefix: str
    created_at: datetime


class AgentSummary(_SDKModel):
    """Compact agent record returned by list endpoints."""

    id: int
    name: str
    description: Optional[str] = None
    logo_url: Optional[str] = None
    status: str
    created_at: str
    updated_at: str
    widget_enabled: bool = False
    allowed_domains: List[str] = Field(default_factory=list)


class Agent(_SDKModel):
    """Full agent detail returned by create / get."""

    id: int
    user_id: int
    name: str
    description: Optional[str] = None
    instructions: Optional[str] = None
    execution_mode: str
    models: Optional[dict[str, Any]] = None
    knowledge_bases: List[str] = Field(default_factory=list)
    skills: List[str] = Field(default_factory=list)
    tool_categories: List[str] = Field(default_factory=list)
    suggested_prompts: List[str] = Field(default_factory=list)
    logo_url: Optional[str] = None
    status: str
    published_at: Optional[str] = None
    created_at: str
    updated_at: str
    widget_enabled: bool = False
    allowed_domains: List[str] = Field(default_factory=list)


class CreateAgentResult(_SDKModel):
    """``POST /v1/agents`` / ``POST /v1/agents/from-template`` response."""

    agent: Agent
    api_key: Optional[RuntimeKey] = None


class CreateTaskResponse(_SDKModel):
    """``POST /v1/chat/tasks`` -- 202 Accepted body."""

    task_id: int
    agent_id: int
    status: str
    created_at: datetime


class AppendMessageResponse(_SDKModel):
    """``POST /v1/chat/tasks/{id}/messages`` -- 202 Accepted body."""

    task_id: int
    agent_id: int
    status: str
    accepted_at: datetime


class TaskInfo(_SDKModel):
    """``GET /v1/chat/tasks/{id}`` -- snapshot of one task's state."""

    task_id: int
    agent_id: int
    status: str
    input: Optional[str] = None
    output: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    @property
    def is_terminal(self) -> bool:
        """True when the task is no longer running."""
        return self.status in ("completed", "failed")


class PublicStep(_SDKModel):
    """One step on the public task timeline."""

    id: str
    type: PublicStepType
    status: PublicStepStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    data: dict[str, Any] = Field(default_factory=dict)


class StepsResponse(_SDKModel):
    """``GET /v1/chat/tasks/{id}/steps`` response body."""

    task_id: int
    agent_id: int
    steps: List[PublicStep] = Field(default_factory=list)
