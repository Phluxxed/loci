---
name: loci
description: Agent-owned codebase navigation infrastructure. Use when repository work needs indexed source retrieval. For standalone documentation or configuration checks where symbol navigation is irrelevant, use a targeted direct read. Skip retrieval only when relevant source from the target checkout is already observed, current, and sufficient.
---

# loci — codebase retrieval

Use Loci's normal MCP operations for repository source discovery and exact
continuation. Supply the actual repository root and the question or known
identity. `source-context-v1` selects bounded source anchors.

## Inspect evidence before acting

A filename, recalled summary or startup index count is not source inspection.
Skip retrieval only when the relevant source from the target checkout is already
observed, current and sufficient for this action. Refresh affected evidence after
edits. Exact edits require the full affected source. Inspect callers separately
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

In Code Mode, save each raw result under a distinct key. Display a compact
receipt first; a full multi-source packet can exceed trace output capture.
Successful `content` is empty. For retrieval:

```javascript
const result = await tools.mcp__loci__loci_retrieve({repo, query});
store("loci.retrieve.1", result);
const packet = result.structuredContent ?? result;
if (packet.error) { text(JSON.stringify({error: packet.error})); exit(); }
text(JSON.stringify({
  status: packet.status,
  scope: packet.scope,
  selection: packet.selection,
  anchors: packet.anchors,
  items: packet.items?.map(({node_id, role, source_ref, complete, extent}) =>
    ({node_id, role, source_ref, complete, extent})),
  sources: packet.sources?.map(({id, file, source_ref, content_hash, start_line, end_line}) =>
    ({id, file, source_ref, content_hash, start_line, end_line})),
  relationship_scope: packet.scope?.relationships,
  omissions: packet.omissions,
  usage: packet.usage,
  recovery_key: "loci.retrieve.1"
}));
```

Use `load("loci.retrieve.1")` to inspect selected source in bounded outputs.
For `loci_read`, save the raw result, display status, source metadata,
`complete`, and `next_source_ref`, then display the source content in bounded
pieces. Follow the next reference when needed. Do not drop coverage or
omissions from the conclusion merely because the first receipt is compact.
Recover a display mistake from the saved result. Inspect returned errors before
consuming success fields.

Use `loci_retrieve` for initial discovery and further source context. It creates
or refreshes the source index and returns candidate identities, selected source,
coverage and omissions. Exact IDs and indexed paths select directly; matching
source literals compete before weak metadata and their excerpts include the
match when possible. Read the returned source before deciding it is sufficient.
Several candidates remain alternatives; an omitted match is not disproved.

For an incomplete source item, pass its short `source_ref` unchanged to
`loci_read`. Follow `next_source_ref` until the exact source needed is complete.
A stale or unavailable reference requires fresh retrieval. Re-anchor a returned
node ID with `loci_retrieve` when more source context is needed. Repeating an
identical request against an unchanged snapshot returns the same bounded selection.

Both operations take `repo`. Loci owns selection and byte budgets; there are no
per-request policy controls. A full selected definition is returned when it
fits; otherwise use the excerpt and exact owning-extent `source_ref`. Indexed
file ownership identities remain distinct from declarations. `ownership`, when
present, describes indexed source membership. Normal `relationships=[]` and
`scope.relationships="not_selected"` do not establish independence.

## Coverage and failures

Preserve partial/unknown coverage, candidate ambiguity, inaccessible or stale
source, and budget omissions in conclusions. Source selection does not report
callers, tests, type dependencies or other graph expansion.

Treat `structuredContent.error` as a failure with a code, message and details.
For `REPOSITORY_ROOT_OVERLAP` with `relationship=requested_descendant`, retry
with `details.existing_root` as `repo`; prefix a known file query with the
requested root's path relative to that ancestor.
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
language's diagnostic static resolution guarantee or omission affects the task.
Resolve a file-symlinked `SKILL.md` to its real source path before following
relative references.
