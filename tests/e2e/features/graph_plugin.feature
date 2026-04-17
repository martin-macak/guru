Feature: Optional graph plugin
  Guru's graph plugin is strictly optional. When disabled or unreachable,
  guru-server must continue to serve the user with reduced accuracy.

  Scenario: Graph disabled by config — client returns None, never raises
    Given graph is disabled in global config
    When I call graph_or_skip with a trivial coroutine that raises GraphUnavailable
    Then the helper returns None

  Scenario: Unknown link kind rejected with 422
    Given a running FakeBackend-backed graph app
    When I POST an unknown link kind to the app
    Then the response is 422
    And the error mentions supported link kinds

  @real_neo4j
  Scenario: Graph enabled → KB auto-registers on first server start
    Given a running guru-graph daemon
    When I upsert Kb "demo"
    Then a Kb node "demo" exists in the graph

  @real_neo4j
  Scenario: KB-to-KB link with known vocabulary succeeds
    Given Kbs "alpha" and "beta" exist in the graph
    When I link alpha -> beta as depends_on
    Then list_links for alpha outgoing contains (alpha, beta, depends_on)

  @real_neo4j
  Scenario: Protocol MAJOR mismatch refused cleanly
    Given a running guru-graph daemon
    When I issue a request with an incompatible protocol header
    Then the server returns 426
    And GraphClient raises GraphUnavailable

  Scenario: Daemon unhealthy → guru-server continues in degraded mode
    Given a guru-server configured with graph enabled but the daemon is unreachable
    When I query status
    Then status reports graph_enabled = True
    And status reports graph_reachable = False
    And the query endpoint still succeeds
