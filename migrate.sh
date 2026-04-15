#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$repo_root"

mkdir -p .agents

timestamp="$(date +%Y%m%d-%H%M%S)"
backup_dir=".agents/.migration-backup-$timestamp"
mkdir -p "$backup_dir"

note() {
  printf '%s\n' "$*"
}

is_import_shim() {
  local path="$1"
  [ -f "$path" ] && grep -qx '@AGENTS.md' "$path"
}

backup_if_unique_file() {
  local path="$1"
  local name
  name="$(basename "$path")"

  if [ -f "$path" ] && [ ! -L "$path" ]; then
    mv "$path" "$backup_dir/$name"
    note "Backed up $path -> $backup_dir/$name"
  elif [ -L "$path" ] || [ -e "$path" ]; then
    rm -f "$path"
    note "Removed existing compatibility entry $path"
  fi
}

canonical=".agents/AGENTS.md"

# Pick the canonical source.
if [ -f "$canonical" ] && [ ! -L "$canonical" ]; then
  note "Using existing $canonical"
else
  if [ -f AGENTS.md ] && [ ! -L AGENTS.md ]; then
    mv AGENTS.md "$canonical"
    note "Moved AGENTS.md -> $canonical"
  elif [ -f CLAUDE.md ] && ! is_import_shim CLAUDE.md; then
    mv CLAUDE.md "$canonical"
    note "Moved CLAUDE.md -> $canonical"
  else
    cat > "$canonical" <<'EOF'
# Project Agent Instructions

Add shared, agent-agnostic project instructions here.
EOF
    note "Created stub $canonical"
  fi
fi

# Preserve any leftover unique root files.
if [ -f AGENTS.md ] && [ ! -L AGENTS.md ]; then
  backup_if_unique_file AGENTS.md
elif [ -L AGENTS.md ] || [ -e AGENTS.md ]; then
  rm -f AGENTS.md
fi

if [ -f CLAUDE.md ] && ! is_import_shim CLAUDE.md; then
  backup_if_unique_file CLAUDE.md
elif [ -L CLAUDE.md ] || [ -e CLAUDE.md ]; then
  rm -f CLAUDE.md
fi

# Recreate compatibility entrypoints.
ln -sfn .agents/AGENTS.md AGENTS.md
printf '%s\n' '@AGENTS.md' > CLAUDE.md

# Remove empty backup dir if nothing was saved.
rmdir "$backup_dir" 2>/dev/null || true

note
note "Verification:"
note "  AGENTS.md -> $(readlink AGENTS.md)"
note "  CLAUDE.md  -> $(tr -d '\n' < CLAUDE.md)"
note
note "Next checks:"
note "  git status --short"
note "  sed -n '1,40p' .agents/AGENTS.md"
note "  sed -n '1,5p' CLAUDE.md"
