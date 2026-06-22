# Spec — Make dummyindex config intuitive: per-command depth, a self-reconciling `wired` plugins/skills list, and a config-UX audit

> Scaffolded by `dummyindex context propose`. Intent + contracts below;
> the **Acceptance** checklist is the source of truth for "done".

## Intent

**Problem.** `.context/config.json` is the durable record of a repo's dummyindex
choices, but two parts of it are blunt and one is misleading:

1. **Depth is a single global dial.** `mode` (`light|standard|deep`) governs
   council effort for *every* council-bearing command at once. A user who wants
   a *deep* first `ingest` but *light* `reconcile` passes — or a one-off deep
   `audit` without editing committed config — has no way to say so. Only
   `audit` today has any per-run override (`--mode`, via
   `audit/workspace.py:resolve_mode`); it's undiscoverable and inconsistent.

2. **`wire_superpowers: true` is the wrong shape.** A boolean says *whether* to
   wire one hard-coded plugin (`superpowers`), but the repo actually wants to
   declare *which* plugins **and skills** should be present, **at which
   version**, and have dummyindex keep reality in sync — wiring what's missing,
   updating what's stale, and prompting when it can't act on its own. The
   boolean can't express any of that, and the wired set is frozen in code
   (`default_plugins.DEFAULT_PLUGINS`) instead of in the user's config.

3. **The config surface is unintuitive.** The `config.py` schema docstring is
   stale (shows `mode: standard`/`model: sonnet-4.6`, omits `reconcile_exclude`
   and `wire_superpowers`); `ModelChoice.OPUS_4_7` has the value `"opus-4.8"`
   (member name lies); `status` doesn't surface depth or wiring state; help text
   doesn't mention any of it.

**For whom.** Every dummyindex user. The first two are concrete capability
gaps; the third is the "isn't intuitive or useful" papercut layer the user
called out, scoped to the config surface (CLI help, `status`, config docstrings)
rather than an open-ended UX rewrite.

## Contracts

### A. Per-command depth (config defaults + `--depth` flag)

- **Config**: add `command_depths: tuple[tuple[DepthCommand, CouncilMode], ...]`
  to `Config` (immutable; serialized as a JSON object). The key is a new closed
  enum `DepthCommand(str, Enum)` (members: `ingest`, `reconcile`, `audit`,
  `build` — see command-set decision below), **not a bare string** — the command
  set is a closed alphabet, so it gets an enum like `CouncilMode`/`ScopeKind`
  (per `conventions/coding-practices.md` enum-constants rule). Absent/empty by
  default — back-compat with every existing config. An unknown key in the JSON is
  rejected at `from_dict` via the enum's `ValueError` path (typo protection),
  listing the valid commands.
- **Resolver** (single seam — **lives in `config.py`**, not `audit/`): add
  `resolve_depth(context_dir, command, depth_flag) -> CouncilMode` to `config.py`
  (pure config-precedence logic over `Config.command_depths`/`Config.mode`).
  Precedence: **`--depth` flag → `config.command_depths[command]` →
  `config.mode` → `STANDARD`**. Invalid value → `ConfigError` listing the allowed
  set. `audit/workspace.py:resolve_mode` becomes a thin audit-bound wrapper that
  delegates to it, so audit's callers/tests are undisturbed. (Rationale: the
  resolver is read by 4 unrelated command modules; keeping it in the `audit`
  domain would force `cli/init.py`, `cli/reconcile.py`, etc. to import the audit
  domain — a layering violation per `conventions/folder-organization.md`.)
- **Flag**: `--depth light|standard|deep` parsed via the **shared
  `cli/common.py:parse_kv_flags`** alphabet (add `depth` there) — *not* by
  importing `onboard._pull_value_flag` into other `cli/` modules (that would
  widen the cross-`cli`-import anti-pattern). One-run override; never written to
  config. `audit`'s existing `--mode` stays audit-local (`cli/audit.py`
  `value_keys`); passing **both** `--mode` and `--depth` to `audit` is an error.
- **Invariant**: `mode` stays the global fallback — removing it is out of scope.
  Every command in `DepthCommand` must have a real council/build consumer of the
  resolved mode (`council_batch.active_stages(mode, …)`); `rebuild` is excluded
  because it is deterministic (no council stage) and would silently no-op a
  `--depth` flag.

