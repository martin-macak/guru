@web
Feature: Graph surface

  Background:
    Given a fresh guru project with documents "a.md, b.md"
    And the graph daemon is enabled
    And the workbench web UI is available

  Scenario: Initial canvas shows federation root and the local KB
    When I open the Graph surface
    Then the canvas has node "federation"
    And the canvas has node "kb:local"
    And the canvas has 2 visible nodes

  Scenario: Clicking a KB node reveals its document children
    When I open the Graph surface
    And I click the canvas node "kb:local"
    Then the canvas has node "doc:a.md"
    And the canvas has node "doc:b.md"

  Scenario: Clicking a document node merges its neighbors
    Given documents "a.md" and "b.md" are linked in the graph
    When I open the Graph surface
    And I click the canvas node "kb:local"
    And I click the canvas node "doc:a.md"
    Then the canvas has node "doc:b.md"
    And a path-to-root overlay connects "federation" to "kb:local" to "doc:a.md"

  Scenario: Cypher projection replaces the canvas
    When I open the Graph surface
    And I run the Cypher query "MATCH (d:Document {path:'a.md'}) RETURN d"
    Then the canvas has node "doc:a.md"
    And the canvas does not have node "doc:b.md"
    And the canvas has node "federation"

  Scenario: Back to exploration restores prior state
    When I open the Graph surface
    And I click the canvas node "kb:local"
    And I run the Cypher query "MATCH (d:Document {path:'a.md'}) RETURN d"
    And I click "Back to exploration"
    Then the canvas has node "doc:b.md"

  Scenario: Write cypher is rejected
    When I open the Graph surface
    And I run the Cypher query "CREATE (:Document {id:'x.md'})"
    Then the Cypher input shows the error "writes are not permitted"

  Scenario: Graph disabled shows no graph canvas
    Given the graph daemon is disabled
    When I open the Graph surface
    Then I see the message "Graph unavailable"
