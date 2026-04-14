@gitignore_project
Feature: Indexing respects .gitignore
  As a developer I don't want gitignored files (build artifacts,
  node_modules, etc.) to be indexed just because they match my
  rule globs. When the project root is inside a git repository,
  discovery must consult .gitignore.

  Background:
    Given a guru project inside a git repository
    And the guru server is running

  Scenario: Files in a gitignored directory are skipped
    Given the knowledge base has been indexed
    When I run "guru list"
    Then the command succeeds
    And the output contains "docs/real.md"
    And the output does not contain "node_modules/README.md"

  Scenario: Gitignored files are also absent from search
    Given the knowledge base has been indexed
    When I run "guru search generated"
    Then the command succeeds
    And the output does not contain "node_modules/README.md"
