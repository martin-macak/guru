Feature: Knowledge base management via CLI
  As a developer using Guru
  I want to index, search, and retrieve documents from my knowledge base
  So that AI agents can access my project's documentation

  Background:
    Given a guru project with sample markdown files
    And the guru server is running

  Scenario: Empty knowledge base reports zero chunks
    When I run "guru server status"
    Then the command succeeds
    And the output contains "server_running: True"
    And the output contains "chunk_count: 0"

  Scenario: Index documents from configured directories
    When I run "guru index"
    Then the command succeeds
    And the output contains "Indexing started"
    And the output contains "job"

  Scenario: List indexed documents
    Given the knowledge base has been indexed
    When I run "guru list"
    Then the command succeeds
    And the output contains "getting-started.md"
    And the output contains "architecture.md"
    And the output contains "auth.md"

  Scenario: Search the knowledge base
    Given the knowledge base has been indexed
    When I search for "OAuth authentication"
    Then the command succeeds
    And the output contains "Result"
    And the output contains "score"

  Scenario: Retrieve a specific document
    Given the knowledge base has been indexed
    When I list documents and pick the path containing "auth.md"
    And I run "guru doc {picked_path}"
    Then the command succeeds
    And the output contains "Authentication"

  Scenario: Server status reflects indexed data
    Given the knowledge base has been indexed
    When I run "guru server status"
    Then the command succeeds
    And the output contains "chunk_count"
    And the output does not contain "chunk_count: 0"

  Scenario: Show resolved configuration
    When I run "guru config"
    Then the command succeeds
    And the output contains "docs"
    And the output contains "specs"
    And the output contains "documentation"
