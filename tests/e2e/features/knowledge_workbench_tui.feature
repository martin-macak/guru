@tui_mocked
Feature: Knowledge workbench TUI
  As a developer using Guru
  I want the default CLI experience to open the workbench shell
  So that I can investigate, operate, and query without leaving the terminal

  Scenario: Bare guru launches the workbench
    When I invoke bare guru
    Then the launch command succeeds
    And the workbench entrypoint was called

  Scenario: Operate mode shows server status
    Given a workbench app with a healthy status snapshot
    When I switch the workbench to operate mode
    Then the operate panel shows document count "7"
    And the operate panel shows graph reachability "reachable"

  Scenario: Query mode runs read-only Cypher
    Given a workbench app with a graph query result
    When I switch the workbench to query mode and submit the Cypher "RETURN 1 AS n"
    Then the query panel shows "n"
    And the graph query was read-only
