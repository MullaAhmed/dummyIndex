# Architect notes — Project equipment toolkit

## What I changed

- Replaced the broad “policy versus CLI I/O” summary with an explicit bounded
  context. Equip owns dynamic toolkit lifecycle and interactive plugin install;
  the reviewed-default module is shared base-layer policy, while init/install
  orchestration remains outside equip.
- Distinguished the three overlapping state stores: `config.wired` declares
  intent, Claude settings hold effective decisions, and `equipment.json` tracks
  managed lifecycle metadata.
- Corrected the draft's overly absolute I/O boundary. Most install policy is
  pure, but `plugins/sources.py` is an intentional runner-backed domain I/O
  adapter and `default_plugins.py` is a base-layer settings/subprocess adapter.
- Removed descriptive repetition and reorganized the plan around bounded
  context, named patterns, dependency direction, and promoted decisions.

## Patterns named

- Policy core with command adapters: pure install-plan construction followed by
  CLI interpretation and writes.
- Desired state plus lifecycle ledger: wired intent, effective settings, and
  managed equipment remain separate representations.
- Declare then materialize: settings reconciliation precedes one selected
  default-plugin installation pass.
- Strategy selection and ports: native/vendor mechanism choice and injectable
  runner seams.
- Conflict guards and result records: stricter reviewed-default identity policy
  wraps generic settings primitives; per-target results preserve best effort.

## Dependencies surfaced

- `default_plugins.py` is deliberately below `context/domains/config.py`; config
  consumes `WiredEntry` and `default_wired()`, so moving reviewed-default policy
  under equip would invert the dependency and risk a cycle.
- Claude settings primitives are shared lower-level mechanisms consumed by both
  reviewed defaults and the dynamic interactive installer.
- `plugins/sources.py` is the only equip domain source adapter that shells out;
  its runner port prevents a dependency on CLI code.
- `cli/equip/install.py` is the composition boundary and may depend inward on
  config, default records, equip policy/models, settings, and atomic I/O.
- `default_plugins.py` overlaps equip and install-surface documentation by
  design: equip documents its reusable records and policy; install-surface owns
  when init invokes it.

## Decisions promoted

- The reviewed default set stays a fixed, validated exception to arbitrary
  discovery and does not inherit dynamic catalog trust.
- The reviewed-default module stays in the base layer to preserve acyclic
  dependency direction.
- Declaration and materialization remain separate, target-filtered operations.
- Explicit false settings remain tombstones; malformed settings fail closed;
  independent default failures remain reportable results rather than aborting
  the whole pass.
- Trust and marketplace identity checks remain policy-layer responsibilities,
  not behavior added to the generic settings upsert.
- Vendored installs keep immutable-ref and never-clobber guarantees; native
  moving-ref provenance remains an explicit unresolved question.
