Feature: Graph is strictly optional — guru operates identically without it

  Background:
    Given the "polyglot" fixture project is copied to a tmpdir

  Scenario: Full guru lifecycle with graph disabled
    Given graph is disabled
    When I run 'guru index'
    Then the index command succeeds
    And the server status reports graph_reachable = False
    And the server status reports graph_enabled = False
    And no guru-graph daemon was spawned

  Scenario: Indexing with graph disabled does not attempt graph calls
    Given graph is disabled
    When I run 'guru index'
    Then the index command succeeds
    And the server's graph client is None

  @skip_until_pr5
  Scenario: Graph MCP tools return status, not error, when disabled
    Given graph is disabled
    When MCP calls graph_describe, graph_find, graph_orphans, graph_annotate
    Then each returns {"status":"graph_disabled", ...}
    And none raise exceptions

  @skip_until_pr5
  Scenario: CLI graph commands exit 0 when graph disabled
    Given graph is disabled
    When I run 'guru graph orphans'
    Then exit code is 0
    And stdout contains "graph is disabled"

  @skip_until_pr3 @real_neo4j
  Scenario: Daemon crash mid-indexing — guru-server completes; graph data is partial
    Given graph is enabled and `guru index` is running
    When I SIGKILL guru-graph after the 3rd file is indexed
    Then `guru index` still completes
    And LanceDB contains every chunk
    And the graph contains what was submitted before the kill
    And `guru status` reports graph_reachable=false afterwards
    When I re-run `guru index` after daemon recovery
    Then the graph catches up to match LanceDB exactly
