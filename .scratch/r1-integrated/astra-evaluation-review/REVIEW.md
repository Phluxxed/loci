# Astra escalation: R1 task and evaluation validity

**Verdict: the primary failure is experimental design and interpretation.** The four cases support an operational smoke test and an observation of non-use on tiny problems. They do not establish a general adoption failure or meaningfully test whether R1 helps an agent acquire sufficient engineering evidence efficiently. Primary responsibility belongs to task selection, evaluator design and the lead's interpretation, not to Terra.

Requested by Vik after the completed pilot. Reviewer: fresh native `gpt-6-astra`, reasoning `max`, `fork_turns=none`; read-only scope. It inspected all frozen source trees, task prompts, oracles and answers; grading code; representative complete native tool sequences; and model-visible startup context across all 16 traces. It did not run models, change scores, investigate the runtime cause of context differences or review the underlying semantic/proof algorithms as a new architecture exercise. Primary independently reproduced source sizes, the exact context groups/hashes and the relevant prompt/oracle contradictions.

## Required: workloads contain almost no navigation difficulty

| Task | Entire source repository | JS source | Physical JS lines |
|---|---:|---:|---:|
| receipt-location | 9 files / 1,016 bytes | 7 files / 909 bytes | 17 |
| inventory-contract | 9 / 1,093 | 7 / 986 | 17 |
| dispatch-ambiguity | 9 / 912 | 7 / 805 | 16 |
| zero-quantity | 8 / 939 | 6 / 832 | 14 |

All four entire repositories together are 3,960 bytes. The active receipt route is 675 bytes in four files. The active inventory route is 850 bytes across five files named in their order by the prompt. Dispatch's prompt already warns against one unconditional target, and the quantity prompt identifies the separate CLI contract.

This appears in actual acquisition: inventory-native reads all nine files in one parallel stage (its archived rollout line 35); dispatch-integrated reads the whole repository using one `rg -n '^'` command (rollout line 38). An additional discovery/retrieval step has little opportunity to save source acquisition when all relevant source fits in one ordinary response. Non-use is compatible with a rational native strategy; motives cannot be established from the records inspected.

Evidence: `pilot/frozen-final/<task>/source/` and prompts, particularly `inventory-contract/prompt.txt:4`; `pilot-availability-v2/archived-runs/inventory-contract-native/observer/qualification/native-rollout.jsonl:35`; equivalent dispatch-integrated rollout line 38.

**Smallest remedy:** retain these as easy controls or smoke fixtures. Prospectively choose real acquisition workloads from an independent, tool-neutral pool; do not select cases because Loci wins or pad source until use appears.

## Required: all seven frozen failures depend on rubric assumptions

Three receipt failures are strict nested representation mismatches. Its oracle line 7 expects bare symbol strings. Integrated supplies path-qualified symbols, eager supplies file/symbol objects, and path-only models the key producer as `key_from`. The visible preamble requests exact paths and symbols without a complete nested schema. `src/billing/submit.js:4` calls the key producer, and line 5 separately calls the sender: those are sibling calls. Flattening both into a linear list conflates call order and call relationships. The requested distinction between receipt helpers also has no explicit answer field/assertion. This is a prompt/rubric defect; it does not establish that every textual requirement was satisfied by every answer.

One inventory failure similarly rejects correct ordered paths plus symbol objects because its oracle line 7 expects strings; the general preamble encourages symbol citations.

Three quantity failures arise from persisted regression tests. All four implementations pass the specified runtime assertions. The visible prompt asks for a relevant check, and the active AGENTS instructions explicitly say to leave a focused verification behind for non-trivial behavior. The wrapper's hidden allowed_changes list nonetheless rejects three added `test/quantity.test.js` files. This is a harness/prompt contradiction, not evidence that these code changes have worse behavior.

Evidence: `pilot/frozen-final/receipt-location/oracle.mjs:7`, its `source/src/billing/submit.js:4`; `inventory-contract/oracle.mjs:7`; `zero-quantity/prompt.txt:4`; `benchmarks/complete_work/r1.py:536` and `:543`; `pilot-create.py:82`; zero-quantity-native's archived rollout line 8 (instructions) and line 58 (test addition).

**Smallest remedy:** prospectively publish complete output types and permitted edits. Grade actual source relationships and behavioral requirements separately from serialization/protocol failures. Preserve existing frozen scores; do not invent a new aggregate quality score or retroactively declare every answer fully compliant.

## Required: unrelated delivered context is aligned with condition

The extra context is separate from the already-recorded personal AGENTS update. In all 16 traces, physical JSONL line 5 is a developer message with six content blocks. Concatenating the `content[].text` values **without separators** yields:

| Condition group | Runs | UTF-8 bytes | Skill entries | SHA-256 |
|---|---:|---:|---:|---|
| Native | 4 | 32,033 | 31 | `7f8eeabe89699601c223193686cbe72fc7ddf1121f45b9437ca693f2243f5bd0` |
| Loci-enabled | 12 | 41,869 | 58 | `e0dfbc365ff17f4c9f60daaaee89f4b3d6f3f295f4295a5d0c626fe11f3ae774` |

