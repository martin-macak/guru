# Guru

A local-first knowledge-base manager that indexes Markdown, Python, and OpenAPI files in a git repo and serves them to AI agents via RAG over MCP. Runs entirely on your machine with no cloud dependencies.

Two storage layers, both local:
- **LanceDB vector index** (always on) — semantic search across doc-chunks and code-chunks.
- **Neo4j-backed structural graph** (optional, opt-out) — `(:Document)`, `(:Module)`, `(:Class)`, `(:Function)`, `(:Method)`, `(:OpenApiOperation)`, `(:OpenApiSchema)` nodes plus parser-emitted `imports` / `inherits_from` edges and agent-written annotations + typed links. Lets agents pivot from a vector hit into structured neighbourhood traversal.

## Prerequisites

- Python >= 3.13
- [uv](https://docs.astral.sh/uv/) (package manager)
- [Ollama](https://ollama.com) with the `nomic-embed-text` model

```bash
# macOS
brew install ollama

# Linux — see https://ollama.com/download
curl -fsSL https://ollama.com/install.sh | sh

# Pull the embedding model
ollama pull nomic-embed-text
```

### Optional: the graph plugin

Guru's graph plugin is enabled by default, but you can ignore it entirely without installing anything extra — vector search works without it. Pick whichever applies:

- **You don't want the graph.** Skip Java/Neo4j. Set `graph.enabled: false` in your `.guru.json` (or in `~/.config/guru/config.json` for machine-wide opt-out) and the daemon never tries to start. You'll get a small noise reduction; everything except `guru graph *` and the `graph_*` MCP tools behaves identically.
- **You want the graph (subprocess mode, default).** Install **Java 17+** *and* **Neo4j 5.x** yourself — they are not bundled. On macOS: `brew install openjdk@17 neo4j`. Debian/Ubuntu: `apt install openjdk-17-jre neo4j`. Other platforms: see https://neo4j.com/download/.
- **You already have Neo4j (Docker, shared cluster, CI service).** Skip the local Java/Neo4j install. Set the `GURU_NEO4J_BOLT_URI` environment variable (e.g. `bolt://127.0.0.1:7687`) and guru-graph will connect to your Neo4j instead of spawning one.

If you leave the graph enabled but haven't installed Java/Neo4j, indexing still works — guru-graph just logs a one-time `graph unavailable` info message and continues without the graph.

## Install

```bash
uv tool install guru --extra-index-url https://martin-macak.github.io/guru/simple/
```

This installs the `guru`, `guru-server`, and `guru-mcp` commands. The graph daemon entry point (`guru-graph-daemon`) is included too, but you normally never invoke it directly — guru-server lazy-spawns it on the first graph call.

## Quick start

```bash
# Initialize guru in your markdown repo
cd /path/to/your/repo
guru init

# Index your documents
guru index

# Search
guru search "authentication flow"
```

`guru init` creates:
- `.guru/` — runtime directory (gitignored automatically)
- `.guru.json` — indexing rules (version-controlled; edit this file to configure indexing)
- `.mcp.json` — MCP server configuration for AI agents
- `.claude/skills/guru-knowledge-base/` — agent skill that teaches Claude (and other AGENTS.md-compatible clients) how to discover, annotate, and curate the KB
- `.agents/skills/guru-knowledge-base` — symlink mirror of the skill for tooling that reads `.agents/`

Configuration precedence: `./.guru.json` > `./guru.json` (legacy) > `./.guru/config.json` > `~/.config/guru/config.json`

Refresh the agent skill after a `guru` upgrade with `guru update` (use `--dry-run` first; `--force` overwrites user-customised files after backing them up).

Full usage manual — what gets indexed, hybrid search, the graph plugin, curating annotations and links, federation, FAQ, troubleshooting: [USAGE.md](USAGE.md).

## MCP integration

After `guru init`, your `.mcp.json` is configured automatically. AI agents that support MCP (Claude Code, Cursor, Continue.dev) will discover the guru tools.

**Search & retrieval** (always on, vector-only):
- `search` — semantic search across your knowledge base (returns both doc-chunks and code-chunks)
- `get_document` — retrieve a full document
- `list_documents` — browse all indexed documents
- `get_section` — retrieve a specific markdown section
- `index_status` — check index health and stats
- `federated_search` / `list_peers` / `clone_codebase` / `unmount_codebase` — cross-project federation when multiple guru projects share a federation directory

**Graph navigation** (read-only; degrade silently to `{"status":"graph_disabled"}` when graph is off):
- `graph_describe` — fetch a node with its annotations and direct links
- `graph_neighbors` — walk neighbours by direction / rel_type / kind / depth
- `graph_find` — find artifacts by name, qualname prefix, label, tag, or KB
- `graph_orphans` — list annotations whose target was deleted
- `graph_query` — read-only Cypher (writes are rejected at the proxy)

**Graph curation** (the only agent-write surface):
- `graph_annotate` — add a `summary`, `gotcha`, `caveat`, or `note` (summary replaces; others append)
- `graph_delete_annotation` — remove an annotation by id
- `graph_link` / `graph_unlink` — typed `imports` / `inherits_from` / `implements` / `calls` / `references` / `documents` edges between artifacts
- `graph_reattach_orphan` — re-bind an orphaned annotation to its renamed target

The guru server starts automatically when an MCP tool is first invoked. The graph daemon (`guru-graph`) auto-spawns lazily on first graph call.

### Configuring `.mcp.json` manually

If you prefer to configure `.mcp.json` yourself (or add guru to an existing file), add the following entry under `mcpServers`:

```json
{
  "mcpServers": {
    "guru": {
      "command": "guru-mcp"
    }
  }
}
```

`guru-mcp` is installed as a binary by `uv tool install guru`. It inherits the working directory from the agent process, so it automatically finds the `.guru/` directory in the repo you are working in.

If guru is not on your `PATH` (e.g. inside a uv-managed project rather than a global tool install), use the `uv run` form instead:

```json
{
  "mcpServers": {
    "guru": {
      "command": "uv",
      "args": ["run", "guru-mcp"]
    }
  }
}
```

To add guru to an existing `.mcp.json` that already has other servers, just merge the `"guru"` key into the existing `"mcpServers"` object:

```json
{
  "mcpServers": {
    "other-server": { "command": "other-mcp" },
    "guru": {
      "command": "guru-mcp"
    }
  }
}
```

## Configuration

Edit `.guru.json` in your project root to control indexing:

```json
[
  {
    "ruleName": "docs",
    "match": { "glob": "docs/**/*.md" },
    "labels": ["documentation"]
  },
  {
    "ruleName": "specs",
    "match": { "glob": "specs/**/*.md" },
    "labels": ["spec"]
  },
  {
    "ruleName": "exclude-vendor",
    "match": { "glob": "vendor/**" },
    "exclude": true
  }
]
```

Config resolution: `./.guru.json` > `./guru.json` (legacy) > `./.guru/config.json` > `~/.config/guru/config.json`. Rules merge by `ruleName` (local overrides global).

## CLI commands

```
guru init                # set up guru in current directory (installs the agent skill)
guru update              # refresh the agent skill (--force / --dry-run)
guru index [PATH]        # index documents
guru search "query"      # semantic search
guru doc <path>          # get full document
guru doc <path> -s "H"   # get specific section
guru list                # list indexed documents
guru config              # show resolved config
guru server start|stop|status

# Graph plugin (optional; opt out via graph.enabled=false in .guru.json)
guru graph start|stop|status              # control the daemon
guru graph kbs                            # list KBs in the graph
guru graph kb <name>                      # show one KB
guru graph links <name>                   # list a KB's cross-KB links
guru graph describe <node-id>             # show artifact + annotations + links
guru graph neighbors <node-id>            # walk neighbours
guru graph find --name X --label Class    # search artifacts by filter
guru graph annotations <node-id>          # list annotations on one node
guru graph orphans                        # list orphaned annotations
guru graph query 'MATCH (n) RETURN n'     # read-only Cypher (writes blocked)
```

`guru graph` is **deliberately read-only**. Graph mutations (annotations, link create/delete, orphan re-attach) are only available through MCP — agents are the writers; the CLI is for inspection.

## Upgrade

```bash
uv tool upgrade guru --extra-index-url https://martin-macak.github.io/guru/simple/
```

## Uninstall

```bash
uv tool uninstall guru
```

## Troubleshooting

**"guru-server did not start"**
- Check that Ollama is running: `ollama list`
- Ensure the embedding model is installed: `ollama pull nomic-embed-text`

**"command not found: guru"**
- Ensure `~/.local/bin` is on your PATH (uv tool install puts binaries there)
- Run `uv tool list` to verify guru is installed

**Server won't stop**
- Run `guru server stop` or check `.guru/guru.pid` for the process ID

**Graph daemon "not reachable"**
- Run `guru graph status` to check daemon + Neo4j health
- The daemon is lazy-spawned on first graph call; `guru graph start` forces it now
- Subprocess mode requires both **Java 17+** and **Neo4j 5.x** on `PATH` (see [Optional: the graph plugin](#optional-the-graph-plugin) for install commands)
- For an externally-managed Neo4j (e.g. Docker), set `GURU_NEO4J_BOLT_URI` and the daemon connects to it instead of spawning — no local Java/Neo4j install needed

**`guru graph *` commands say "graph is disabled"**
- The graph is opted out in your config. To enable it, set `graph.enabled: true` in `.guru.json` (it's the default — absence of the key means enabled)
- If you don't want the graph at all, this message is the expected behaviour; the rest of guru works as normal

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, testing, and release process.

## Agent Instructions

Shared project instructions for coding agents live in [`.agents/AGENTS.md`](.agents/AGENTS.md).
Root [`AGENTS.md`](AGENTS.md) is a compatibility symlink to that file, and root
[`CLAUDE.md`](CLAUDE.md) imports `@AGENTS.md` so Claude Code reads the same shared
instructions without duplication.

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full architecture constitution.
