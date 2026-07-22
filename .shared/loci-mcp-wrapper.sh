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
# regardless of where the runtime symlink lives.
_self="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "${BASH_SOURCE[0]}")"
_repo_root="$(cd "$(dirname "$_self")/.." && pwd)"
exec "$_repo_root/.venv/bin/loci-mcp" "$@"
