@real_ollama
Feature: Semantic search with real embeddings and labeling
  As a developer using Guru
  I want semantic search to return relevant results based on meaning
  And I want documents to be labeled according to my config rules
  So that I can find the right knowledge and filter by category

  Background:
    Given a guru project with topically distinct documents
    And the guru server is running with real embeddings
    And the knowledge base has been indexed

  Scenario: Search finds documents about cooking by meaning
    When I search for "recipes and ingredients for dinner"
    Then the command succeeds
    And the first result contains "cooking" or "recipe" or "ingredient"

  Scenario: Search finds documents about databases by meaning
    When I search for "storing and querying structured data"
    Then the command succeeds
    And the first result contains "database" or "SQL" or "query"

  Scenario: Search finds documents about astronomy by meaning
    When I search for "planets orbiting stars in the galaxy"
    Then the command succeeds
    And the first result contains "planet" or "star" or "galaxy" or "orbit"

  Scenario: Documents in guides/ are labeled as guide
    When I get the document containing "cooking"
    Then the command succeeds
    And the document has label "guide"

  Scenario: Documents in references/ are labeled as reference
    When I get the document containing "database"
    Then the command succeeds
    And the document has label "reference"

  Scenario: Documents in references/ are labeled as technical
    When I get the document containing "database"
    Then the command succeeds
    And the document has label "technical"

  Scenario: Labels are present in search results
    When I search for "recipes and ingredients for dinner"
    Then the command succeeds
    And the search results contain label "guide"
