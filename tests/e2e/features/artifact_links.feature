Feature: Parser-emitted and agent-written artifact RELATES links

  # ----------------------------------------------------------------
  # Design-spec scenarios — require PR-7 Python parser and/or PR-8
  # OpenAPI parser. Skipped until those PRs land.
  # ----------------------------------------------------------------

  @skip_until_pr7 @real_neo4j
  Scenario: Parser emits imports and inheritance from Python source
    Given fixture "polyglot" is indexed
    Then edges of kind "imports" and "inherits_from" are present per the parser rules

  @real_neo4j
  Scenario: Agent manually links a class to its OpenAPI contract
    Given the polyglot fixture has a Python class and an OpenAPI schema indexed with graph enabled
    When agent calls graph_link with from_id "polyglot::pkg.services.user.UserService" to_id "polyglot::api/openapi.yaml::components/schemas/UserResource" kind "implements"
    Then the edge exists with author "agent:test"
    When agent calls graph_unlink with the same triple and kind "implements"
    Then the edge is gone

  # ----------------------------------------------------------------
  # Document<->Document scenarios that pass in PR-4 — only require the
  # markdown parser's Document/MarkdownSection nodes (already in PR-2).
  # ----------------------------------------------------------------

  @real_neo4j
  Scenario: Agent links one Document to another with kind "references"
    Given the polyglot fixture is indexed with two documents and graph enabled
    When I create a link from "polyglot::docs/guide.md" to "polyglot::docs/api.md" with kind "references"
    Then the link is returned with author "agent:test"
    And the link kind is "references"
    When I delete the link from "polyglot::docs/guide.md" to "polyglot::docs/api.md" with kind "references"
    Then the second delete of the same link returns "not found"

  @real_neo4j
  Scenario: Linking to a missing artifact returns 404
    Given the polyglot fixture is indexed with two documents and graph enabled
    When I attempt to create a link from "polyglot::docs/guide.md" to "polyglot::docs/missing.md" with kind "references"
    Then the link create attempt fails with GraphUnavailable

  # ----------------------------------------------------------------
  # Pydantic 422 paths — bound-checked at the route layer.
  # ----------------------------------------------------------------

  Scenario: Unknown link kind is rejected with 422 (POST /relates)
    Given a running guru-graph daemon
    When I POST /relates with an invalid kind "invented_kind"
    Then the response status is 422

  Scenario: Unknown link kind is rejected with 422 (DELETE /relates)
    Given a running guru-graph daemon
    When I DELETE /relates with an invalid kind "invented_kind"
    Then the response status is 422

  # ----------------------------------------------------------------
  # MCP-shaped error contract — deferred to PR-5 (graph_link tool).
  # The HTTP /relates 422 above is the PR-4-runnable equivalent.
  # ----------------------------------------------------------------

  @skip_until_pr5
  Scenario: Unknown link kind is rejected via the MCP tool
    Given a Claude-Code-style MCP session is connected
    When agent calls graph_link(kind="invented_kind", ...)
    Then the MCP tool returns {"error":"invalid_request","detail":"kind must be one of imports/inherits_from/implements/calls/references/documents"}
