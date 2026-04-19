---
name: raise-bug-issue
description: >
  Interview-driven skill for filing a HIGH-QUALITY bug (or defect) GitHub issue against this
  repository. Use whenever a user wants to "report a bug", "raise a bug", "log a defect",
  "open a bug report", "file an issue for a problem I'm seeing", or describes unexpected
  behaviour without a proper report yet. The skill interviews the user, validates every
  claim against the codebase + docs, writes a preliminary Root-Cause Analysis, and only
  then files the issue via the `create-github-issue` skill. This skill MUST NEVER start
  fixing the bug — it ends as soon as the issue URL is returned.
---

# Raise a Bug Issue (with interview + preliminary RCA)

**Scope guard — read first:**

- This skill creates a **bug issue only**. It MUST NOT attempt any fix, workaround,
  refactor, or code edit. Implementation belongs to the `bug-fixer` GitHub Copilot agent
  (`.github/agents/bug-fixer.md`) or a human engineer.
- If, during investigation, you find the fix is trivial and are tempted to patch it —
  STOP. File the issue anyway. Link the location of the suspected fix in the RCA.
- If the claim does not survive codebase verification (the code does what the user says
  it doesn't, or the described path is impossible), **do not file**. Push back with
  evidence and ask the user to provide more. Only file when either (a) the bug is
  reproducible or plausibly real, or (b) the user overrides with additional evidence.

---

## Step 0 — Load the template rules

The final filing step delegates to the existing skill:
`.claude/skills/create-github-issue/SKILL.md`.

Read that skill's Bug Report checklist before the interview so you know which fields are
required (title, version, component, description, steps, expected, actual). Your
interview must collect enough material to populate every required field.

---

## Step 1 — Interview the user (batched `AskUserQuestion`)

Ask the user in ≤4-question batches using the `AskUserQuestion` tool, never plain text.
Each question has `header` ≤12 chars, `label` 1–5 words, one-line `description`, and 2–4
mutually-exclusive options; preferred option first with the ` (Recommended)` suffix.

Work through these topic clusters in order. Skip any cluster where you already have a
confident answer.

### Cluster A — Symptom framing (always ask)

1. **Which component?** — `guru-server` · `guru-mcp` · `guru-cli / TUI` · `guru-core` ·
   `guru-graph` · `Other / Unknown` (matches `bug_report.yml`).
2. **Severity?** — e.g. `Crash / data loss`, `Feature broken`, `Degraded / slow`,
   `Cosmetic`. (Used to shape priority language in the body; not a template field.)
3. **Is it reproducible?** — `Every time`, `Intermittent`, `Once`, `Not yet attempted`.
4. **Regression?** — `Worked in prior version`, `Never worked`, `Unsure`.

### Cluster B — Environment

1. **Guru version** — ask the user to paste the output of `uv run guru --version`. The
   value must be a valid PEP 440 string. Reject `unknown`/empty.
2. **OS / Python / Ollama / Neo4j (if relevant)** — optional but encouraged.
3. **Install source** — `uv tool install` (Pages index), `uv sync --all-packages`
   (monorepo dev), `other`.

### Cluster C — Reproduction

Ask for minimal numbered steps starting from a **clean state** (`guru init` in an empty
dir unless otherwise stated). Push back if the steps depend on undisclosed prior state,
private data, or mutate the user's real knowledge base.

### Cluster D — Observed vs. Expected

1. The **actual** output — paste verbatim: error message, stack trace, log snippet.
   Redact secrets/paths yourself before logging.
2. The **expected** output — what the user believed should have happened, with a
   reference (doc, feature file, prior behaviour) if possible.

### Cluster E — Scoping / blast radius (optional)

Does the bug affect writes, reads only, a single command, a whole subsystem, or cross
components? This goes into the RCA, not the template.

---

## Step 2 — Validate claims against the codebase

Before writing anything into the issue body, verify that the user's story is consistent
with the code and specs. You MUST do at least the following:

1. **Locate the relevant package(s)** under `packages/<component>/`. Use `Glob`/`Grep`
   to find the symbol, command, endpoint, or tool the user referenced.
2. **Cross-check against `ARCHITECTURE.md`** — the architecture constitution. If the
   user's expectation violates an invariant (e.g. expecting `guru-mcp` to talk to
   LanceDB directly), the expectation is wrong, not the code. Push back instead of
   filing.