The enabled condition has 9,836 extra bytes, including unrelated Drive, Notion, Pages, Promptfoo, pet and plugin skills, with different Sites entries/versions. Both group hashes are stable within their group. An additional developer message at line 4 is identical in all 16 traces, which does not remove the line-5 difference.

Minimal reproduction against an archived trace:

```python
p = json.loads(trace.read_text().splitlines()[4])["payload"]
text = "".join(c.get("text", "") for c in p["content"])
raw = text.encode("utf-8")
print(len(raw), hashlib.sha256(raw).hexdigest())
print(sum("(file:" in line for line in text.splitlines()))
```

Using newline separators instead adds five bytes to each group; the 9,836-byte difference is unchanged. The retained checks use the no-separator convention above.

**Consequence:** native-versus-Loci token/time differences include an unrelated, perfectly condition-aligned context difference. Configuration hashes did not qualify equivalent rendered instructions. The three enabled conditions share this particular context hash; this finding does not claim that this specific difference exists between those three arms. Runtime cause was not investigated. No post-hoc token subtraction or causal correction is justified.

**Smallest remedy:** qualify actual rendered common startup context before measurement, allowing only declared treatment differences, rather than treating global file equality as sufficient or freezing every personal setting.

## Required: availability is not understanding or broad adoption failure

`benchmarks/complete_work/availability.py:14` shows that the measured prefix returns tool names only. The richer instructions to fetch full contracts and invoke operations belong to the separate operational probe at lines 59–69. The inspected integrated startup does not provide `loci_semantic` or `loci_proof` contracts. Ambient discovery guidance still names `loci_index`, `loci_search` and `loci_file` (receipt-location-integrated rollout line 13). The correct live descriptions remain discoverable, but scored agents do not fetch them.

Successful probes establish callability on their fixture, and scored catalogs establish name exposure. They do not establish that agents understood when the new capabilities would help. There is no observed failed R1 invocation supporting a host-callability explanation, nor readable reasoning evidence establishing agent motives. Tiny workloads, unfamiliar affordances and preferences remain competing explanations for zero use.

**Smallest remedy:** provide enabled arms concise, accurate capability descriptions while retaining native tools and voluntary use. Do not force retrieval to manufacture treatment uptake.

## One bounded prospective correction, not another framework

Astra recommends one replacement four-task pilot in the existing native harness, **only after task/rubric/input qualification**:

1. Select from a fixed, tool-neutral source pool before any candidate run. Keep an easy control. Other cases must require evidence spread across meaningful source with plausible alternatives, rather than source that fits in one unfiltered read. Record source sizes, required evidence spans and ambiguity counts. Do not select on Loci use, a Loci win or native failure.
2. Preserve source-location, relationship/contract, genuine uncertainty and bounded behavioral-change purposes. Include a supported relationship and a case whose correct answer retains uncertainty. Give realistic symptoms or entry points, not the full answer route. Publish exact output/file constraints and independently assess behavior/source facts.
3. Freeze and verify actual common instructions, relevant capability descriptions, normal native tools, sources/scorers/model/effort/order. Distinguish names seen, contracts seen, attempted calls, successful evidence delivery and evidence used in the result. Measure startup/acquisition/task/validation boundaries, retaining unknown attribution as unknown.

Correctness remains primary, then time and effort for comparable successful work. If realistic qualified tasks still finish cheaply through native tools with no Loci use, that is a valid scoped negative finding. Zero uptake leaves mechanism utility unidentified; do not keep reshaping tasks until adoption appears.

No replacement tasks, scorers, harness edits or runs were created by this review. Implementing the prospective correction is separate work.

## Primary disposition and corrected interpretation

All four consequential findings are adopted. Primary verified the source-size totals, exact context hashes and pertinent prompt/oracle/code evidence. The broader previous attribution to product/workflow adoption failure is withdrawn. The execution records, availability checks, accounting, independent replay and frozen scores remain intact.

**Corrected conclusion:** “The pilot's task and evaluator design failed to identify R1's engineering utility. Availability was verified; voluntary use was absent on four approximately 1 KB fixtures. Comparative correctness and efficiency claims are unsupported.”

Holding an advancement claim for insufficient evidence is defensible. Product/workflow redesign because this allegedly proves a broad adoption failure is not. Keeping frozen evidence unchanged was correct; recognizing and reporting the validity gap before another scored replication was the lead's responsibility. This correction does not assess the semantic/proof algorithms as deficient or excuse the evaluation mistakes as Terra behavior.

The original published report remains at `pilot-availability-v2/analysis/REPORT.md` and commit `eafcfdd3`; this review supersedes its adoption-failure interpretation, without modifying the underlying evidence or scores.
