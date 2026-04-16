@federation
Feature: Federation discovery and lifecycle

  Scenario: Server registers on startup
    Given a running guru server "alpha"
    Then a discovery file "alpha.json" exists in the federation directory

  Scenario: Orphan discovery file is cleaned up
    Given a stale discovery file "dead-project.json" with a non-running PID
    And a running guru server "alpha"
    When the maintenance sweep runs
    Then the discovery file "dead-project.json" is removed
