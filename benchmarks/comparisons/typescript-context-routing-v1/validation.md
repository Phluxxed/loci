# Routing definition verification — 12 September 2026

Preparation is complete. No trial has been frozen or measured, and no shared
Loci instruction or runtime has been changed.

- Three focused tests pass: all 17 original prompt suffixes are preserved;
  both conditions require the same real B tool schema; prompt tampering and
  substitution of the old 13-tool A schema are rejected.
- Type checking passes for the prompt module, transport verifier and tests.
- Two actual offline Codex/MCP round trips pass. A and B both expose fourteen
  retrieval tools and three helpers with canonical schema hash
  `f70174b36e4bb4ec3051e0df1ab2cb1449ad93c4f2dd5511823e1c7348999858`.
- Each request carries its exact declared prompt. Each scripted type exploration
  returns the requested `processOrder` anchor and five source spans. The spans
  match the frozen snapshot bytes and file hashes; complete native payloads
  arrive unchanged in the next request, with one fully accounted call per mode.
- Production source verifies against `36f5e2b1662c2d6bbe2449c3189430469e8c013f`
  and extractor 25. Existing source, corpus, controls, freezes and results remain
  unchanged.

The candidate policy prefix is 1,155 UTF-8 bytes, including its separator.
The policy's terminal blank line is part of the recorded prompt bytes.
Its policy file SHA-256 is
`cb940c97c00d1f5a2e3a5b2e266cf6ecfef47aea0e0283ad98f9644d157ffaed`.
[Prompt identities](prompt-manifest.json), [transport summary](transport-verification.json)
and the adjacent raw evidence directory retain the check inputs and outputs.

The loopback server scripts the call and intentionally returns HTTP 400 after
capturing the next request; both host processes exit 1 at that declared stop.
No provider model selected a tool. These checks establish transport, not
adoption or improved task outcomes.

Reproduction uses a new, nonexistent output path:

```sh
.venv/bin/python -m pytest tests/test_typescript_context_routing.py -q
pyright --pythonpath .venv/bin/python benchmarks/typescript_context_routing.py benchmarks/typescript_context_routing_transport.py tests/test_typescript_context_routing.py
.venv/bin/python -m benchmarks.typescript_context_routing_transport --output /tmp/loci-routing-new-proof.json --catalog benchmarks/comparisons/typescript-context-explore-v2/model-catalog.json
```

Next: W2.5.1.3 (`task_2727497172e9ceadea5ab07538da0b31`) binds this policy and
the declared exposure accounting into a separately frozen matched measurement.
W2.5 delivery acceptance remains open, and multilingual W4 is outstanding.
