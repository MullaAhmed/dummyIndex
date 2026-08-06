# Project equipment toolkit — plan

`confidence: INFERRED`

## Where it lives

**Bounded context.** Equip owns the *lifecycle of Claude Code equipment in one
repo*: deciding what toolkit this repo should have, rendering it, fingerprinting
it, and reconciling it on every later pass. It does **not** own when init runs
(`cli/init.py`, `installer/install/project_init.py`), what a convention doc says
(`preflight`, `source_docs`), or what Claude Code does with the settings it
writes. The seam is a decision boundary, not a package boundary: three of equip's
stores are written by modules outside `domains/equip/`.

**Policy core — `dummyindex/context/domains/equip/`.** Pure decisions. No argv,
no printing, one deliberate I/O exception.

| Package | Role | Anchor |
|---|---|---|
| `generate/` | catalog decision, capability→template table, coverage resolution, rendering | `generate/catalog.py:75-111`, `generate/adopt.py:82`, `generate/specialists.py:66-80` |
| `lifecycle/` | hash baseline + the five verbs it enables | `lifecycle/hashing.py:17-19`, `lifecycle/status.py:1-24` (`classify_item:143`, `status:190`, `refresh:221`, `reset:314`, `uninstall:343`) |
| `plugins/` | catalog parsing, blast radius, mechanism+approval policy, the one shell-out | `plugins/blast_radius.py:33-37`, `plugins/install_plan.py:36-53`, `plugins/sources.py:31-49` |
| `wiring/` | equip's own sentinel-keyed hook entry; never-clobber predicates | `wiring/hooks.py:31-55` |
| `models.py` / `enums.py` / `constants.py` / `errors.py` | frozen records, closed alphabets, `SCHEMA_VERSION = 4`, `EQUIP_SENTINEL` | `models.py:82-159`, `enums.py:79-95`, `constants.py:11-21` |
| `eval/` | pure scoring stage | `eval/cases.py`, `eval/score.py` |

**Base layer — `dummyindex/context/`.** Below the domains; importable by config
and by equip without a cycle.

- `default_plugins.py` — reviewed built-ins, the `WiredEntry` record, trust
  disclosure, declaration, target-filtered materialization
  (`default_plugins.py:64-79`, `:227`, `:472-554`, `:676-700`).
- `claude_plugins.py` / `claude_settings.py` — the shared settings primitives.
  `install_hook_entry` / `remove_hook_entries` live here, not in equip, because
  **two** sentinel families need the same merge mechanism
  (`claude_settings.py:64`, `:116`).
- `hooks.py` — the five managed session-hook events plus the statusLine
  (`hooks.py:270-276`, `hooks.py:486-571`).
- `output/bootstrap.py:78-91` — `ALWAYS_ON_TURN_REMINDER`, the exact string the
  `UserPromptSubmit` hook injects.
- `domains/atomic_io.py` — `_replace_bytes:13`, `write_text_atomic:37`,
  `normalize_eof_newline:50`.

**CLI boundary — `dummyindex/cli/equip/` and `dummyindex/cli/hooks.py`.**
Wire-only, and the *only* place equip writes. `dispatch.py:102-144` is the verb
table; `dispatch.py:393` (`_apply_write`) owns the apply pipeline and its
ordering; `verbs.py` the lifecycle verbs; `install.py` the interactive installer
and the `config.wired` write-back (`install.py:449-490`).

## Architecture in three sentences

A pure policy core decides — `build_catalog` turns a stack profile plus
convention docs plus a preflight report into a `CatalogDecision`
(`generate/catalog.py:75-111`), and `build_install_plan` turns candidates into
mechanism-plus-approval decisions (`plugins/install_plan.py:36-53`) — while thin
CLI adapters interpret those decisions and perform every write. Every generated
artifact is fingerprinted at write time into an `origin_hash` recorded in
`.context/equipment.json`, and every later operation re-hashes the file on disk
and compares before touching it, so "did the user take ownership of this?" is
answered by data rather than convention (`lifecycle/status.py:1-24`). External
effects are pinched into narrow ports: subprocesses run through injected `Runner`
callables with fixed argv and no shell (`plugins/sources.py:31-49`), and settings
mutation runs through sentinel-keyed primitives that preserve-or-refuse on an
unparseable file (`claude_settings.py:64`).

