Repository retrieval policy:

For a task about a named declaration's typed input or output contract, fields,
aliases, or explicit heritage, start repository retrieval with `loci_explore`
using `intent="type_dependencies"`. Put the target declaration names and a few
relevant field terms from the task in `query`. Use `seed_ids` only for exact IDs
already returned by a repository tool. Keep the tool's default budgets.

Inspect the returned anchor source, dependencies, relationship proof and
omissions. If the anchor is missing or wrong, use focused `search` or a scoped
`outline`, then call `loci_explore` with the observed target IDs. Retrieve any
still-needed source with targeted `get`, `file` or `grep` calls. Treat an omitted
or unresolved dependency as missing evidence, and finish only when the source
supports the requested answer.

When the task first requires tracing a call to its target declaration, start
with the existing call/reference graph tools and exact source reads. Once the
target is established, use `type_dependencies` if its declared type context is
needed. For other exact source questions, use the existing retrieval tools.

