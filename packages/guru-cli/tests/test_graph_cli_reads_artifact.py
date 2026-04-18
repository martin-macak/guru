"""Tests for the artifact-graph read-only subcommands.

Covers:
  guru graph describe NODE_ID
  guru graph neighbors NODE_ID
  guru graph find ...
  guru graph annotations NODE_ID
  guru graph orphans

For each command we verify:
  - text-mode happy path
  - --json output
  - empty result rendering
  - GraphUnavailable -> exit 1, "daemon: unreachable" on stderr
  - graph-disabled short-circuit -> exit 0, "graph is disabled" on stdout
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

import guru_cli.commands.graph as graph_module
from guru_cli.commands.graph import graph_group
from guru_core.graph_errors import GraphUnavailable
from guru_core.graph_types import (
    AnnotationKind,
    AnnotationNode,
    ArtifactNeighborsResult,
    ArtifactNode,
    GraphEdgePayload,
    OrphanAnnotation,
)

_NOW = datetime(2026, 4, 18, 5, 11, 13, tzinfo=UTC)


def _artifact_node(
    id: str = "kb::a",
    label: str = "Document",
    properties: dict[str, Any] | None = None,
    annotations: list[AnnotationNode] | None = None,
    links_out: list | None = None,
    links_in: list | None = None,
) -> ArtifactNode:
    return ArtifactNode(
        id=id,
        label=label,
        properties=properties or {"kb_name": "kb"},
        annotations=annotations or [],
        links_out=links_out or [],
        links_in=links_in or [],
    )


def _annotation(
    id: str = "ann1",
    target_id: str | None = "kb::a",
    target_label: str | None = "Document",
    kind: AnnotationKind = AnnotationKind.NOTE,
    body: str = "hello",
    author: str = "alice",
) -> AnnotationNode:
    return AnnotationNode(
        id=id,
        target_id=target_id,
        target_label=target_label,
        kind=kind,
        body=body,
        tags=[],
        author=author,
        created_at=_NOW,
        updated_at=_NOW,
        target_snapshot_json="{}",
    )


def _orphan(
    id: str = "orph1",
    kind: AnnotationKind = AnnotationKind.NOTE,
    body: str = "stale note",
    author: str = "bob",
) -> OrphanAnnotation:
    return OrphanAnnotation(
        id=id,
        kind=kind,
        body=body,
        tags=[],
        author=author,
        created_at=_NOW,
        updated_at=_NOW,
        target_snapshot_json="{}",
    )


def _edge(
    from_id: str = "kb::a",
    to_id: str = "kb::b",
    rel_type: str = "RELATES",
    kind: str | None = "imports",
) -> GraphEdgePayload:
    return GraphEdgePayload(
        from_id=from_id,
        to_id=to_id,
        rel_type=rel_type,
        kind=kind,
        properties={},
    )


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def mock_client():
    with patch("guru_cli.commands.graph._client") as f:
        client = AsyncMock()
        f.return_value = client
        yield client


@pytest.fixture
def disable_graph_check(monkeypatch):
    """Make sure the graph-disabled pre-flight is a no-op for tests that
    care about the daemon path, not the graph-disabled exit-0 path."""
    monkeypatch.setattr(graph_module, "_exit_if_graph_disabled", lambda: None)


@pytest.fixture
def force_graph_disabled(monkeypatch):
    """Force the pre-flight to print + exit 0 as if the project opted out."""

    def _disabled() -> None:
        import click

        click.echo("graph is disabled")
        sys.exit(0)

    monkeypatch.setattr(graph_module, "_exit_if_graph_disabled", _disabled)


# ---- describe ----


def test_describe_text(runner, mock_client, disable_graph_check):
    mock_client.describe_artifact = AsyncMock(
        return_value=_artifact_node(
            id="kb::doc",
            properties={"kb_name": "polyglot", "language": "markdown"},
            annotations=[_annotation()],
            links_out=[],
        )
    )
    result = runner.invoke(graph_group, ["describe", "kb::doc"])
    assert result.exit_code == 0, result.output
    assert "id:" in result.output and "kb::doc" in result.output
    assert "Document" in result.output
    assert "kb_name=polyglot" in result.output
    assert "annotations: 1" in result.output
    mock_client.describe_artifact.assert_awaited_once_with(node_id="kb::doc")


def test_describe_json(runner, mock_client, disable_graph_check):
    mock_client.describe_artifact = AsyncMock(return_value=_artifact_node(id="kb::doc"))
    result = runner.invoke(graph_group, ["describe", "kb::doc", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["id"] == "kb::doc"
    assert data["label"] == "Document"


def test_describe_not_found(runner, mock_client, disable_graph_check):
    mock_client.describe_artifact = AsyncMock(return_value=None)
    result = runner.invoke(graph_group, ["describe", "kb::ghost"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_describe_graph_unavailable(runner, mock_client, disable_graph_check):
    mock_client.describe_artifact = AsyncMock(side_effect=GraphUnavailable("boom"))
    result = runner.invoke(graph_group, ["describe", "kb::doc"])
    assert result.exit_code == 1
    assert "daemon: unreachable" in result.output


def test_describe_graph_disabled(runner, force_graph_disabled, mock_client):
    mock_client.describe_artifact = AsyncMock()
    result = runner.invoke(graph_group, ["describe", "kb::doc"])
    assert result.exit_code == 0
    assert "graph is disabled" in result.output
    mock_client.describe_artifact.assert_not_awaited()


# ---- neighbors ----


def test_neighbors_text(runner, mock_client, disable_graph_check):
    res = ArtifactNeighborsResult(
        node_id="kb::a",
        nodes=[_artifact_node(id="kb::a"), _artifact_node(id="kb::b", label="Module")],
        edges=[_edge(from_id="kb::a", to_id="kb::b", rel_type="RELATES", kind="imports")],
    )
    mock_client.neighbors = AsyncMock(return_value=res)
    result = runner.invoke(graph_group, ["neighbors", "kb::a"])
    assert result.exit_code == 0, result.output
    assert "kb::b" in result.output
    assert "Module" in result.output
    assert "RELATES" in result.output
    assert "imports" in result.output
    mock_client.neighbors.assert_awaited_once_with(
        node_id="kb::a",
        direction="both",
        rel_type="both",
        kind=None,
        depth=1,
        limit=50,
    )


def test_neighbors_empty(runner, mock_client, disable_graph_check):
    res = ArtifactNeighborsResult(node_id="kb::a", nodes=[], edges=[])
    mock_client.neighbors = AsyncMock(return_value=res)
    result = runner.invoke(graph_group, ["neighbors", "kb::a"])
    assert result.exit_code == 0, result.output
    assert "no neighbors" in result.output


def test_neighbors_json(runner, mock_client, disable_graph_check):
    res = ArtifactNeighborsResult(
        node_id="kb::a",
        nodes=[_artifact_node(id="kb::b")],
        edges=[_edge()],
    )
    mock_client.neighbors = AsyncMock(return_value=res)
    result = runner.invoke(graph_group, ["neighbors", "kb::a", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["node_id"] == "kb::a"
    assert data["edges"][0]["kind"] == "imports"


def test_neighbors_filter_options(runner, mock_client, disable_graph_check):
    res = ArtifactNeighborsResult(node_id="kb::a", nodes=[], edges=[])
    mock_client.neighbors = AsyncMock(return_value=res)
    result = runner.invoke(
        graph_group,
        [
            "neighbors",
            "kb::a",
            "--direction",
            "out",
            "--rel-type",
            "RELATES",
            "--kind",
            "imports",
            "--depth",
            "2",
            "--limit",
            "10",
        ],
    )
    assert result.exit_code == 0, result.output
    mock_client.neighbors.assert_awaited_once_with(
        node_id="kb::a",
        direction="out",
        rel_type="RELATES",
        kind="imports",
        depth=2,
        limit=10,
    )


def test_neighbors_invalid_direction_rejected(runner, mock_client, disable_graph_check):
    mock_client.neighbors = AsyncMock()
    result = runner.invoke(graph_group, ["neighbors", "kb::a", "--direction", "sideways"])
    assert result.exit_code != 0
    mock_client.neighbors.assert_not_awaited()


def test_neighbors_graph_unavailable(runner, mock_client, disable_graph_check):
    mock_client.neighbors = AsyncMock(side_effect=GraphUnavailable("boom"))
    result = runner.invoke(graph_group, ["neighbors", "kb::a"])
    assert result.exit_code == 1
    assert "daemon: unreachable" in result.output


def test_neighbors_graph_disabled(runner, force_graph_disabled, mock_client):
    mock_client.neighbors = AsyncMock()
    result = runner.invoke(graph_group, ["neighbors", "kb::a"])
    assert result.exit_code == 0
    assert "graph is disabled" in result.output
    mock_client.neighbors.assert_not_awaited()


# ---- find ----


def test_find_text(runner, mock_client, disable_graph_check):
    mock_client.find_artifacts = AsyncMock(
        return_value=[
            _artifact_node(id="kb::a", label="Module", properties={"kb_name": "kb"}),
            _artifact_node(id="kb::b", label="Document", properties={"kb_name": "kb"}),
        ]
    )
    result = runner.invoke(graph_group, ["find", "--label", "Document"])
    assert result.exit_code == 0, result.output
    assert "kb::a" in result.output and "kb::b" in result.output
    assert "Module" in result.output and "Document" in result.output
    call = mock_client.find_artifacts.await_args
    q = call.args[0]
    assert q.label == "Document"
    assert q.limit == 50


def test_find_empty(runner, mock_client, disable_graph_check):
    mock_client.find_artifacts = AsyncMock(return_value=[])
    result = runner.invoke(graph_group, ["find", "--name", "ghost"])
    assert result.exit_code == 0, result.output
    assert "no matches" in result.output


def test_find_json(runner, mock_client, disable_graph_check):
    mock_client.find_artifacts = AsyncMock(return_value=[_artifact_node(id="kb::a")])
    result = runner.invoke(graph_group, ["find", "--label", "Document", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert data[0]["id"] == "kb::a"


def test_find_filter_options_passed_through(runner, mock_client, disable_graph_check):
    mock_client.find_artifacts = AsyncMock(return_value=[])
    result = runner.invoke(
        graph_group,
        [
            "find",
            "--name",
            "foo",
            "--qualname-prefix",
            "pkg.mod",
            "--label",
            "Function",
            "--tag",
            "core",
            "--kb-name",
            "polyglot",
            "--limit",
            "7",
        ],
    )
    assert result.exit_code == 0, result.output
    q = mock_client.find_artifacts.await_args.args[0]
    assert q.name == "foo"
    assert q.qualname_prefix == "pkg.mod"
    assert q.label == "Function"
    assert q.tag == "core"
    assert q.kb_name == "polyglot"
    assert q.limit == 7


def test_find_graph_unavailable(runner, mock_client, disable_graph_check):
    mock_client.find_artifacts = AsyncMock(side_effect=GraphUnavailable("boom"))
    result = runner.invoke(graph_group, ["find", "--label", "Document"])
    assert result.exit_code == 1
    assert "daemon: unreachable" in result.output


def test_find_graph_disabled(runner, force_graph_disabled, mock_client):
    mock_client.find_artifacts = AsyncMock()
    result = runner.invoke(graph_group, ["find"])
    assert result.exit_code == 0
    assert "graph is disabled" in result.output
    mock_client.find_artifacts.assert_not_awaited()


# ---- annotations ----


def test_annotations_text(runner, mock_client, disable_graph_check):
    mock_client.describe_artifact = AsyncMock(
        return_value=_artifact_node(
            id="kb::doc",
            annotations=[
                _annotation(id="ann1", body="first"),
                _annotation(id="ann2", body="second"),
            ],
        )
    )
    result = runner.invoke(graph_group, ["annotations", "kb::doc"])
    assert result.exit_code == 0, result.output
    assert "ann1" in result.output and "ann2" in result.output
    assert "first" in result.output and "second" in result.output


def test_annotations_empty(runner, mock_client, disable_graph_check):
    mock_client.describe_artifact = AsyncMock(
        return_value=_artifact_node(id="kb::doc", annotations=[])
    )
    result = runner.invoke(graph_group, ["annotations", "kb::doc"])
    assert result.exit_code == 0, result.output
    assert "no annotations" in result.output


def test_annotations_json(runner, mock_client, disable_graph_check):
    mock_client.describe_artifact = AsyncMock(
        return_value=_artifact_node(id="kb::doc", annotations=[_annotation(id="ann1")])
    )
    result = runner.invoke(graph_group, ["annotations", "kb::doc", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert data[0]["id"] == "ann1"


def test_annotations_not_found(runner, mock_client, disable_graph_check):
    mock_client.describe_artifact = AsyncMock(return_value=None)
    result = runner.invoke(graph_group, ["annotations", "kb::ghost"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_annotations_graph_unavailable(runner, mock_client, disable_graph_check):
    mock_client.describe_artifact = AsyncMock(side_effect=GraphUnavailable("boom"))
    result = runner.invoke(graph_group, ["annotations", "kb::doc"])
    assert result.exit_code == 1
    assert "daemon: unreachable" in result.output


def test_annotations_graph_disabled(runner, force_graph_disabled, mock_client):
    mock_client.describe_artifact = AsyncMock()
    result = runner.invoke(graph_group, ["annotations", "kb::doc"])
    assert result.exit_code == 0
    assert "graph is disabled" in result.output
    mock_client.describe_artifact.assert_not_awaited()


# ---- orphans ----


def test_orphans_text(runner, mock_client, disable_graph_check):
    mock_client.list_orphans = AsyncMock(
        return_value=[_orphan(id="orph1"), _orphan(id="orph2", body="another")]
    )
    result = runner.invoke(graph_group, ["orphans"])
    assert result.exit_code == 0, result.output
    assert "orph1" in result.output and "orph2" in result.output
    mock_client.list_orphans.assert_awaited_once_with(limit=50)


def test_orphans_empty(runner, mock_client, disable_graph_check):
    mock_client.list_orphans = AsyncMock(return_value=[])
    result = runner.invoke(graph_group, ["orphans"])
    assert result.exit_code == 0, result.output
    assert "no orphans" in result.output


def test_orphans_json(runner, mock_client, disable_graph_check):
    mock_client.list_orphans = AsyncMock(return_value=[_orphan(id="orph1")])
    result = runner.invoke(graph_group, ["orphans", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert data[0]["id"] == "orph1"


def test_orphans_limit_flag(runner, mock_client, disable_graph_check):
    mock_client.list_orphans = AsyncMock(return_value=[])
    result = runner.invoke(graph_group, ["orphans", "--limit", "3"])
    assert result.exit_code == 0, result.output
    mock_client.list_orphans.assert_awaited_once_with(limit=3)


def test_orphans_graph_unavailable(runner, mock_client, disable_graph_check):
    mock_client.list_orphans = AsyncMock(side_effect=GraphUnavailable("boom"))
    result = runner.invoke(graph_group, ["orphans"])
    assert result.exit_code == 1
    assert "daemon: unreachable" in result.output


def test_orphans_graph_disabled(runner, force_graph_disabled, mock_client):
    mock_client.list_orphans = AsyncMock()
    result = runner.invoke(graph_group, ["orphans"])
    assert result.exit_code == 0
    assert "graph is disabled" in result.output
    mock_client.list_orphans.assert_not_awaited()


# ---- _exit_if_graph_disabled helper unit-tests ----


def test_exit_if_graph_disabled_noop_when_no_project(monkeypatch, capsys):
    """When we cannot resolve a guru project, fall through silently."""
    from guru_core.discovery import GuruNotFoundError

    monkeypatch.setattr(
        "guru_cli.commands.graph.find_guru_root",
        lambda _p: (_ for _ in ()).throw(GuruNotFoundError("nope")),
        raising=False,
    )
    # Real call shouldn't raise, even when not in a project.
    graph_module._exit_if_graph_disabled()
    out = capsys.readouterr()
    assert out.out == ""
    assert out.err == ""


def test_exit_if_graph_disabled_exits_when_disabled(monkeypatch, capsys, tmp_path):
    """If config explicitly sets graph.enabled=false, exit 0 + stdout msg."""
    from guru_core.types import GraphConfig, GuruConfig

    fake_root = tmp_path
    monkeypatch.setattr("guru_cli.commands.graph.find_guru_root", lambda _p: fake_root)
    monkeypatch.setattr(
        "guru_cli.commands.graph.resolve_config",
        lambda *, project_root: GuruConfig(
            version=1,
            rules=[],
            graph=GraphConfig(enabled=False),
        ),
    )
    with pytest.raises(SystemExit) as exc:
        graph_module._exit_if_graph_disabled()
    assert exc.value.code == 0
    out = capsys.readouterr()
    assert "graph is disabled" in out.out


def test_exit_if_graph_disabled_falls_through_when_enabled(monkeypatch, capsys, tmp_path):
    from guru_core.types import GraphConfig, GuruConfig

    fake_root = tmp_path
    monkeypatch.setattr("guru_cli.commands.graph.find_guru_root", lambda _p: fake_root)
    monkeypatch.setattr(
        "guru_cli.commands.graph.resolve_config",
        lambda *, project_root: GuruConfig(
            version=1,
            rules=[],
            graph=GraphConfig(enabled=True),
        ),
    )
    graph_module._exit_if_graph_disabled()  # must not raise
    assert capsys.readouterr().out == ""