### Patterns in use

| Pattern | Where | Why this and not the obvious alternative |
|---|---|---|
| **Functional core / imperative shell** | pure `generate/catalog.py:75-111` → writing `cli/equip/dispatch.py:393` | the decision is testable without a filesystem; the cost is that ordering and partial-failure policy leak into the CLI (see Data model) |
| **Hash-baseline lifecycle** (3-state reconciliation, extended to 5) | `lifecycle/hashing.py:17-19` + `enums.py:79-95` | ownership is derived from bytes, not from a marker a user can accidentally keep while rewriting the body |
| **Verb table dispatcher** | `cli/equip/dispatch.py:102-144` | a flat `if verb is …` chain over a closed `EquipVerb` enum; chosen over argparse subparsers so the verbless carve-out (`--dry-run` only) is one readable branch |
| **Port / adapter** | `Runner = Callable[[list[str]], RunResult]`, `plugins/sources.py:31`, injected at `default_plugins.py:676-700` | keeps the single shelling-out module inside the domain without an inward dependency on `cli/`; the seam is also the test seam |
| **Sentinel-keyed idempotent upsert** | `wiring/hooks.py:31-55` over `claude_settings.install_hook_entry:64` | a re-run refreshes in place; co-located *user* hooks inside the managed entry survive |
| **Ledger merge, last-writer-per-name** | `cli/equip/dispatch.py:512-533` | this run's records win collisions; every unre-derived prior record is carried forward verbatim |
| **Tolerant reader / strict writer** | `models.py:114-159` | `from_dict` defaults every v2/v3 field to `None`; `to_dict` omits empty `invariants` so a v3 manifest stays byte-identical |
| **Out-of-band canary metadata** | `generate/specialists.py:66-80` | invariants live in the manifest, never in rendered bytes, so recording them cannot shift the hash they are meant to police |
| **Declare-then-materialize** | `default_plugins.py:472-554` then `:676-700` | useful project state survives a missing `claude` executable |
| **Narrow legacy-shape healing** | `default_plugins.py:353-370` | exact-shape match only; anything else keeps preserve-or-refuse |
| **Preserve-or-refuse** (fail-closed write) | `hooks.py:366-375`, `:574-584`, `:644-660`, `default_plugins.py:521-547` | applied at *every* settings touchpoint, not just the risky-looking ones |
| **Ability, not opt-in** | specialists `generate/catalog.py:62-72`; statusLine `hooks.py:553-562`; turn reminder `hooks.py:110-145` | the same policy shape recurs three times — capability is granted by default, and the "off" path is a user edit the hash baseline then respects |

## Dependencies

**Direction is enforced and acyclic.** Equip's domain reaches *out* to exactly
four things: `domains/preflight/models.PreflightReport`
(`generate/catalog.py:26`), `domains/dev_pick.SubagentType`
(`generate/adopt.py:31`), `domains/atomic_io.write_text_atomic`
(`lifecycle/evolve.py:16`), and the base-layer settings primitives
(`claude_settings`, `claude_plugins`). Nothing in `dummyindex/context/*.py`
imports `domains.equip` — `claude_settings.py:3-4` and `default_plugins.py:72`
reference it in **docstrings only**, which is what keeps
`domains/config.py:68 → default_plugins` safe.

- **Upstream (equip consumes):** `preflight` (the report that drives coverage),
  `dev_pick` (subagent alphabet), `source_docs`/conventions (grounding paths),
  `atomic_io` (byte-faithful writes), `config` (the `wired` declaration read back
  by `install.py`).
