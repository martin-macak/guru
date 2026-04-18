---
name: curate-usage-md
description: Use when the user asks to create, update, regenerate, or refresh USAGE.md — or any project usage manual derived from BDD scenarios. Invoke this skill whenever the user mentions USAGE.md, "usage docs", "usage manual", "the user manual", or "user-facing docs from features". Use proactively after sizable changes to `tests/e2e/features/*.feature` (new feature files, large scenario rewrites, new tags) since USAGE.md drifts otherwise. The skill spawns one fast Haiku agent per feature file in parallel to extract user-facing usage patterns, then synthesises a coherent USAGE.md grouped by user concern, including FAQ and troubleshooting sections.
---

# Curate USAGE.md from BDD scenarios

USAGE.md is the project's user-facing manual, derived from the BDD acceptance criteria under `tests/e2e/features/`. Behave feature files double as the source of truth for what the system DOES (per the spec-driven methodology in CLAUDE.md), so they are also the right source for what users CAN DO. This skill keeps USAGE.md aligned with the BDD suite so the manual never lies about behaviour the tests don't actually exercise.

## Strict division of labour

The point of this skill is to keep the master agent **out of the slow, expensive work** of reading every feature file. The master is the orchestrator and synthesiser; it must never crack open a `.feature` file. All scenario reading, classification, and per-feature summarisation happens in parallel Haiku subagents.

**The master agent MUST:**
- List feature files (`ls tests/e2e/features/*.feature`) — that's the only filesystem read it does on the BDD suite.
- Spawn one Haiku subagent per feature, all in a single tool-call batch (parallel dispatch).
- Wait for all subagents to return.
- Synthesise their structured reports into USAGE.md.

**The master agent MUST NOT:**
- Read any `.feature` file itself.
- Read any `tests/e2e/features/steps/*.py` file itself.
- Spawn subagents serially or in waves — one batch, all at once.
- Use a model bigger than Haiku for the per-feature work.

If the master finds itself wanting to peek at a scenario, that's a signal the per-feature reports are missing detail — re-dispatch the relevant subagent with a more pointed question rather than reading the file directly. Reading the file directly defeats the whole skill: it makes re-curation O(N) wall-clock and burns master-agent context that should be reserved for synthesis.

## Process

### Step 1: Inventory the BDD suite

Run:

```bash
ls tests/e2e/features/*.feature | sort
```

Note the count. If zero, stop and tell the user there are no features to summarise. **Do not open any of the listed files.**

### Step 2: Spawn N Haiku agents in ONE batch (maximal parallelism)

Send a SINGLE response containing N `Agent` tool calls — one per feature file. Use `subagent_type: "general-purpose"`, `model: "haiku"`, `description: "Summarise <feature-name> for USAGE.md"`. Multiple `Agent` blocks in the same tool-use turn run concurrently; sequential dispatch (one Agent per turn) defeats the skill.

A 22-feature suite should produce 22 simultaneous Agent calls. The master agent's job in this step is purely dispatch — it does not read any feature file content.

Each agent prompt uses this template VERBATIM, with `<FEATURE_PATH>` substituted:

> You are summarising a single BDD feature file for inclusion in a user-facing USAGE.md.
>
> Read the file: `<FEATURE_PATH>` (relative to repo root).
>
> For each scenario, decide:
> 1. **User-facing?** Does the scenario describe a workflow, command, MCP tool, or behaviour an end user would actually invoke? Or is it an architectural / safety / regression test that locks an internal invariant but doesn't translate into user guidance? Be honest — many scenarios are pure invariant guards (e.g. "MCP write-surface is bounded") and SHOULD NOT appear in USAGE.md. Skip those.
> 2. **What use case does it support?** One sentence of plain prose, written from the user's perspective ("After indexing, agents can ..."). No Gherkin syntax in the summary.
> 3. **Tag flags.** If the scenario requires `@real_neo4j` or `@real_ollama`, or is `@skip_until_*`, note it so the master agent knows whether to include the use case yet.
>
> Return your report in this exact shape (Markdown), no preamble, no commentary:
>
> ```
> # Feature: <Feature title>
> # File: <path relative to repo root>
> # Concern: <one of: discovery / indexing / graph-plugin / curation / agent-skill / federation / invariant / other>
>
> ## In scope for USAGE.md
> - <use case from scenario "<title>"> [tags: @real_neo4j, @real_ollama]
> - ...
>
> ## Out of scope for USAGE.md
> - "<scenario title>" — <one-line reason; e.g. "internal regression guard">
> ```
>
> Keep the report tight — fewer than 30 lines total. Don't editorialise.

