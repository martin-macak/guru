Feature: Hybrid vector + graph search via a single search() call

  These scenarios verify that PR-7's PythonParser-emitted artifact chunks
  flow end-to-end into LanceDB and are reachable by the agent's normal
  search/graph_describe pivot pattern. All three require real embeddings
  (Ollama); two also require a live Neo4j daemon.

  @real_ollama
  Scenario: search() returns a mix of doc-chunks and artifact-chunks
    Given fixture project "polyglot" is indexed with graph enabled
    When I call search "user authentication"
    Then results include at least one chunk with kind "markdown_section"
    And results include at least one chunk with kind "code" and artifact_qualname set
    And every result has parent_document_id set

  @real_ollama @real_neo4j
  Scenario: Agent pivots from a vector hit into the graph
    Given fixture project "polyglot" is indexed with graph enabled
    And the top search hit has artifact_qualname "polyglot::pkg.services.user.UserService"
    When the agent calls graph_describe with node_id "polyglot::pkg.services.user.UserService"
    Then the response includes the class's methods inheritance and annotations

  @real_ollama
  Scenario: Graph disabled — search() still returns mixed chunks
    Given fixture project "polyglot" is indexed with graph disabled
    When I call search "user authentication"
    Then artifact chunks are still present in results
    But no graph nodes exist
    And graph_describe returns the disabled sentinel
