Feature: guru cache CLI commands
  As a developer I can observe and manage my embedding cache through
  the guru CLI and see its status in guru server status.

  Background:
    Given a guru project with sample markdown files
    And the guru server is running

  Scenario: guru cache info shows current state after indexing
    Given the knowledge base has been indexed
    When I run "guru cache info"
    Then the command succeeds
    And the output contains "total entries"
    And the output contains "nomic-embed-text"

  Scenario: guru cache clear wipes everything
    Given the knowledge base has been indexed
    When I run "guru cache clear --yes"
    Then the command succeeds
    And the output contains "Deleted"

  Scenario: guru cache clear scoped to a model
    Given the knowledge base has been indexed
    When I run "guru cache clear --model nomic-embed-text --yes"
    Then the command succeeds
    And the output contains "Deleted"

  Scenario: guru cache prune with a duration works
    Given the knowledge base has been indexed
    When I run "guru cache prune --older-than 30d --yes"
    Then the command succeeds
    And the output contains "Pruned"

  Scenario: guru cache prune rejects malformed duration
    When I run "guru cache prune --older-than 30days --yes"
    Then the command fails
    And the output contains "Invalid duration"

  Scenario: guru server status shows cache block
    Given the knowledge base has been indexed
    When I run "guru server status"
    Then the command succeeds
    And the output contains "Cache:"
