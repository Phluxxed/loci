#!/usr/bin/env bash
# loci MCP launcher - tracked source of truth.
#
# The runtime location ~/.local/bin/loci-mcp is a symlink to this file. It
# mirrors .shared/loci-wrapper.sh so MCP and CLI use the same safe default
# routing, then execs the real MCP entry point from this repo's virtualenv.
#
# Host routing (an explicit LOCI_BASE_DIR from the caller always wins):
#   - Claude Code (CLAUDECODE=1)  -> ~/.claude/loci-index
#   - Bare terminal / anything else -> ~/.codeindex
#
# Agent hosts that need their own stores must pass LOCI_BASE_DIR explicitly via
# MCP config or hooks. A bare terminal must not write to an agent-owned store.
set -euo pipefail

if [[ -z "${LOCI_BASE_DIR:-}" ]]; then
    if [[ "${CLAUDECODE:-}" == "1" ]]; then
        export LOCI_BASE_DIR="$HOME/.claude/loci-index"
    else
        export LOCI_BASE_DIR="$HOME/.codeindex"
    fi
fi

# Resolve this script through any symlink so we can find the repo's .venv,
# regardless of where the runtime symlink lives.
_self="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "${BASH_SOURCE[0]}")"
_repo_root="$(cd "$(dirname "$_self")/.." && pwd)"
exec "$_repo_root/.venv/bin/loci-mcp" "$@"
