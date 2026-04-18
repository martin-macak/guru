# Using Guru

This is the practical manual for developers and maintainers who install guru on their own repositories. The goal: maximise the gain you and your AI agents get from a knowledge base that learns alongside the code.

If you haven't installed guru yet, start with the [README](README.md). This document picks up at "I ran `guru init`, now what?".

## Mental model

Guru gives you two stores backed by one indexing pass:

- A **vector index** (LanceDB, always on) that semantically searches every Markdown / Python / OpenAPI file in your repo.
- A **structural graph** (Neo4j-backed, optional and on by default) that records `:Document → :Module → :Class → :Method`, parser-emitted `imports` / `inherits_from` edges, agent-written annotations, and typed cross-artifact links.

The vector index answers "find me text about X". The graph answers "what does this class call, who calls it, and what did the team learn about it last quarter?". The graph is the part that makes guru a *knowledge* base instead of a search index — every fact agents discover and write back compounds across sessions.

Everything in guru is local. There is no cloud, no telemetry, no shared service. Embeddings come from a local Ollama; the graph runs on a Neo4j subprocess (or one you point it at).

## Quick start

```bash
cd /path/to/your/repo
guru init                       # creates .guru/, .guru.json, .mcp.json, .claude/skills/...
guru index                      # build / refresh the index
guru search "authentication"    # try a semantic query
```

`guru init` is idempotent — re-running it on an existing project leaves your config untouched and only adds what's missing.

After `init`, the agents you use in this repo (Claude Code, Cursor, Continue.dev — anything that reads `.mcp.json`) automatically discover the guru MCP server. The first time an agent calls a guru tool, the server starts in the background; the graph daemon spawns lazily on the first graph call.

## What gets indexed

Three parsers ship out of the box. Files are dispatched to a parser by suffix.

| Parser     | Files                       | Emits in the graph                                           |
| ---        | ---                         | ---                                                          |
| Markdown   | `*.md`                      | `Document`, `MarkdownSection` per H2/H3                      |
| Python     | `*.py`                      | `Document`, `Module`, `Class`, `Function`, `Method` + imports + inheritance edges |
| OpenAPI    | `*.yaml`, `*.yml`, `*.json` | `Document`, `OpenApiSpec`, `OpenApiOperation`, `OpenApiSchema` + `$ref` edges |

OpenAPI's parser is suffix-based, so non-OpenAPI YAML/JSON files are tolerated — they show up as plain `Document` nodes with `openapi=False`. Malformed YAML doesn't crash the index; you get a single `Document` node with `valid=False` and the parse error in its properties so an agent can `graph_describe` it later.

### Configuration

`.guru.json` declares the rules:

```json
[
  { "ruleName": "docs",           "match": { "glob": "docs/**/*.md" },  "labels": ["documentation"] },
  { "ruleName": "specs",          "match": { "glob": "specs/**/*.md" }, "labels": ["spec"] },
  { "ruleName": "exclude-vendor", "match": { "glob": "vendor/**" },     "exclude": true }
]
```

- `match.glob` selects files. Use standard glob syntax.
- `labels` propagate onto the chunks for later filtering at search time. Folder convention works well: `guides/` → `["guide"]`, `references/` → `["reference"]`, etc.
- `exclude: true` removes a path from indexing entirely.
- Rules are evaluated in order; first match wins.

Resolution order: `./.guru.json` > `./guru.json` (legacy) > `./.guru/config.json` > `~/.config/guru/config.json`. Local rules merge over global by `ruleName`. Run `guru config` to see what guru actually resolved.

### .gitignore

Anything matched by `.gitignore` is automatically excluded from indexing. You don't need to mirror entries into `.guru.json` — generated files in `node_modules/`, `dist/`, etc. stay out of the index by default.

### Custom parsers

The parser registry is an extension point. To add a parser for a new file type, write a `DocumentParser` (subclass with `name`, `supports(path)`, `parse(file_path, rule, *, kb_name, rel_path) -> ParseResult`) and register it at startup. Once registered, indexing dispatches matching files to it automatically; emitted chunks land in LanceDB and emitted nodes/edges land in the graph. There are no core changes needed.

