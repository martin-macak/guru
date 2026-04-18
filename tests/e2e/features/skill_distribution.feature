Feature: Guru skill is installed and updated safely

  Scenario: `guru init` installs the skill tree
    Given a fresh tmpdir project
    When I run skill command "guru init"
    Then ".claude/skills/guru-knowledge-base/SKILL.md" exists in the project
    And all six reference files exist under ".claude/skills/guru-knowledge-base/references/"
    And ".agents/skills/guru-knowledge-base" is a symlink (or directory copy) to the .claude path
    And "MANIFEST.json" contains a sha256 for every shipped file

  Scenario: `guru update` is a no-op on an up-to-date tree
    Given the skill was just installed in a tmpdir project
    When I run skill command "guru update"
    Then no files under ".claude/skills/guru-knowledge-base/" are modified
    And stdout contains "already up to date"

  Scenario: `guru update` overwrites unmodified files when the manifest is stale
    Given the skill was installed in a tmpdir project
    And the MANIFEST.json hash for "SKILL.md" was tampered to look stale
    When I run skill command "guru update"
    Then "SKILL.md" appears in the update output
    And MANIFEST.json is refreshed

  Scenario: `guru update` refuses to clobber user edits
    Given the skill was installed in a tmpdir project
    And the user has edited "SKILL.md" in the project
    And the MANIFEST.json hash for "SKILL.md" was tampered to look stale
    When I run skill command "guru update"
    Then "SKILL.md" was not overwritten
    And exit code is 0

  Scenario: `guru update --force` backs up and overwrites user edits
    Given the skill was installed in a tmpdir project
    And the user has edited "SKILL.md" in the project with content "user-customised\n"
    When I run skill command "guru update --force"
    Then a "SKILL.md.bak.<timestamp>" file exists with the previous user content
    And "SKILL.md" matches the shipped version

  Scenario: `guru update --dry-run` writes nothing
    Given the skill was installed in a tmpdir project
    And the MANIFEST.json hash for "SKILL.md" was tampered to look stale
    When I run skill command "guru update --dry-run"
    Then "SKILL.md" output line starts with "would update"
    And the SKILL.md mtime did not change
