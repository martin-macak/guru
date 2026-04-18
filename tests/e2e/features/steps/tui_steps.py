"""Step definitions for the knowledge_workbench_tui.feature scenarios."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from behave import given, then, when
from click.testing import CliRunner

from guru_cli.cli import cli
from guru_cli.tui.app import WorkbenchApp
from guru_cli.tui.session import GuruSession
from guru_core.graph_types import QueryResult


def _run(coro):
    return asyncio.run(coro)


def _make_session(*, document_count: int = 7, graph_reachable: bool = True):
    guru_client = AsyncMock()
    graph_client = AsyncMock()
    guru_client.status.return_value = {
        "server_running": True,
        "document_count": document_count,
        "chunk_count": 55,
        "last_indexed": None,
        "ollama_available": True,
        "model_loaded": True,
        "current_job": None,
        "graph_enabled": True,
        "graph_reachable": graph_reachable,
    }
    graph_client.query.return_value = QueryResult(columns=["n"], rows=[[1]], elapsed_ms=1.2)
    session = GuruSession(guru_client=guru_client, graph_client=graph_client)
    return session, graph_client


@when("I invoke bare guru")
def step_invoke_bare_guru(context):
    runner = CliRunner()
    with patch("guru_cli.tui.app.run_tui") as mock_run_tui:
        result = runner.invoke(cli, [])
    context.launch_result = result
    context.run_tui_mock = mock_run_tui


@then("the launch command succeeds")
def step_launch_succeeds(context):
    assert context.launch_result.exit_code == 0, context.launch_result.output


@then("the workbench entrypoint was called")
def step_entrypoint_called(context):
    context.run_tui_mock.assert_called_once_with()


@given("a workbench app with a healthy status snapshot")
def step_workbench_with_status(context):
    session, graph_client = _make_session(document_count=7, graph_reachable=True)
    context.workbench_session = session
    context.workbench_app = WorkbenchApp(session=session)
    context.graph_client = graph_client


@given("a workbench app with a graph query result")
def step_workbench_with_query_result(context):
    session, graph_client = _make_session(document_count=7, graph_reachable=True)
    context.workbench_session = session
    context.workbench_app = WorkbenchApp(session=session)
    context.graph_client = graph_client


@when("I switch the workbench to operate mode")
def step_switch_to_operate(context):
    async def _switch():
        async with context.workbench_app.run_test() as pilot:
            await pilot.press("4")
            context.operate_output = context.workbench_app.query_one(
                "#operate-body"
            ).renderable.plain

    _run(_switch())


@then('the operate panel shows document count "{count}"')
def step_operate_document_count(context, count):
    assert f"documents: {count}" in context.operate_output, context.operate_output


@then('the operate panel shows graph reachability "{state}"')
def step_operate_graph_state(context, state):
    assert f"graph: {state}" in context.operate_output, context.operate_output


@when('I switch the workbench to query mode and submit the Cypher "{cypher}"')
def step_switch_to_query(context, cypher):
    async def _switch():
        async with context.workbench_app.run_test() as pilot:
            await pilot.press("3")
            editor = context.workbench_app.query_one("#query-input")
            editor.value = cypher
            await pilot.press("ctrl+enter")
            context.query_output = context.workbench_app.query_one(
                "#query-results"
            ).renderable.plain

    _run(_switch())


@then('the query panel shows "{text}"')
def step_query_panel_shows(context, text):
    assert text in context.query_output, context.query_output


@then("the graph query was read-only")
def step_graph_query_read_only(context):
    context.graph_client.query.assert_awaited_once()
    assert context.graph_client.query.await_args.kwargs["read_only"] is True
