#!/usr/bin/env bash
# loci launcher — tracked source of truth.
#
# The runtime location ~/.local/bin/loci is a symlink to this file. Its job is
# to pick a per-host base dir so Claude Code's index + analytics live under
# ~/.claude and don't commingle with Codex's, then exec the real loci entry
# point from this repo's virtualenv.
#
# Host routing (an explicit LOCI_BASE_DIR from the caller always wins):
#   - Claude Code (CLAUDECODE=1)  -> ~/.claude/loci-index
#   - Codex / anything else       -> ~/.codex/loci-index
set -euo pipefail

if [[ -z "${LOCI_BASE_DIR:-}" ]]; then
    if [[ "${CLAUDECODE:-}" == "1" ]]; then
        export LOCI_BASE_DIR="$HOME/.claude/loci-index"
    else
        export LOCI_BASE_DIR="$HOME/.codex/loci-index"
    fi
fi

# Resolve this script through any symlink so we can find the repo's .venv,
# regardless of where the runtime symlink lives.
_self="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "${BASH_SOURCE[0]}")"
_repo_root="$(cd "$(dirname "$_self")/.." && pwd)"
exec "$_repo_root/.venv/bin/loci" "$@"
