#!/usr/bin/env bash
# loci MCP launcher - tracked source of truth.
#
# The runtime location ~/.local/bin/loci-mcp is a symlink to this file. It
# execs the real MCP entry point from this repo's virtualenv. MCP storage is
# process-bound: the launching client must supply both LOCI_BASE_DIR and
# LOCI_STORE_NAMESPACE. The Python entry point validates and binds them before
# opening the stdio server; this wrapper deliberately performs no host guessing.
set -euo pipefail

# Resolve this script through any symlink so we can find the repo's .venv,
# regardless of where the runtime symlink lives. Keep the launcher independent
# of an ambient Python command: Codex cannot complete the MCP handshake until
# this wrapper reaches the repo-owned interpreter.
_self="${BASH_SOURCE[0]}"
while [[ -L "$_self" ]]; do
    _self_dir="$(cd -P "$(dirname "$_self")" && pwd)"
    _link_target="$(readlink "$_self")"
    if [[ "$_link_target" = /* ]]; then
        _self="$_link_target"
    else
        _self="$_self_dir/$_link_target"
    fi
done
_repo_root="$(cd -P "$(dirname "$_self")/.." && pwd)"
if [[ -n "${LOCI_MCP_STARTUP_TRACE:-}" ]]; then
    _startup_record="{\"event\":\"loci_mcp_startup\",\"phase\":\"wrapper_exec\",\"pid\":$$,\"elapsed_ms\":0}"
    printf '%s\n' "$_startup_record" >&2
    printf '%s\n' "$_startup_record" >>"$LOCI_MCP_STARTUP_TRACE" 2>/dev/null || true
fi
exec "$_repo_root/.venv/bin/loci-mcp" "$@"