### B. `wired` — a declarative, version-aware, self-reconciling list

Replace `wire_superpowers: bool` with `wired`: a list of declared entries, each
naming a plugin **or** skill, its target, and an optional pinned version. It is
the **user-facing source of truth for what should be present**; it is committed,
hand-editable, and reconciled against reality.

- **Shape** (new frozen dataclass `WiredEntry`, defined in the **base-layer**
  `default_plugins.py` so `config.py` imports it *upward* — never the reverse —
  keeping `default_plugins.py`'s "imports nothing from `domains/`" rule intact):
  ```jsonc
  "wired": [
    { "kind": "plugin", "target": "superpowers@claude-plugins-official", "version": null },
    { "kind": "skill",  "target": "some-skill", "version": "1.2.0" }
  ]
  ```
  `kind ∈ {plugin, skill}` (an enum, not bare strings); `target` is
  `<plugin>@<marketplace>` for a plugin or a skill name; `version` is a
  **descriptive** pin or `null`. `version` is recorded and surfaced, **not
  enforced as a git ref** (the install-listing semver is not an install ref — see
  the equip "wrong-ref" precedent). `WiredEntry` reuses `DefaultPlugin.target`'s
  format via one adapter so the two don't drift.
- **Seed**: a fresh `default_config()` seeds `wired` from
  `default_plugins.DEFAULT_PLUGINS` (today: one `superpowers` entry) — the
  default set moves from code-as-law to config-as-declaration.
- **Reconcile is non-interactive and never-blocking** (this is load-bearing:
  `wire_default_plugins` runs inside best-effort `install`/`ingest`, which are
  documented to never raise and run on the CI/`--defaults`/headless path).
  `default_plugins.wire_default_plugins` evolves into a list-driven reconciler
  that takes `tuple[WiredEntry, ...]` as a parameter (no `config` import) and
  **only classifies and reports** — it never calls `input()`. Per entry, against
  the actual `.claude/settings.json` (presence is what's truthfully knowable;
  per-machine installed version is **not** in settings.json, so the reconciler
  does not synthesize a "stale" verdict from it):
  - **satisfied** — plugin present in settings → left untouched.
  - **acted** — plugin declared but absent → dummyindex wires it
    (`enable_plugin`/`add_marketplace` + best-effort `install_default_plugins`).
  - **needs-user** — dummyindex can't act unattended (untrusted source needing
    `--yes`, install failure, or a `kind: skill` entry — see below) →
    **classified into a returned `needs_user` field and reported in the summary
    line, never silently dropped, never prompted in-process.** The actual
    user-facing prompt is raised only by the *interactive* surface (the
    `/dummyindex` skill / build conductor — a `**GATE**`/main-session item),
    which is never reached from `install --defaults` or a headless init. `status`
    is the durable surface so a missed escalation is recoverable.
