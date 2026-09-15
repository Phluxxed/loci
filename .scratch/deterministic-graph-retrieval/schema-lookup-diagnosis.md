# W1.8.4.4.9.2 — retained schema/declaration lookup diagnosis

## Scope and evidence

This is a read-only diagnosis of the retained v3 t16/t21 round trips.  It
does not interpret successful packet delivery as proof that either agent relied
on it, and it does not propose a provider rerun.

The fixed source roots have the same relevant `binding.ts` content hash,
`fcf9ce8fbbefdffcfdbd461a4c5b08e84f7a36220e99aee6dcdd64ad8ce3ca3f`.
The expected source is the exported TypeScript declaration in
`src/work-context/binding.ts`, lines 48–66:

```ts
export const workContextBindingViewSchema = z
  .object({ /* public binding fields */ })
  .strict();
export type WorkContextBindingView = z.infer<typeof workContextBindingViewSchema>;
```

An exact-path Loci retrieval plus its issued source reference read returned
that source from t16.  The artifact's retained packets confirm the same hash
in t21.  The source is available and a continuation can return it completely.

The currently observed normal implementation is `src/loci/retrieval.py`:

- `_select_anchors` (lines 847–879) takes metadata anchors whenever any exist;
  only zero metadata anchors invoke `_literal_anchors`.
- `_literal_anchors` (lines 904–953) scans files in sorted path order, stores
  the enclosing indexed symbol or file node once per match, and returns that
  insertion order.  It does not score occurrences.  Its file-node anchor is
  hydrated from the beginning of the whole file by `_anchor_addition` (lines
  673–700), not from the literal occurrence.

These are live Loci source observations made through `loci_retrieve` followed
by every `loci_read` continuation to completion.  Normal retrieval documents
the same metadata-then-literal rule and the fixed budgets.

## Retained calls and what each established

| Run / outer call / native item | Exact query | Expected declaration or source | Actual selection and outcome |
| --- | --- | --- | --- |
| v3-01 `call_kBLyJvOPkyiBRKMXfWFwNdIV`, item line 32 | `captureCommandResult binding accepted work context public type imported definition similarly named view type` | `captureCommandResult` options, accepted `WorkContextBinding`, and the public-view distinction | Metadata chose `captureCommandResult`, `WorkContextBindingView`, and `workContextBindingView`. Its proved `uses_type` edges delivered complete `CaptureCommandResultOptions` and `WorkContextBinding` declarations. The function preview was clipped, then `call_eK8Hzm1v2yjGPyW8KRgHp3N5` / line 39 read its exact issued reference successfully. This is successful related graph delivery plus an intended continuation, not a schema lookup failure. |
| v3-01 `call_eK8Hzm1v2yjGPyW8KRgHp3N5`, item line 40 | `src/tool-results/service.ts validateBinding WorkContextBindingView workContextBindingViewSchema` | schema declaration | Metadata chose `validateBinding`, `WorkContextBindingView`, and `workContextBindingView` (1,428 candidates), and related `WorkContextBinding`. It delivered the alias `type WorkContextBindingView = z.infer<typeof workContextBindingViewSchema>` but no schema declaration. The unindexed exact identifier did not become a metadata anchor. |
| v3-01 `call_GK8CoK07yXmSqU2coQ7VOpHN`, item line 47 | `src/work-context/binding.ts workContextBindingViewSchema session_id observed_cwd` | schema fields and the private fields omitted from its view | Metadata chose `BINDING_ID_PATTERN`, `bindingIdForSession`, and a plan section (1,554 candidates). Because metadata was nonempty, the literal fallback was not run. A path plus extra words is not an exact-file query under the published contract, so this is a compound-query / metadata-precedence miss, not evidence of source absence. |
| v3-01 `call_XySoUvHJ0BTS3Fz5t1gP8qde`, item line 54; `call_4xFqZWfs8sf0d0P1I2SAAVlx`, line 61 | `src/work-context/binding.ts` then issued `sr1_uc4yaw6m4xsvsvnvrelezygyxe` | whole binding source | Exact-file selection returned a clipped file anchor; `loci_read` returned the full file successfully. The later fallback shell read in `call_YBdfQXnh7wdNGeEO4GL3A6LE` was therefore agent behavior after a successful Loci continuation, not clipping or availability failure. |
| v3-02 `call_ZRVyUfjsLpNZikXvJVnVSQxH`, line 45; `call_ez9wmYErBFE9acAlhgwOxziu`, line 52; `call_LYIW83lhYtDGEXuJ9nkqXA6R`, line 59 | `captureCommandResult` twice, then issued source ref | callable and accepted binding | The structured packet contained complete options and binding graph content. The first call rendered only `r.content`, so its structured value appeared empty; the second displayed it and read the continuation successfully. Result presentation is a separate observed problem; it does not show a missing declaration. |
| v3-02 `call_VmmouQ2YTpLF0M8J7vWc8RsM`, lines 66–67 | `WorkContextBindingView` and `validateBinding` | public-view type/function and runtime validator | Both metadata queries delivered the relevant declarations and relationships. The view packet's alias names the schema, but it neither contains the schema object nor makes the schema a selected declaration. This is successful related graph delivery with a remaining direct-schema gap. |
| v3-02 `call_jqaicsjZeTF0R7ptB7n2xvVj`, item line 74 | `workContextBindingViewSchema` | exported schema declaration, lines 48–66 | Metadata found no matching declaration node, so literal fallback ran: `mode=literal`, 9 candidates, 6 omitted. Sorted-path/first-match selection chose a documentation section, `src/bootstrap/index.ts` file, and `src/brain-usage/index.ts` file. `src/work-context/binding.ts` was among the literal candidates but came after the three-anchor cap. The returned related `WorkContextBindingView` alias is complete, but it is not the schema. The agent then used direct shell reads in `call_VdY0MqJezFs3lx6uzGdnNBic`. |

