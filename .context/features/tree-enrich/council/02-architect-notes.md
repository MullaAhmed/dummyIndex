# Architect notes — Tree abstract enrichment

`confidence: INFERRED`

## What I changed

- Replaced the historical polluted-map narrative and broad clustered-test claims
  with the two-file enrichment boundary. Removed “pure/I/O-clean” wording: both
  domain and CLI read/write files.
- Corrected the draft's EXTRACTED-only planning claim: `source-stale` nodes are
  also selected (`dummyindex/context/domains/enrich.py:120-123`). File heads stay
  in file batches; `structure` contains only project/directory nodes.
- Documented actual apply semantics: any current tree ID is accepted, known
  updates commit before unknown IDs cause CLI exit 1, and touched confidence is
  assigned INFERRED (`dummyindex/context/domains/enrich.py:207-227`,
  `dummyindex/context/domains/enrich.py:268-285`). The preserved spec's stronger
  stub-only/never-demotes language is not a general validation guarantee.

## Patterns and dependencies

Plan / out-of-process author / apply with per-file batching and temp replacement.
Upstream: backbone tree/stale labels; downstream: authored mapping and future
navigation, with feedback through tree.json. No Python LLM client or cross-file
transaction is implied. Mode policy belongs to the host; the current skill's
all-modes assertion still conflicts with its light-mode table
(`dummyindex/skills/skill.md:334-340`). That contradiction remains explicit.

## Evidence

Mapped enrichment identifiers were checked against current source; current maps
contain first-party Python, so the old foreign-only warning is obsolete. No low
confidence historical doc was used as present authority. Single-shot reasoning
used because Sequential Thinking MCP is unavailable. Spec/source/logs remained
untouched; these plan corrections add no behavior or new test/model result.
