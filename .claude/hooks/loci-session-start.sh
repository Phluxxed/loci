#!/bin/bash
# Claude Code SessionStart hook for loci.
#
# Thin wrapper around .shared/loci-session-start-core.sh. The wrapper's
# only job is platform-specific output formatting:
#   - Claude Code reads the hook's stdout as plain-text session context.
#   - If the core bails (no loci installed, or cwd not in a git repo),
#     this script emits nothing and exits 0.
#
# Source of truth is in the loci repo at .claude/hooks/. The runtime
# location ~/.claude/hooks/loci-session-start.sh is a symlink installed
# by .claude/install-hooks.sh.

# Resolve our real path through any symlink so we can find the sibling
# .shared/ dir. Python's os.path.realpath handles this portably.
_LOCI_HOOK_DIR="$(cd "$(dirname "$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "${BASH_SOURCE[0]}")")" && pwd)"
# shellcheck disable=SC1091
source "$_LOCI_HOOK_DIR/../../.shared/loci-session-start-core.sh"

loci_session_compute

if [[ -n "$LOCI_SESSION_MESSAGE" ]]; then
    echo "$LOCI_SESSION_MESSAGE"
fi
