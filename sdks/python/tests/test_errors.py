"""Unit tests for the SDK error-envelope translator."""

from __future__ import annotations

import pytest

from xagent_sdk.errors import (
    AgentNotFoundError,
    InternalServerError,
    InvalidApiKeyError,
    InvalidInputError,
    RateLimitedError,
    TaskBusyError,
    TaskNotFoundError,
    TemplateNotFoundError,
    XagentApiError,
    raise_for_error,
)


@pytest.mark.parametrize(
    "code, exc_cls",
    [
        ("invalid_api_key", InvalidApiKeyError),
        ("agent_not_found", AgentNotFoundError),
        ("task_not_found", TaskNotFoundError),
        ("template_not_found", TemplateNotFoundError),
        ("task_busy", TaskBusyError),
        ("invalid_input", InvalidInputError),
        ("rate_limited", RateLimitedError),
        ("internal_error", InternalServerError),
    ],
)
def test_known_codes_map_to_typed_exceptions(code: str, exc_cls: type) -> None:
    """Every documented V1ErrorCode should map to a dedicated subclass."""
    body = {"error": {"code": code, "message": "boom"}}
    with pytest.raises(exc_cls) as excinfo:
        raise_for_error(418, body)
    err = excinfo.value
    assert err.status_code == 418
    assert err.code == code
    assert err.message == "boom"
    assert err.response_body == body


def test_unknown_code_falls_back_to_base_class() -> None:
    """Forward-compat: unknown codes still surface as XagentApiError."""
    body = {"error": {"code": "future_code", "message": "soon"}}
    with pytest.raises(XagentApiError) as excinfo:
        raise_for_error(500, body)
    assert type(excinfo.value) is XagentApiError
    assert excinfo.value.code == "future_code"


def test_missing_envelope_yields_unknown_code() -> None:
    """Non-envelope bodies still raise, with code='unknown'."""
    with pytest.raises(XagentApiError) as excinfo:
        raise_for_error(502, "Bad Gateway")
    assert excinfo.value.code == "unknown"
    assert excinfo.value.message is None


def test_envelope_with_non_string_fields_is_tolerated() -> None:
    """Malformed envelope shouldn't crash the parser."""
    body = {"error": {"code": 123, "message": ["nope"]}}
    with pytest.raises(XagentApiError) as excinfo:
        raise_for_error(400, body)
    assert excinfo.value.code == "unknown"
    assert excinfo.value.message is None
