# Shared core for loci SessionStart hooks (Claude Code + Codex).
#
# Intended invocation by a wrapper (NOT executed directly):
#
#   _LOCI_HOOK_DIR="$(cd "$(dirname "$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "${BASH_SOURCE[0]}")")" && pwd)"
#   # shellcheck disable=SC1091
#   source "$_LOCI_HOOK_DIR/../../.shared/loci-session-start-core.sh"
#   loci_session_compute
#   if [[ -n "$LOCI_SESSION_MESSAGE" ]]; then ... fi
#
# After calling loci_session_compute, the wrapper has:
#
#   LOCI_SESSION_MESSAGE       — formatted plain-text message (empty if bail)
#   LOCI_SESSION_REPO_ROOT     — repo root that was indexed     (empty if bail)
#   LOCI_SESSION_SYMBOL_COUNT  — symbol count                   (empty if bail)
#
# Bail conditions (function returns 0, all three vars stay empty):
#   - loci binary not installed
#   - cwd not inside any git repo (use `git init` to opt in)
#
# Function is defensive: safe to source under `set -euo pipefail`.

loci_session_compute() {
    LOCI_SESSION_MESSAGE=""
    LOCI_SESSION_REPO_ROOT=""
    LOCI_SESSION_SYMBOL_COUNT=""

    # Find the loci binary. Try PATH first, fall back to a common
    # user-local install location.
    local loci
    loci="$(command -v loci 2>/dev/null || true)"
    if [[ -z "$loci" && -x "$HOME/.local/bin/loci" ]]; then
        loci="$HOME/.local/bin/loci"
    fi
    if [[ -z "$loci" || ! -x "$loci" ]]; then
        return 0
    fi

    # Find the repo root for whatever directory we're in. Handles:
    #   - cwd is repo root  -> returns cwd
    #   - cwd is a subdir   -> returns the repo root
    #   - cwd is a worktree -> returns the worktree root (.git is a file)
    # Empty if cwd is not inside any git repo — bail silently.
    local repo_root
    repo_root="$(git -C "$(pwd)" rev-parse --show-toplevel 2>/dev/null || true)"
    if [[ -z "$repo_root" ]]; then
        return 0
    fi
    LOCI_SESSION_REPO_ROOT="$repo_root"

    # Try an incremental index first (fast no-op if nothing changed).
    local index_output
    index_output="$("$loci" index "$repo_root" --incremental 2>/dev/null || true)"

    if [[ -n "$index_output" ]]; then
        local count
        count="$(printf '%s' "$index_output" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('symbols_indexed', '?'))" 2>/dev/null || true)"
        if [[ -n "$count" ]]; then
            LOCI_SESSION_SYMBOL_COUNT="$count"
            LOCI_SESSION_MESSAGE="loci: repo indexed at $repo_root ($count symbols). Use the loci skill for codebase navigation."
            return 0
        fi
    fi

    # Fallback: if `loci index` didn't produce parseable output, see if
    # this repo is already cached from a previous session.
    local listed
    listed="$("$loci" list 2>/dev/null | python3 -c "
import json, sys
target = '$repo_root'
for r in json.load(sys.stdin):
    if r.get('path', '') == target:
        print(r.get('symbols', '?'))
        break
" 2>/dev/null || true)"
    if [[ -n "$listed" ]]; then
        LOCI_SESSION_SYMBOL_COUNT="$listed"
        LOCI_SESSION_MESSAGE="loci: $listed symbols already indexed for $repo_root. Use the loci skill."
    fi
}
