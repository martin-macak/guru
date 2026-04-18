Feature: guru graph CLI read commands
  Developers can inspect the graph via the CLI (kbs, kb, links, query) for
  debugging. Writes are never exposed. When the daemon isn't running, the
  CLI exits 1 with a clear message, never blocks or crashes.

  Scenario: graph --help lists all seven subcommands
    When I run the graph help command
    Then the graph help output lists "kb"
    And the graph help output lists "kbs"
    And the graph help output lists "links"
    And the graph help output lists "query"
    And the graph help output lists "start"
    And the graph help output lists "status"
    And the graph help output lists "stop"

  Scenario: query --help mentions read-only and has no --write flag
    When I run the graph query help command
    Then the graph help output contains "read-only"
    And the graph help output does not contain "--write"

  Scenario: kbs with daemon unreachable exits 1
    Given no graph daemon is running and no sockets exist
    When I run the graph command "kbs"
    Then the graph command exits with code 1
    And the graph command output contains "daemon: unreachable"

  Scenario: query with daemon unreachable exits 1
    Given no graph daemon is running and no sockets exist
    When I run the graph command "query 'MATCH (n) RETURN n'"
    Then the graph command exits with code 1
    And the graph command output contains "daemon: unreachable"

  @real_neo4j
  Scenario: kbs lists a KB upserted by the daemon
    Given a running guru-graph daemon with a KB "demo" upserted
    When I run the graph command "kbs"
    Then the graph command exits with code 0
    And the graph command output contains "demo"
    And the graph command output contains "NAME"

  @real_neo4j
  Scenario: kbs --json returns parseable JSON
    Given a running guru-graph daemon with a KB "demo" upserted
    When I run the graph command "kbs --json"
    Then the graph command exits with code 0
    And the graph command output is a JSON array of length 1
    And the first graph JSON item has name "demo"

  @real_neo4j
  Scenario: kb NAME shows a single KB
    Given a running guru-graph daemon with a KB "demo" upserted
    When I run the graph command "kb demo"
    Then the graph command exits with code 0
    And the graph command output contains "name:"
    And the graph command output contains "demo"

  @real_neo4j
  Scenario: kb NAME missing exits 1
    Given a running guru-graph daemon with a KB "demo" upserted
    When I run the graph command "kb nonexistent-xyz"
    Then the graph command exits with code 1
    And the graph command output contains "not found"

  @real_neo4j
  Scenario: query runs read-only Cypher and returns a row
    Given a running guru-graph daemon with a KB "demo" upserted
    When I run the graph command "query 'MATCH (k:Kb) RETURN count(k) AS n'"
    Then the graph command exits with code 0
    And the graph command output contains "elapsed:"
