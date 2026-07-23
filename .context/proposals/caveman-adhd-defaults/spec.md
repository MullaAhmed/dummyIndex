# Spec — Add https://github.com/juliusbrussee/caveman and https://github.com/ayghri/i-have-adhd as defaults similar to superpowers and make sure they are always used

> Scaffolded by `dummyindex context propose`. Flesh out the intent
> and contracts below, then keep the **Acceptance** checklist honest.

## Intent

Make `caveman` and `i-have-adhd` part of dummyindex's batteries-included
experience alongside `superpowers`. A user who initializes or updates a
Claude-enabled dummyindex repo should get all three declared and materialized
without a separate marketplace setup step. A user entering any dummyindex-managed
repo through Claude Code or Codex should receive the combined terse,
action-first output behavior from the first turn rather than having to remember
`/caveman`, `/i-have-adhd`, or `$i-have-adhd` in every session.

The upstream activation mechanisms are not equivalent. `caveman` ships a
Claude `SessionStart` command hook and a `UserPromptSubmit` command hook and
documents activation from message one, while `i-have-adhd` is an inert skill
with `disable-model-invocation: true` and documents an explicit invocation that
lasts only until stopped. Therefore plugin installation alone cannot establish
the requested invariant. Dummyindex owns a short, host-neutral output-policy
sentence in its managed project guidance as the always-on fallback; the
installed plugins still provide their commands and full behavior when invoked
explicitly.

## Contracts

### Default set and marketplace identity

- Reuse `DefaultPlugin`, `DEFAULT_PLUGINS`, `_plugin_to_wired`, and
  `default_wired` in `dummyindex/context/default_plugins.py` as the single source
  of default targets. Preserve the existing
  `superpowers@claude-plugins-official` entry, then add
  `caveman@caveman` backed by `JuliusBrussee/caveman` at immutable commit
  `0d95a81d35a9f2d123a5e9430d1cfc43d55f1bb0` and
  `i-have-adhd@i-have-adhd` backed by `ayghri/i-have-adhd` at immutable commit
  `0241185d6c7f2d0763a988ce52eceb13ea9f5c1f`.
- Treat these two records as a narrow, reviewed built-in exception to equip's
  dynamic third-party approval flow, not as a relaxation of that flow. Record
  and disclose their reviewed blast radius before mutation: Caveman ships
  skills/commands plus Node command hooks on `SessionStart` and
  `UserPromptSubmit` (`runs_code=true`); i-have-adhd ships one skill and no
  executable plugin hook (`runs_code=false`). A future ref change is a source
  update requiring a new code review and release; it never follows mutable
  `main` silently.
- Claude and both-host installs/ingests declare the selected defaults in the
  project `.claude/settings.json`. Reuse `add_marketplace` to write each exact
  non-official repo/ref into `extraKnownMarketplaces` before writing its
  `enabledPlugins` target, so a missing Claude CLI can still resolve the plugin
  on a later session. An identical declaration is a no-op; a same-name,
  different-source declaration is reported as needs-user and is never
  overwritten or installed. Materialization uses the existing `Runner` seam and
  fixed argv with no shell. Codex-only installs do not write `.claude/**` and do
  not run the Claude CLI.
- Default declaration and materialization remain best-effort. A missing Claude
  CLI defers all selected plugins; marketplace or install failures are reported
  per target, do not prevent later independent defaults from being attempted,
  and never fail the index build or skill installation.

### Upgrade and opt-out behavior

- A fresh Claude/both config seeds all three defaults through `default_wired()`.
  Add an explicit config-state field in the next config schema so
  "Claude defaults disabled" is distinguishable from "not applicable yet on a
  Codex-only repo." Reinstall/update appends any newly introduced default target
  missing from an opted-in config before that same run reads, declares, or
  materializes plugins, preserving order and every custom entry. A Codex-only
  baseline stays mutation-free but can transition to Claude/both in one run and
  receive defaults; schema migration preserves known explicit opt-outs.
- An explicitly disabled default-plugin state remains the durable all-defaults
  opt-out and is never backfilled. An explicit `false` value for an individual
  target in project or local `enabledPlugins` remains an individual tombstone:
  it is neither changed to `true` nor materialized by dummyindex. A malformed
  config fails closed: warn and skip all default marketplace/plugin mutation
  instead of falling back to `default_wired()`.
- Introduce `--no-default-plugins` as the accurately named one-run opt-out.
  Continue accepting `--no-superpowers` as a backward-compatible alias; either
  skips the complete default set before config reconciliation, marketplace
  declaration, settings writes, runner probes, or code execution. On a current
  config, the file remains byte-identical.
- Reuse `wire_default_plugins` for declaration and
  `install_default_plugins` for one target-aware materialization pass. Only
  defaults both declared in the selected `wired` set and effectively `true`
  after project/local precedence are eligible. A single init/update must not
  re-run the whole install loop once per newly declared target. The interactive
  `context wire` path reuses the same one-target seam and must never install
  unrelated defaults.

