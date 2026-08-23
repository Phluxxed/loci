# Explicit Search Selection Lineage

Status: ready-for-agent

## Problem Statement

Loci is agent-facing navigation infrastructure. Vik does not use it directly; Rowan and other Codex sessions use it to navigate codebases more effectively, and the weekly improvement review depends on its telemetry to identify durable weaknesses.

Loci previously inferred that any symbol retrieval occurring within five minutes of the latest search in the same repository had been caused by that search. It copied the latest search identifier and apparent result rank onto the retrieval event. The analyzer then interpreted missing or low ranks as evidence of search blind spots and poor ranking.

That inference was false. Direct navigation, outline-driven retrieval, unrelated work, and bulk hydration could all happen after a search without representing an agent's selection from that search. In practice, large hydration batches dominated the findings and made the search-quality telemetry untrustworthy. A safety change stopped the analyzer from producing the two causal findings, but the temporal correlation machinery and its `correlated_pct` summary remain even though they have no valid analytical meaning.

The weekly review therefore cannot currently answer an important question: when the agent deliberately chooses source because of a Loci search, did Loci surface that source and rank it usefully?

## Solution

Replace time-based correlation with an explicit, agent-declared lineage contract across the public MCP tools.

A successful non-empty search returns an opaque search identifier. When the agent deliberately selects one or more symbols because of that search, it supplies the identifier to the subsequent get call through an optional parameter whose name states the selection semantics. Direct retrieval, outline-driven navigation, and bulk hydration omit the parameter.

Loci validates the supplied lineage against the recorded search in the same repository, resolves each selected symbol's zero-based rank in the returned result list, and records a distinct explicit-selection event. A selected symbol absent from the returned list is recorded with no rank, representing a result that was not surfaced to the agent. Invalid or cross-repository lineage is rejected rather than silently recorded.

Analysis uses only explicit-selection events for search-ranking and not-surfaced findings. Historical retrieval events carrying inferred search fields remain readable for unrelated retrieval metrics but are never treated as causal evidence. The latest-search cache, five-minute expiry rule, automatic retrieval attribution, and inferred correlation percentage are removed.

The shipped contract is accepted through one end-to-end stdio MCP test covering search output, explicit get input, telemetry persistence, and analyzer output. This tests the same boundary used by the agent rather than only internal logging helpers.

## User Stories

1. As the Codex agent, I want Loci search to return a search identifier, so that I can explicitly reference the search that informed a later source selection.
2. As the Codex agent, I want the identifier to be opaque, so that I do not need to understand or construct Loci's telemetry keys.
3. As the Codex agent, I want an empty search response to have no usable selection identifier, so that a nonexistent search result set cannot accidentally be presented as a source of selections.
4. As the Codex agent, I want get to accept an optional selected-from-search identifier, so that I can declare causation only when it is true.
5. As the Codex agent, I want the optional input name and tool description to state that it means deliberate selection, so that future sessions do not confuse temporal proximity with causation.
6. As the Codex agent, I want a get chosen directly by symbol identifier to omit search lineage, so that direct navigation does not contaminate search-quality evidence.
7. As the Codex agent, I want a get chosen from an outline to omit search lineage, so that outline quality is not misreported as search quality.
8. As the Codex agent, I want bulk hydration to omit search lineage, so that loading every candidate does not look like deliberately choosing every candidate.
9. As the Codex agent, I want a batch get to apply one declared search lineage to every symbol in that batch, so that a deliberately selected group can be recorded without one call per symbol.
10. As the Codex agent, I want to split mixed-purpose retrievals into separate calls, so that selected symbols and hydration symbols cannot share ambiguous telemetry.
11. As the Codex agent, I want Loci to verify that the referenced search exists, so that fabricated or stale identifiers cannot create false evidence.
12. As the Codex agent, I want Loci to verify that the search belongs to the same canonical repository as the get, so that work across repositories cannot be cross-correlated.
13. As the Codex agent, I want an invalid lineage declaration to fail with a structured error before retrieval is recorded, so that telemetry remains fail-closed.
14. As the Codex agent, I want explicit lineage to remain valid without an arbitrary five-minute deadline, so that a real selection remains causal even when analysis or conversation takes longer.
15. As the Codex agent, I want Loci to record the rank of each explicitly selected symbol, so that weekly analysis can measure whether useful source was placed near the top.
16. As the Codex agent, I want rank to be resolved by Loci from the recorded ordered results, so that callers cannot submit convenient or incorrect ranks.
17. As the Codex agent, I want a selected symbol absent from the returned results to remain linked to the originating search with no rank, so that Loci can identify searches that failed to surface source I later needed.
18. As the Codex agent, I want explicit selections stored as their own event type, so that they cannot be confused with historical get events containing inferred correlation fields.
19. As the Codex agent, I want normal retrieval-cost telemetry to remain available for every get, so that causal search repair does not remove unrelated efficiency evidence.
20. As the Codex agent, I want historical inferred search fields ignored by search-quality analysis, so that old contaminated data cannot reappear in future weekly findings.
21. As the Codex agent, I want the analyzer to report counts of explicit selections, ranked selections, and selections not surfaced, so that the evidence base behind a finding is visible.
22. As the Codex agent, I want the analyzer to stop reporting `correlated_pct`, so that absence of an explicit declaration is not misrepresented as a measurable correlation failure.
23. As the Codex agent, I want poor-ranking findings based only on repeated explicit selections, so that a single recent event is not described as a durable pattern.
24. As the Codex agent, I want not-surfaced findings based only on repeated explicit selections, so that weekly review distinguishes recurring search weakness from an isolated miss.
25. As the Codex agent, I want ranking thresholds expressed against zero-based stored ranks but described to humans as result positions, so that implementation and report wording cannot disagree about whether rank three means the third or fourth result.
26. As the Codex agent, I want the repository-owned Loci skill to teach the explicit lineage rule, so that fresh agent sessions use the contract consistently.
27. As the Codex agent, I want existing callers that do not provide lineage to continue working unchanged, so that adding causal tracking does not break navigation clients.
28. As the Codex agent, I want the public MCP schemas to advertise the new output and input, so that the host can serialize and validate the contract without hidden conventions.
29. As the Codex agent, I want the real MCP transport test to prove the selection reaches persisted telemetry and analysis, so that passing isolated unit tests cannot mask a disconnected public contract.
30. As the Codex agent, I want weekly review to consume causal evidence rather than call ordering, so that changes to Loci are driven by trustworthy patterns in how it helps me navigate code.