- **Downstream (consume equip):** `cli/equip/*`, `cli/status.py`, `cli/help.py`,
  `cli/build_loop/waves.py`, `domains/audit/catalog.py`,
  `domains/buildloop/mapping.py`, `installer/install/project_init.py`.
- **The one near-cycle, resolved by placement:** `config` needs `WiredEntry` and
  `default_wired()`; equip's installer needs `config`. Keeping
  `default_plugins.py` in the base layer (it imports nothing from `cli/`,
  `installer/`, or `context/domains/` — `default_plugins.py:12-17`) breaks what
  would otherwise be `config → equip → config`.
- **Shared-mechanism coupling, not a cycle:** `claude_settings` is consumed by
  both hook owners. `hooks.py` writes under `DUMMYINDEX_AUTO_REFRESH`,
  `wiring/hooks.py` under `DUMMYINDEX_EQUIP:<event>`; they coexist and uninstall
  independently (`hooks.py:56-73`, `constants.py:16-21`).

## Data model

No database. Persistence is four JSON stores with distinct authority, all written
through tmp-file + `replace`:

| Store | Authority | Written by |
|---|---|---|
| `.context/equipment.json` | the lifecycle ledger: what dummyindex owns, its hash baseline, version, origin, mechanism | `write_manifest` (`lifecycle/manifest.py:54`) via `cli/equip/dispatch.py:535-540` |
| `.context/config.json` `wired` | declared project intent, `<plugin>@<marketplace>` + descriptive version | `_write_back_wired`, `cli/equip/install.py:449-490` |
| `.claude/settings.json` (+ `settings.local.json`) | effective marketplace declarations, `enabledPlugins`, hook entries, `statusLine` | `claude_plugins` / `claude_settings` primitives |
| `.context/equipment-evals/*.result.json` | recorded eval runs, read back by `equip status` | `cli/equip/eval.py` |

**Split-brain is structural, not accidental.** A fifth store exists that
dummyindex does not write — Claude Code's per-machine plugin registry — and no
component reconciles the five. `equip status` reads the manifest plus the evals
dir and nothing else (`cli/equip/verbs.py:74-118`), so reviewed defaults, which
live only in `config.wired` + settings + Claude's registry, are invisible to it.

Schema evolution is additive and tolerant: `SCHEMA_VERSION = 4` (the bump that
introduced `EquipmentKind.PLUGIN`), `EquipmentItem.from_dict` defaults every v2/v3
field to `None`, and `invariants` is omitted from `to_dict` when empty so a v3
manifest stays byte-identical (`models.py:114-159`, `constants.py:11-14`).

There is no transaction spanning stores, so `_apply_write` orders the steps to
degrade rather than corrupt: files first, then hooks (a `MalformedSettingsError`
is a warning, files stay written), then the merged manifest, then silent eval
seeding (`cli/equip/dispatch.py:499-545`). **Decided: ordering policy lives in the
CLI, not the domain** — the domain is pure and therefore cannot express "already
wrote three files, now degrade." The atomicity that does exist is per-file:
`_replace_bytes` writes a **uniquely named** temporary sibling and `replace`s it,
precisely because hooks from two Claude profiles can write the same repo-local
cache concurrently (`domains/atomic_io.py:13-34`).

## Key decisions

**Hash baseline over sentinel.** The in-body `GENERATED_SENTINEL` is a human
marker; the sha256 recorded at write time is the authority (`models.py:27-29`,
`lifecycle/status.py:1-24`). This is why `write_text_atomic` is contractually
byte-faithful — a silent EOL normalization there would make every generated
artifact look user-edited, so callers wanting pre-commit-clean output call
`normalize_eof_newline` *after* (`domains/atomic_io.py:37-47`).
Trade-off accepted: a semantically-null whitespace edit permanently forfeits
refresh for that file. `reset` is the deliberate escape hatch
(`lifecycle/status.py:314`).

