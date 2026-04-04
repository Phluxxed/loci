#!/bin/bash
# Auto-index the current working directory with loci at session start.
# Outputs context that gets injected into the Claude Code session.

LOCI="$(which loci 2>/dev/null || echo "$HOME/.local/bin/loci")"

# Bail silently if loci not installed
if [[ ! -x "$LOCI" ]]; then
    exit 0
fi

CWD="$(pwd)"

# Run incremental index (fast if nothing changed, silent on errors)
INDEX_OUTPUT=$("$LOCI" index "$CWD" --incremental 2>/dev/null)

if [[ $? -eq 0 ]] && [[ -n "$INDEX_OUTPUT" ]]; then
    SYMBOL_COUNT=$(echo "$INDEX_OUTPUT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('symbols_indexed', '?'))" 2>/dev/null)
    echo "loci: repo indexed at $CWD ($SYMBOL_COUNT symbols). Use the loci skill for codebase navigation."
else
    # Check if already indexed from a previous session
    LISTED=$("$LOCI" list 2>/dev/null | python3 -c "
import json,sys
repos = json.load(sys.stdin)
cwd = '$(pwd)'
for r in repos:
    if r.get('path','') == cwd:
        print(f\"loci: {r.get('symbols','?')} symbols already indexed for {cwd}. Use the loci skill.\")
        break
" 2>/dev/null)
    if [[ -n "$LISTED" ]]; then
        echo "$LISTED"
    fi
fi
