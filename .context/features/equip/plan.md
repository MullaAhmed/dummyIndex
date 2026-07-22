# Project equipment toolkit — plan

`confidence: INFERRED`

## Bounded context

Equip owns the project toolkit lifecycle: it discovers plugin candidates,
derives install policy, mutates the selected Claude settings scope or vendored
skill tree, and records managed equipment. Its dynamic install path accepts
arbitrary catalogs and repositories, so every untrusted candidate crosses an
explicit approval gate before native enablement or vendoring
(`dummyindex/context/domains/equip/plugins/install_plan.py:21-53`,
`dummyindex/cli/equip/install.py:62-215`).

Reviewed default plugins are an adjacent base-layer policy, not another catalog.
`default_plugins.py` owns the fixed, validated identities and the headless
declare/materialize operations; it reuses Claude settings primitives but imports
nothing from `cli/` or `context/domains/`. This placement lets
`context/domains/config.py` depend on `default_wired()` without creating a
config-to-equip-to-config cycle (`dummyindex/context/default_plugins.py:1-30`,
`dummyindex/context/default_plugins.py:149-244`,
`dummyindex/context/domains/config.py:64-82`). Equip's interactive installer may
consume both the base-layer wired records and domain equipment models; the base
layer must not depend back on it (`dummyindex/cli/equip/install.py:13-46`).

The overlapping state stores have distinct authority:

- `.context/config.json` `wired` entries are declared project intent, with an
  optional descriptive version (`dummyindex/context/default_plugins.py:62-108`).
- `.claude/settings*.json` contains the effective marketplace declarations and
  plugin enable/disable decisions (`dummyindex/context/claude_plugins.py:105-170`).
- `.context/equipment.json` is the lifecycle ledger for equipment managed by the
  dynamic path, including origin and ownership hashes
  (`dummyindex/context/domains/equip/models.py:81-159`,
  `dummyindex/context/domains/equip/models.py:223-245`).

Default-plugin orchestration during init/install belongs to the install surface;
equip owns the reusable records and interactive plugin-management path. Shared
use of `default_plugins.py` does not make init dispatch part of this bounded
context.

## Components and responsibilities

- `dummyindex/context/default_plugins.py`: reviewed default records, the
  `WiredEntry` adapter, trust disclosure, conflict-safe declaration,
  target-filtered materialization, and per-target results
  (`dummyindex/context/default_plugins.py:62-108`,
  `dummyindex/context/default_plugins.py:118-278`,
  `dummyindex/context/default_plugins.py:357-530`,
  `dummyindex/context/default_plugins.py:584-752`).
- `dummyindex/context/claude_plugins.py`: atomic marketplace and
  `enabledPlugins` settings primitives; these are mechanism, not trust policy
  (`dummyindex/context/claude_plugins.py:105-170`).
- `dummyindex/context/domains/equip/plugins/`: catalog parsing, blast-radius
  analysis, pure install planning, and the isolated runner-backed source adapter
  (`dummyindex/context/domains/equip/plugins/marketplace.py:85-175`,
  `dummyindex/context/domains/equip/plugins/blast_radius.py:23-37`,
  `dummyindex/context/domains/equip/plugins/install_plan.py:21-53`,
  `dummyindex/context/domains/equip/plugins/sources.py:1-96`).
- `dummyindex/context/domains/equip/models.py`: frozen generated-tool and
  manifest records (`dummyindex/context/domains/equip/models.py:44-245`).
- `dummyindex/cli/equip/install.py`: command adapter for argument validation,
  candidate selection, approval and usage gates, native settings writes,
  vendored file writes, manifest recording, and wired write-back
  (`dummyindex/cli/equip/install.py:62-215`,
  `dummyindex/cli/equip/install.py:258-489`).

## Architectural patterns

### Policy core with command adapters

`build_install_plan()` is a pure policy function that assigns mechanism,
blast radius, and approval; `run_install()` interprets that plan and performs
the writes. Catalog-provided surface metadata remains disclosure input and
cannot waive the untrusted-source gate
(`dummyindex/context/domains/equip/plugins/install_plan.py:1-53`,
`dummyindex/cli/equip/install.py:62-215`).

### Desired state plus lifecycle ledger

`WiredEntry` represents desired presence, Claude settings represent effective
plugin decisions, and `EquipmentManifest` records what dummyindex owns and can
later evolve. These records must not be collapsed: a false settings decision is
a durable tombstone, while origin refs and hashes answer lifecycle questions
that `wired` cannot (`dummyindex/context/default_plugins.py:62-108`,
`dummyindex/context/default_plugins.py:337-349`,
`dummyindex/context/domains/equip/models.py:81-159`,
`dummyindex/context/domains/equip/models.py:223-245`).

### Declare, then materialize

Reviewed defaults first reconcile marketplace and enablement settings, then run
one selected, target-filtered install pass. This preserves useful project state
when the Claude executable is absent and prevents settings mutation from being
repeated inside each installer invocation
(`dummyindex/context/default_plugins.py:448-530`,
`dummyindex/context/default_plugins.py:645-729`).

