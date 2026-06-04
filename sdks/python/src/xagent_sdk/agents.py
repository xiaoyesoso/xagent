"""``client.agents`` namespace -- personal-key control plane.

Endpoints covered (all require a ``PERSONAL`` API key):

  - ``GET  /v1/me``
  - ``GET  /v1/agents``
  - ``POST /v1/agents``
  - ``POST /v1/agents/from-template``
  - ``POST /v1/agents/{id}/api-key``  (rotate runtime key)

Templates and other personal-key surfaces can be added later without
changing the existing method signatures.
"""

from __future__ import annotations

from typing import Any, List, Optional

from ._http import _AsyncTransport, _SyncTransport
from .models import AgentSummary, CreateAgentResult, Me, RuntimeKey


def _create_payload(
    *,
    name: str,
    description: Optional[str],
    instructions: Optional[str],
    execution_mode: Optional[str],
    models: Optional[dict[str, Any]],
    knowledge_bases: Optional[List[str]],
    skills: Optional[List[str]],
    tool_categories: Optional[List[str]],
    suggested_prompts: Optional[List[str]],
    generate_runtime_key: bool,
) -> dict[str, Any]:
    """Build the JSON body for ``POST /v1/agents``.

    Optional list fields default to empty lists on the server, so we
    omit them client-side rather than sending ``None`` (the server
    would reject ``None`` for a ``list[str]`` field).
    """
    payload: dict[str, Any] = {
        "name": name,
        "generate_runtime_key": generate_runtime_key,
    }
    if description is not None:
        payload["description"] = description
    if instructions is not None:
        payload["instructions"] = instructions
    if execution_mode is not None:
        payload["execution_mode"] = execution_mode
    if models is not None:
        payload["models"] = models
    if knowledge_bases is not None:
        payload["knowledge_bases"] = knowledge_bases
    if skills is not None:
        payload["skills"] = skills
    if tool_categories is not None:
        payload["tool_categories"] = tool_categories
    if suggested_prompts is not None:
        payload["suggested_prompts"] = suggested_prompts
    return payload


def _from_template_payload(
    *,
    template_id: str,
    name: Optional[str],
    description: Optional[str],
    instructions: Optional[str],
    execution_mode: Optional[str],
    models: Optional[dict[str, Any]],
    knowledge_bases: Optional[List[str]],
    skills: Optional[List[str]],
    tool_categories: Optional[List[str]],
    suggested_prompts: Optional[List[str]],
    generate_runtime_key: bool,
) -> dict[str, Any]:
    """Build the JSON body for ``POST /v1/agents/from-template``.

    Only ``template_id`` is required; every other field is optional
    and inherited from the template when omitted.
    """
    payload: dict[str, Any] = {
        "template_id": template_id,
        "generate_runtime_key": generate_runtime_key,
    }
    for key, value in (
        ("name", name),
        ("description", description),
        ("instructions", instructions),
        ("execution_mode", execution_mode),
        ("models", models),
        ("knowledge_bases", knowledge_bases),
        ("skills", skills),
        ("tool_categories", tool_categories),
        ("suggested_prompts", suggested_prompts),
    ):
        if value is not None:
            payload[key] = value
    return payload


