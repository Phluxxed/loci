#!/usr/bin/env bash

set -euo pipefail

escape_for_json() {
    local s="$1"
    s="${s//\\/\\\\}"
    s="${s//\"/\\\"}"
    s="${s//$'\n'/\\n}"
    s="${s//$'\r'/\\r}"
    s="${s//$'\t'/\\t}"
    printf '%s' "$s"
}

direnv_env="$(ls -d "$HOME"/.direnv/python-* 2>/dev/null | head -n 1 || true)"
if [[ -n "$direnv_env" && -f "$direnv_env/bin/activate" ]]; then
    # Hooks run outside repo-specific activation, so use the shared root Python env.
    # shellcheck disable=SC1090
    source "$direnv_env/bin/activate"
fi

LOCI="$(command -v loci 2>/dev/null || true)"
if [[ -z "$LOCI" && -x "$HOME/.local/bin/loci" ]]; then
    LOCI="$HOME/.local/bin/loci"
fi

message=""

if [[ -n "$LOCI" && -x "$LOCI" ]]; then
    cwd="$(pwd)"
    index_output="$("$LOCI" index "$cwd" --incremental 2>/dev/null || true)"

    if [[ -n "$index_output" ]]; then
        symbol_count="$(
            printf '%s' "$index_output" | python3 -c "import json,sys; data=json.load(sys.stdin); print(data.get('symbols_indexed', '?'))" 2>/dev/null || true
        )"
        if [[ -n "$symbol_count" ]]; then
            message="loci: repo indexed at $cwd ($symbol_count symbols). Use loci for codebase navigation."
        fi
    fi

    if [[ -z "$message" ]]; then
        listed="$(
            "$LOCI" list 2>/dev/null | python3 -c '
import json
import os
import sys

cwd = os.getcwd()
for repo in json.load(sys.stdin):
    if repo.get("path", "") == cwd:
        print(f"loci: {repo.get('symbols', '?')} symbols already indexed for {cwd}. Use loci for codebase navigation.")
        break
' 2>/dev/null || true
        )"
        if [[ -n "$listed" ]]; then
            message="$listed"
        fi
    fi
fi

escaped_message="$(escape_for_json "$message")"

cat <<EOF
{
  "additional_context": "${escaped_message}",
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "${escaped_message}"
  }
}
EOF
