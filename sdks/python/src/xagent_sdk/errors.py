"""Typed exceptions for the Python SDK.

The server returns a stable error envelope on every ``/v1/*`` failure
(see ``src/xagent/web/api/v1/errors.py`` in the main repo):

    {"error": {"code": "<V1ErrorCode>", "message": "<text>"}}

The SDK translates each ``code`` value into a dedicated exception
subclass so callers can ``except TaskBusyError:`` and retry, instead of
string-matching against the message. Unknown codes fall back to
:class:`XagentApiError` so adding new codes server-side is forward
compatible.
"""

from __future__ import annotations

from typing import Any, Mapping


class XagentError(Exception):
    """Base class for every SDK-raised exception.

    Network errors, JSON decode failures, and timeouts come through as
    this base class; API-level errors come through as
    :class:`XagentApiError` or one of its subclasses.
    """


class XagentApiError(XagentError):
    """Raised on any HTTP error response from the server.

    Attributes:
        status_code: HTTP status returned by the server.
        code: Stable ``V1ErrorCode`` enum value (string) from the
            envelope. ``"unknown"`` if the response did not match the
            envelope shape.
        message: Human-readable text from the envelope. May be
            ``None`` if the body could not be parsed.
        response_body: Raw decoded body for debugging.
    """

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str | None,
        response_body: Any = None,
    ) -> None:
        super().__init__(f"[{status_code} {code}] {message or ''}".rstrip())
        self.status_code = status_code
        self.code = code
        self.message = message
        self.response_body = response_body


class InvalidApiKeyError(XagentApiError):
    """``invalid_api_key`` (401) -- missing / malformed / revoked key."""


class AgentNotFoundError(XagentApiError):
    """``agent_not_found`` (404) -- agent missing or not bound to the key."""


class TaskNotFoundError(XagentApiError):
    """``task_not_found`` (404) -- task missing or not owned by the agent."""


class TemplateNotFoundError(XagentApiError):
    """``template_not_found`` (404)."""


class TaskBusyError(XagentApiError):
    """``task_busy`` (409) -- task is running, retry after polling."""


class InvalidInputError(XagentApiError):
    """``invalid_input`` (400/422) -- request body failed validation."""


class RateLimitedError(XagentApiError):
    """``rate_limited`` (429) -- reserved; server may emit later."""


class InternalServerError(XagentApiError):
    """``internal_error`` (5xx) -- server-side bug."""


# Maps stable error codes to the corresponding exception class. Keep
# in lockstep with V1ErrorCode in the main repo. Unknown codes fall
# back to :class:`XagentApiError` in :func:`raise_for_error` so adding
# a code server-side does not break old SDK versions.
_CODE_TO_EXC: Mapping[str, type[XagentApiError]] = {
    "invalid_api_key": InvalidApiKeyError,
    "agent_not_found": AgentNotFoundError,
    "task_not_found": TaskNotFoundError,
    "template_not_found": TemplateNotFoundError,
    "task_busy": TaskBusyError,
    "invalid_input": InvalidInputError,
    "rate_limited": RateLimitedError,
    "internal_error": InternalServerError,
}


def raise_for_error(status_code: int, body: Any) -> None:
    """Translate a non-2xx response body into the right typed exception.

    Args:
        status_code: HTTP status from the response.
        body: Parsed JSON body, or ``None`` if the body was not JSON.
            The expected envelope is ``{"error": {"code": ..., "message": ...}}``
            but anything else is tolerated and surfaced as
            :class:`XagentApiError` with ``code="unknown"``.

    Raises:
        XagentApiError or one of its subclasses. Never returns.
    """
    code = "unknown"
    message: str | None = None
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            raw_code = err.get("code")
            if isinstance(raw_code, str):
                code = raw_code
            raw_msg = err.get("message")
            if isinstance(raw_msg, str):
                message = raw_msg

    exc_cls = _CODE_TO_EXC.get(code, XagentApiError)
    raise exc_cls(
        status_code=status_code,
        code=code,
        message=message,
        response_body=body,
    )
