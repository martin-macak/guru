"""Step definitions for web_documents.feature.

Drives the Documents surface via Playwright against a real TCP guru-server
instance started by the @web feature bootstrap in environment.py.
"""

from __future__ import annotations

import re
import time

from behave import given, then, when

# ---------------------------------------------------------------------------
# Background / setup steps
# ---------------------------------------------------------------------------


@given('a fresh guru project with documents "{names}"')
def step_fresh_project_with_documents(context, names):
    """Write minimal markdown files and wait for ingestion.

    The guru project dir and server are already started by before_feature.
    This step writes the requested documents into the project and triggers
    indexing so they appear in the list.
    """
    import httpx

    doc_names = [n.strip() for n in names.split(",")]
    project_dir = context.project_dir

    # Write minimal markdown documents into docs/ so they match the
    # "docs/**/*.md" rule in _create_standard_project()'s .guru.json.
    docs_dir = project_dir / "docs"
    docs_dir.mkdir(exist_ok=True)
    for name in doc_names:
        (docs_dir / name).write_text(
            f"---\ntitle: {name}\n---\n\n# {name}\n\nContent of {name}.\n"
        )

    # Trigger indexing via the UDS server
    socket_path = str(project_dir / ".guru" / "guru.sock")
    transport = httpx.HTTPTransport(uds=socket_path)
    with httpx.Client(transport=transport, timeout=10.0) as client:
        client.post("http://localhost/index", json={})

    # Wait for the index to complete
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        try:
            transport = httpx.HTTPTransport(uds=socket_path)
            with httpx.Client(transport=transport, timeout=5.0) as c:
                resp = c.get("http://localhost/status")
                data = resp.json()
                if data.get("current_job") is None:
                    break
        except Exception:
            pass
        time.sleep(0.3)
    else:
        raise RuntimeError("Indexing did not complete within timeout")


@given("the workbench web UI is available")
def step_workbench_available(context):
    """Assert the web runtime is responding on the TCP listener."""
    import httpx

    resp = httpx.get(f"{context.server_url}/web/boot", timeout=10.0)
    assert resp.status_code == 200, f"Expected /web/boot to return 200, got {resp.status_code}"
    data = resp.json()
    assert data.get("web", {}).get("available") or data.get("web", {}).get("enabled"), (
        f"Web runtime not available: {data}"
    )


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------


@when("I open the Documents surface")
def step_open_documents(context):
    context.page.goto(f"{context.server_url}/#/documents")
    context.page.wait_for_load_state("networkidle")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _document_list_items(context):
    """Return a locator for the actual document list rows.

    DocumentList renders ``<li aria-label={title} role=listitem>`` for the
    full list. Search results render ``<li>`` without aria-label, but both
    are inside the DocumentsPage's left <section>. Scope to <li> inside that
    <section> so we exclude the nav bar's menu items entirely.
    """
    return context.page.locator("main section ul > li")


def _documents_section(context):
    """Locator for the DocumentsPage's left-hand list <section>.

    DocumentsPage renders the list in the first <section> inside <main>.
    We use it to disambiguate toggle buttons and headings.
    """
    return context.page.locator("main > div > section")


# ---------------------------------------------------------------------------
# Assertions — document list
# ---------------------------------------------------------------------------


@then('I see a document row for "{name}"')
def step_see_row(context, name):
    locator = _document_list_items(context).filter(has_text=name).first
    locator.wait_for(state="visible", timeout=15000)
    assert locator.is_visible(), f"Expected to see a document row for '{name}'"


@when('I search documents for "{query}"')
def step_search(context, query):
    box = context.page.get_by_placeholder("Search documents (similarity)")
    box.fill(query)
    box.press("Enter")
    # Wait briefly for results to arrive + render
    time.sleep(0.8)
    context.page.wait_for_load_state("networkidle")


