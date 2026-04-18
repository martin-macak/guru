"""Invariants that must hold for the CLI forever.

These tests are deliberately coarse: they inspect the click command tree
and the source file. If someone later adds a 'guru graph upsert' command,
the first test trips. If someone later flips read_only to False in any
branch of 'query', the second test trips.
"""

from __future__ import annotations

import inspect

from guru_cli.commands.graph import graph_group, query

_MUTATION_SUBCOMMANDS = {
    "upsert",
    "upsert-kb",
    "create-kb",
    "create",
    "delete",
    "delete-kb",
    "rm",
    "link",
    "create-link",
    "unlink",
    "delete-link",
}


def test_no_mutation_subcommands_registered():
    """The click group must expose only reads + lifecycle commands."""
    names = set(graph_group.commands.keys())
    conflicts = names & _MUTATION_SUBCOMMANDS
    assert conflicts == set(), (
        f"Mutation subcommand(s) found in 'guru graph': {conflicts}. "
        "The CLI must stay read-only per the design spec."
    )


def test_graph_group_only_contains_expected_subcommands():
    """Whitelist — accept only lifecycle + read commands."""
    allowed = {"start", "stop", "status", "kbs", "kb", "links", "query"}
    names = set(graph_group.commands.keys())
    unexpected = names - allowed
    assert unexpected == set(), (
        f"Unexpected subcommand(s) in 'guru graph': {unexpected}. "
        "Add to the whitelist only if intentional."
    )


def test_query_callback_hard_codes_read_only_true():
    """Source inspection: 'query' command must only call client.query with
    read_only=True as a literal keyword argument.
    """
    src = inspect.getsource(query.callback)
    assert "read_only=True" in src, (
        "query must pass read_only=True literally; do not parameterise it."
    )
    assert "read_only=False" not in src
    assert "--write" not in src
