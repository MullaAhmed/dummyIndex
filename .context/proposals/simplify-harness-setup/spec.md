# Spec — Shared host workflow, removal of equipment-eval, and exact candidate verification

## Intent

Prepare and use the same project capabilities on Claude and Codex, remove the
equipment-eval subsystem, and qualify the exact evolve candidate before adoption.
This is the first implementation tranche; the full researched backlog remains.

## Contracts

- Reuse the existing skill family, equipment registry and hash ownership lifecycle.
- Canonical capability bodies live in `.context/equipment/`; native discovery files
  are optional references. Preserve edited/evolved legacy records and user settings.
- `equip apply` prepares canonical capabilities; `--platform claude` also prepares
  supported native adapters. Both hosts prepare, delegate, verify and learn through
  one workflow. Pass selected policy mandates, including Ponytail, to delegates.
- Stop generating/scoring equipment-eval suites. Existing user files remain intact.
- Evolve evaluates baseline and exact staged files in isolated current-input copies.
  No relevant checks means blocked/unmeasured. Ordinary project tests remain the gate;
  passing them does not claim measured model improvement.
- Bind receipts to candidate, baseline, verification inputs and execution profile.
  Promotion rejects stale identities, preserves relative paths and recovers partial writes.
- No live-production testing steps, optimizer service, unrestricted source mutation,
  global install changes or automatic learning/PPC rollout in this tranche.

## Acceptance

- [x] Both host workflows resolve canonical capability content and selected policies;
  missing Claude equipment never blocks native delegation.
- [x] Equip creates no equipment-eval files or evaluation nags and preserves custom,
  edited/evolved and unrelated host configuration.
- [x] A broken staged candidate fails while owner files remain unchanged; distinct
  same-basename targets retain distinct content; no applicable checks cannot pass.
- [x] Changed candidate/baseline/verification invalidates promotion; a second-target
  write failure restores earlier writes and records recoverable state.
- [x] Relevant tests and lint pass; public guidance describes the implemented behavior.

<!-- dummyindex:consistency:begin -->
## Consistency

**Related features:**

- `install-surface`
- `equip`
- `gc`
- `bootstrap`
- `cli-dispatch`

**Conventions to honor:**

- `conventions/coding-practices.md`
- `conventions/data-access.md`
- `conventions/folder-organization.md`
- `conventions/naming.md`
- `conventions/testing.md`

<!-- dummyindex:consistency:end -->
