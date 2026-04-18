Feature: Annotations survive refactors as orphans, agent triages

  # -----------------------------------------------------------------------
  # Design-spec scenarios (§"orphan_triage.feature")
  # Both require the Python parser (PR-7) because the Background refers to
  # UserService, a (:Class) node produced by the Python parser.
  # -----------------------------------------------------------------------

  @skip_until_pr7 @real_neo4j
  Scenario: Rename produces three orphans; agent reattaches
    Given fixture "polyglot" is indexed
    And an agent has written a summary + two gotchas on (:Class "…UserService")
    When a developer renames UserService to AccountService
    And I run `guru index`
    Then graph_describe("…UserService") returns {"error":"not_found"}
    And graph_orphans() returns three annotations
    And each orphan.target_snapshot_json contains {"target_id":"…UserService", ...}
    When agent calls graph_reattach_orphan(annotation_id, new_node_id="…AccountService")
    Then the annotation now has :ANNOTATES -> AccountService
    And it is no longer returned by graph_orphans()

  @skip_until_pr7 @real_neo4j
  Scenario: Obsolete orphan is pruned
    Given fixture "polyglot" is indexed
    And an agent has written a summary + two gotchas on (:Class "…UserService")
    When an orphan summary refers to a deleted experiment class
    And agent calls graph_delete_annotation(orphan_id)
    Then graph_orphans() no longer contains it
    And the annotation node is gone

  # -----------------------------------------------------------------------
  # Document-scoped orphan scenario that passes in PR-3
  # (uses only Document/MarkdownSection nodes; no Python parser required)
  # -----------------------------------------------------------------------

  @real_neo4j
  Scenario: Deleting a Document orphans its annotations; reattach restores them
    Given the polyglot fixture is indexed with graph enabled
    And an annotation "keep-me" (note) on "polyglot::docs/guide.md" with body "notes for later"
    When the document "polyglot::docs/guide.md" is deleted from the graph
    Then the annotation appears in list_orphans
    And its target_snapshot_json contains "polyglot::docs/guide.md"
    When I reattach the annotation to "polyglot::docs/guide.md" (assuming the doc is re-created)
    Then the annotation no longer appears in list_orphans