3. **Cross-check against the matching BDD feature** (`tests/e2e/features/*.feature`).
   Features ARE the acceptance criteria. If a feature asserts the behaviour the user
   expects, that's strong evidence of a bug. If a feature asserts the behaviour the
   user is calling a bug, it's probably a feature request / misconception.
4. **Cross-check against the OpenAPI / `response_model`** for REST endpoints and
   against FastMCP tool definitions for MCP claims.
5. **Search for prior issues** using the GitHub MCP/API: title keywords + the failing
   function name. Avoid duplicates — if one exists, surface it to the user and stop.

Capture the exact file paths and line numbers you inspected. You will cite them in the
RCA.

### When validation fails

If the bug is implausible (code path can't execute, claim contradicts architecture, or
a spec explicitly codifies the "buggy" behaviour), do NOT file. Instead:

1. Reply with the evidence (paths + line numbers + the contradicting passage).
2. Ask the user for additional evidence — a log line, screen recording, or a failing
   test case.
3. Only proceed to Step 3 after the user either provides that evidence or explicitly
   overrides with "file it anyway, this is what I observed".

---

## Step 3 — Write the preliminary RCA

Add a **Preliminary Root-Cause Analysis** section to the issue body (below the template
fields, under `## Additional Context` or a new `## Preliminary RCA` heading). The RCA
is YOUR analysis, not the user's. It MUST contain:

- **Suspected location** — file path(s) and line numbers where the bug most likely
  lives (use the `path:line` format).
- **Hypothesis** — one paragraph explaining the most probable mechanism, phrased as a
  hypothesis ("likely caused by X because Y"), not a conclusion.
- **Evidence supporting the hypothesis** — links to the specific code, specs, or
  feature files that you read during Step 2.
- **Evidence that could disprove it** — what would need to be true for the hypothesis
  to be wrong. This keeps the fixer honest.
- **Suggested verification** — the smallest experiment that would confirm or refute it
  (a failing unit test, a behave scenario to add, a log to capture).
- **Scope / blast radius** — which components are affected, which are safe.
- **Confidence** — `Low` / `Medium` / `High`, with one sentence of justification.

Do NOT propose or include a patch. Do NOT mention "how to fix" beyond pointing at the
suspected location. The downstream `bug-fixer` agent does the fixing.

---

## Step 4 — File the issue (delegate to `create-github-issue`)

Invoke the `create-github-issue` skill with:

- **Template:** `bug_report`
- **Title:** `fix: <short, imperative description>` (matches repo convention and
  `bug_report.yml`'s default title).
- **Body:** All required template fields, followed by `## Preliminary RCA` with the
  content from Step 3.
- **Labels:** `bug` (added automatically by the template; verify it's present).

Obey every rule in that skill: valid PEP 440 version, component dropdown value, no
blank required fields. If any required field is still missing after the interview, go
back to Step 1 and ask — do not invent values.

---

## Step 5 — Hand off and stop

After the issue is created:

1. Report the issue URL to the user.
2. Remind them that the `bug-fixer` GitHub Copilot agent can be assigned to the issue
   to attempt a TDD-driven fix, or that they can pick it up manually.
3. **Stop.** Do not open a PR, do not edit code, do not run tests against a
   hypothesized patch. This skill has completed its job.

If the user now asks you to fix the bug, that is a separate task — it is NOT covered
by this skill and should be handled by the `bug-fixer` agent or a fresh session.

---

## Red flags (STOP conditions)

| Signal | Action |
|---|---|
| User asks you to "just fix it while you're at it" | Decline. File issue, stop. |
| Interview reveals the user is describing a feature request, not a defect | Suggest the `enhancement` template via `create-github-issue` instead, and exit this skill. |
| A duplicate issue already exists | Link it to the user, do not file a second. |
| Validation disproves the bug | Push back with evidence; do not file unless the user provides new evidence. |
| Required template field is still missing after interview | Ask again; never invent a value, never submit blanks. |
| User wants the version set to "unknown"/"latest"/empty | Refuse — PEP 440 string required. Ask them to run `uv run guru --version`. |
