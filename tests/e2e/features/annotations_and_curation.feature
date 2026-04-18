Feature: Agent-writable annotations with closed vocabulary + open tags

  # -----------------------------------------------------------------------
  # Design-spec scenarios (§"annotations_and_curation.feature")
  # These require the MCP tool layer (PR-5) or the Python parser (PR-7).
  # They are tagged accordingly and skipped until those PRs land.
  # -----------------------------------------------------------------------

  @skip_until_pr5 @skip_until_pr7 @real_neo4j
  Scenario: Agent writes a summary (replace-semantics)
    Given fixture project "polyglot" is indexed with graph enabled
    And a Claude-Code-style MCP session is connected
    When agent calls graph_annotate(node_id="…UserService", kind="summary", body="Owns user auth lifecycle.")
    Then graph_describe("…UserService").annotations.summary.body == "Owns user auth lifecycle."
    And annotation.author == "agent:claude-code"
    When agent calls graph_annotate(…, kind="summary", body="Orchestrates login + session.")
    Then only one summary annotation exists on …UserService
    And its body == "Orchestrates login + session."

  @skip_until_pr5 @skip_until_pr7 @real_neo4j
  Scenario: Gotcha append-semantics preserve history
    Given fixture project "polyglot" is indexed with graph enabled
    And a Claude-Code-style MCP session is connected
    When agent writes three gotchas on …UserService with different tags
    Then graph_describe returns all three, each its own :Annotation node
    And filtering by tag returns the right subset

  @skip_until_pr5 @skip_until_pr7 @real_neo4j
  Scenario: User vs agent authorship is preserved
    Given fixture project "polyglot" is indexed with graph enabled
    And a Claude-Code-style MCP session is connected
    When the HTTP API writes an annotation with author="user:me@example.com"
    Then the annotation is distinguishable at query time via author prefix

  @skip_until_pr5 @skip_until_pr7 @real_neo4j
  Scenario: Agent dedup workflow before writing
    Given fixture project "polyglot" is indexed with graph enabled
    And a Claude-Code-style MCP session is connected
    And a gotcha "Retries double-invoke on timeout" already exists on …UserService
    When the agent calls graph_describe(…UserService) before writing
    Then it sees the existing gotcha
    And the skill guidance instructs to update rather than re-add

  @skip_until_pr5
  Scenario: Attempting to invent a new annotation kind is rejected
    Given a Claude-Code-style MCP session is connected
    When agent calls graph_annotate(kind="warning", ...)
    Then the MCP tool returns {"error":"invalid_request","detail":"kind must be one of summary/gotcha/caveat/note"}

  # -----------------------------------------------------------------------
  # Document-scoped scenarios that pass in PR-3
  # (no Python parser required — uses Document/MarkdownSection nodes only)
  # -----------------------------------------------------------------------

  @real_neo4j
  Scenario: Agent writes a summary on a MarkdownSection (replace-semantics)
    Given the polyglot fixture is indexed with graph enabled
    When I create an annotation on "polyglot::docs/guide.md" with kind "summary" and body "Owns the polyglot feature guide"
    Then the annotation is returned with author "agent:test"
    And the annotation target_id is "polyglot::docs/guide.md"
    When I create another summary on "polyglot::docs/guide.md" with body "Replaces v1 summary"
    Then exactly one summary annotation exists on that target
    And its body is "Replaces v1 summary"

  @real_neo4j
  Scenario: Gotcha append-semantics on a MarkdownSection preserve history
    Given the polyglot fixture is indexed with graph enabled
    When I create gotcha annotations with bodies "g1", "g2", "g3" on "polyglot::docs/guide.md"
    Then 3 annotations exist on "polyglot::docs/guide.md"
    And deleting one of them leaves 2

  Scenario: Invalid annotation kind rejected with 422
    Given a running guru-graph daemon
    When I POST /annotations with an invalid kind "warning"
    Then the response status is 422

  Scenario: Empty annotation body rejected with 422
    Given a running guru-graph daemon
    When I POST /annotations with an empty body
    Then the response status is 422
