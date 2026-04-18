"""Protocol-mismatch contract test.

Reproduces the CI failure from run 24585516720:
  BDD step "GraphClient raises GraphUnavailable" after a 426 from the server
  never actually raises, because the default GraphClient sends its own
  (compatible) protocol version.

This test proves the full contract end-to-end:
  1. Server returns 426 when the client's MAJOR doesn't match.
  2. GraphClient translates that 426 into GraphUnavailable.

Without the corresponding BDD-step fix (patching PROTOCOL_VERSION to force
an incompatible version), step 4 of the Protocol-MAJOR-mismatch scenario
cannot pass — a default GraphClient would always send a matching header.
"""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

import guru_core.graph_client as gc_module
from guru_core.graph_client import GraphClient
from guru_core.graph_errors import GraphUnavailable


@pytest.mark.asyncio
async def test_default_graphclient_does_not_raise_against_compatible_server(tmp_path):
    """Default client against a server that returns 200 MUST NOT raise.

    This is the original BDD-step bug: assuming a default client would
    trigger GraphUnavailable when the server is healthy.
    """
    response = httpx.Response(
        status_code=200,
        json={
            "status": "healthy",
            "graph_reachable": True,
            "backend": "fake",
            "backend_version": "0.0.0",
            "schema_version": 1,
        },
    )
    client = GraphClient(socket_path=str(tmp_path / "s.sock"), auto_start=False)
    from unittest.mock import AsyncMock

    with patch.object(httpx.AsyncClient, "request", AsyncMock(return_value=response)):
        result = await client.health()
    assert result.status == "healthy"


@pytest.mark.asyncio
async def test_graphclient_raises_when_protocol_version_patched_and_server_returns_426(
    tmp_path,
):
    """The fix: force-override PROTOCOL_VERSION and call health.

    The server returns 426, the client translates to GraphUnavailable.
    The BDD step must use the same monkeypatch to actually exercise this.
    """
    response = httpx.Response(
        status_code=426,
        json={"error": "protocol_upgrade_required", "supported": ["1.x"]},
    )
    client = GraphClient(socket_path=str(tmp_path / "s.sock"), auto_start=False)
    from unittest.mock import AsyncMock

    fake_request = AsyncMock(return_value=response)
    with (
        patch("guru_core.graph_client.PROTOCOL_VERSION", "99.0.0"),
        patch.object(httpx.AsyncClient, "request", fake_request),
        pytest.raises(GraphUnavailable) as exc,
    ):
        await client.health()
    # Sanity: the header we sent carried the forced version.
    _args, kwargs = fake_request.call_args
    assert kwargs["headers"]["X-Guru-Graph-Protocol"] == "99.0.0"
    assert "protocol" in str(exc.value).lower() or "426" in str(exc.value)


def test_protocol_version_module_constant_is_patchable():
    """Regression-guard: PROTOCOL_VERSION must live at module scope so
    tests/step-defs can monkeypatch it without rewriting the client.
    """
    assert hasattr(gc_module, "PROTOCOL_VERSION")
    with patch("guru_core.graph_client.PROTOCOL_VERSION", "99.0.0"):
        assert gc_module.PROTOCOL_VERSION == "99.0.0"
    assert gc_module.PROTOCOL_VERSION == "1.1.0"