**Canary invariants as manifest metadata, not rendered bytes.** A template's
load-bearing convention substrings are recorded in `EquipmentItem.invariants` and
never written into the file, so they cannot shift the origin hash; a user edit
that deletes one is surfaced as `INVARIANT_BROKEN` rather than a silent
`CUSTOMIZED`, and refresh prints it as its own `⚠` alarm section
(`generate/specialists.py:66-80`, `enums.py:79-95`, `cli/equip/verbs.py:39-68`).
Note the state lattice this creates: `CUSTOMIZED` and `INVARIANT_BROKEN` are
*refinements* of `USER_MODIFIED`, reachable only when an item carries invariants —
both remain user-owned and are never auto-rewritten (`enums.py:91-95`).

**Specialists are abilities, not opt-ins.** `_all_templated_capabilities`
(`generate/catalog.py:62`) hands the whole templated alphabet to
`resolve_coverage` on every pass; `--specialist` and `add-specialist` were demoted
from gates to order-forcers so an already-applied specialist keeps a stable
manifest position and hash identity (`generate/catalog.py:86-96`,
`cli/equip/dispatch.py:309-313`). Rejected: generating a specialist only when a
proposal happened to name its capability.

**Merge, never rebuild, the manifest.** Records this run does not re-derive are
carried forward verbatim, including a generated record under a now-stale name;
this run's records win name collisions (`cli/equip/dispatch.py:512-533`).
Rejected: rewriting the ledger from the current catalog, which silently dropped
marketplace and vendored entries. The residual cost is that a renamed template
leaves an orphan record until `remove` is run.

**Explicit verb.** Bare `equip` prints usage and exits 2; only the read-only
`--dry-run` survives verblessly, because a help/discovery probe must never mutate
the repo (`cli/equip/dispatch.py:102-115`).

**Reviewed defaults stay in the base layer.** `default_plugins.py` imports
nothing from `cli/`, `installer/`, or `context/domains/`, so
`context/domains/config.py:68` can depend on `default_wired()` without a
config→equip→config cycle (`default_plugins.py:12-17`, `:227`). Rejected: moving
the reviewed set under `domains/equip/`.

**Declaration and materialization are two operations.** `wire_default_plugins`
only classifies and writes settings (and explicitly `del`s its `runner`);
`install_default_plugins` runs the `claude` CLI once per eligible target. This
preserves useful project state when the executable is absent and keeps settings
mutation out of every installer invocation (`default_plugins.py:472-505`,
`:676-700`).

**No commit pin for default marketplaces.** Claude Code materializes with
`git clone --branch <ref>`, which accepts branch/tag names but never a commit
SHA, so third-party defaults track the upstream default branch and disclose the
blast radius instead of pinning; a dummyindex ≤ 0.33.x SHA pin left in settings is
*healed* to the unpinned shape rather than treated as a conflict, because it fails
the clone at every session start (`default_plugins.py:1-18`, `:353-409`). Healing
is deliberately shape-exact — `set(source) == {"source","repo","ref"}` plus a
40-hex ref — so a deliberate branch/tag pin stays a conflict
(`default_plugins.py:362-370`). This is a reversal of the earlier pinned-defaults
design and is load-bearing for `i-have-adhd`, which now declares an opt-in
SessionStart shell hook and `runs_code=True` (`default_plugins.py:185-191`).

**Declared surfaces never waive the gate.** `analyze_blast_radius` reads
attacker-controlled catalog metadata; `_plan_one` therefore sets
`requires_approval = not candidate.trusted` unconditionally
(`plugins/install_plan.py:41-48`). Trust policy also stays out of the generic
settings primitives: `add_marketplace` is a plain upsert, and the reviewed-default
wrapper adds its own identity guard at the policy boundary
(`claude_plugins.py:105-124`, `default_plugins.py:373-409`). Decided: *mechanism*
in the base layer, *policy* in its caller — which is exactly why the two disagree
on name conflicts (see Open questions).