## Indexing

### From the CLI

```bash
guru index               # full index
guru index path/to/file  # index a specific path
guru list                # show what's currently indexed
guru status              # health, document count, last index time
```

### Background indexing and incremental updates

`guru-server` exposes an HTTP `/index` endpoint that returns immediately with a `job_id` for async tracking. Re-indexing skips files whose content hasn't changed (content-addressed embedding cache); only modified files are re-embedded, and deleted files drop out of the manifest.

If you append a new section to an existing file, the chunks for the unchanged sections come straight from the cache and only the new section pays the embedding cost. This makes editing-heavy workflows (e.g. drafting docs) feel snappy on re-index.

You can poll job state via `GET /jobs/<id>` for the full job detail (timestamps, status, type).

### Embedding cache

Embeddings are content-addressed — the same chunk content always produces the same cache hit, even across different files or worktrees. Manage the cache with:

```bash
guru cache info                                    # entry count, model name
guru cache clear --yes                             # nuke everything
guru cache clear --model nomic-embed-text --yes    # nuke entries for one model
guru cache prune --older-than 30d --yes            # drop stale entries
guru server status                                 # cache state in the dashboard
```

The `--yes` flag skips the confirmation prompt — useful in scripts.

## Searching

### Semantic search from the CLI

```bash
guru search "OAuth token refresh flow"
guru search "OAuth token refresh flow" -n 5
guru search "OAuth token refresh flow" --filter labels:spec
```

Results are ranked by semantic relevance and include the matching chunk plus its document path and any labels. Filters use the labels you set up in `.guru.json`.

### From an MCP-aware agent

Once `.mcp.json` is in place, agents see these tools. The names and shapes are stable — they're what your agent's prompts can rely on.

**Search and retrieval (always on):**

| Tool              | Purpose                                                                                  |
| ---               | ---                                                                                      |
| `search`          | Semantic query. Returns mixed doc-chunks and code-chunks ranked by relevance.            |
| `get_document`    | Fetch the full content of a file by path.                                                |
| `get_section`     | Fetch one Markdown section by header breadcrumb (e.g. `"Auth > OAuth > Token Refresh"`). |
| `list_documents`  | Enumerate the indexed catalogue, optionally filtered.                                    |
| `index_status`    | Health, document count, last-index timestamp.                                            |

A common agent pattern is search → retrieve: hit `search` to find a relevant chunk, then `get_document` (or `get_section`) to fetch the surrounding context.

### Hybrid search: pivot from a hit into the graph

When the graph plugin is enabled, every code-chunk carries an `artifact_qualname` (e.g. `pkg.services.user.UserService`). An agent that gets a search hit on a method body can then call `graph_describe(qualname)` to pull the class's annotations, methods, and outgoing/incoming `RELATES` edges in one round-trip — no second search needed.

This is where the graph earns its keep: vectors find the *right place* to look, the graph reveals the *neighbourhood*.

### Federated search across multiple repos

If you run guru in multiple repos on the same machine, federation lets one query span all of them. Servers register themselves in a shared federation directory on startup (default name = project directory name; configurable via `name` in `.guru.json`). MCP tools available:

| Tool                | Purpose                                                                              |
| ---                 | ---                                                                                  |
| `federated_search`  | Query every reachable peer in parallel; results grouped by server or merged-and-ranked. |
| `list_peers`        | See who's discoverable, with liveness status.                                        |
| `clone_codebase`    | Mount a peer's repo locally under `.guru/federated/<name>/` for direct file access.  |
| `unmount_codebase`  | Reclaim the cloned directory.                                                        |

Unreachable peers are reported but never fail the call — federated search is best-effort by design.

## The graph plugin

The graph turns "what does my codebase look like?" into a queryable structure. By default it's enabled; opt out per-project with `graph: { "enabled": false }` in `.guru.json` or globally in `~/.config/guru/config.json`.