After all subagents return, you have N structured reports in your context. Don't summarise them back to the user yet — go straight to synthesis.

### Step 3: Synthesise USAGE.md from the returned reports

Synthesis works ONLY from the structured reports the subagents returned. Don't read source feature files at this stage either — if a report is too vague, re-dispatch THAT specific subagent with a follow-up question (still Haiku, single Agent call). Do not crack open the file yourself.

Group the in-scope items by **user concern**, not by feature file. Suggested top-level sections (skip any that come back empty; reorder if a different flow reads better):

1. `## Quick start` — minimal install → init → index → search loop. Pulls from `knowledge_base.feature` and the README.
2. `## Indexing` — what gets indexed (Markdown / Python / OpenAPI), gitignore semantics, background re-indexing, embedding cache, worktree behaviour.
3. `## Search and retrieval` — `guru search`, MCP `search`, `get_document`, `get_section`, hybrid vector + graph search.
4. `## The graph plugin` — what it adds, when it's useful, how to opt out, `guru graph` subcommands, MCP `graph_*` read tools.
5. `## Curating knowledge` — annotations (kinds + tags + dedup semantics), typed links between artifacts, orphan triage workflow.
6. `## The agent skill` — what `guru init` installs, refreshing with `guru update`, drift handling and `--force` backups.
7. `## Federation` — discovering peers, federated search, cloning a peer's codebase, unmounting.
8. `## FAQ` — gather common confusion points surfaced across scenarios. Likely candidates:
   - "What happens when the graph daemon isn't running?"
   - "Why doesn't `guru graph` have write commands?"
   - "Can I write a parser for a new file type?"
   - "How do I move my annotations after a refactor?"
   - "What's the difference between `summary` and `note` annotations?"
9. `## Troubleshooting` — recurring failure modes the scenarios exercise (daemon unreachable, embedding misses, malformed YAML, missing Java).

For each section, write running prose in the same voice as README.md. Show concrete commands and tool calls. The reader should never see "the scenario X verifies Y" — they should see "guru lets you Y". Collapse related scenarios into a single paragraph or example.

### Step 4: Cross-link from README.md

Add (or confirm) a one-liner under "Quick start" or near "CLI commands":

> Full usage manual: [USAGE.md](USAGE.md).

### Step 5: Sanity check before reporting done

Run:

```bash
grep -c "^## " USAGE.md
```

Expect at least 5 top-level sections. Then read the file top-to-bottom and ask yourself: would a brand-new user with `guru init` get unstuck? Patch obvious gaps before declaring victory.

## Tips

- **Preserve user-visible terminology exactly** — MCP tool names (`graph_describe`, `graph_annotate`), CLI subcommand names (`guru graph orphans`), config keys (`graph.enabled`), as they appear in the codebase. Drift between docs and reality is the failure mode.
- **Convert deliberate-design constraints into FAQ entries.** Invariant scenarios usually answer a "why" question — "why are CLI graph commands read-only?" → because writes are an agent surface; CLI is for inspection.
- **Don't include `@skip_until_pr*` scenarios.** They describe future state and would mislead today's users.
- **Mention `@real_neo4j` / `@real_ollama` only via natural prerequisite language.** "Requires Java for the graph daemon" / "Requires Ollama for embeddings". Don't litter the doc with internal tag references.
- **Don't rewrite scenarios as Gherkin.** USAGE.md is prose for end users, not a test catalogue.
- **Don't dedicate a section to `constitution_invariants.feature`** — those scenarios are engineering discipline, not user education. They may seed FAQ entries but not their own section.

## Why this design

- **Parallel small-model agents** keep per-file analysis cheap and fast. Haiku is plenty for "is this user-facing? summarise". Spawning N at once means re-curation completes in one round-trip rather than serially walking the suite.
- **Strict delegation** keeps the master agent's context lean and its work bounded to synthesis. If the master starts reading feature files, re-curation cost grows with the BDD suite and the master's context fills with low-value detail it can't fit alongside the synthesis.
- **One-batch parallel dispatch** is the difference between "22-second curation" and "ten-minute curation". Sequential Agent calls compound; one tool-use turn with N Agent blocks runs them concurrently.
- **Master synthesis** is where judgment lives — picking groupings, smoothing voice, deciding what's FAQ-worthy. That's the job of the model running the skill, not the per-file workers.
- **Concern-grouped output** matches how users mentally segment the product (search vs. curation vs. federation), not how the engineering team segmented PRs.
- **BDD-as-source** means the manual cannot promise behaviour that isn't tested. If a scenario lapses or gets `@skip_until_*` tagged, the next re-curation will catch it.
