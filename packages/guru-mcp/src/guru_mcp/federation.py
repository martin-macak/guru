from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
from pathlib import Path

from guru_core.client import GuruClient

logger = logging.getLogger(__name__)

FEDERATED_TIMEOUT = 3.0


class FederatedSearcher:
    """Fan out search queries to local index + federation peers."""

    def __init__(
        self,
        local_client: GuruClient,
        local_name: str,
        peers: list[dict],
        timeout: float = FEDERATED_TIMEOUT,
    ):
        self.local_client = local_client
        self.local_name = local_name
        self.peers = peers
        self.timeout = timeout

    async def search(
        self,
        query: str,
        n_results: int = 10,
        filters: dict | None = None,
        group_by_server: bool = True,
    ) -> dict:
        """Search local index and all peers in parallel."""
        tasks: dict[str, asyncio.Task] = {}

        async def _local_search():
            return await self.local_client.search(query, n_results, filters)

        tasks[self.local_name] = asyncio.create_task(_local_search())

        for peer in self.peers:
            name = peer["name"]
            socket = peer["socket"]

            async def _peer_search(s=socket):
                client = GuruClient.from_socket(s)
                return await client.search(query, n_results, filters)

            tasks[name] = asyncio.create_task(_peer_search())

        results_by_server: dict[str, list] = {}
        unreachable: list[str] = []

        for name, task in tasks.items():
            try:
                result = await asyncio.wait_for(task, timeout=self.timeout)
                results_by_server[name] = result
            except (TimeoutError, Exception) as exc:
                logger.warning("Peer '%s' unreachable: %s", name, exc)
                unreachable.append(name)
                task.cancel()

        if group_by_server:
            return {"results": results_by_server, "unreachable": unreachable}

        merged = []
        for server_name, items in results_by_server.items():
            for item in items:
                merged.append({**item, "server": server_name})
        merged.sort(key=lambda r: r.get("score", 0), reverse=True)

        return {"results": merged, "unreachable": unreachable}


class CodebaseCloner:
    """Handles codebase cloning and unmounting for federation."""

    def __init__(self, local_project_root: Path):
        self.local_project_root = local_project_root
        self.federated_dir = local_project_root / ".guru" / "federated"

    def clone(self, server_name: str, remote_project_root: str) -> str:
        """Clone a peer's codebase locally.

        Returns the local path to the cloned codebase.
        """
        remote_root = Path(remote_project_root)
        if not remote_root.is_dir():
            raise FileNotFoundError(f"Peer project root does not exist: {remote_project_root}")

        dest = self.federated_dir / server_name

        if dest.exists():
            shutil.rmtree(dest)

        self.federated_dir.mkdir(parents=True, exist_ok=True)

        try:
            file_list = self._get_file_list(remote_root)
            self._copy_files(remote_root, dest, file_list)
        except Exception:
            if dest.exists():
                shutil.rmtree(dest)
            raise

        return str(dest)

    def unmount(self, server_name: str) -> None:
        """Remove a cloned codebase. Idempotent."""
        dest = self.federated_dir / server_name
        if dest.exists():
            shutil.rmtree(dest)

    def _get_file_list(self, project_root: Path) -> list[str] | None:
        """Get tracked + unignored files via git. Returns None if git unavailable."""
        try:
            result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(project_root),
                    "ls-files",
                    "--cached",
                    "--others",
                    "--exclude-standard",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                return [f for f in result.stdout.strip().split("\n") if f]
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        logger.warning("git ls-files unavailable, using simple exclusion filter")
        return None

    def _copy_files(self, src: Path, dest: Path, file_list: list[str] | None) -> None:
        """Copy files respecting file list or simple filter."""
        if file_list is not None:
            for rel_path in file_list:
                src_file = src / rel_path
                if not src_file.is_file():
                    continue
                dest_file = dest / rel_path
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(src_file), str(dest_file))
        else:
            shutil.copytree(
                str(src),
                str(dest),
                ignore=shutil.ignore_patterns(".git", ".guru"),
            )