### Always-on output policy

- Define one shared, terse policy string at the managed-guidance seam in
  `dummyindex/context/output/bootstrap.py`. It requires every reply to use the
  combined `caveman`/`i-have-adhd` behavior without waiting for an invocation:
  lead with the outcome or next action, keep prose compact, number multi-step
  work, suppress tangents, restate current state, and preserve technical and
  safety detail. Explicit user formatting requests and safety requirements win.
- Reuse that same string in Claude's `generate_managed_block()` and Codex's
  project `_PROJECT_BLOCK`; do not duplicate drifting variants. Do not add it to
  Codex's global block, because the default-plugin behavior is project-scoped
  like the existing `superpowers` wiring.
- This proposal does not create a Codex third-party-plugin installer. Codex-only
  projects receive the always-on behavior through their active managed
  `AGENTS.md`; Claude/both projects additionally receive the native plugins.

### Compatibility and documentation

- Preserve existing user content and managed-marker ownership in CLAUDE.md and
  AGENTS.md. Re-running bootstrap replaces only dummyindex's block.
- Update CLI help, command/reference docs, and the shipped dummyindex skill text
  so the three defaults, both opt-out spellings, host scope, and activation
  contract agree with code.
- Tests use `tmp_path` and injected runners only. They never execute a real
  `claude` command or access the network.

## Acceptance

- [ ] `DEFAULT_PLUGINS` contains exactly the existing superpowers default plus
  the two reviewed, full-SHA-pinned third-party records above, with unique
  targets in deterministic order and explicit surfaces/`runs_code` metadata.
- [ ] Before any third-party settings/network action, install/init output names
  each source/ref, its reviewed surfaces, whether it runs code, and the
  `--no-default-plugins` opt-out; tests prove the disclosure precedes runner
  calls. Equip's separate untrusted-source approval behavior remains unchanged.
- [ ] For both `install` and `context init` on `claude` and `both`, a fresh repo
  writes both pinned third-party entries to `extraKnownMarketplaces` and all
  three targets as `true` in `enabledPlugins`; the fake runner observes each
  marketplace add before its matching install with no duplicate install pass.
- [ ] With the Claude CLI absent, all eligible targets are deferred while the
  pinned marketplace declarations and enabled targets remain resolvable in
  project settings. A marketplace-add failure skips that target's install, later
  defaults still run, exact result buckets are reported, and init/install still
  succeeds.
- [ ] An identical predeclared marketplace is not rewritten; a same-name source
  conflict is neither overwritten nor installed and is reported needs-user.
- [ ] A Codex-only install/init neither writes `.claude/settings.json` nor invokes
  the Claude runner, while its managed project AGENTS.md contains the shared
  always-on output policy. A Codex-only config can transition to Claude/both and
  receive all defaults in that same run; an explicit prior opt-out stays off.
- [ ] Reinstalling an opted-in current config backfills the two new defaults
  before wiring, then persists and materializes them in the same run without
  losing or duplicating custom entries; rerunning is byte- and call-idempotent.
- [ ] A target explicitly set to `false` in project or local settings stays
  false and is absent from the fake runner's marketplace/install calls. A
  declared set that omits a default never materializes it, and an empty/disabled
  set makes zero runner calls.
- [ ] `--no-default-plugins` and legacy `--no-superpowers` each skip all three
  defaults for both `install` and `context init`; on a current non-empty config
  the installer leaves `config.json` byte-identical and performs no marketplace,
  settings, runner, or backfill action.
- [ ] A malformed config causes install/init to warn and perform no default
  marketplace, enabled-plugin, runner, or config mutation.
- [ ] Generated Claude CLAUDE.md and Codex project AGENTS.md carry the same
  policy byte-for-byte exactly once and preserve user-authored surrounding
  content on refresh; rendered Codex global guidance does not contain it.
- [ ] CLI help, `docs/COMMANDS.md`, `docs/guide/07-cli.md`, and the shipped
  dummyindex skill describe the three defaults and the canonical/legacy opt-out
  flags consistently. Exact help-output and documentation-sync tests cover the
  top-level, install, ingest/init, host-scope, and trust-disclosure wording.
- [ ] Focused config/default-plugin/install/init/guidance tests and the full
  pytest suite pass without network access; Ruff reports no lint or format drift.

<!-- dummyindex:consistency:begin -->
## Consistency

**Related features:**

- `tree-enrich`
- `install-surface`
- `council`
- `equip`
- `gc`

**Conventions to honor:**

- `conventions/coding-practices.md`
- `conventions/data-access.md`
- `conventions/folder-organization.md`
- `conventions/naming.md`
- `conventions/testing.md`

<!-- dummyindex:consistency:end -->
