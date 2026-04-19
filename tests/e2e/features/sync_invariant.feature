Feature: LanceDB ↔ graph sync invariant

  The sync invariant guarantees that for every document in LanceDB a
  corresponding document node exists in the graph when the graph is enabled.
  These scenarios exercise the SyncService and the /sync/* endpoints using
  fake in-process adapters — no real Neo4j or running server required.

  Background:
    Given a fresh sync harness
    And the graph daemon is enabled

  Scenario: Ingested doc appears in graph
    When I ingest document "a.md"
    Then the graph has a document node "a.md"
    And sync drift is 0

  Scenario: Ingesting with graph disabled leaves drift
    Given the graph daemon is disabled
    When I ingest document "b.md"
    Then sync drift is 1

  Scenario: Enabling the graph heals drift
    Given the graph daemon is disabled
    When I ingest document "c.md"
    And I enable the graph daemon
    And I trigger a reconcile
    Then the graph has a document node "c.md"
    And sync drift is 0

  Scenario: Pruned graph is rebuilt from LanceDB
    When I ingest document "d.md"
    And the graph store is pruned
    And I trigger a reconcile
    Then the graph has a document node "d.md"
    And sync drift is 0

  Scenario: Deleting a document removes the graph node
    Given I ingest document "e.md"
    When I delete document "e.md"
    Then the graph has no document node "e.md"
    And sync drift is 0

  Scenario: Startup reconcile runs when drift exists
    Given the graph store is pruned
    And documents "f.md, g.md" exist in LanceDB
    When the server restarts
    Then sync drift is 0
