---
name: create-github-issue
description: >
  Invoke whenever an agent is asked to track a bug, file a defect, report unexpected
  behaviour, or create an enhancement/feature request as a GitHub issue.
  Trigger phrases include: "create an issue", "open an issue", "file a bug", "track this bug",
  "log a defect", "create an enhancement", "file a feature request", "open a ticket".
  This skill enforces the project's mandatory template rules — blank issues are disabled
  and every field must be filled correctly before submission.
---

# Create a GitHub Issue

All GitHub issues **must** use one of the two official templates. Blank issues are
disabled in this repository. Follow this skill to completion before creating the issue.

---

## Step 1 — Choose the correct template

| Situation | Template to use |
|---|---|
| Unexpected behaviour, crash, wrong output, regression | **Bug Report** (`bug_report`) |
| New feature, improvement, or change request | **Enhancement** (`enhancement`) |

When in doubt: if something is broken → Bug Report. If something is missing or could be
better → Enhancement.

---

## Step 2 — Collect required fields

### Bug Report — required fields

| Field | How to obtain / what to write |
|---|---|
| **Title** | `fix: <short description>` — e.g. `fix: search returns empty after re-index` |
| **version** | Run `uv run guru --version` or `dunamai from git`. Must be a semver string (e.g. `0.3.1`, `1.0.0`, `2.1.0-alpha.1`). **Never** leave blank or write "unknown". |
| **component** | Pick one: `guru-server` · `guru-mcp` · `guru-cli / TUI` · `guru-core` · `guru-graph` · `Other / Unknown` |
| **description** | A clear, concise description of the bug. |
| **steps** | Minimal numbered steps to reproduce (start from a clean state). |
| **expected** | What should have happened. |
| **actual** | What actually happened — include error messages, stack traces, or log output. |

Optional: `environment` (OS, Python version, Ollama version), `context` (screenshots, related issues).

### Enhancement — required fields

| Field | How to obtain / what to write |
|---|---|
| **Title** | `feat: <short description>` — e.g. `feat: add PDF ingestion support` |
| **component** | Pick one: `guru-server` · `guru-mcp` · `guru-cli / TUI` · `guru-core` · `guru-graph` · `Documentation` · `CI / Tooling` · `Other / New Component` |
| **problem** | The motivation or pain point — "I'm always frustrated when …" |
| **solution** | The proposed change or feature. |

Optional: `alternatives` (alternative solutions considered), `context` (mockups, references).

---

## Step 3 — Submit the issue

Use the GitHub MCP tool or API to create the issue with **all required fields** supplied
explicitly. Do not omit or skip required fields.

```
owner: martin-macak
repo:  guru
title: <as assembled in Step 2>
body:  <all required fields, formatted per the template>
labels:
  - bug          # for Bug Reports
  - enhancement  # for Enhancements
```

When using the GitHub API directly, map the form fields to the body as Markdown sections
matching the template layout (the same headings the `.github/ISSUE_TEMPLATE/*.yml` files
define). This ensures the issue looks identical to one filed via the web UI.

---

## Step 4 — Verify

After the issue is created, confirm:

1. The title follows `<type>: <description>` convention.
2. All required fields are populated (non-empty).
3. The correct label is applied (`bug` or `enhancement`).
4. For Bug Reports: `version` is a valid semver string.

If any of these checks fail, edit the issue immediately to fix the problem before
reporting the issue URL back to the user.
