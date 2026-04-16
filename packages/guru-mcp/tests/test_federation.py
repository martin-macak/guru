from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from guru_mcp.federation import FederatedSearcher


@pytest.fixture
def local_client():
    client = AsyncMock()
    client.search.return_value = [
        {"file_path": "docs/local.md", "content": "local content", "score": 0.9, "labels": []},
    ]
    return client


@pytest.fixture
def peer_info():
    return {
        "name": "beta",
        "pid": 12345,
        "socket": "/tmp/beta.sock",
        "project_root": "/tmp/beta",
    }


class TestFederatedSearch:
    def test_grouped_results_include_local_and_peer(self, local_client, peer_info):
        peer_client = AsyncMock()
        peer_client.search.return_value = [
            {"file_path": "docs/remote.md", "content": "remote", "score": 0.8, "labels": []},
        ]

        searcher = FederatedSearcher(
            local_client=local_client,
            local_name="alpha",
            peers=[peer_info],
            timeout=3.0,
        )

        with patch("guru_mcp.federation.GuruClient.from_socket", return_value=peer_client):
            result = asyncio.run(searcher.search("test query", n_results=10, group_by_server=True))

        assert "alpha" in result["results"]
        assert "beta" in result["results"]
        assert len(result["unreachable"]) == 0

    def test_merged_results_are_flat_list(self, local_client, peer_info):
        peer_client = AsyncMock()
        peer_client.search.return_value = [
            {"file_path": "docs/remote.md", "content": "remote", "score": 0.8, "labels": []},
        ]

        searcher = FederatedSearcher(
            local_client=local_client,
            local_name="alpha",
            peers=[peer_info],
            timeout=3.0,
        )

        with patch("guru_mcp.federation.GuruClient.from_socket", return_value=peer_client):
            result = asyncio.run(
                searcher.search("test query", n_results=10, group_by_server=False)
            )

        assert isinstance(result["results"], list)
        assert all("server" in r for r in result["results"])

    def test_unreachable_peer_reported(self, local_client, peer_info):
        peer_client = AsyncMock()
        peer_client.search.side_effect = Exception("connection refused")

        searcher = FederatedSearcher(
            local_client=local_client,
            local_name="alpha",
            peers=[peer_info],
            timeout=3.0,
        )

        with patch("guru_mcp.federation.GuruClient.from_socket", return_value=peer_client):
            result = asyncio.run(searcher.search("test query", n_results=10, group_by_server=True))

        assert "alpha" in result["results"]
        assert "beta" in result["unreachable"]

    def test_timeout_marks_peer_unreachable(self, local_client, peer_info):
        async def slow_search(*args, **kwargs):
            await asyncio.sleep(10)
            return []

        peer_client = AsyncMock()
        peer_client.search = slow_search

        searcher = FederatedSearcher(
            local_client=local_client,
            local_name="alpha",
            peers=[peer_info],
            timeout=0.1,
        )

        with patch("guru_mcp.federation.GuruClient.from_socket", return_value=peer_client):
            result = asyncio.run(searcher.search("test query", n_results=10, group_by_server=True))

        assert "beta" in result["unreachable"]

    def test_no_peers_returns_local_only(self, local_client):
        searcher = FederatedSearcher(
            local_client=local_client,
            local_name="alpha",
            peers=[],
            timeout=3.0,
        )

        result = asyncio.run(searcher.search("test query", n_results=10, group_by_server=True))

        assert "alpha" in result["results"]
        assert len(result["unreachable"]) == 0

    def test_merged_results_sorted_by_score(self, local_client, peer_info):
        peer_client = AsyncMock()
        peer_client.search.return_value = [
            {"file_path": "docs/remote.md", "content": "remote", "score": 0.95, "labels": []},
        ]

        searcher = FederatedSearcher(
            local_client=local_client,
            local_name="alpha",
            peers=[peer_info],
            timeout=3.0,
        )

        with patch("guru_mcp.federation.GuruClient.from_socket", return_value=peer_client):
            result = asyncio.run(
                searcher.search("test query", n_results=10, group_by_server=False)
            )

        scores = [r["score"] for r in result["results"]]
        assert scores == sorted(scores, reverse=True)
