Feature: Non-negotiable architectural invariants

  These scenarios encode invariants that must hold across every release —
  if any of them flips red, the change violates a constitutional rule and
  needs explicit ARCHITECTURE.md amendment before merging.

  Scenario: Indexing never blocks on graph I/O when the graph daemon hangs
    Given a small fixture project with three markdown files
    And the GraphClient.submit_parse_result is patched to hang for 30 seconds
    When I run the indexer with a per-file budget of 5 seconds
    Then the indexer completes within 30 seconds total
    And every fixture file has chunks in LanceDB

  Scenario: MCP write-capable tools are bounded to the agreed set
    When the MCP tool list is enumerated
    Then the only write-capable graph tools are graph_annotate, graph_delete_annotation, graph_link, graph_unlink, graph_reattach_orphan
    And no MCP tool exists named upsert_kb, delete_kb, link_kbs, unlink_kbs

  Scenario: Graph-agnostic surfaces are unchanged by the artifact-graph PRs
    When I enumerate the public surface of search, get_document, list_documents, get_section, index_status, federated_search, list_peers
    Then each surface is reachable as a tool function in guru_mcp.server
    And none of them takes a graph_ prefixed parameter
    And the CLI commands guru init, guru index, guru search are still registered
