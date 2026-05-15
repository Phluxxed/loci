#!/bin/bash
# Auto-index the current repo with loci at session start.
# Bails silently if cwd is not inside a git repo (use this as a nudge to
# `git init` work even when you don't plan to push it remotely — and to
# stop loci's index from filling with non-repo parent directories).
# Outputs context that gets injected into the Claude Code session.

LOCI="$(which loci 2>/dev/null || echo "$HOME/.local/bin/loci")"

# Bail silently if loci not installed
if [[ ! -x "$LOCI" ]]; then
    exit 0
fi

# Find the repo root for whatever directory we're in. Handles:
#   - cwd is repo root  -> returns cwd
#   - cwd is a subdir   -> returns the repo root
#   - cwd is a worktree -> returns the worktree root (.git is a file, not a dir)
# Exits empty / non-zero if cwd is not inside a git repo at all.
REPO_ROOT="$(git -C "$(pwd)" rev-parse --show-toplevel 2>/dev/null)"
if [[ -z "$REPO_ROOT" ]]; then
    exit 0
fi

# Run incremental index (fast if nothing changed, silent on errors)
INDEX_OUTPUT=$("$LOCI" index "$REPO_ROOT" --incremental 2>/dev/null)

if [[ $? -eq 0 ]] && [[ -n "$INDEX_OUTPUT" ]]; then
    SYMBOL_COUNT=$(echo "$INDEX_OUTPUT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('symbols_indexed', '?'))" 2>/dev/null)
    echo "loci: repo indexed at $REPO_ROOT ($SYMBOL_COUNT symbols). Use the loci skill for codebase navigation."
else
    # Check if already indexed from a previous session
    LISTED=$("$LOCI" list 2>/dev/null | python3 -c "
import json,sys
repos = json.load(sys.stdin)
root = '$REPO_ROOT'
for r in repos:
    if r.get('path','') == root:
        print(f\"loci: {r.get('symbols','?')} symbols already indexed for {root}. Use the loci skill.\")
        break
" 2>/dev/null)
    if [[ -n "$LISTED" ]]; then
        echo "$LISTED"
    fi
fi
