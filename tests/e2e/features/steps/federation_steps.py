"""Step definitions for federation scenarios.

Covers:
  - Federation discovery and lifecycle (federation_discovery.feature)
  - Federated search (federation_search.feature)
  - Codebase cloning (federation_clone.feature)
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import httpx
from behave import given, then, when

from guru_core.client import GuruClient
from guru_mcp.federation import CodebaseCloner, FederatedSearcher

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


def _trigger_and_wait_index_for(project_dir: Path, timeout: float = 30.0) -> None:
    """Trigger indexing on a federation server and wait for completion."""
    socket_path = str(project_dir / ".guru" / "guru.sock")
    transport = httpx.HTTPTransport(uds=socket_path)
    with httpx.Client(transport=transport, timeout=10.0) as client:
        client.post("http://localhost/index", json={})

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            transport = httpx.HTTPTransport(uds=socket_path)
            with httpx.Client(transport=transport, timeout=5.0) as client:
                resp = client.get("http://localhost/status")
                data = resp.json()
                if data.get("current_job") is None:
                    return
        except Exception:
            pass
        time.sleep(0.3)
    raise RuntimeError(f"Index for {project_dir.name} did not complete within {timeout}s")


def _start_named_server(context, name: str) -> None:
    """Create project, start server, register in federation — idempotent."""
    if name in context.servers:
        return  # already running

    from environment import _create_federation_project, _start_federation_server

    project_dir = _create_federation_project(name, context.fed_base_dir, context.fed_dir)
    server, thread, registry = _start_federation_server(
        project_dir, context.embedder, context.fed_dir
    )
    context.servers[name] = (server, thread)
    context.registries[name] = registry
    context.fed_project_dirs[name] = project_dir


# ---------------------------------------------------------------------------
# GIVEN steps
# ---------------------------------------------------------------------------


@given('a running guru server "{name}"')
def step_start_single_server(context, name):
    """Create and start a single named federation server."""
    _start_named_server(context, name)


@given('running guru servers "{names}" with indexed documents')
def step_start_indexed_servers(context, names):
    """Create and start multiple named federation servers, each with indexed docs."""
    server_names = [n.strip() for n in names.split(",")]
    for name in server_names:
        _start_named_server(context, name)

    # Trigger and wait for indexing on each server
    for name in server_names:
        project_dir = context.fed_project_dirs[name]
        _trigger_and_wait_index_for(project_dir)


@given('a stale discovery file "{filename}" with a non-running PID')
def step_create_stale_discovery(context, filename):
    """Write a discovery file with a non-running PID (999999999)."""
    stale_data = {
        "name": filename.replace(".json", ""),
        "pid": 999999999,
        "socket": "/tmp/nonexistent-dead-project.sock",
        "project_root": "/tmp/nonexistent-dead-project",
        "started_at": "2000-01-01T00:00:00+00:00",
    }
    context.fed_dir.mkdir(parents=True, exist_ok=True)
    (context.fed_dir / filename).write_text(json.dumps(stale_data, indent=2))


# ---------------------------------------------------------------------------
# WHEN steps
# ---------------------------------------------------------------------------


@when('"{client}" performs a federated search for "{query}"')
def step_federated_search(context, client, query):
    """Fan out search from the named client server to all live peers."""
    registry = context.registries[client]
    project_dir = context.fed_project_dirs[client]
    peers = registry.list_peers()

    local_client = GuruClient.from_socket(str(project_dir / ".guru" / "guru.sock"))
    searcher = FederatedSearcher(
        local_client=local_client,
        local_name=client,
        peers=peers,
        timeout=5.0,
    )
    context.fed_result = _run(searcher.search(query, n_results=10, group_by_server=True))


@when('"{client}" performs a federated search for "{query}" with merge enabled')
def step_federated_search_merged(context, client, query):
    """Fan out search with group_by_server=False (merged ranked list)."""
    registry = context.registries[client]
    project_dir = context.fed_project_dirs[client]
    peers = registry.list_peers()

    local_client = GuruClient.from_socket(str(project_dir / ".guru" / "guru.sock"))
    searcher = FederatedSearcher(
        local_client=local_client,
        local_name=client,
        peers=peers,
        timeout=5.0,
    )
    context.fed_result = _run(searcher.search(query, n_results=10, group_by_server=False))


@when("the maintenance sweep runs")
def step_maintenance_sweep(context):
    """Run registry.sweep() on any available server registry."""
    # Pick any registry in the test context — sweep is side-effect on the fed_dir
    for _name, registry in context.registries.items():
        registry.sweep()
        return
    raise AssertionError("No federation registry available to run sweep")


@when('"{client}" clones the codebase of "{server}"')
def step_clone_codebase(context, client, server):
    """Clone the named server's project root into the client's federated dir."""
    client_project_dir = context.fed_project_dirs[client]
    server_project_dir = context.fed_project_dirs[server]

    cloner = CodebaseCloner(local_project_root=client_project_dir)
    clone_path = cloner.clone(
        server_name=server,
        remote_project_root=str(server_project_dir),
    )
    context.clone_path = clone_path


@when('"{client}" unmounts the codebase of "{server}"')
def step_unmount_codebase(context, client, server):
    """Remove the cloned codebase of the named server from the client."""
    client_project_dir = context.fed_project_dirs[client]
    cloner = CodebaseCloner(local_project_root=client_project_dir)
    cloner.unmount(server_name=server)


# ---------------------------------------------------------------------------
# THEN steps
# ---------------------------------------------------------------------------


@then('a discovery file "{filename}" exists in the federation directory')
def step_discovery_file_exists(context, filename):
    """Assert that a discovery file exists in the federation directory."""
    discovery_path = context.fed_dir / filename
    assert discovery_path.exists(), (
        f"Discovery file '{filename}' not found in {context.fed_dir}. "
        f"Files present: {list(context.fed_dir.iterdir()) if context.fed_dir.exists() else []}"
    )


@then('the discovery file "{filename}" is removed')
def step_discovery_file_removed(context, filename):
    """Assert that a discovery file is absent from the federation directory."""
    discovery_path = context.fed_dir / filename
    assert not discovery_path.exists(), (
        f"Discovery file '{filename}' still exists in {context.fed_dir} after sweep"
    )


@then('results include matches from both "{a}" and "{b}"')
def step_results_from_both_servers(context, a, b):
    """Assert the grouped result dict has non-empty entries for both servers."""
    result = context.fed_result
    results_section = result.get("results", {})
    assert isinstance(results_section, dict), (
        f"Expected grouped results dict, got: {type(results_section)}: {results_section}"
    )
    a_results = results_section.get(a, [])
    b_results = results_section.get(b, [])
    assert len(a_results) > 0, (
        f"No results from server '{a}'. Keys present: {list(results_section.keys())}"
    )
    assert len(b_results) > 0, (
        f"No results from server '{b}'. Keys present: {list(results_section.keys())}"
    )


@then('results are grouped under "{a}" and "{b}" keys')
def step_results_grouped_by_server(context, a, b):
    """Assert the result has a dict 'results' with keys for both servers."""
    result = context.fed_result
    results_section = result.get("results", {})
    assert isinstance(results_section, dict), (
        f"Expected dict under 'results', got {type(results_section)}: {results_section}"
    )
    assert a in results_section, (
        f"Key '{a}' missing from results. Keys: {list(results_section.keys())}"
    )
    assert b in results_section, (
        f"Key '{b}' missing from results. Keys: {list(results_section.keys())}"
    )


@then("results are returned as a single ranked list")
def step_results_are_merged_list(
    context,
):
    """Assert the result's 'results' section is a list (merged mode)."""
    result = context.fed_result
    results_section = result.get("results", None)
    assert isinstance(results_section, list), (
        f"Expected merged list under 'results', got {type(results_section)}: {results_section}"
    )
    assert len(results_section) > 0, "Merged results list is empty"


@then("the clone path is returned to the caller")
def step_clone_path_returned(context):
    """Assert context.clone_path was set and the directory exists."""
    assert hasattr(context, "clone_path"), "clone_path was not set by the WHEN step"
    clone_path = Path(context.clone_path)
    assert clone_path.exists(), f"Clone path does not exist: {clone_path}"
    assert clone_path.is_dir(), f"Clone path is not a directory: {clone_path}"


@then("the cloned codebase directory does not exist")
def step_cloned_dir_does_not_exist(context):
    """Assert the previously cloned directory was removed."""
    assert hasattr(context, "clone_path"), "clone_path was not set — clone step must run first"
    clone_path = Path(context.clone_path)
    assert not clone_path.exists(), (
        f"Cloned codebase directory still exists after unmount: {clone_path}"
    )