## Implementation Decisions

- Loci is treated as agent-only infrastructure. Documentation, tool descriptions, and user stories describe the agent as the actor; Vik is the operator and beneficiary, not the tool caller.
- A successful search response gains a nullable opaque `search_id`. It is populated for a non-empty result set and null for an empty result set.
- The search identifier is generated and persisted with the ordered identifiers actually returned to the caller. Search result order is the authoritative ranking envelope visible to the agent.
- The public get contract gains an optional `selected_from_search_id`. Its presence is an explicit assertion that every requested symbol was deliberately selected because of that search. Omission carries no negative meaning; it simply produces no search-selection evidence.
- Existing callers remain source-compatible because the new get input is optional and the existing search fields remain intact.
- Mixed batches are not given another classification protocol. A caller with both selected and hydration symbols must issue separate gets. This keeps the public contract small and prevents per-symbol purpose arrays from becoming a second telemetry language.
- Before retrieving or logging a declared selection, Loci resolves the search identifier from durable session telemetry and verifies the canonical repository matches. Unknown identifiers and repository mismatches produce a structured lineage error and do not write selection or retrieval events for that request.
- Explicit lineage has no time-to-live. Causation comes from the caller's declaration and repository validation, not elapsed time.
- Each symbol in a lineage-bearing get produces one `search_selection` event containing the search identifier, canonical repository, symbol identifier, and resolved rank. The event carries an explicit schema/provenance marker so it is distinguishable from legacy inferred fields.
- Ranks are stored zero-based because they are derived from ordered result identifiers. Reports translate them into one-based result positions when speaking to humans.
- A selected symbol absent from the recorded returned-result envelope produces an explicit selection event with a null rank. This means “not surfaced in the results available to the agent,” not “absent from every possible internal match.”
- Ordinary get events continue to record retrieval size, file size, repository, language, and symbol kind. They no longer receive search identifiers or ranks automatically.
- The latest-search cache, its five-minute expiry behavior, temporal resolver, and automatic get attribution are removed. No replacement ambient state is introduced.
- Analysis reads explicit selection events as the sole causal source for search-quality findings. Legacy get events remain readable for retrieval metrics but their search identifiers and ranks are ignored.
- The analysis summary replaces `correlated_pct` with factual counts: total explicit selections, explicitly ranked selections, and explicit selections not surfaced. It does not report an adoption or correlation percentage because omitted lineage cannot reveal why it was omitted.
- The `search_blind_spot` finding is restored with clarified semantics: it reports repeated explicit selections that were not surfaced in the recorded result envelope.
- The `search_ranking_poor` finding is restored using explicitly ranked selections only. A stored rank of three or greater means the fourth result or lower.
- Percentage thresholds remain 15% for not-surfaced selections and 20% for poor-ranked selections, preserving the intended sensitivity of the prior findings.
- Both restored findings require at least ten eligible explicit selections and at least three matching adverse selections in the requested analysis window. This prevents one or two recent events from being presented as durable patterns.
- Existing analysis-window and repository filtering behavior applies equally to search-selection events. Repository filtering must compare canonical repository identities.
- Existing search-empty telemetry remains separate. This change does not redefine a search that returns no results as an explicit selection event.
- Output schemas and tool descriptions are updated with the new fields and semantics. The get description explicitly says to omit lineage for direct navigation, outline navigation, and hydration.
- The repository-owned Loci skill is updated to require passing the identifier only when a get represents deliberate selection from that search. Its bulk-fetch guidance explicitly omits the identifier for hydration.
- The temporary safety change that suppressed causal findings is superseded by the explicit-event implementation. The findings return only after they are backed by the new event type.

