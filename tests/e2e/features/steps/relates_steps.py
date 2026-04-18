"""Step definitions for artifact_links.feature (Document-scoped scenarios).

The @real_neo4j scenarios interact with a running guru-graph daemon via
GraphClient, seeding two Document nodes via submit_parse_result so that
both link endpoints exist (the create_link path 404s otherwise).

The default-suite scenarios (invalid kind on POST/DELETE) use a
FakeBackend-backed TestClient directly — no daemon needed — to verify
the Pydantic enum validation returns 422.

The "Then the response status is {code:d}" step is intentionally NOT
redefined here; it lives in `annotation_steps.py` and behave picks up
step definitions from all `steps/*.py` files automatically.
"""

from __future__ import annotations

import asyncio

from behave import given, then, when
from fastapi.testclient import TestClient

from guru_core.graph_client import GraphClient
from guru_core.graph_errors import GraphUnavailable
from guru_core.graph_types import (
    ArtifactLinkCreate,
    ArtifactLinkKind,
    GraphEdgePayload,
    GraphNodePayload,
    KbUpsert,
    ParseResultPayload,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _graph_client(context) -> GraphClient:
    """Return a GraphClient pointed at the daemon socket set up by before_feature.

    `auto_start=True` lets the client spawn a guru-graph daemon on first call
    (via `connect_or_spawn`) when the test hasn't set one up explicitly. The
    daemon's HOME/XDG dirs are isolated under a per-feature tmpdir (see
    `tests/e2e/features/environment.py`).
    """
    from guru_graph.config import GraphPaths

    paths = GraphPaths.default()
    return GraphClient(socket_path=str(paths.socket), auto_start=True)


async def _seed_one_document(client: GraphClient, *, kb_name: str, doc_id: str) -> None:
    """POST a minimal ParseResultPayload for a single Document node."""
    payload = ParseResultPayload(
        chunks_count=1,
        document=GraphNodePayload(
            node_id=doc_id,
            label="Document",
            properties={"kb_name": kb_name, "language": "markdown"},
        ),
        nodes=[
            GraphNodePayload(
                node_id=f"{doc_id}::Overview",
                label="MarkdownSection",
                properties={"kb_name": kb_name, "breadcrumb": "Overview"},
            ),
        ],
        edges=[
            GraphEdgePayload(
                from_id=doc_id,
                to_id=f"{doc_id}::Overview",
                rel_type="CONTAINS",
            ),
        ],
    )
    await client.submit_parse_result(kb_name=kb_name, payload=payload)


async def _seed_two_documents(client: GraphClient) -> None:
    """Seed the polyglot KB with two Document nodes for link testing."""
    await client.upsert_kb(KbUpsert(name="polyglot", project_root="/tmp/polyglot"))
    await _seed_one_document(client, kb_name="polyglot", doc_id="polyglot::docs/guide.md")
    await _seed_one_document(client, kb_name="polyglot", doc_id="polyglot::docs/api.md")


async def _seed_py_class_and_openapi_schema(client: GraphClient) -> None:
    """Seed a minimal Python class + an OpenAPI schema under the polyglot KB.

    Used by the ``graph_link`` OpenAPI-contract scenario. We only need the
    two artifact node_ids to exist so ``create_link`` can resolve both
    endpoints — we do not emulate the full polyglot parse.
    """
    await client.upsert_kb(KbUpsert(name="polyglot", project_root="/tmp/polyglot"))

    # Python side: Document -> Module -> Class.
    py_payload = ParseResultPayload(
        chunks_count=1,
        document=GraphNodePayload(
            node_id="polyglot::src/pkg/services/user.py",
            label="Document",
            properties={"kb_name": "polyglot", "language": "python"},
        ),
        nodes=[
            GraphNodePayload(
                node_id="polyglot::pkg.services.user",
                label="Module",
                properties={"kb_name": "polyglot", "qualname": "pkg.services.user"},
            ),
            GraphNodePayload(
                node_id="polyglot::pkg.services.user.UserService",
                label="Class",
                properties={
                    "kb_name": "polyglot",
                    "qualname": "pkg.services.user.UserService",
                },
            ),
        ],
        edges=[
            GraphEdgePayload(
                from_id="polyglot::src/pkg/services/user.py",
                to_id="polyglot::pkg.services.user",
                rel_type="CONTAINS",
            ),
            GraphEdgePayload(
                from_id="polyglot::pkg.services.user",
                to_id="polyglot::pkg.services.user.UserService",
                rel_type="CONTAINS",
            ),
        ],
    )
    await client.submit_parse_result(kb_name="polyglot", payload=py_payload)

    # OpenAPI side: Document (the spec file) -> OpenApiSchema.
    #
    # Note: the document node uses label "Document" rather than the
    # parser-emitted "OpenApiSpec" because IngestService.submit funnels
    # ``payload.document`` through ``upsert_document``, which strictly
    # requires label="Document". For this BDD seed we only need the
    # ``components/schemas/UserResource`` node_id to exist as the link
    # target — its OpenApiSchema label is the load-bearing detail.
    oa_payload = ParseResultPayload(
        chunks_count=1,
        document=GraphNodePayload(
            node_id="polyglot::api/openapi.yaml",
            label="Document",
            properties={"kb_name": "polyglot", "language": "yaml"},
        ),
        nodes=[
            GraphNodePayload(
                node_id="polyglot::api/openapi.yaml::components/schemas/UserResource",
                label="OpenApiSchema",
                properties={
                    "kb_name": "polyglot",
                    "qualname": "api/openapi.yaml::components/schemas/UserResource",
                    "name": "UserResource",
                },
            ),
        ],
        edges=[
            GraphEdgePayload(
                from_id="polyglot::api/openapi.yaml",
                to_id="polyglot::api/openapi.yaml::components/schemas/UserResource",
                rel_type="CONTAINS",
            ),
        ],
    )
    await client.submit_parse_result(kb_name="polyglot", payload=oa_payload)


# ---------------------------------------------------------------------------
# GIVEN
# ---------------------------------------------------------------------------


@given("the polyglot fixture is indexed with two documents and graph enabled")
def step_index_two_documents(context):
    """Seed the graph daemon with two minimal polyglot Documents."""
    client = _graph_client(context)
    asyncio.run(_seed_two_documents(client))
    context.graph_client = client
    context.last_link = None
    context.last_delete_result = None
    context.last_exception = None


@given("the polyglot fixture has a Python class and an OpenAPI schema indexed with graph enabled")
def step_seed_class_and_schema(context):
    """Seed a UserService class + a UserResource schema via submit_parse_result.

    This is a minimal seed — not a full polyglot parse. We just need the two
    artifact node_ids to exist so ``graph_link`` can succeed.
    """
    client = _graph_client(context)
    asyncio.run(_seed_py_class_and_openapi_schema(client))
    context.graph_client = client
    context.last_link = None
    context.last_triple = None
    context.last_unlink_ok = None


# Note: `Given a running guru-graph daemon` is defined in `graph_steps.py`
# and reused here. behave loads step definitions from all `steps/*.py` files,
# and re-defining the same step text would raise AmbiguousStep.


# ---------------------------------------------------------------------------
# WHEN — link creation / deletion via GraphClient (daemon scenarios)
# ---------------------------------------------------------------------------


@when('I create a link from "{from_id}" to "{to_id}" with kind "{kind}"')
def step_create_link(context, from_id, to_id, kind):
    client: GraphClient = context.graph_client
    req = ArtifactLinkCreate(from_id=from_id, to_id=to_id, kind=ArtifactLinkKind(kind))
    link = asyncio.run(client.create_link(req, author="agent:test"))
    context.last_link = link


@when('I delete the link from "{from_id}" to "{to_id}" with kind "{kind}"')
def step_delete_link(context, from_id, to_id, kind):
    client: GraphClient = context.graph_client
    result = asyncio.run(
        client.delete_link(from_id=from_id, to_id=to_id, kind=ArtifactLinkKind(kind))
    )
    context.last_delete_result = result
    # Stash for the second-delete step.
    context.last_delete_triple = (from_id, to_id, kind)


@when('I attempt to create a link from "{from_id}" to "{to_id}" with kind "{kind}"')
def step_attempt_create_link(context, from_id, to_id, kind):
    client: GraphClient = context.graph_client
    req = ArtifactLinkCreate(from_id=from_id, to_id=to_id, kind=ArtifactLinkKind(kind))
    try:
        context.last_link = asyncio.run(client.create_link(req, author="agent:test"))
        context.last_exception = None
    except Exception as exc:
        context.last_exception = exc


# ---------------------------------------------------------------------------
# WHEN — default-suite (FakeBackend TestClient, no daemon)
# ---------------------------------------------------------------------------


def _seeded_test_client() -> TestClient:
    """Build a TestClient with two artifacts seeded so the request reaches the kind validator."""
    from guru_graph.app import create_app
    from guru_graph.testing import FakeBackend

    backend = FakeBackend()
    backend.start()
    backend.ensure_schema(target_version=1)
    backend.upsert_artifact(node_id="test::a", label="Document", properties={"kb_name": "test"})
    backend.upsert_artifact(node_id="test::b", label="Document", properties={"kb_name": "test"})
    return TestClient(create_app(backend=backend))


@when('I POST /relates with an invalid kind "{kind}"')
def step_post_relates_invalid_kind(context, kind):
    """POST /relates with an invented kind must fail Pydantic enum validation with 422."""
    client = _seeded_test_client()
    resp = client.post(
        "/relates",
        json={"from_id": "test::a", "to_id": "test::b", "kind": kind},
    )
    context.last_response = resp


@when('I DELETE /relates with an invalid kind "{kind}"')
def step_delete_relates_invalid_kind(context, kind):
    """DELETE /relates with an invented kind must fail Pydantic enum validation with 422."""
    client = _seeded_test_client()
    # httpx (used by TestClient) supports a JSON body on DELETE via `request`.
    resp = client.request(
        "DELETE",
        "/relates",
        json={"from_id": "test::a", "to_id": "test::b", "kind": kind},
    )
    context.last_response = resp


# ---------------------------------------------------------------------------
# THEN
# ---------------------------------------------------------------------------


@then('the link is returned with author "{author}"')
def step_link_author(context, author):
    link = context.last_link
    assert link is not None, "no link in context"
    assert link.author == author, f"expected author={author!r}, got {link.author!r}"


@then('the link kind is "{kind}"')
def step_link_kind(context, kind):
    link = context.last_link
    assert link is not None, "no link in context"
    assert link.kind.value == kind, f"expected kind={kind!r}, got {link.kind.value!r}"


@then('the second delete of the same link returns "not found"')
def step_second_delete_not_found(context):
    """Issue a second delete on the same triple; expect False (404 -> not found)."""
    client: GraphClient = context.graph_client
    from_id, to_id, kind = context.last_delete_triple
    result = asyncio.run(
        client.delete_link(from_id=from_id, to_id=to_id, kind=ArtifactLinkKind(kind))
    )
    assert result is False, f"expected second delete to return False, got {result!r}"


@then("the link create attempt fails with GraphUnavailable")
def step_link_create_fails(context):
    exc = context.last_exception
    assert exc is not None, "expected an exception, got none"
    assert isinstance(exc, GraphUnavailable), (
        f"expected GraphUnavailable, got {type(exc).__name__}: {exc!r}"
    )


# ---------------------------------------------------------------------------
# WHEN/THEN — agent-style graph_link / graph_unlink (OpenAPI-contract scenario)
# ---------------------------------------------------------------------------


@when('agent calls graph_link with from_id "{from_id}" to_id "{to_id}" kind "{kind}"')
def step_agent_graph_link(context, from_id, to_id, kind):
    client: GraphClient = context.graph_client
    req = ArtifactLinkCreate(from_id=from_id, to_id=to_id, kind=ArtifactLinkKind(kind))
    context.last_link = asyncio.run(client.create_link(req, author="agent:test"))
    context.last_triple = (from_id, to_id, kind)


@then('the edge exists with author "{expected}"')
def step_edge_exists_with_author(context, expected):
    link = context.last_link
    assert link is not None, "no link in context"
    assert link.author == expected, f"expected author={expected!r}, got {link.author!r}"


@when('agent calls graph_unlink with the same triple and kind "{kind}"')
def step_agent_graph_unlink(context, kind):
    client: GraphClient = context.graph_client
    from_id, to_id, _ = context.last_triple
    context.last_unlink_ok = asyncio.run(
        client.delete_link(from_id=from_id, to_id=to_id, kind=ArtifactLinkKind(kind))
    )


@then("the edge is gone")
def step_edge_gone(context):
    """Verify via a second delete — if it returns False, the edge is gone."""
    client: GraphClient = context.graph_client
    from_id, to_id, kind = context.last_triple
    ok = asyncio.run(client.delete_link(from_id=from_id, to_id=to_id, kind=ArtifactLinkKind(kind)))
    assert ok is False, f"expected edge to be gone, but second delete returned {ok!r}"
