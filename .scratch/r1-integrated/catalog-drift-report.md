# R1 blocked: operational probes pass, common catalog differs

All four normal-Terminal operational probes closed successfully, qualified with
known provider usage and passed their tool checks. No scored assignment ran.
The original failed gate and all raw evidence remain unchanged.

Independent raw replay confirms that every ordered startup instruction and
native tool schema is equal across the four conditions after the declared path
and transport normalization. The only remaining common-context difference is
the aggregate common-tool catalog fingerprint.

| Condition | Common tools | Catalog SHA-256 |
| --- | ---: | --- |
| Native | 608 | e653a4c4fa810cdd4c6692fa5e24b7f1257892ed46dd80146435c2490f5e51a0 |
| Path-only | 608 | e653a4c4fa810cdd4c6692fa5e24b7f1257892ed46dd80146435c2490f5e51a0 |
| Integrated | 608 | e653a4c4fa810cdd4c6692fa5e24b7f1257892ed46dd80146435c2490f5e51a0 |
| Eager | 608 | 24116802358a3b9eb3e1815ac9914f814ed19205a98c0ad9559e546cffde7901 |

Equal counts do not establish equal names or descriptions. These sequential
observations cannot distinguish a temporal change from a condition-dependent
change. There is no evidence identifying a changed tool or showing that the
difference is harmless.

## Capture gap and bounded investigation

The fixed program fingerprints sorted full name/description pairs but exports
only their count and aggregate SHA. Retaining no underlying catalog was an
instrumentation gap: the check can detect this difference but cannot explain it.

The four retained rollouts, observer artifacts and empty stderr contain no
complete historical nested Code Mode registry. Their additional_tools and
world_state expose top-level tools, rather than the full nested catalog. Later
calls expose only selected descriptors. Existing R0 copying/accounting reduces
these same bytes and cannot recover an un-emitted JavaScript variable.
Default local SQLite records scoped to these four thread IDs contain no
dynamic-tool catalog or matching diagnostic log records.

A bounded forensic check also tried reconstructing 608-entry candidates from
two independently available 619-entry operator snapshots, retaining their MCP
entries and enumerating compatible native-helper subsets. Neither produced
either recorded SHA. No present-day snapshot is accepted as historical without
an exact fingerprint match.

Astra independently confirmed the retained-input equality, missing catalog,
validity of stopping and limits of retrospective recovery. No source code,
freeze, prompt, model, condition, permission, global setting or launcher changed
during this investigation. No new pilot session, Codex CLI process or MCP call
was made.

Official OpenAI documentation describes
[scoped diagnostic logging](https://learn.chatgpt.com/docs/config-file/environment-variables)
and [developer diagnostics](https://learn.chatgpt.com/docs/developer-commands).
This investigation did not establish an existing supported passive export of
the exact nested catalog at the fingerprint point. No logging settings or
alternative Code Mode host were enabled.

## Retained cost, not task results

These are unscored setup costs, with different probe operations. They cannot
rank architecture efficiency or task correctness. Input includes cached input;
reasoning is included in output. Provider usage does not establish billing or
invisible retry completeness.

| Condition | Native elapsed seconds | Input tokens | Output tokens |
| --- | ---: | ---: | ---: |
| Native | 41.816 | 49,112 | 1,801 |
| Path-only | 90.786 | 276,516 | 7,207 |
| Integrated | 95.501 | 358,921 | 7,169 |
| Eager | 96.416 | 343,216 | 6,663 |

[Machine evidence, usage components and raw-replay rejection](catalog-drift-checks.json).
Detailed private source and traces remain in the ignored local pilot directory.

## Disposition

Keep scoring blocked and do not run the unchanged command again. The required
next evidence is a session-attributed full sorted common catalog whose bytes
reproduce the recorded first-call count and SHA, retained outside model context.
A verified passive capture path would preserve frozen prompts; none has been
established in the existing host path. An explicit diagnostic protocol change
would need to be distinguished from the unchanged scored experiment.

The gate was not waived. Four tool checks passed; zero of sixteen scored tasks
were attempted. Correctness, elapsed-to-task-outcome, scored usage and optional
semantic benefit remain unmeasured. Hold the architecture advancement decision;
this blocked pilot does not justify accepting or rejecting R1.