### Strategy selection and ports

`InstallMechanism` selects native enablement or vendored copying, and the CLI
dispatches to the corresponding implementation. External commands are isolated
behind injected `Runner` callables with fixed argv and no shell, in both source
discovery and reviewed-default materialization
(`dummyindex/context/domains/equip/plugins/install_plan.py:21-49`,
`dummyindex/cli/equip/install.py:158-215`,
`dummyindex/context/domains/equip/plugins/sources.py:24-65`,
`dummyindex/context/default_plugins.py:550-581`).

### Conflict guards and result records

The reviewed-default wrapper accepts an identical marketplace declaration but
refuses a same-name/different-source collision before invoking the generic
upsert. Wiring and installation return one result per target, so an independent
failure is reported without blocking later defaults
(`dummyindex/context/default_plugins.py:247-278`,
`dummyindex/context/default_plugins.py:357-389`,
`dummyindex/context/default_plugins.py:584-599`,
`dummyindex/context/default_plugins.py:680-729`).

## Dependency direction

1. Frozen domain records and pure plugin policy depend only on equip enums,
   errors, and models (`dummyindex/context/domains/equip/plugins/install_plan.py:9-13`,
   `dummyindex/context/domains/equip/plugins/marketplace.py:85-175`).
2. Source discovery is the domain's explicit I/O exception and exposes a runner
   port rather than importing CLI code
   (`dummyindex/context/domains/equip/plugins/sources.py:1-49`).
3. Claude settings primitives are a lower-level mechanism consumed by both the
   reviewed-default base layer and the interactive command adapter
   (`dummyindex/context/default_plugins.py:20-25`,
   `dummyindex/cli/equip/install.py:13-18`).
4. `context/default_plugins.py` remains below `context/domains/config.py`; the
   config domain may import `WiredEntry` and `default_wired`, never the reverse
   (`dummyindex/context/default_plugins.py:8-14`,
   `dummyindex/context/domains/config.py:64-82`).
5. `cli/equip/install.py` is the composition boundary. It may depend on config,
   default-plugin records, equip policy, settings primitives, and atomic I/O;
   none of those modules may depend on the command adapter
   (`dummyindex/cli/equip/install.py:13-46`).

## Decisions

- Keep reviewed defaults separate from arbitrary discovery. The built-in tuple
  is code-reviewed and full-SHA-pinned; dynamic untrusted candidates require
  `--yes` even if their catalog declares no code surface
  (`dummyindex/context/default_plugins.py:149-202`,
  `dummyindex/context/domains/equip/plugins/install_plan.py:36-48`).
- Keep the reviewed-default implementation in the base layer. Moving it under
  equip would reverse the established config dependency and risk a cycle
  (`dummyindex/context/default_plugins.py:8-14`,
  `dummyindex/context/domains/config.py:64-82`).
- Preserve declaration/materialization as two operations and expose target
  filtering, so higher-level init dispatch can aggregate selected targets into
  one materialization pass (`dummyindex/context/default_plugins.py:448-530`,
  `dummyindex/context/default_plugins.py:645-729`).
- Preserve explicit local decisions. False plugin values are tombstones,
  malformed settings fail closed with reported errors, and later targets still
  run after an independent failure (`dummyindex/context/default_plugins.py:337-349`,
  `dummyindex/context/default_plugins.py:487-530`,
  `dummyindex/context/default_plugins.py:680-729`).
- Pin vendored bytes to a resolved ref and never replace unsafe or user-owned
  paths. Native dynamic installs remain delegated to Claude's marketplace
  mechanism and currently record no origin ref
  (`dummyindex/cli/equip/install.py:258-287`,
  `dummyindex/cli/equip/install.py:335-446`).
- Keep trust policy outside generic settings primitives. `add_marketplace()` is
  a mechanism-level upsert; reviewed defaults add their stricter identity guard
  at the policy boundary (`dummyindex/context/claude_plugins.py:105-124`,
  `dummyindex/context/default_plugins.py:357-389`).

## Open questions

- Dynamic native installs approve catalog metadata and then enable a moving
  marketplace HEAD. Should that path resolve and persist a commit ref as the
  vendor path does (`dummyindex/cli/equip/install.py:158-178`,
  `dummyindex/cli/equip/install.py:258-287`)?
- The generic `add_marketplace()` primitive overwrites a same-name,
  different-source declaration, whereas the reviewed-default wrapper refuses
  it. Should interactive dynamic install adopt the same identity-conflict
  contract (`dummyindex/context/claude_plugins.py:105-124`,
  `dummyindex/context/default_plugins.py:357-389`)?
- Dynamic native installs write `config.wired` and `equipment.json`, while the
  default materializer relies on config, settings, and Claude's machine-local
  registry. Is the absence of default entries from `.context/equipment.json`
  the intended long-term lifecycle contract
  (`dummyindex/cli/equip/install.py:183-209`,
  `dummyindex/context/default_plugins.py:645-729`)?
