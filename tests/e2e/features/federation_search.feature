@federation
Feature: Federated search

  Scenario: Federated search queries all live peers
    Given running guru servers "alpha, beta" with indexed documents
    When "alpha" performs a federated search for "overview"
    Then results include matches from both "alpha" and "beta"

  Scenario: Federated search results are grouped by server by default
    Given running guru servers "alpha, beta" with indexed documents
    When "alpha" performs a federated search for "overview"
    Then results are grouped under "alpha" and "beta" keys

  Scenario: Federated search results can be merged
    Given running guru servers "alpha, beta" with indexed documents
    When "alpha" performs a federated search for "overview" with merge enabled
    Then results are returned as a single ranked list
