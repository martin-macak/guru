Feature: MCP tools provide knowledge base access to AI agents
  As an AI agent connected via MCP
  I want to search, list, and retrieve documents through MCP tools
  So that I can access the project's knowledge base during development

  Background:
    Given a guru project with sample markdown files
    And the guru server is running
    And the MCP server is connected
    And the knowledge base has been indexed via MCP

  # --- index_status tool ---

  Scenario: Check index status after indexing
    When I call MCP tool "index_status" with no arguments
    Then the MCP call succeeds
    And the MCP result field "server_running" is "True"
    And the MCP result field "chunk_count" is greater than 0
    And the MCP result field "document_count" equals 3

  # --- search tool ---

  Scenario: Search returns relevant results
    When I call MCP tool "search" with query "OAuth authentication flow"
    Then the MCP call succeeds
    And the MCP result is a non-empty list
    And the first MCP result has field "file_path"
    And the first MCP result has field "score"
    And the first MCP result has field "content"
    And the first MCP result has field "header_breadcrumb"

  Scenario: Search respects n_results limit
    When I call MCP tool "search" with query "authentication" and n_results 2
    Then the MCP call succeeds
    And the MCP result has at most 2 items

  # --- list_documents tool ---

  Scenario: List all indexed documents
    When I call MCP tool "list_documents" with no arguments
    Then the MCP call succeeds
    And the MCP result is a list with 3 items
    And the MCP result contains an item with file_path matching "getting-started.md"
    And the MCP result contains an item with file_path matching "architecture.md"
    And the MCP result contains an item with file_path matching "auth.md"

  # --- get_document tool ---

  Scenario: Retrieve a full document by path
    Given I know the file path of a document matching "auth.md"
    When I call MCP tool "get_document" with the known file path
    Then the MCP call succeeds
    And the MCP result has field "content"
    And the MCP result field "content" contains "Authentication"
    And the MCP result has field "chunk_count"

  # --- get_section tool ---

  Scenario: Retrieve a specific section by header breadcrumb
    Given I know the file path of a document matching "auth.md"
    And I know a section header containing "OAuth"
    When I call MCP tool "get_section" with the known file path and header
    Then the MCP call succeeds
    And the MCP result has field "content"
    And the MCP result field "content" contains "OAuth"

  # --- comprehensive search and retrieval workflow ---

  Scenario: Full workflow - search then retrieve any document via MCP
    When I call MCP tool "search" with query "authentication"
    Then the MCP call succeeds
    And the MCP result is a non-empty list
    When I retrieve the document from the first search result via MCP
    Then the MCP call succeeds
    And the MCP result has field "content"
    And the MCP result has field "labels"
    And the MCP result has field "chunk_count"

  Scenario: Search results contain labels
    When I call MCP tool "search" with query "authentication"
    Then the MCP call succeeds
    And the MCP result is a non-empty list
    And some MCP result has label "spec"
    And some MCP result has label "documentation"

  Scenario: Documents retrieved via MCP carry correct labels
    Given I know the file path of a document matching "getting-started.md"
    When I call MCP tool "get_document" with the known file path
    Then the MCP call succeeds
    And the MCP result field "labels" contains "documentation"

  Scenario: Spec documents carry spec label
    Given I know the file path of a document matching "auth.md"
    When I call MCP tool "get_document" with the known file path
    Then the MCP call succeeds
    And the MCP result field "labels" contains "spec"
