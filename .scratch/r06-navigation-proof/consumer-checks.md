# R0.6 retained consumer uncertainty checks

**Status: PASS**

Independent raw JSON/gzip comparison of consumer uncertainty against each paired native case-index projection. No candidate summarizer, scorer, source resolver, or measurement was run.

## Coverage

- Comparisons: 4
- Uncertainty-bearing packet responses checked: 1456
- Old R0.5 demand baseline responses confirmed without the R0.6 uncertainty field: 1044
- Passed packet checks: 1456; failed: 0
- `rust_unproven_contracts` target observations: 72
- Uncertainty-bearing packets with `status=empty` and partial uncertainty coverage: 36

Each candidate repetition includes initial and immediate-repeat responses. Each focused arm includes its initial semantic packet and focused same-slice packets. Full and targeted demand-focused and focused-wide comparisons are included.

## `rust_unproven_contracts`

The native projection and consumer summary agree for each checked packet. The case retains one external import, four unresolved symbol references, and two unresolved type records with reason `type_parameter`. The nested `import_unresolved_reason=external` is preserved in an example. `configuration_possible_count` is read from native records marked `declared_possible`; the packet's explicit meaning says those do not establish active configuration. This audit validates uncertainty delivery only; it does not duplicate the retained strict proof replay.

Some focused packets have `status=empty` because they delivered no source item or proof relationship. Where native uncertainty is present, those packets still expose the reason counts and report `scope.coverage=partial`, `scope.exhaustive=false`, and nonempty omissions; this status label therefore does not hide uncertainty or claim absence.

## Unsupported language boundary

Python and Go remain a separate capability gap: R0.5 retained outcomes classify them as source-only, with 25 authored positive links receiving no semantic credit. Those are not native unresolved-record counts and are not used to inflate the checks above.

## Per-comparison response counts

| Comparison | Arm | Packet files | Responses with uncertainty | Responses without uncertainty |
|---|---|---:|---:|---:|
| full-demand-focused | control-1-suite-0 | 34 | 0 | 228 |
| full-demand-focused | control-1-suite-1 | 38 | 0 | 214 |
| full-demand-focused | control-2-suite-0 | 34 | 0 | 228 |
| full-demand-focused | control-2-suite-1 | 38 | 0 | 214 |
| full-demand-focused | variant-1-suite-0 | 34 | 126 | 192 |
| full-demand-focused | variant-1-suite-1 | 38 | 86 | 176 |
| full-demand-focused | variant-2-suite-0 | 34 | 126 | 192 |
| full-demand-focused | variant-2-suite-1 | 38 | 86 | 176 |
| full-focused-wide | control-1-suite-0 | 34 | 126 | 192 |
| full-focused-wide | control-1-suite-1 | 38 | 86 | 176 |
| full-focused-wide | control-2-suite-0 | 34 | 126 | 192 |
| full-focused-wide | control-2-suite-1 | 38 | 86 | 176 |
| full-focused-wide | variant-1-suite-0 | 34 | 124 | 192 |
| full-focused-wide | variant-1-suite-1 | 38 | 86 | 176 |
| full-focused-wide | variant-2-suite-0 | 34 | 124 | 192 |
| full-focused-wide | variant-2-suite-1 | 38 | 86 | 176 |
| targeted-demand-focused | control-1-suite-0 | 4 | 0 | 60 |
| targeted-demand-focused | control-1-suite-1 | 4 | 0 | 20 |
| targeted-demand-focused | control-2-suite-0 | 4 | 0 | 60 |
| targeted-demand-focused | control-2-suite-1 | 4 | 0 | 20 |
| targeted-demand-focused | variant-1-suite-0 | 4 | 20 | 56 |
| targeted-demand-focused | variant-1-suite-1 | 4 | 12 | 16 |
| targeted-demand-focused | variant-2-suite-0 | 4 | 20 | 56 |
| targeted-demand-focused | variant-2-suite-1 | 4 | 12 | 16 |
| targeted-focused-wide | control-1-suite-0 | 4 | 20 | 56 |
| targeted-focused-wide | control-1-suite-1 | 4 | 12 | 16 |
| targeted-focused-wide | control-2-suite-0 | 4 | 20 | 56 |
| targeted-focused-wide | control-2-suite-1 | 4 | 12 | 16 |
| targeted-focused-wide | variant-1-suite-0 | 4 | 18 | 56 |
| targeted-focused-wide | variant-1-suite-1 | 4 | 12 | 16 |
| targeted-focused-wide | variant-2-suite-0 | 4 | 18 | 56 |
| targeted-focused-wide | variant-2-suite-1 | 4 | 12 | 16 |

## Detailed records

See `consumer-checks.json` for per-packet native counts, packet omission counts, paired index paths, matched example records, and check results.
