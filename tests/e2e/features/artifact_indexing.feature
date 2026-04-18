Feature: Artifact graph indexing for Python, OpenAPI, and Markdown

  Background:
    Given the "polyglot" fixture project is copied to a tmpdir

  @real_neo4j
  Scenario: Markdown index creates Document + MarkdownSection nodes
    Given graph is enabled
    When I run 'guru index'
    Then (:Document {id: "polyglot::docs/guide.md"}) exists in the graph
    And at least one (:MarkdownSection) node under docs/guide.md exists
    And LanceDB contains chunks for docs/guide.md with kind="markdown_section"

  # PR-8 shipped the OpenAPI parser, but the compound "fresh index in lockstep"
  # assertions (LanceDB-per-file, Module/Method containment, OpenApi spec/op/schema
  # counts, MarkdownSection headings) need a dedicated step-def authoring pass
  # that's out of PR-8's scope. Retagged for PR-9.
  @skip_until_pr9 @real_neo4j @real_ollama
  Scenario: Fresh index populates LanceDB and graph in lockstep
    Given graph is enabled
    When I run 'guru index'
    Then LanceDB contains chunks for every file, each with kind/language metadata
    And every indexed file has a corresponding (:Document) node in the graph
    And pkg.auth has a (:Module) node containing its classes and functions
    And every (:Class) in pkg.services.user has its (:Method) children via :CONTAINS
    And api/openapi.yaml has one (:OpenApiSpec) + N (:OpenApiOperation) + M (:OpenApiSchema)
    And docs/guide.md has (:MarkdownSection) nodes matching its H2/H3 headings

  @real_neo4j
  Scenario: Parser emits structural imports and inheritance
    Given graph is enabled
    When I run 'guru index'
    Then (:Module "pkg.auth")-[:RELATES {kind:"imports"}]->(:Module "pkg.services.user") exists
    And for every `class Derived(Base):`, (:Class)-[:RELATES {kind:"inherits_from"}]-> exists

  # Steps for "no commits to Neo4j" require a transaction-counting hook the
  # graph daemon doesn't yet expose; un-skip in a follow-up PR.
  @skip_until_pr7 @real_neo4j
  Scenario: Re-indexing an unchanged file is a no-op in the graph
    Given `guru index` has run once
    When I record the (:Document) updated_at timestamps
    And I run `guru index` again without modifying files
    Then every (:Document).updated_at is unchanged
    And no transactions were committed to Neo4j beyond reads

  # Diff-reconciliation BDD steps (file editing + per-method assertions) not
  # yet authored; un-skip in a follow-up PR.
  @skip_until_pr7 @real_neo4j
  Scenario: Editing a file adds/removes artifacts via diff reconciliation
    Given `guru index` has run once
    When I add a new method `logout` to UserService in pkg.services.user
    And I remove the method `deprecated_fn` from pkg.services.user
    And I run `guru index`
    Then (:Method "pkg.services.user.UserService.logout") exists
    And (:Method "pkg.services.user.UserService.deprecated_fn") does not exist
    And no other (:Method) node under UserService was touched

  # Cascade-orphan BDD steps share the annotation/orphan plumbing exercised by
  # orphan_triage.feature; the file-delete + cascade wiring is not yet authored
  # for this fixture.
  @skip_until_pr7 @real_neo4j
  Scenario: Deleting a file cascades and creates orphans
    Given an annotation was written on (:Function "pkg.auth.hash_password")
    When the file src/pkg/auth.py is deleted
    And I run `guru index`
    Then (:Document "polyglot::src/pkg/auth.py") does not exist
    And no (:Module "pkg.auth") exists
    And the annotation is now an orphan (no outgoing :ANNOTATES edge)
    And graph_orphans() returns it with target_snapshot_json pointing at "pkg.auth.hash_password"