The call and item identities above come from each retained
`outer-round-inventory.json` and `observation.json`; no frozen evidence was
modified.

## Diagnosis

1. **The exact schema is not an indexed declaration.** `WorkContextBindingView`
   is a type node and `workContextBindingView` is a function node, while the
   exported lower-camel `const workContextBindingViewSchema` has no node in the
   retained metadata.  This is specific evidence about this declaration class;
   it does not imply that all variables are unindexed (`BINDING_ID_PATTERN` is
   an indexed constant in the same file).
2. **For the exact one-token query, the metadata fallback gate worked as
   designed.** It reached literal lookup because metadata had no anchors.  The
   failure is literal candidate ranking: files are scanned lexically and
   unique enclosing nodes are retained in that order. Documentation and two
   import-consuming file nodes consume the three-anchor budget before the
   declaration's file node.
3. **For the v3-01 compound query, metadata precedence prevented literal
   lookup.** The query was not an exact file path and broad terms generated
   many metadata candidates.  The normal contract documents this behavior, so
   this is an inadequate compound lookup for a direct schema request, although
   it is understandable agent behavior and the subsequent exact-file/read
   path succeeded.
4. **Source clipping is not the causal miss.** The relevant alias source was
   complete; the target declaration was never selected. File and function
   previews were deliberately bounded and every retained continuation read
   succeeded. A different literal rank that merely selects `binding.ts` would
   still preview from byte zero, before the line-48 schema, unless it also
   changes literal-occurrence hydration.
5. **Availability and graph proof are sound but do not demonstrate reliance or
   savings.** The options-to-binding chain and the public-view/validator
   context were delivered with complete static proof. That establishes source
   availability, not that the agents used it or that a change would reduce
   provider tokens.

## Bounded correction options

### Preferred: index conservative top-level TypeScript const declarations

Add a declaration node only for a lexically unambiguous, top-level TypeScript
`const` identifier (including `export const`), retaining its exact declaration
span and normal file ownership. Do not create value/call/type relationships or
infer runtime schema semantics. The existing normal metadata rule already
prioritizes an identical camel/Pascal identifier, so
`workContextBindingViewSchema` becomes an exact metadata anchor and its source
starts at the declaration rather than at the file beginning.

This is the smallest correction that supplies both a deterministic candidate
identity and the source extent the agent actually needed. It preserves
`normal-graph-v1` traversal, exact proof requirements, snapshot/source hashes,
all budgets, and existing ambiguous/unsupported semantics. It is a bounded
parser/index persistence extension, so its change should be justified and
tested as a declaration capability rather than presented as a generic ranking
tweak.

### Alternative: literal declaration-context ranking and occurrence hydration

Keep the schema unindexed, but in literal fallback recognize an exact token in
a supported lexical declaration context, rank that occurrence before imports
and prose, and hydrate a hash-bound window beginning at that occurrence while
keeping the anchor's identity as the containing file. This avoids claiming a
new symbol identity, but it needs both a language-aware declaration-context
check and a source-span path in anchor packing. Ranking alone is insufficient:
the present file-anchor preview begins at byte zero and would still omit the
schema declaration. It therefore changes more retrieval behavior than the
preferred declaration node while producing weaker graph semantics.

Do not change the broad metadata-first gate merely to force literal matching:
doing so would demote supported metadata candidates for ordinary natural
language questions and does not solve the source-span issue.

## Smallest meaningful acceptance checks (for a later repair task)

1. Index a fixture with `export const workContextBindingViewSchema = ...` and
   prove its node id, exact declaration source span/hash, and file ownership.
2. On the fixed t16/t21 snapshot, exact query
   `workContextBindingViewSchema` must select that declaration as a metadata
   anchor and expose its declaration source (not an incidental doc/import file)
   under current fixed limits.
3. The retained compound query must give the exact identifier priority over
   broad incidental metadata candidates when the direct declaration exists.
4. Existing literal-only unknown-token behavior, source/output budgets,
   explicit seed behavior, and no-edge/unsupported/ambiguity qualification
   remain unchanged. No acceptance criterion should claim agent reliance or a
   token reduction without a new controlled measurement.

## Disposition

The bounded diagnosis is complete. It supports a focused declaration-indexing
repair investigation; it does not support a normal-policy redesign, a parser
coverage expansion beyond the narrow declaration form, or a provider trial.