- **Skill auto-wiring is descoped to "declared + surfaced" for this proposal.**
  There is no "enable a bare skill" primitive (skills are files / are bundled by
  plugins); a `kind: skill` entry is recorded in `wired`, shown by `status`, and
  classified **needs-user** if not present — it is never auto-wired here. Plugins
  (`kind: plugin`) are fully auto-wired. (Keeps the user-requested "plugins **and**
  skills" list while not promising a wiring mechanism that doesn't exist.)
- **equip writes back** (project/in-repo scope only): `equip install`
  (`cli/equip/discover.py:run_install`) upserts the matching `wired` entry in
  `config.json` keyed on `<plugin>@<marketplace>`, alongside its existing
  `equipment.json` MARKETPLACE record. **If no committed `config.json` exists**
  (e.g. `--scope user`, or a repo indexed before config existed), write-back is
  **skipped with a warning** — it never silently materializes a full seeded
  config as a side effect of one install. `write_config` is atomic; concurrency
  assumption: equip install is single-writer per repo (stated, since build can
  fan out). `config.wired` (declared intent) and `equipment.json` (render/
  lifecycle manifest) stay reconcilable via that shared key; an Acceptance test
  asserts they don't diverge after an install.
- **Migration**: bump `CONFIG_SCHEMA_VERSION` 1 → 2. On read, a v1 config is
  migrated **in-memory only** (no eager rewrite to disk — a migrated config is
  persisted only when the user already triggered a write): `wire_superpowers:
  true` → seed default `wired`; `false` → empty `wired` (opt-out preserved).
  `--no-superpowers` CLI flag and `resolve_enabled` precedence (CLI > config >
  on) are preserved against the new shape (empty `wired` == opted out).
  **Forward-compat limitation (accepted):** an *older* CLI that hard-rejects
  `schema_version != 1` will refuse a v2 config; the drift/version check warns
  about this, and `/dummyindex-update` is the documented remedy.

### C. Config-UX audit (scoped)

Concrete papercuts to fix (the audit may surface more on the listed surfaces,
but these are committed):
- `config.py` module docstring schema example → regenerate to the v2 shape
  (all current fields, `command_depths`, `wired`).
- Rename `ModelChoice.OPUS_4_7` → `OPUS_4_8` (value already `"opus-4.8"`). The
  value is unchanged, so configs/serialization are unaffected — pure identifier
  fix. **8 occurrences across 3 files**, two of them test modules
  (`tests/context/domains/test_config.py`, `tests/context/domains/audit/test_audit_domain.py`,
  the latter asserting on the member name directly) — all must move in lockstep
  or the suite goes red.
- `onboard.py` usage banner + `cli/help.py` → document `--depth` and the
  `wired`/`command_depths` config keys.
- `status` (`cli/status.py`) → surface effective depth per command and the
  `wired` reconcile state (satisfied / acted / needs-user counts).

### D. Config records the dummyindex version

`config.json` gains a `dummyindex_version: str` field recording the CLI version
that last wrote it (sourced from `importlib.metadata.version("dummyindex")`, the
same source `init.py:48-52` already reads). It is **descriptive, not a gate**:
read tolerates any value (never refuses to load) and `write_config` stamps the
current version on every write, so the field always reflects the last *config*
writer.

> **Divergence noted (user-requested over architect caution).** A
> `dummyindex_version` already lives in `.context/meta.json` (last *build*) and
> `cli/check.py`/`status.py` already render a "written by vX, CLI vY" drift
> signal from it. The architecture critic flagged the config copy as a duplicate
> stamp. The user explicitly asked that **config** hold the version, so we keep
> it — but to avoid two contradictory drift signals: `meta.dummyindex_version`
> stays the *build*-version anchor `check.py` reads; `config.dummyindex_version`
> is specifically the *last-config-writer* stamp (a different, finer event), and
> `status` labels them distinctly rather than emitting a second conflicting
> drift line. On v1→v2 migration the field is populated with the current version.

### Boundary decision (resolved — config.wired vs equipment.json)

`config.wired` is the **declared desired set** (user intent, committed,
version-pinned). `.context/equipment.json` remains the **render/lifecycle
manifest** of what equip generated/wired (hash-baselined). They are not merged:
`equip install` writes **both**. This keeps equip's idempotent, never-clobber
lifecycle intact while giving the user one editable declaration of intent.

## Decisions (made, not open — several settled in response to the critique panel)

- **Schema bump to v2 with v1→v2 *in-memory* read migration** — removing
  `wire_superpowers` and changing shape warrants the bump; `from_dict` accepts v1
  and migrates so no committed config breaks. Migration does **not** eagerly
  rewrite disk; a v1 file is only upgraded when the user already triggered a
  write. Byte-stable round-trip is asserted for **v2-in → v2-out**; v1→v2 is
  asserted by **field-equality**, not byte-equality.
- **`resolve_depth` lives in `config.py`**, not `audit/` (panel HIGH) —
  `resolve_mode` becomes a thin audit wrapper delegating to it.
- **`command_depths` is keyed on a `DepthCommand(str, Enum)`** (panel HIGH), not
  a bare-string map guarded by a frozenset.
- **`--depth` is canonical; `--mode` stays an audit-local back-compat alias**;
  passing both to `audit` is an error.
- **`mode` (global) is retained** as the fallback below `command_depths`.
- **Depth-bearing command set** = `ingest`/`init`, `reconcile`, `audit`, `build`.
  **`rebuild` is excluded** — deterministic, no council stage to consume depth
  (panel MEDIUM). Non-council commands (`status`, `query`, `equip`) ignore depth.
- **Reconcile is classify-and-report only; never interactive in-process** (panel
  BLOCK ×2) — prompting is relocated to the interactive `/dummyindex` surface.
- **Version is recorded/surfaced, not enforced** (panel BLOCK) — settings.json
  has no installed-version field; the reconciler does not synthesize "stale".
- **`kind: skill` is declared + surfaced, not auto-wired** (panel BLOCK) — no
  skill-enable primitive exists; skill entries classify needs-user if absent.
- **`WiredEntry` is defined in base-layer `default_plugins.py`** (panel
  MEDIUM) — `config.py` imports it upward; the reconciler takes it as a param.
- **equip write-back is project-scope only; absent config → skip-with-warning**
  (panel HIGH), single-writer-per-repo assumption.
- **Forward-compat limitation accepted** — an older CLI rejects a v2 config; the
  version/drift check warns and `/dummyindex-update` is the remedy (panel HIGH).

## Acceptance

- [ ] A config with `command_depths: {"reconcile": "light"}` makes `reconcile`
      run light while `ingest` (unset) still runs the global `mode` (asserted via
      the resolved `CouncilMode` the command passes to `active_stages`).
- [ ] `--depth deep` on a depth-bearing command overrides config for that run and
      `config.json` bytes are unchanged afterward (not written back).
- [ ] `resolve_depth` precedence holds under unit test: flag > `command_depths[cmd]`
      > `mode` > `standard`; an invalid `--depth`/`command_depths` value raises
      `ConfigError` with the allowed set listed.
- [ ] An unknown command key in `command_depths` is rejected by `Config.from_dict`
      (enum `ValueError` path) with a message naming the valid commands;
      `command_depths` serializes as a JSON object (`{"reconcile":"light"}`,
      enum-repr-free) and round-trips back to the tuple form.
- [ ] A v1 config with `wire_superpowers: true` migrates (field-equality) to a
      `wired` seeded from `DEFAULT_PLUGINS`; `false` migrates to empty `wired`.
- [ ] Reconcile returns each `wired` entry classified satisfied / acted /
      needs-user **on the result object** (asserted with an injected fake runner,
      no stdin/TTY); needs-user entries are non-empty in `result.needs_user` and
      appear as a `capsys`-asserted per-class count in the init summary — never
      silently dropped, and **no test hangs on an interactive prompt**.
- [ ] `equip install <plugin>@<marketplace>` (project scope) upserts a matching
      `wired` entry in `config.json` keyed on `<plugin>@<marketplace>`, alongside
      the existing `equipment.json` record, and the two do not diverge.
- [ ] `equip install --scope user` (no committed config) does **not** raise and
      does **not** create a spurious `config.json`; a `write_config` failure is
      warned-and-continued, leaving the install rc + manifest record intact.
- [ ] `--no-superpowers` yields an empty `wired` **and** leaves `superpowers`
      absent from `.claude/settings.json` (both the config-level and the existing
      end-to-end settings assertion hold; the dead `wire_superpowers=False`
      opt-out test is migrated to a `wired=()` config).
- [ ] `ModelChoice.OPUS_4_8` is the member name; `grep -rn OPUS_4_7` over
      `dummyindex/` + `tests/` is empty (incl. the two test modules); a v2 config
      round-trips **byte-stable**.
- [ ] `config.json` carries `dummyindex_version`; `write_config` stamps the
      current version on every write; `read_config` loads any version without
      error; v1→v2 migration populates it.
- [ ] `status` surfaces effective depth per command, the `wired` classification
      counts, and a config-version line — and a unit test proves `status` does
      **not** mutate `config.json` (bytes unchanged after the call).
- [ ] `config.py` docstring, `onboard` usage, and `cli/help.py` output contain
      `--depth` / `command_depths` / `wired` substrings (capsys, mirroring the
      existing `--skill-only` usage-help test).
- [ ] `python -m pytest tests/ -q --tb=short` passes on the 3.10/3.12 matrix; new
      behavior is covered (config round-trip/migration, resolver precedence,
      reconcile outcomes, equip write-back + absent-config, status no-mutate) at
      the repo's standard.

<!-- dummyindex:consistency:begin -->
## Consistency

**Related features:**

- `tree-enrich`
- `audit-panel`
- `equip`
- `install-surface`
- `build-loop`

**Conventions to honor:**

- `conventions/coding-practices.md`
- `conventions/data-access.md`
- `conventions/folder-organization.md`
- `conventions/naming.md`
- `conventions/testing.md`

<!-- dummyindex:consistency:end -->
