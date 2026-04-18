"""Step definitions for orphan_triage.feature (Document-scoped scenario).

The @real_neo4j scenario requires a running guru-graph daemon. It seeds a
Document node via submit_parse_result, creates an annotation, deletes the
document (orphaning the annotation), asserts it appears in list_orphans, then
reattaches it after re-seeding the document.

The @skip_until_pr7 scenarios are skipped automatically by environment.py.
"""

from __future__ import annotations

import asyncio

from behave import given, then, when

from guru_core.graph_client import GraphClient
from guru_core.graph_types import (
    AnnotationCreate,
    AnnotationKind,
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

    `auto_start=True` lets the client spawn a guru-graph daemon on first call.
    """
    from guru_graph.config import GraphPaths

    paths = GraphPaths.default()
    return GraphClient(socket_path=str(paths.socket), auto_start=True)


async def _seed_document(client: GraphClient, doc_id: str = "polyglot::docs/guide.md") -> None:
    """POST a minimal ParseResultPayload so the Document exists in the graph."""
    kb_name = doc_id.split("::")[0]
    await client.upsert_kb(KbUpsert(name=kb_name, project_root=f"/tmp/{kb_name}"))
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


# ---------------------------------------------------------------------------
# GIVEN
# ---------------------------------------------------------------------------


@given('an annotation "{label}" (note) on "{target_id}" with body "{body}"')
def step_create_named_annotation(context, label, target_id, body):
    """Create a NOTE annotation; store it in context for later assertions."""
    client = _graph_client(context)
    # Ensure the document exists first (may have been seeded by a prior step).
    if not getattr(context, "_polyglot_seeded", False):
        asyncio.run(_seed_document(client, doc_id=target_id))
        context._polyglot_seeded = True
    context.graph_client = client

    req = AnnotationCreate(
        node_id=target_id,
        kind=AnnotationKind.NOTE,
        body=body,
        tags=[],
    )
    ann = asyncio.run(client.create_annotation(req, author="agent:test"))
    context.orphan_annotation = ann
    context.orphan_target_id = target_id


# ---------------------------------------------------------------------------
# WHEN
# ---------------------------------------------------------------------------


@when('the document "{doc_id}" is deleted from the graph')
def step_delete_document(context, doc_id):
    """Delete the document node; this should orphan all annotations on it."""
    client: GraphClient = context.graph_client
    kb_name = doc_id.split("::")[0]
    asyncio.run(client.delete_document_in_graph(kb_name=kb_name, doc_id=doc_id))


@when('I reattach the annotation to "{target_id}" (assuming the doc is re-created)')
def step_reattach_annotation(context, target_id):
    """Re-seed the document then reattach the orphaned annotation to it."""
    client: GraphClient = context.graph_client
    # Re-create the document so the reattach target exists.
    asyncio.run(_seed_document(client, doc_id=target_id))
    ann = context.orphan_annotation
    result = asyncio.run(client.reattach_orphan(annotation_id=ann.id, new_node_id=target_id))
    context.reattached_annotation = result


# ---------------------------------------------------------------------------
# THEN
# ---------------------------------------------------------------------------


@then("the annotation appears in list_orphans")
def step_annotation_in_orphans(context):
    client: GraphClient = context.graph_client
    ann = context.orphan_annotation
    orphans = asyncio.run(client.list_orphans())
    ids = [o.id for o in orphans]
    assert ann.id in ids, f"expected annotation {ann.id!r} in orphans, got: {ids}"


@then('its target_snapshot_json contains "{substring}"')
def step_target_snapshot_contains(context, substring):
    client: GraphClient = context.graph_client
    ann = context.orphan_annotation
    orphans = asyncio.run(client.list_orphans())
    matching = [o for o in orphans if o.id == ann.id]
    assert matching, f"annotation {ann.id!r} not found in orphans"
    snapshot = matching[0].target_snapshot_json
    assert substring in snapshot, (
        f"expected {substring!r} in target_snapshot_json, got: {snapshot!r}"
    )


@then("the annotation no longer appears in list_orphans")
def step_annotation_not_in_orphans(context):
    client: GraphClient = context.graph_client
    ann = context.orphan_annotation
    orphans = asyncio.run(client.list_orphans())
    ids = [o.id for o in orphans]
    assert ann.id not in ids, (
        f"annotation {ann.id!r} should not be in orphans after reattach, got: {ids}"
    )