class AgentsAPI:
    """Synchronous agents namespace exposed as ``client.agents``."""

    def __init__(self, transport: _SyncTransport) -> None:
        self._t = transport

    def me(self) -> Me:
        """Identity probe -- returns user info bound to the personal key."""
        return Me.model_validate(self._t.request("GET", "/v1/me"))

    def list(self) -> List[AgentSummary]:
        """List agents owned by the calling user."""
        data = self._t.request("GET", "/v1/agents")
        return [AgentSummary.model_validate(item) for item in data or []]

    def create(
        self,
        *,
        name: str,
        description: Optional[str] = None,
        instructions: Optional[str] = None,
        execution_mode: Optional[str] = "balanced",
        models: Optional[dict[str, Any]] = None,
        knowledge_bases: Optional[List[str]] = None,
        skills: Optional[List[str]] = None,
        tool_categories: Optional[List[str]] = None,
        suggested_prompts: Optional[List[str]] = None,
        generate_runtime_key: bool = True,
    ) -> CreateAgentResult:
        """Create a new agent."""
        payload = _create_payload(
            name=name,
            description=description,
            instructions=instructions,
            execution_mode=execution_mode,
            models=models,
            knowledge_bases=knowledge_bases,
            skills=skills,
            tool_categories=tool_categories,
            suggested_prompts=suggested_prompts,
            generate_runtime_key=generate_runtime_key,
        )
        return CreateAgentResult.model_validate(
            self._t.request("POST", "/v1/agents", json=payload)
        )

    def create_from_template(
        self,
        *,
        template_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        instructions: Optional[str] = None,
        execution_mode: Optional[str] = None,
        models: Optional[dict[str, Any]] = None,
        knowledge_bases: Optional[List[str]] = None,
        skills: Optional[List[str]] = None,
        tool_categories: Optional[List[str]] = None,
        suggested_prompts: Optional[List[str]] = None,
        generate_runtime_key: bool = True,
    ) -> CreateAgentResult:
        """Create a new agent from a template id."""
        payload = _from_template_payload(
            template_id=template_id,
            name=name,
            description=description,
            instructions=instructions,
            execution_mode=execution_mode,
            models=models,
            knowledge_bases=knowledge_bases,
            skills=skills,
            tool_categories=tool_categories,
            suggested_prompts=suggested_prompts,
            generate_runtime_key=generate_runtime_key,
        )
        return CreateAgentResult.model_validate(
            self._t.request("POST", "/v1/agents/from-template", json=payload)
        )

    def rotate_runtime_key(self, agent_id: int) -> RuntimeKey:
        """Generate a new runtime API key for ``agent_id``.

        The previous key (if any) remains valid; the server returns
        the new full key only this once -- callers must persist it.
        """
        return RuntimeKey.model_validate(
            self._t.request("POST", f"/v1/agents/{agent_id}/api-key")
        )


class AsyncAgentsAPI:
    """Async counterpart of :class:`AgentsAPI`."""

    def __init__(self, transport: _AsyncTransport) -> None:
        self._t = transport

    async def me(self) -> Me:
        return Me.model_validate(await self._t.request("GET", "/v1/me"))

    async def list(self) -> List[AgentSummary]:
        data = await self._t.request("GET", "/v1/agents")
        return [AgentSummary.model_validate(item) for item in data or []]

    async def create(
        self,
        *,
        name: str,
        description: Optional[str] = None,
        instructions: Optional[str] = None,
        execution_mode: Optional[str] = "balanced",
        models: Optional[dict[str, Any]] = None,
        knowledge_bases: Optional[List[str]] = None,
        skills: Optional[List[str]] = None,
        tool_categories: Optional[List[str]] = None,
        suggested_prompts: Optional[List[str]] = None,
        generate_runtime_key: bool = True,
    ) -> CreateAgentResult:
        payload = _create_payload(
            name=name,
            description=description,
            instructions=instructions,
            execution_mode=execution_mode,
            models=models,
            knowledge_bases=knowledge_bases,
            skills=skills,
            tool_categories=tool_categories,
            suggested_prompts=suggested_prompts,
            generate_runtime_key=generate_runtime_key,
        )
        return CreateAgentResult.model_validate(
            await self._t.request("POST", "/v1/agents", json=payload)
        )

    async def create_from_template(
        self,
        *,
        template_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        instructions: Optional[str] = None,
        execution_mode: Optional[str] = None,
        models: Optional[dict[str, Any]] = None,
        knowledge_bases: Optional[List[str]] = None,
        skills: Optional[List[str]] = None,
        tool_categories: Optional[List[str]] = None,
        suggested_prompts: Optional[List[str]] = None,
        generate_runtime_key: bool = True,
    ) -> CreateAgentResult:
        payload = _from_template_payload(
            template_id=template_id,
            name=name,
            description=description,
            instructions=instructions,
            execution_mode=execution_mode,
            models=models,
            knowledge_bases=knowledge_bases,
            skills=skills,
            tool_categories=tool_categories,
            suggested_prompts=suggested_prompts,
            generate_runtime_key=generate_runtime_key,
        )
        return CreateAgentResult.model_validate(
            await self._t.request("POST", "/v1/agents/from-template", json=payload)
        )

    async def rotate_runtime_key(self, agent_id: int) -> RuntimeKey:
        return RuntimeKey.model_validate(
            await self._t.request("POST", f"/v1/agents/{agent_id}/api-key")
        )
