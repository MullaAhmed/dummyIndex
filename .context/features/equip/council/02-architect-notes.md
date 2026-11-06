# Architect notes — Shared project capabilities

`confidence: INFERRED`

## What I changed

- Reorganized the existing source inventory around canonical bodies, native
  discovery adapters and hash-owned lifecycle. Retained preservation, package
  identity and exact-once learning contracts.
- Named the real decision/render/write pipeline and surfaced upstream proposal
  requirements and downstream build role paths. Made partial recovery distinct
  from a global transaction (`dummyindex/cli/equip/dispatch.py:467-687`).

Native pointer ownership compares decoded text (including universal-newline
normalization), not literal raw bytes; the preserved spec's “exact bytes” phrase
is stronger than this code path
(`dummyindex/context/domains/equip/generate/adapters.py:73-89`).

## Patterns and decisions

Pure catalog at `dummyindex/context/domains/equip/generate/catalog.py:74-110`;
canonical-body/native-pointer adapter at
`dummyindex/context/domains/equip/generate/adapters.py:18-89`; hash ownership at
`dummyindex/context/domains/equip/lifecycle/status.py:138-167`.
Decided to keep template/package identity separate from project binding and loaded
body bytes because each answers a different ownership/attribution question.

## Dependencies and evidence

Upstream: context/conventions, stack/commands, prior manifest and optional
proposal capabilities. Downstream: host/build execution; explicit patches feed
back through the body/manifest pair. Installer linking and plugin trust remain
separate. Named public/domain symbols were checked in map/source. The map omits
`_run_apply`, which source defines at dispatch.py:257; the source-verified range
is cited without treating map omission as proof of absence. Single-shot reasoning
used because Sequential Thinking MCP is unavailable. Specs/source/logs and test
results were not changed; byte identity does not establish model compliance.
