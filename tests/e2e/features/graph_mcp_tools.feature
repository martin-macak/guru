Feature: The 10 new graph MCP tools

  Background: in-memory FastMCP client backed by a FakeBackend guru-graph.

  Scenario: graph_describe returns the artifact + annotations + links via the proxy
    Given the polyglot fixture is seeded into a FakeBackend graph
    And an MCP client is connected
    When the MCP client calls graph_describe with node_id "polyglot::docs/guide.md"
    Then the response includes "id" "polyglot::docs/guide.md"
    And the response includes "label" "Document"

  Scenario: graph_find returns matching artifacts
    Given the polyglot fixture is seeded into a FakeBackend graph
    And an MCP client is connected
    When the MCP client calls graph_find with kb_name "polyglot"
    Then the response is a list of artifact nodes

  Scenario: graph_annotate stamps the agent author
    Given the polyglot fixture is seeded into a FakeBackend graph
    And an MCP client is connected
    When the MCP client calls graph_annotate with node_id "polyglot::docs/guide.md", kind "note", body "from MCP"
    Then the resulting annotation has author starting with "agent:"

  Scenario: graph_query cannot smuggle writes
    Given the polyglot fixture is seeded into a FakeBackend graph
    And an MCP client is connected
    When the MCP client calls graph_query with cypher "CREATE (x:Evil) RETURN x"
    Then either the response indicates a write rejection or no :Evil node exists in the graph

  @real_neo4j
  Scenario: graph_query forces read-only against Neo4j
    Given the polyglot fixture is indexed against the real graph daemon
    And an MCP client is connected
    When the MCP client calls graph_query with cypher "CREATE (x:Evil) RETURN x"
    Then no :Evil node exists in the graph
