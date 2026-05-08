# Semble → Loci: Quick Breakdown

## Working read

Semble is not magic context compression. It is a small hybrid code-retrieval system with a surprisingly useful ranker.

The “98% token reduction” claim should be treated as benchmark-shaped marketing, not a real agent-session guarantee. The useful core is still worth stealing: combine lexical search, semantic search, and code-specific ranking priors, then return narrow chunks instead of whole files.

## What Semble actually does

Semble roughly works like this:

1. Walk the repo and skip junk directories.
2. Chunk source files.
3. Build a dense embedding index using a small static code embedding model.
4. Build a BM25 lexical index.
5. Retrieve from both.
6. Fuse rankings with Reciprocal Rank Fusion.
7. Apply code-aware boosts and penalties.
8. Return small relevant chunks instead of dumping entire files.

That is sane. Not revolutionary. But sane is rare enough to keep in jars.

## The genuinely good bits

### 1. Hybrid retrieval

Semble uses both:

- lexical retrieval for exact-ish symbol/path/name matching
- dense retrieval for fuzzy “what does this behaviour smell like?” queries

This is exactly the right shape for loci, but loci should put structural search ahead of both.

Better loci order:

```text
symbol / AST lookup
→ lexical retrieval
→ dense retrieval
→ rank fusion
→ structural expansion
```

Semble starts from search. Loci should start from code structure.

### 2. Query intent detection

Semble changes retrieval weighting based on the query shape.

A symbol-like query should not be treated like a prose question. For example:

```text
parse_config
AuthSessionManager
frontend.healthcheck.ready
```

These should heavily favour exact lexical/symbol matching.

A prose query like:

```text
how does retry logic work
```

should lean more on semantic retrieval.

Loci should steal this, but upgrade it using AST knowledge.

### 3. Identifier decomposition

Semble splits identifiers into useful searchable pieces:

```text
parseConfig       → parse, config
parse_config      → parse, config
ConfigParser      → config, parser
HTTPRetryPolicy   → http, retry, policy
```

This is boring and powerful. Definitely steal.

### 4. Code-aware ranking priors

This is the most valuable part.

Semble boosts or penalises results based on code-shaped hints:

- definition matches beat reference-only matches
- file name/path matches matter
- multiple weak hits in one file can beat one random hit
- implementation files often matter more than tests/examples
- compatibility, legacy, docs-source, and re-export files may deserve penalties

For loci, these should become explicit rank features.

### 5. Token-efficiency framing

Semble’s benchmark is not gospel, but the measurement idea is useful.

Loci should track:

- tokens returned per query
- tokens until first useful context
- whether the agent needed a second retrieval call
- whether the retrieved span was structurally complete
- whether the retrieved context caused wrong edits

This is better than only measuring “did the right file appear in top 10?”

## The okay bits

### Static embeddings

Useful sidecar. Not the throne.

Small static embeddings are fast and cheap, especially CPU-side. But they are not deep code understanding. They are good for fuzzy recall when the user or agent does not know the symbol names.

For loci:

```text
dense search = discovery layer
symbol graph = truth layer
```

### Chunking

Semble’s chunking is serviceable for general search.

For loci, chunks should not be the primary unit. Symbols should be.

Better retrieval units:

```text
module
class
function
method
symbol span
doc/comment span
fallback text chunk
```

Chunks are fallback compost. Symbols are the bones.

### RRF fusion

Reciprocal Rank Fusion is a good simple way to combine rankings from different systems without obsessing over raw score scales.

Worth stealing early.

Later, loci may want a custom scoring model using structural features.

## The bullshit / weak claims

### “98% token reduction”

The number is only meaningful against the benchmark baseline.

It mostly says:

```text
small chunks use fewer tokens than reading whole matched files
```

True. Useful. Not a universal agent claim.

Against a disciplined tool like loci, where the baseline is already outline/get/symbol-window retrieval, the reduction would be much smaller.

### Weak grep baseline

The benchmark’s comparison target appears closer to naive grep plus reading whole files.

That is a bad agent workflow. Useful as a straw-baseline, not a serious competitor to AST-aware retrieval.

### Not real code intelligence

Semble retrieves relevant text. It does not appear to deeply model:

- call graphs
- reference graphs
- symbol identity
- import/export relationships
- stable symbol IDs
- mutation flows
- type relationships
- public/private API surface

That is where loci can win.

## What loci should steal hard

- hybrid retrieval
- BM25 plus semantic search
- Reciprocal Rank Fusion
- query-shape-based weighting
- identifier splitting
- definition boosts
- file/path/stem boosts
- test/example/docs/legacy penalties
- multi-hit file coherence boosts
- token-efficiency evaluation
- simple CLI/MCP tool surface

## What loci should steal lightly

- static code embeddings
- chunking fallback
- auto-reindexing ideas
- benchmark structure
- agent-facing instructions that nudge tools before raw grep/read

## What loci should not steal

- search-first design
- chunks as the core abstraction
- marketing confidence around synthetic benchmark numbers
- treating dense retrieval as code understanding
- assuming one retrieval call should answer everything
- relying on repo text instead of structural identity

## Loci-shaped design direction

Semble is a retriever.

Loci should be a code map with retrieval attached.

Suggested stack:

```text
1. Repo walker
2. Tree-sitter parser
3. Symbol index with stable IDs
4. File/module outline
5. Lexical index over symbols, paths, comments, and bodies
6. Dense embedding sidecar over symbol spans/chunks
7. Ranker with code-aware priors
8. Structural expansion tools
```

Agent-facing flow:

```text
loci outline
loci get <symbol-id | file | path>
loci search <query>
loci related <symbol-id | file:line>
loci refs <symbol-id>
loci callers <symbol-id>
loci imports <file>
```

## The strongest steal

The ranker.

Not the model. Not the token claim. Not the chunker.

The ranker is the goblin engine:

```text
symbol-aware priors
+ path-aware priors
+ identifier splitting
+ definition boosts
+ file coherence
+ lexical/semantic fusion
```

That is the part most likely to improve loci quickly without bloating the architecture.

## Working thesis

Semble proves that a lot of “AI code retrieval” gain comes from normal search-engine craft wearing an embedding hat.

For loci, that is excellent news.

It means the winning move is not chasing a magical model. The winning move is building a precise structural index, then letting lexical and semantic search orbit it like useful little satellites.
