# Install surface — plan

confidence: INFERRED

## Bounded context

One responsibility: make `dummyindex install` / `uninstall` an idempotent,
non-destructive surface that lays down the skill family and — on a git repo —
auto-inits the project. **In scope:** flag parsing, skill/command copy +
teardown, version stamping, and the three managed init side-effects (CLAUDE.md
block, hooks, default plugins). **Out of scope and merely *called*:** the
`.context/` builders (`build`/`ingest`), the `claude` plugin CLI, and the equip
toolkit — this feature owns the *wiring*, not the artefacts wired.

## Where it lives

The `installer/` package holds the verbs and plumbing: `args.py` (flag
parsing), `install.py` (skill copy + auto-init), `uninstall.py` (teardown),
`common.py` (version, paths, command copy/remove), re-exported from
`installer/__init__.py:14-26`. `__main__.py:245-267` is the thin dispatcher.
Init's two managed side-effects live one layer down in `context/`:
`context/default_plugins.py` (enable + materialise defaults) and
`context/hooks.py` (SessionStart/Stop/PreCompact wiring).

## Dependencies (one-way fan-out, no cycle)

Strict layering `__main__ → installer → context`
(`conventions/coding-practices.md` §Layering) holds end to end:

- **Upstream (callers):** `__main__.main` (`__main__.py:245-267`) is the only
  entry; the `/dummyindex-update` skill re-runs `install` to refresh wiring.
- **Downstream (callees of `_auto_init_project`, all best-effort):** the
  `.context/` builders for the full vs. deterministic-refresh fork
  (`install.py:248-277`); `hooks.install` (`hooks.py:329-412`);
  `wire_default_plugins` + `install_default_plugins`
  (`default_plugins.py:136-172,287-329`). These are siblings — `install.py`
  fans out to each independently; **hooks and default_plugins never call each
  other**, so the apparent triangle is a fan-out, not a cycle.
- **Shared leaf:** both managed-block writers read/write `.claude/settings.json`
  via the same `load_settings` helper, but through disjoint keys
  (`hooks.<Event>` vs. `enabledPlugins`) — no write contention.

## Architecture in three sentences

`main()` parses with `parse_install_args` then calls `install`/`uninstall`,
which copy or remove the skill tree under `<base>/.claude/skills/` and the
bundled commands. When the resolved candidate is a git repo and `--skill-only`
is absent, `install` calls `_auto_init_project`, which full-builds `.context/`
(fresh) or refreshes deterministic artefacts only (enriched), then bootstraps
CLAUDE.md, installs hooks, and wires defaults. Every secondary step swallows its
own errors and reports them, so the skill copy never fails on a hook, config, or
plugin snag.

## Patterns (named, located)

- **Additive settings merge** — every `.claude/settings.json` write is a
  read-merge-write that touches only this feature's keys and leaves foreign keys
  byte-for-byte. `wire_default_plugins` merges into `enabledPlugins`
  (`default_plugins.py:136-172`); `hooks.install` merges under `hooks.<Event>`
  (`hooks.py:329-412`). Both refuse a non-object settings file rather than
  overwrite it, and both go through one `load_settings` reader.
- **Managed-block** — hook entries carry the `SENTINEL =
  "DUMMYINDEX_AUTO_REFRESH"` (`hooks.py:48`) plus a managed comment so
  install/uninstall/status select *exactly their own* entries and never touch
  user-authored hooks (no sentinel → left alone, `hooks.py:339-340`). The
  CLAUDE.md registration block is the same idea in markdown
  (`install.py:171-172`).
- **Runner seam** — `install_default_plugins` takes an injectable `Runner`;
  `default_runner` (`default_plugins.py:207-223`) uses fixed argv, no shell,
  maps a missing executable to returncode 127, never raises
  (`conventions/coding-practices.md` §Runner seam).

## Data model

- **`DEFAULT_PLUGINS`** (`default_plugins.py:60-62`) — a tuple of frozen
  `DefaultPlugin(plugin, marketplace, repo=None, ref=None)` (`default_plugins.py:36-52`)
  with a `.target` = `"<plugin>@<marketplace>"` property. Today: a single
  `superpowers@claude-plugins-official` (official marketplace, so no
  `extraKnownMarketplaces` / `repo` needed). Adding a default is a one-line edit.
- **Managed settings.json keys** — plugins *declared* under `enabledPlugins`
  in the committed project `.claude/settings.json` (team-wide; user
  `~/.claude/settings.json` deliberately not consulted —
  `default_plugins.py:115-133`). Hooks written under `hooks.<Event>` with the
  sentinel + comment (`hooks.py:48-57,162-165`).
- **Result records** (frozen dataclasses, `errors` tuples, never raise):
  `PluginWireResult`, `PluginInstallResult`, `RunResult`
  (`default_plugins.py:65-79,192-241`); `HookResult`, `HookStatus`
  (`hooks.py:276-309`).
- **Version stamp** — `.dummyindex_version` beside the skill and `__VERSION__`
  substituted into each shipped SKILL.md (`install.py:73-76,157`).

## Key decisions (why additive / non-destructive)

The whole surface is re-run on every upgrade by `/dummyindex-update`, on repos
that may already be curated and team-configured. So the invariant is: **a
second run, or a run over an existing config, must never lose user state.** Each
decision below is that invariant applied to one seam.

- **Auto-init never re-clusters an enriched index** — protects hand-curated
  feature docs from being flattened by a deterministic re-cluster; an enriched
  `.context/` takes the refresh-only path and a re-cluster needs explicit
  `rebuild --full`/`ingest` (`install.py:246-277`).
- **Best-effort secondaries** — hooks, `config.json`, and plugin wiring each
  catch and report their own errors so a partial-environment snag (no `claude`
  CLI, malformed settings) never aborts the skill copy; `_install_project_hooks`
  always returns `True` (`install.py:303-323,326-350,353-385`).
- **Declaration vs materialisation split** — separates the *git-travelling*
  team decision from the *per-machine* effect: `wire_default_plugins` writes the
  shared `enabledPlugins` declaration; `install_default_plugins` materialises via
  the `claude` CLI, degrading to "deferred" when the CLI is absent or
  `DUMMYINDEX_SKIP_PLUGIN_INSTALL` is set (`default_plugins.py:175-189,287-329`).
- **Already-decided is sacrosanct** — a plugin the repo already enabled *or*
  explicitly disabled is left untouched (`_already_decided`,
  `default_plugins.py:115-172`); user hooks, existing `config.json`, and prior
  CLAUDE.md registration are never clobbered (`hooks.py:339-340`,
  `install.py:171-172,344-345`).
- **Legacy compatibility** — `--platform` flags skipped silently
  (`args.py:82-89`); legacy `git post-commit` / `PostToolUse` auto-refresh hooks
  scrubbed on install so upgraders aren't left with the retired auto-refresh
  behaviour (`hooks.py:348-369`).

## Open questions

- `DEFAULT_PLUGINS` is a single entry; the `repo`/`ref` non-official-marketplace
  path (`_install_one`, `default_plugins.py:255-274`) is exercised only by tests —
  no shipped default uses it yet.
- `_install_project_hooks` returns `True` unconditionally, so `_auto_init_project`'s
  bool collapses to "build ran" regardless of hook outcome; callers treat it
  purely as the init-ran flag (`install.py:192-196,298-300`).