When the graph is off (or unreachable, or crashed), guru transparently degrades: search and indexing keep working, MCP graph tools return `{"status": "graph_disabled"}` instead of erroring, and CLI graph commands exit 0 with a friendly message. Agents can detect the disabled state and stop attempting graph calls.

### Lifecycle

The graph daemon (`guru-graph`) is a separate process that owns a Neo4j Community subprocess. It auto-spawns the first time `guru-server` makes a graph call. Two modes:

- **Subprocess mode** (default): the daemon spawns and supervises a Neo4j process. Requires Java 21+ on `PATH`.
- **Connect-only mode**: set `GURU_NEO4J_BOLT_URI` (e.g. `bolt://127.0.0.1:7687`) and the daemon connects to a Neo4j you manage yourself (Docker, shared cluster, CI service container). No subprocess spawned.

Manage the daemon explicitly:

```bash
guru graph start    # block until socket is ready
guru graph stop     # SIGTERM the daemon
guru graph status   # daemon PID, Neo4j health, schema version
```

### Inspecting the graph from the CLI

These commands are deliberately **read-only**. Mutations live on the MCP surface; the CLI is for inspection.

```bash
guru graph kbs                          # list registered knowledge bases
guru graph kbs --json                   # same, pipe-friendly
guru graph kb my-project                # detail for one KB
guru graph links my-project             # cross-KB links from this KB
guru graph describe <node-id>           # one artifact + annotations + links
guru graph neighbors <node-id>          # walk neighbours by direction/depth/kind
guru graph find --label Class --kb my-project
guru graph annotations <node-id>        # annotations attached to one node
guru graph orphans                      # annotations whose target was deleted
guru graph query 'MATCH (n:Class) RETURN n.qualname LIMIT 20'   # read-only Cypher
```

`guru graph query` cannot mutate — there is no `--write` flag, and the proxy rejects writes at the daemon level even if you craft a `CREATE` statement.

### Graph MCP tools (read-only)

These are what your agent will reach for during a session. Each one degrades silently to `{"status": "graph_disabled"}` if the daemon isn't reachable.

| Tool              | Purpose                                                                              |
| ---               | ---                                                                                  |
| `graph_describe`  | One node's properties, annotations, and direct links — a single round-trip overview. |
| `graph_neighbors` | Walk by `direction` (in/out/both), `rel_type` (CONTAINS/RELATES/both), `kind`, `depth`, `limit`. |
| `graph_find`      | Filter by `name`, `qualname_prefix`, `label`, `tag`, `kb_name`.                      |
| `graph_orphans`   | List orphaned annotations awaiting triage.                                           |
| `graph_query`     | Read-only Cypher escape hatch for one-off custom traversals.                         |

## Curating knowledge with agents

This is the part of guru that compounds. Annotations and typed links are the durable artefacts your agents leave behind so the next session starts ahead of where this one started. The agent skill installed by `guru init` teaches your AI assistant exactly when and how to write them — what follows here is the manual version.

### Annotations: closed kinds + open tags

Every annotation has a `kind` from a closed vocabulary, plus free-form `tags`:

| Kind       | Semantics                                  | When to use                                                                    |
| ---        | ---                                        | ---                                                                            |
| `summary`  | One per target. Replaces in place.         | The canonical "what does this thing do?" answer.                               |
| `gotcha`   | Append-only.                               | Surprising behaviour, edge case, foot-gun. Saves debugging next time.          |
| `caveat`   | Append-only.                               | Constraint or limitation ("don't call this on the request thread").            |
| `note`     | Append-only.                               | General observation that doesn't fit summary/gotcha/caveat.                    |

Tags are open strings — pick whatever helps you filter later. Common families: `perf`, `latency`, `concurrency`, `api`, `internal`, `deprecated`, `fragile`, `security`.

The agent flow:

1. `graph_describe(target)` — see what already exists. Don't duplicate.
2. If a `summary` already covers the insight: update it (one summary per node, replace-in-place).
3. Otherwise: `graph_annotate(node_id=..., kind="gotcha", body="...", tags=[...])`.

Authorship is stamped automatically — `agent:claude-code`, `agent:<client-name>`, or `user:<email>`. Authorship survives across sessions and is visible in `graph_describe` output.

