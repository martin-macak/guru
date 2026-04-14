Feature: Embedding cache reuses vectors across indexing runs
  The content-addressed embedding cache must deliver cache hits on
  subsequent indexing runs when individual chunks remain unchanged,
  even if the file content overall has changed. This is the
  acceptance criterion for the worktree-speed goal — without this,
  cache reuse across worktrees is silently broken.

  Background:
    Given a guru project with sample markdown files
    And the guru server is running

  Scenario: Appending a new section to a file yields cache hits for unchanged chunks
    Given the knowledge base has been indexed
    And the first indexing job embedded every chunk from scratch
    When I append a new section to "docs/getting-started.md"
    And I run "guru index" and wait for completion
    Then the most recent index job reports at least one cache hit
    And the most recent index job reports at least one cache miss
