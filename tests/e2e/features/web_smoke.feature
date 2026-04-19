@web
Feature: Web smoke

  Scenario: Workbench serves the boot payload
    Given a guru server is running
    When I open the workbench in a browser
    Then I see the "Documents" menu item