### Typed links: structure beats prose

If the insight is "X relates to Y", express it as a structural edge, not as a note. The closed `ArtifactLinkKind` vocabulary:

| Kind            | Source                  | Example                                                       |
| ---             | ---                     | ---                                                           |
| `imports`       | Parser-emitted          | `import requests` → `pkg.foo` → `requests`                    |
| `inherits_from` | Parser-emitted          | `class Derived(Base):` → `Derived` → `Base`                   |
| `calls`         | Parser-emitted          | Statically-resolvable function/method calls                   |
| `implements`    | Agent-authored          | `UserService` implements an OpenAPI `UserResource` schema     |
| `references`    | Agent-authored or weak  | A doc references an API endpoint                              |
| `documents`     | Agent-authored          | `docs/auth.md` is the canonical docs for `pkg.auth.AuthService` |

Imports / inheritance / calls come from the parsers. The other three are agent or human work.

```
graph_link(from_id="kb::docs/auth.md", to_id="kb::pkg.auth.AuthService", kind="documents")
graph_unlink(from_id=..., to_id=..., kind="documents")
```

A `graph_link` against a missing artifact returns 404 — the parser must have indexed both endpoints first. Unknown `kind` values are rejected.

Why links over notes: links are queryable. `graph_neighbors(node, rel_type="RELATES", kind="calls")` returns the answer instantly; a note buried in prose is invisible to traversal.

### Orphan triage after refactors

When you rename or delete code, annotations whose target disappeared become **orphans** — they survive but lose their `:ANNOTATES` edge. The agent's triage flow:

1. `graph_orphans(limit=50)` lists them. Each entry includes a `target_snapshot_json` with the original target's id, label, and breadcrumb so context isn't lost.
2. For each orphan, decide:
   - **Renamed/refactored**: search for the new artifact (`graph_find(name=<old name>)` or `graph_find(qualname_prefix=...)`), then `graph_reattach_orphan(annotation_id, new_node_id)`.
   - **Obsolete**: `graph_delete_annotation(annotation_id)`.
   - **Unclear**: leave it; surface to the human.

This workflow assumes the parser has re-indexed after the refactor — which `guru index` does automatically.

## The agent skill

`guru init` installs an MD-format skill at:

- `.claude/skills/guru-knowledge-base/` — for Claude Code and any client that reads `.claude/skills/`
- `.agents/skills/guru-knowledge-base` → symlink to the above (or a directory copy on Windows)

The skill is a `SKILL.md` plus six lazy-loaded reference files (`model.md`, `discovery.md`, `curation.md`, `annotation-shape.md`, `linking-patterns.md`, `orphans.md`). It tells the agent how to discover, when to annotate, when *not* to annotate, the kind/tag taxonomy, the link vocabulary, and the orphan-triage flow.

### Refreshing the skill after a guru upgrade

```bash
guru update             # report-only; reconciles unmodified files, leaves your edits alone
guru update --dry-run   # preview what would change
guru update --force     # overwrite user-customised files (originals saved to <name>.bak.<timestamp>)
```

`guru update` reads the on-disk `MANIFEST.json` (sha256 of every shipped file) and compares against the bytes the new wheel ships:

- shipped == user → no-op
- shipped changed && user matches the manifest → safe overwrite + manifest refresh
- shipped changed && user diverges → **skip**, with a message. Use `--force` to override; user content goes to `.bak.<timestamp>` first

Customising the skill is supported. Future `guru update` runs respect your edits.

## FAQ

### What happens when the graph daemon isn't running?

Search and indexing keep working — they don't depend on the graph. MCP graph tools return `{"status": "graph_disabled"}` and the CLI's `guru graph *` commands exit 0 with `"graph is disabled"`. Agents can use this as a signal to stop calling graph tools and operate vector-only. Indexing never blocks on graph I/O — even a hung daemon won't slow down `guru index`.

### Why are `guru graph` commands read-only?

