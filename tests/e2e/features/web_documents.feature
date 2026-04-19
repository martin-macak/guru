@web
Feature: Documents surface

  Background:
    Given a fresh guru project with documents "alpha.md, beta.md, gamma.md"
    And the workbench web UI is available

  Scenario: Full list visible when surface opened
    When I open the Documents surface
    Then I see a document row for "alpha.md"
    And I see a document row for "beta.md"
    And I see a document row for "gamma.md"

  Scenario: Similarity search replaces the list
    When I open the Documents surface
    And I search documents for "alpha"
    Then the document list shows "alpha.md" ranked first
    And the document list has at most 3 rows

  Scenario: Clicking a document reveals its detail and metadata
    When I open the Documents surface
    And I click the document row for "alpha.md"
    Then I see the document title "alpha.md" in the detail pane
    And the metadata pane shows a "LanceDB" section

  Scenario: Metadata pane is closeable and persists
    When I open the Documents surface
    And I click the document row for "alpha.md"
    And I close the metadata pane
    And I reload the page
    Then the metadata pane is still closed

  @skip_until_phase_5
  Scenario: Go to graph navigates with the doc pre-focused
    When I open the Documents surface
    And I click the document row for "alpha.md"
    And I click "Go to graph"
    Then the URL path is "/graph"
    And the Graph canvas has node "doc:alpha.md" focused
