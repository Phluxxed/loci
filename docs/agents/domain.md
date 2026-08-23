# Domain Docs

How engineering skills should consume this repo's domain documentation.

## Before exploring, read these

- `CONTEXT.md` at the repository root, or
- `CONTEXT-MAP.md` if it exists
- Relevant ADRs under `docs/adr/`

If these files do not exist, proceed silently. Domain documentation is created lazily when terminology or architectural decisions need recording.

## File structure

Loci uses the single-context layout:

```
/
├── CONTEXT.md
├── docs/adr/
└── src/
```

## Use the glossary's vocabulary

When naming domain concepts, use the terminology defined in `CONTEXT.md`. If a required concept is absent, reconsider the terminology or note the gap for domain modelling.

## Flag ADR conflicts

Surface any conflict with an existing ADR explicitly instead of silently overriding it.
