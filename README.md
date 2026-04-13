# Guru

A local-first knowledge-base manager that indexes markdown documents in a git repo and serves them to AI agents via RAG over MCP. Runs entirely on your machine with no cloud dependencies.

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

## Install

```bash
uv tool install guru --extra-index-url https://martin-macak.github.io/guru/simple/
```

This installs the `guru`, `guru-server`, and `guru-mcp` commands.

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

Configuration precedence: `./.guru.json` > `./guru.json` (legacy) > `./.guru/config.json` > `~/.config/guru/config.json`

## MCP integration

After `guru init`, your `.mcp.json` is configured automatically. AI agents that support MCP (Claude Code, Cursor, Continue.dev) will discover the guru tools:

- `search` — semantic search across your knowledge base
- `get_document` — retrieve a full document
- `list_documents` — browse all indexed documents
- `get_section` — retrieve a specific markdown section
- `index_status` — check index health and stats

The guru server starts automatically when an MCP tool is first invoked.

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
guru init                # set up guru in current directory
guru index [PATH]        # index documents
guru search "query"      # semantic search
guru doc <path>          # get full document
guru doc <path> -s "H"   # get specific section
guru list                # list indexed documents
guru config              # show resolved config
guru server start|stop|status
```

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

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, testing, and release process.

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full architecture constitution.
