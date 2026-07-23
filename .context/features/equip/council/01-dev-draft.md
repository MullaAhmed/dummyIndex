# Project equipment toolkit — plan

`confidence: INFERRED`

## Where it lives

- `dummyindex/context/default_plugins.py` owns the reviewed default records,
  declarative wired adapter, trust disclosure, conflict-safe declaration, and
  best-effort materialization (`dummyindex/context/default_plugins.py:62-108`,
  `dummyindex/context/default_plugins.py:118-244`,
  `dummyindex/context/default_plugins.py:448-729`).
- `dummyindex/context/claude_plugins.py` owns the atomic marketplace and
  `enabledPlugins` settings primitives
  (`dummyindex/context/claude_plugins.py:105-170`).
- `dummyindex/cli/equip/install.py` owns interactive install I/O, approval and
  usage gates, native settings writes, vendored file writes, manifest recording,
  and config wired write-back (`dummyindex/cli/equip/install.py:62-215`,
  `dummyindex/cli/equip/install.py:258-489`).
- `dummyindex/context/domains/equip/plugins/` owns catalog parsing, blast-radius
  analysis, install planning, and runner-backed source access
  (`dummyindex/context/domains/equip/plugins/marketplace.py:85-175`,
  `dummyindex/context/domains/equip/plugins/blast_radius.py:23-37`,
  `dummyindex/context/domains/equip/plugins/install_plan.py:21-53`,
  `dummyindex/context/domains/equip/plugins/sources.py:24-283`).
- `dummyindex/context/domains/equip/models.py` owns the frozen generated-tool and
  manifest records (`dummyindex/context/domains/equip/models.py:44-245`).

## Architecture in three sentences

Equip separates policy records and frozen decisions from the CLI boundary that performs filesystem, settings, network, and subprocess work. The default path is a reviewed built-in exception that declares pinned identities first and materializes only selected effective-true targets, while the dynamic path resolves catalog candidates and subjects every untrusted source to explicit approval. Both paths preserve user decisions through idempotent settings writes, false tombstones, never-clobber file ownership, and result records instead of exception-driven best-effort failure.

## Data model

`DefaultPlugin` is the immutable built-in identity: plugin, marketplace, optional
repo/ref, reviewed surfaces, and `runs_code`; module-load validation enforces
unique targets, non-empty surfaces, and full lowercase SHA refs for third-party
records (`dummyindex/context/default_plugins.py:118-202`). `WiredEntry` is the
committed desired-state projection, keyed by `<plugin>@<marketplace>`, while
`PluginWireResult` and `PluginInstallResult` retain independent per-target
outcomes (`dummyindex/context/default_plugins.py:62-108`,
`dummyindex/context/default_plugins.py:247-278`,
`dummyindex/context/default_plugins.py:584-599`).

Dynamic discovery parses external JSON into `PluginEntry` and
`MarketplaceCatalog`; trust and collection flags come from the caller, never the
catalog payload (`dummyindex/context/domains/equip/plugins/marketplace.py:85-110`,
`dummyindex/context/domains/equip/plugins/marketplace.py:144-175`).
`PlannedInstall` adds the computed `BlastRadius`, native/vendor mechanism, and
approval requirement (`dummyindex/context/domains/equip/plugins/install_plan.py:21-49`).
`EquipmentItem` and `EquipmentManifest` are the lifecycle ledger for generated,
adopted, native, and vendored equipment, including origin repo/ref and ownership
hashes (`dummyindex/context/domains/equip/models.py:81-159`,
`dummyindex/context/domains/equip/models.py:223-245`).

## Key decisions

- Keep reviewed defaults separate from arbitrary discovery. The built-in tuple
  is code-reviewed and full-SHA-pinned; dynamic untrusted candidates still
  require `--yes` even when their own catalog claims no code surface
  (`dummyindex/context/default_plugins.py:149-202`,
  `dummyindex/context/domains/equip/plugins/install_plan.py:36-48`).
- Split declaration from materialization. Project settings remain resolvable
  when the Claude CLI is absent, and callers run one target-filtered install
  pass instead of coupling runner execution to settings mutation
  (`dummyindex/context/default_plugins.py:448-546`,
  `dummyindex/context/default_plugins.py:645-729`).
- Treat marketplace identity as part of the built-in safety boundary. The
  default wrapper accepts an identical declaration, refuses a same-name source
  conflict, and only then calls the generic upsert primitive
  (`dummyindex/context/default_plugins.py:357-389`,
  `dummyindex/context/claude_plugins.py:105-124`).
- Preserve explicit local intent. A false project/local target is a tombstone;
  malformed settings produce reported errors; independent default failures do
  not stop later targets (`dummyindex/context/default_plugins.py:337-349`,
  `dummyindex/context/default_plugins.py:487-530`,
  `dummyindex/context/default_plugins.py:680-729`).
- Pin vendored bytes and refuse unsafe paths or user-owned replacements. Native
  dynamic plugins remain on Claude's marketplace mechanism and currently record
  no origin ref (`dummyindex/cli/equip/install.py:258-287`,
  `dummyindex/cli/equip/install.py:335-446`).
- Keep subprocesses behind injected runner seams with fixed argv and no shell
  (`dummyindex/context/default_plugins.py:557-581`,
  `dummyindex/context/domains/equip/plugins/sources.py:24-49`).

## Open questions

- Dynamic native installs still approve catalog metadata and later enable a
  moving marketplace HEAD; should that path resolve and persist a commit ref as
  the vendor path does (`dummyindex/cli/equip/install.py:158-178`,
  `dummyindex/cli/equip/install.py:258-287`)?
- The generic `add_marketplace` primitive overwrites a same-name different-source
  declaration, while the reviewed-default wrapper refuses it. Should interactive
  dynamic install adopt the same identity-conflict contract
  (`dummyindex/context/claude_plugins.py:105-124`,
  `dummyindex/context/default_plugins.py:357-389`)?
- Native dynamic installs write back `config.wired` and `equipment.json`, but
  the default materializer relies on config/settings plus Claude's machine-local
  registry. Is the intentional absence of default entries from
  `.context/equipment.json` the long-term lifecycle contract
  (`dummyindex/cli/equip/install.py:183-209`,
  `dummyindex/context/default_plugins.py:645-729`)?
