Feature: Background indexing and change detection
  As a developer using Guru
  I want indexing to run in the background and only re-index changed files
  So that my knowledge base stays current without manual intervention

  Background:
    Given a guru project with sample markdown files
    And the guru server is running

  Scenario: Job reaches completed status
    When I trigger indexing via REST API
    And I wait for the index job to complete
    Then the job status is "completed"
    And the job files_total is 3
    And the job files_processed is 3
    And the job files_skipped is 0

  Scenario: Index returns immediately with job reference
    When I trigger indexing via REST API
    Then the response contains a job_id
    And the response status is "running" or "queued"

  Scenario: Unchanged files are skipped on re-index
    When I trigger indexing via REST API
    And I wait for the index job to complete
    And I trigger indexing via REST API again
    And I wait for the index job to complete
    Then the job files_skipped is 3
    And the job files_processed is 0

  Scenario: Modified file is re-indexed
    When I trigger indexing via REST API
    And I wait for the index job to complete
    And I modify the file "docs/getting-started.md"
    And I trigger indexing via REST API again
    And I wait for the index job to complete
    Then the job files_processed is 1
    And the job files_skipped is 2

  Scenario: Deleted file is cleaned up
    When I trigger indexing via REST API
    And I wait for the index job to complete
    And I delete the file "docs/getting-started.md"
    And I trigger indexing via REST API again
    And I wait for the index job to complete
    Then the job files_deleted is 1

  Scenario: Rapid consecutive index requests each return a valid job_id
    When I trigger indexing via REST API
    And I immediately trigger indexing again
    Then both responses have a valid job_id

  Scenario: Job detail endpoint returns full info
    When I trigger indexing via REST API
    And I wait for the index job to complete
    Then I can retrieve the job detail via REST API
    And the job detail contains job_type "index"
    And the job detail contains created_at
    And the job detail contains finished_at

  Scenario: Status includes current_job field
    When I trigger indexing via REST API
    And I wait for the index job to complete
    Then the server status has current_job as null