@then('the document list shows "{name}" ranked first')
def step_ranked(context, name):
    items = _document_list_items(context)
    first = items.first
    first.wait_for(timeout=15000)
    text = first.inner_text()
    assert name in text, f"Expected first row to contain '{name}', got: '{text}'"


@then("the document list has at most {n:d} rows")
def step_row_count(context, n):
    count = _document_list_items(context).count()
    assert count <= n, f"Expected at most {n} rows in document list, got {count}"


# ---------------------------------------------------------------------------
# Document detail & metadata
# ---------------------------------------------------------------------------


@when('I click the document row for "{name}"')
def step_click_doc(context, name):
    _document_list_items(context).filter(has_text=name).first.click()
    context.page.wait_for_load_state("networkidle")


@then('I see the document title "{title}" in the detail pane')
def step_title(context, title):
    # DocumentDetail renders the title in <header><h1>{title}</h1></header>.
    # ReactMarkdown may ALSO render a <h1># title</h1> in the body. Scope
    # by the <header> wrapper to avoid the strict-mode collision.
    heading = context.page.locator("article > header").get_by_role("heading", name=title)
    heading.wait_for(state="visible", timeout=15000)
    assert heading.is_visible(), f"Expected detail-pane heading '{title}' to be visible"


@then('the metadata pane shows a "{label}" section')
def step_meta_section(context, label):
    # The metadata pane lives inside <aside aria-label="Metadata">.
    # Scope to the right-hand aside that's inside <main> (DocumentsPage's
    # RightPane) — not the AppShell default RightPane (which is empty).
    aside = context.page.locator("main aside[aria-label='Metadata']")
    element = aside.get_by_text(label, exact=True)
    element.wait_for(state="visible", timeout=15000)
    assert element.is_visible(), f"Expected metadata pane to show '{label}' section"


# ---------------------------------------------------------------------------
# Metadata pane toggle / persistence
# ---------------------------------------------------------------------------


def _inner_metadata_toggle(context):
    """Return the toggle button for the DocumentsPage's RightPane.

    AppShell renders a default <RightPane>{null}</RightPane> AND DocumentsPage
    renders its own <RightPane>. Both contain a toggle button with aria-label
    "Toggle metadata pane" — we scope to the inner one (inside <main>).
    """
    return context.page.locator("main aside[aria-label='Metadata']").get_by_role(
        "button", name="Toggle metadata pane"
    )


@when("I close the metadata pane")
def step_close_meta(context):
    _inner_metadata_toggle(context).click()


@when("I reload the page")
def step_reload(context):
    context.page.reload()
    context.page.wait_for_load_state("networkidle")


@then("the metadata pane is still closed")
def step_pane_closed(context):
    # After reload the pane should still be closed — no LanceDB heading visible.
    time.sleep(0.8)  # brief settle after reload so the page can hydrate
    aside = context.page.locator("main aside[aria-label='Metadata']")
    assert not aside.get_by_text("LanceDB", exact=True).is_visible(), (
        "Expected metadata pane to remain closed after page reload"
    )


# ---------------------------------------------------------------------------
# Graph navigation (Phase 5 — skip_until_phase_5)
# ---------------------------------------------------------------------------


@when('I click "Go to graph"')
def step_click_go_to_graph(context):
    context.page.get_by_role("button", name="Go to graph").click()


@then('the URL path is "{path}"')
def step_url_path(context, path):
    # Hash router: URL looks like http://host/#/graph?focus=...
    assert re.search(rf"#{re.escape(path)}(?:\?|$)", context.page.url), (
        f"Expected URL to contain '#{path}', got: '{context.page.url}'"
    )


@then('the Graph canvas has node "{node_id}" focused')
def step_graph_focused(context, node_id):
    locator = context.page.locator(f'[data-node-id="{node_id}"][data-focused="true"]')
    assert locator.is_visible(), (
        f"Expected graph canvas node '{node_id}' to be focused and visible"
    )
