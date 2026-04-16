from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from guru_mcp.federation import CodebaseCloner, FederatedSearcher


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


class TestCodebaseCloner:
    @pytest.fixture
    def remote_project(self, tmp_path: Path) -> Path:
        """Create a fake remote project directory."""
        project = tmp_path / "remote-project"
        project.mkdir()
        (project / ".git").mkdir()
        (project / ".guru").mkdir()
        (project / "src").mkdir()
        (project / "src" / "main.py").write_text("print('hello')")
        (project / "README.md").write_text("# Remote Project")
        (project / "build.pyc").write_text("bytecode")

        # Set up git repo so ls-files works
        import subprocess

        subprocess.run(["git", "init"], cwd=str(project), capture_output=True)
        subprocess.run(
            ["git", "-C", str(project), "config", "user.email", "test@test.com"],
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(project), "config", "user.name", "Test"],
            capture_output=True,
        )
        # Add .gitignore
        (project / ".gitignore").write_text("*.pyc\n.guru/\n")
        subprocess.run(["git", "-C", str(project), "add", "."], capture_output=True)
        subprocess.run(
            ["git", "-C", str(project), "commit", "-m", "init"],
            capture_output=True,
        )
        return project

    @pytest.fixture
    def cloner(self, tmp_path: Path) -> CodebaseCloner:
        local_project = tmp_path / "local-project"
        local_project.mkdir()
        (local_project / ".guru").mkdir()
        return CodebaseCloner(local_project_root=local_project)

    def test_clone_copies_tracked_files(self, cloner, remote_project):
        path = cloner.clone("beta", str(remote_project))
        assert Path(path, "src", "main.py").exists()
        assert Path(path, "README.md").exists()

    def test_clone_excludes_git_directory(self, cloner, remote_project):
        path = cloner.clone("beta", str(remote_project))
        assert not Path(path, ".git").exists()

    def test_clone_excludes_guru_directory(self, cloner, remote_project):
        path = cloner.clone("beta", str(remote_project))
        assert not Path(path, ".guru").exists()

    def test_clone_excludes_gitignored_files(self, cloner, remote_project):
        path = cloner.clone("beta", str(remote_project))
        assert not Path(path, "build.pyc").exists()

    def test_clone_returns_path(self, cloner, remote_project):
        path = cloner.clone("beta", str(remote_project))
        assert "federated" in path
        assert "beta" in path

    def test_unmount_removes_directory(self, cloner, remote_project):
        cloner.clone("beta", str(remote_project))
        cloner.unmount("beta")
        assert not Path(cloner.federated_dir / "beta").exists()

    def test_unmount_idempotent(self, cloner):
        cloner.unmount("nonexistent")  # should not raise

    def test_clone_unknown_project_raises(self, cloner):
        with pytest.raises(FileNotFoundError):
            cloner.clone("bad", "/nonexistent/path")

    def test_clone_overwrites_stale(self, cloner, remote_project):
        cloner.clone("beta", str(remote_project))
        (remote_project / "new_file.txt").write_text("new content")
        import subprocess

        subprocess.run(
            ["git", "-C", str(remote_project), "add", "new_file.txt"],
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(remote_project), "commit", "-m", "add new"],
            capture_output=True,
        )
        path = cloner.clone("beta", str(remote_project))
        assert Path(path, "new_file.txt").exists()
