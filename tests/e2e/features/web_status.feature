@web
Feature: Status surface

  Background:
    Given a fresh guru project with documents "a.md, b.md"
    And the workbench web UI is available

  Scenario: Healthy graph shows 0 drift
    Given the graph daemon is enabled for status
    When I open the Status surface
    Then I see the drift value "0"

  Scenario: Disabled graph disables reconcile
    Given the graph daemon is disabled for status
    When I open the Status surface
    Then the "Reconcile now" button is disabled

  Scenario: Reconcile heals drift
    Given the graph daemon is enabled for status
    And the graph store is pruned for status
    When I open the Status surface
    Then I see the drift value "2"
    When I click "Reconcile now"
    Then I see the drift value "0"