## Testing Decisions

- The primary acceptance seam is one end-to-end test through a freshly started `loci-mcp` stdio server. This is the highest existing boundary and exercises the same schema publication, serialization, service logic, persistence, and analysis path used by Codex.
- The representative end-to-end scenario indexes a small repository, performs a search, captures the returned identifier, explicitly selects one well-ranked result, retrieves another symbol without lineage, and runs analysis. The persisted and analyzed selection count must include only the explicit selection.
- The same boundary test includes an explicitly selected symbol not present in the search result envelope. After enough repeated evidence to meet the durable-pattern floor, analysis must report the not-surfaced finding from explicit selections only.
- The boundary test also establishes enough deliberately low-ranked selections to meet the durable-pattern floor and verifies the poor-ranking finding uses visible result positions correctly.
- A bulk get without `selected_from_search_id` is included in the public scenario and must not change explicit-selection counts or either search-quality finding.
- A get referencing a search from another repository must return the structured lineage error and must not append retrieval or selection events for that failed request.
- A get referencing an unknown search identifier must behave the same way as other invalid lineage, with no partial logging.
- Targeted storage tests cover resolution of a valid search, a selected symbol's zero-based rank, a selected symbol absent from the returned envelope, and rejection of legacy inferred get fields as causal evidence.
- Targeted analyzer tests cover both the percentage threshold and the minimum evidence floor. One or two adverse events must remain below the durable-pattern threshold even when their percentage is 100%.
- Schema tests verify that search success advertises the nullable identifier and get advertises the optional lineage input while retaining object-root success and error schemas.
- Existing CLI and MCP retrieval tests provide prior art for indexing a temporary repository, performing public search/get round trips, and inspecting session telemetry. Existing analyzer tests provide prior art for constructing bounded telemetry windows and asserting finding payloads.
- Tests assert observable contracts and persisted event semantics, not private helper names or the structure of the removed latest-search cache.
- Verification ends when the end-to-end MCP contract and the directly targeted storage, analyzer, and schema checks pass. Independent review and broad regression testing are separate opt-in work.

## Out of Scope

- Building or redesigning the weekly-review skill or command. This spec makes its search-quality inputs trustworthy; the review workflow is separate work.
- Measuring occasions when an agent should have supplied lineage but did not. There is no reliable negative observation for an omitted optional declaration.
- Inferring semantic usefulness from dwell time, conversation order, token usage, or other ambient behavior.
- Tracking human use of Loci. Vik does not use the tool directly.
- Adding a general tracing framework, distributed telemetry service, database, queue, or new control surface.
- Classifying every retrieval purpose. The contract distinguishes explicit search selection from everything else and does not create a wider retrieval-purpose taxonomy.
- Treating all llm-wiki candidate hydration as selection. Hydration remains uncorrelated unless a later consumer explicitly identifies a final chosen result.
- Changing search scoring, indexing, extraction, or ranking algorithms in this implementation. The resulting trustworthy findings may justify those changes later.
- Redesigning existing search-empty, retrieval-cost, refetch-hotspot, extraction, or dead-weight findings.
- Retrofitting explicit causation into historical telemetry. Legacy inferred records remain preserved but excluded from causal analysis.
- Adding causal-lineage inputs to the human-facing CLI unless a concrete agent consumer requires them later.

## Further Notes

- The current worktree already contains a safety fix that suppresses the two contaminated search-quality findings while retaining temporal correlation. Implementers must treat that state as the starting point, not as the completed solution.
- “Not surfaced” is the precise interpretation of a null rank because Loci records the bounded ordered results returned to the agent, not every internal candidate beyond the result limit.
- Explicit lineage makes positive causal evidence trustworthy, but it cannot prove that every qualifying selection was declared. Weekly reports must present counts and findings as evidence from declared selections, not as complete coverage of all navigation behavior.
- The design deliberately uses the existing search, get, telemetry, and analyze boundaries. No new user-facing command or service is required.
