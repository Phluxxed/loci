# Repaired normal graph retrieval: live acceptance

The restarted Codex Loci server now executes the repaired selection policy.
The options query and explicit-anchor pair both deliver the previously omitted
`CaptureCommandResultOptions -> WorkContextBinding` relation, including exact
type use, public import, barrel re-export, defining type and resolver controls.

| Live request | Native result bytes | Required result |
| --- | ---: | --- |
| Options query | 16,091 | Complete binding identity proof |
| Explicit pair | 16,019 | Complete binding identity proof |
| Browser query | 14,417 | Forward call and reverse caller/barrel proof |
| Renderer query | 16,117 | Forward and reverse calls |
| Exact binding file | 15,498 | Original file identity and paging locator |
| Read page 1 | 9,568 | Exact bytes 0–8,192; continuation retained |
| Read page 2 | 6,827 | Exact bytes 8,192–14,082; terminal continuation |

Each successful response is uniquely attributable to an original native call
and complete model-visible outer JSON value. Native envelope bytes equal the
reported output usage. Source hashes, byte/line spans and locators validate.
The two pages reconstruct the entire file exactly; the first page alone remains
incomplete. All normal responses retain partial coverage and explicit omissions.

The initial request failed with `PATH_NOT_FOUND`: the old temporary source copy
had disappeared. That result is retained without proof. The source was restored
from Anvil commit `53bf29e60cece2335aa39fe301935a07e8e8d4e4`; every one of the
638 frozen file hashes matches with no extras, before and after live requests.
Historical archive bytes remain unavailable. All 45 frozen audit inputs match.

Evidence: [native validation](../../.scratch/deterministic-graph-retrieval/repair-host-acceptance-20260915/validation-summary.json),
[call/proof provenance](../../.scratch/deterministic-graph-retrieval/repair-host-acceptance-20260915/capture-native-receipt.json),
and [source restoration](../../.scratch/deterministic-graph-retrieval/repair-host-acceptance-20260915/source-restoration-receipt.json).
Primary source inspection adopts the nine passing checks and their qualifications.
The actual native prefix is intentionally unfinished; no completed primary
trial interval or per-case provider cost is fabricated.

**W1.8.4.4 remains open for ordinary value.** These directed functional checks
establish activation and delivery, not lower ordinary token use or better answers.
Vik selected two fresh binding tasks to measure the original 2.72x regression.
Their [separate protocol](../../benchmarks/comparisons/ordinary-adoption-repair-binding-v1/protocol.md)
preserves the original prompts, source, required facts and per-case cost ceiling.
That narrow result cannot close the remaining original workload requirements.