Mutations are an *agent surface*, not a *human surface*. Annotations and links live in the graph because they want to be written by AI assistants during investigation work. Exposing the same writes via CLI would make it tempting to script ad-hoc mutations that bypass the dedup-and-author-stamp discipline the MCP layer enforces. CLI is for inspection; mutations go through MCP.

### Can I write a parser for a new file type?

Yes. `DocumentParser` is a small protocol (`name`, `supports`, `parse`). Register your parser at startup in `app.py` (or via a startup hook) and indexing dispatches matching files to it. Your parser owns the chunk shape and the graph nodes/edges it emits.

### How do I move my annotations after a refactor?

Re-index with `guru index`. Annotations whose target disappeared become orphans; an agent (or you, via the MCP API) calls `graph_orphans()`, then `graph_reattach_orphan(annotation_id, new_node_id)` for renames or `graph_delete_annotation(annotation_id)` for obsolete entries. The orphan's `target_snapshot_json` preserves the original target context for matching.

### What's the difference between `summary` and `note`?

`summary` is the one canonical "what is this?" paragraph — one per target, replace-in-place. `note` is everything else: an observation, a thought, a side comment. If you call `graph_annotate(kind="summary", ...)` again on the same node, the previous summary is replaced. `note`/`gotcha`/`caveat` always append.

### What's the difference between an annotation and a link?

Annotations capture *judgement* ("this method retries twice on timeout") — prose attached to one node. Links capture *structure* ("this class implements that contract") — typed edges between two nodes. If you can express the insight as "X relates to Y", prefer a link. If it's "X behaves like W in situation Z", use an annotation.

### What runs locally? What's external?

Everything. The vector store (LanceDB) is on disk under `.guru/db/`. The graph store (Neo4j) is a subprocess of the graph daemon, also local. Embeddings come from your local Ollama. There are no cloud calls and no telemetry.

### Does guru work offline?

Yes, after the first `ollama pull nomic-embed-text` to fetch the embedding model. Indexing, searching, graph operations — all local.

### How do I share the knowledge base across teammates?

`.guru.json` is checked in (it's the indexing config). The `.guru/` directory is gitignored and machine-local — each teammate runs `guru index` to build their own. Annotations live in the graph, which is also machine-local. Sharing a curated graph across machines is on the roadmap; today, federated search across separate guru servers (per machine) is the closest thing.

### Can multiple guru servers run on one machine?

Yes — one server per project. They share a single graph daemon and discover each other through the federation directory. `federated_search` queries them all in parallel.

## Troubleshooting

**"guru-server did not start"**
- Check Ollama is running: `ollama list`
- Confirm the embedding model: `ollama pull nomic-embed-text`
- Look for a stale PID file under `.guru/guru.pid`

**"command not found: guru"**
- `~/.local/bin` must be on `PATH` (uv tool install puts binaries there)
- `uv tool list` to confirm the install

**"Server won't stop"**
- `guru server stop`, or kill the PID in `.guru/guru.pid`

**Graph daemon "not reachable"**
- `guru graph status` shows daemon + Neo4j health
- `guru graph start` forces the daemon to start now (instead of waiting for the lazy spawn)
- Subprocess mode needs Java 21+ on `PATH`. To check: `java --version`
- For an externally-managed Neo4j, set `GURU_NEO4J_BOLT_URI` and the daemon will connect instead of spawning

**`guru graph *` says "graph is disabled"**
- The graph is opted out in your config. Set `graph.enabled: true` in `.guru.json` (the default — absence means enabled)

**A YAML or JSON file is showing as `valid=false` in the graph**
- Malformed YAML doesn't crash the index. The file landed as a single `Document` node with `valid=False` and the parse error in its properties. Fix the YAML and re-index.

**Embeddings are slow on re-index**
- Check the cache hit rate: `guru cache info`
- If you've changed the embedding model, the old cache entries are now misses. Either clear them (`guru cache clear --yes`) or `guru cache prune --older-than 30d --yes` to drop stale ones.

**Indexed files I expected aren't in `guru list`**
- Check `.gitignore` — anything tracked there is skipped
- Run `guru config` to see the resolved rule set; confirm the file matches one of the active globs and isn't excluded
