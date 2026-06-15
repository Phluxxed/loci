#!/usr/bin/env bash
# loci launcher — tracked source of truth.
#
# The runtime location ~/.local/bin/loci is a symlink to this file. Its job is
# to pick the base dir so loci's index + analytics live under ~/.claude, then
# exec the real loci entry point from this repo's virtualenv.
#
# Everything defaults to the Claude Code store so that an interactive
# `loci stats` from a plain terminal (where CLAUDECODE is unset) reads the same
# log that Claude Code sessions write to — no split, no stale "last get".
# An explicit LOCI_BASE_DIR from the caller always wins.
set -euo pipefail

if [[ -z "${LOCI_BASE_DIR:-}" ]]; then
    export LOCI_BASE_DIR="$HOME/.claude/loci-index"
fi

# Resolve this script through any symlink so we can find the repo's .venv,
# regardless of where the runtime symlink lives.
_self="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "${BASH_SOURCE[0]}")"
_repo_root="$(cd "$(dirname "$_self")/.." && pwd)"
exec "$_repo_root/.venv/bin/loci" "$@"
