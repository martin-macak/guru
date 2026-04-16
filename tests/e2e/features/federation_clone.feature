@federation
Feature: Codebase cloning

  Scenario: Clone a peer's codebase
    Given a running guru server "alpha"
    And a running guru server "beta"
    When "alpha" clones the codebase of "beta"
    Then the clone path is returned to the caller

  Scenario: Unmount deletes cloned codebase
    Given a running guru server "alpha"
    And a running guru server "beta"
    When "alpha" clones the codebase of "beta"
    And "alpha" unmounts the codebase of "beta"
    Then the cloned codebase directory does not exist