**The per-prompt contract must survive a missing CLI.** The first
`UserPromptSubmit` command is a pure `printf` of a pre-serialized, `shlex.quote`d
JSON payload with no `command -v dummyindex` self-gate, so an alternate Claude
profile that can read project settings but has no `dummyindex` on PATH still gets
the behavior contract; `_guard_body` special-cases exactly that command when
adding the global defer-check guard (`hooks.py:105-145`, `hooks.py:379-409`). No
project path or prompt text is interpolated into the command string. The second
command in the same entry is independently fail-open and does **not** redirect
stdout, because that stream carries the `UserPromptSubmit` JSON
(`hooks.py:132-142`).

**Install classifies by file bytes, not by body comparison.**
`install_hook_entry` preserves co-located user hooks inside the managed entry, so
comparing against the canonical body would report "refreshed" forever once a user
wires their own hook beside ours; the honest signal is a byte-level before/after
read of `settings.json` (`hooks.py:534-549`).

**Two sentinels, deliberately.** `DUMMYINDEX_AUTO_REFRESH` (legacy name, kept so
upgrades still recognize and scrub old entries — recognition is
`SENTINEL in command`, so the accurate `_MANAGED_COMMENT` text can sit alongside
it) keys the five managed session hooks; `DUMMYINDEX_EQUIP:<event>` keys equip's
format hook (`hooks.py:56-73`, `hooks.py:270-276`, `constants.py:16-21`).

**Preserve-or-refuse everywhere settings are touched.** An unparseable
`settings.json` is never overwritten: hook uninstall records the error and skips,
the legacy scrub returns empty, `install_statusline` returns an advisory nudge,
and `wire_default_plugins` records the error per target and continues
(`hooks.py:644-660`, `hooks.py:574-584`, `hooks.py:366-375`,
`default_plugins.py:521-547`).

## Open questions

- `add_marketplace` overwrites a same-name entry whose source differs, while
  `_declare_marketplace` refuses it. Should the interactive `equip install` path
  adopt the same identity-conflict contract, or is upsert the intended behavior
  for a user-driven install (`claude_plugins.py:105-124`,
  `default_plugins.py:373-409`)?
- Native dynamic installs record `origin_ref=None` and enable a moving
  marketplace HEAD, while vendoring pins a resolved SHA. The base layer documents
  why a commit pin is not expressible for Claude Code's clone
  (`default_plugins.py:1-10`) — does that constraint also make a recorded ref
  useless for the native path, or should equip resolve one purely for
  lifecycle/audit purposes (`cli/equip/install.py:258-287`, `:335-446`)?
- Reviewed defaults never enter `.context/equipment.json`; they live in
  `config.wired`, settings, and Claude's per-machine registry, so `equip status`
  cannot report them at all (`default_plugins.py:676-760`,
  `cli/equip/verbs.py:74-118`). Is the ledger's silence about them the intended
  long-term contract, or does the five-store split-brain need a reconciler?
- `_USER_PROMPT_SUBMIT_PAYLOAD` bakes `ALWAYS_ON_TURN_REMINDER` verbatim into
  `settings.json` with no version stamp inside the command. `hooks install`
  rewrites the body when the text changes, but nothing else does — is a reinstall
  the only intended upgrade path for a repo whose reminder text has drifted
  (`hooks.py:110-145`, `hooks.py:534-549`)?
- `wire_default_plugins` keeps a `runner` parameter it immediately `del`s as a
  compatibility shim, and no in-tree caller passes it
  (`default_plugins.py:477`, `:505`; callers at `cli/init.py:73`,
  `cli/wire.py:240`, `installer/install/project_init.py:345`). What still depends
  on the signature?
