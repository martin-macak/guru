from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from guru_core.graph_errors import GraphUnavailable
from guru_server.graph_integration import (
    build_graph_client_if_enabled,
    graph_or_skip,
    register_self_kb,
)


@pytest.mark.asyncio
async def test_graph_or_skip_returns_value_on_success():
    async def coro():
        return 42

    result = await graph_or_skip(coro(), feature="test_success")
    assert result == 42


@pytest.mark.asyncio
async def test_graph_or_skip_swallows_unavailable():
    async def coro():
        raise GraphUnavailable("down")

    result = await graph_or_skip(coro(), feature="test_unavailable")
    assert result is None


@pytest.mark.asyncio
async def test_graph_or_skip_swallows_unexpected_error():
    async def coro():
        raise RuntimeError("weird")

    result = await graph_or_skip(coro(), feature="test_weird")
    assert result is None


@pytest.mark.asyncio
async def test_register_self_kb_no_op_when_client_none():
    await register_self_kb(client=None, name="p", project_root="/p")


@pytest.mark.asyncio
async def test_register_self_kb_upserts_via_client():
    client = AsyncMock()
    await register_self_kb(client=client, name="p", project_root="/p")
    client.upsert_kb.assert_awaited_once()


def test_build_graph_client_disabled_returns_none():
    assert build_graph_client_if_enabled(graph_enabled=False) is None


def test_build_graph_client_enabled_returns_client():
    client = build_graph_client_if_enabled(graph_enabled=True)
    # guru-graph is installed in this workspace, so we expect a client.
    assert client is not None
