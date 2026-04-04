#!/bin/bash
# Injected before Agent tool calls to include loci skill context in subagent prompts.
# Requires the loci skill to be installed via the Claude Code marketplace.

SKILL="$HOME/.claude/skills/loci/SKILL.md"

if [[ ! -f "$SKILL" ]]; then
    exit 0
fi

SKILL_CONTENT=$(cat "$SKILL")

cat <<EOF
IMPORTANT: You are about to dispatch a subagent. If the task involves codebase navigation, include the following loci skill content verbatim in the subagent prompt so the subagent can use loci without needing to load the skill itself:

--- BEGIN LOCI SKILL ---
$SKILL_CONTENT
--- END LOCI SKILL ---
EOF
