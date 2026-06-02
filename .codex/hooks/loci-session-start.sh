#!/usr/bin/env bash
# Codex SessionStart hook for loci.
#
# Thin wrapper around .shared/loci-session-start-core.sh. The wrapper's
# only job is platform-specific output formatting:
#   - Codex expects a JSON envelope with hookSpecificOutput fields.
#   - This script always emits the envelope; additionalContext is empty
#     if the core bailed (no loci installed, or cwd not in a git repo).
#
# Source of truth is in the loci repo at .codex/hooks/. The runtime
# location ~/.codex/hooks/loci-session-start.sh is a symlink installed
# by .codex/install-hooks.py.

set -euo pipefail

# Hooks run outside repo-specific activation, so pull in the shared root
# Python env via direnv if one exists.
direnv_env="$(ls -d "$HOME"/.direnv/python-* 2>/dev/null | head -n 1 || true)"
if [[ -n "$direnv_env" && -f "$direnv_env/bin/activate" ]]; then
    # shellcheck disable=SC1090
    source "$direnv_env/bin/activate"
fi

# Resolve our real path through any symlink so we can find the sibling
# .shared/ dir.
_LOCI_HOOK_DIR="$(cd "$(dirname "$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "${BASH_SOURCE[0]}")")" && pwd)"
# shellcheck disable=SC1091
source "$_LOCI_HOOK_DIR/../../.shared/loci-session-start-core.sh"

loci_session_compute

escape_for_json() {
    local s="$1"
    s="${s//\\/\\\\}"
    s="${s//\"/\\\"}"
    s="${s//$'\n'/\\n}"
    s="${s//$'\r'/\\r}"
    s="${s//$'\t'/\\t}"
    printf '%s' "$s"
}

escaped_message="$(escape_for_json "${LOCI_SESSION_MESSAGE:-}")"

cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "${escaped_message}"
  }
}
EOF
