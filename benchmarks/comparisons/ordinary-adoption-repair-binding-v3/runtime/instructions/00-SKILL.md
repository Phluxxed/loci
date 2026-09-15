---
name: loci
description: Agent-owned codebase navigation infrastructure. Use when repository work needs source retrieval or relationship tracing. For standalone documentation or configuration checks where symbol navigation is irrelevant, use a targeted direct read. Skip retrieval only when relevant source from the target checkout is already observed, current, and sufficient.
---

# loci — codebase retrieval

Use Loci's normal MCP operation for repository source discovery and relationship
tracing. Supply the actual repository root and the question or known identity.
Loci selects graph context deterministically inside the operation.

## Inspect evidence before acting

A filename, recalled summary or startup index count is not source inspection.
Skip retrieval only when the relevant source from the target checkout is already
observed, current and sufficient for this action. Refresh affected evidence after
edits. Exact edits require the full affected source, including relevant callers
when the change depends on them.

## Normal workflow

First locate the normal entrypoints by their exact operation names. With
`tool_search`, search for `loci_retrieve` and `loci_read`. In Code Mode, use
this names-only discovery pass:

```javascript
const matches = ALL_TOOLS.filter(t => /(?:^|__)loci_(?:retrieve|read)$/.test(t.name));
store("loci.normal.tools", matches);
text({
  status: matches.length ? "found" : "no_match",
  count: matches.length,
  names: matches.slice(0, 8).map(t => t.name)
});
```

Then exact-match the selected name and read its complete live description and
input declaration before invoking it. Discovery returns names only; full
descriptions belong to that second, single-tool pass. A zero-match result
requires the setup check below; it does not establish missing configuration.

```text
loci_retrieve(repo, query="the source or behavior needed")
loci_retrieve(repo, query="src/known-file.ts")
loci_retrieve(repo, seed_ids=[known_id], query="remaining source question")
loci_read(repo, source_ref=returned_item.source_ref)
```

Use `loci_retrieve` for initial discovery and further context. It creates or
refreshes the index and runs the maintained graph policy. The response includes
candidate identities, selected source, proved relationships, coverage and
omissions. Read the returned source and proof before deciding it is sufficient.
Several candidates remain alternatives; an omitted match is not disproved.

For an incomplete source item, pass its short `source_ref` unchanged to
`loci_read`. Follow `next_source_ref` until the exact source needed is complete.
A stale or unavailable reference requires fresh retrieval. Re-anchor a returned
node ID with `loci_retrieve` when further context is needed. Repeating an identical request
against an unchanged snapshot returns the same bounded selection.

Both operations take `repo`. Traversal families, direction, depth, ranking and
budgets are owned by Loci; there are no per-request policy controls. An import's
file/package/module endpoint remains distinct from its selected declarations.
The `ownership` field describes indexed source membership and is not a semantic
relationship. A zero-edge packet does not prove that no dependencies exist.

## Coverage and failures

Preserve partial/unknown coverage and unsupported, unresolved, ambiguous,
external, inaccessible, stale and budget omissions in conclusions. Stored edges
prove only the supported static relationship, not runtime dispatch or exhaustive
impact. Rust `declared_possible` configuration remains possible.

Treat `structuredContent.error` as a failure with a code, message and details.
A busy catalog or refresh lock calls for a bounded retry after the writer can
finish; it does not authorize catalog repair. For repeated unchanged failures,
report the limitation and use a targeted source-read fallback where necessary.
Standalone documentation or configuration checks where symbol navigation is
irrelevant may use a targeted direct read.

## Setup and operator diagnostics

The normal MCP catalog contains `loci_retrieve` and `loci_read`. If focused
discovery cannot find them, read
[setup-and-cli.md](references/setup-and-cli.md) for local stdio setup, store
identity and the temporary fallback. An old loaded catalog can require a fresh
host session after installation. Report the actual visibility limitation.

Low-level search, outline, get, explore and graph utilities belong to an
operator-selected diagnostic server. Changing the surface is an installation
choice, not ordinary retrieval routing. When explicitly investigating Loci
itself through that surface, consult
[graph-navigation.md](references/graph-navigation.md) and
[tool-contracts.md](references/tool-contracts.md).

Read [normal-retrieval.md](references/normal-retrieval.md) when interpreting the
normal packet, exact-source continuation or work limits. Read
[language-resolution.md](references/language-resolution.md) when a particular
language's static resolution guarantee or omission affects the task.
Resolve a file-symlinked `SKILL.md` to its real source path before following
relative references.
