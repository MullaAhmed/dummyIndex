# Install surface — plan

confidence: INFERRED

## Where it lives

The `installer/` package holds the verbs and their plumbing: `args.py` (flag
parsing), `install.py` (skill copy + auto-init), `uninstall.py` (teardown),
`common.py` (version, paths, command copy/remove), re-exported from
`installer/__init__.py:14-26`. `__main__.py:245-267` is the thin dispatcher.
Init's two managed side-effects live one layer down in `context/`:
`context/default_plugins.py` (enable + materialise defaults) and
`context/hooks.py` (SessionStart/Stop/PreCompact wiring). This respects the
one-way layering `__main__ → installer → context` (`conventions/coding-practices.md`
§Layering).

## Architecture in three sentences

`main()` parses with `parse_install_args` then calls `install`/`uninstall`,
which copy or remove the skill tree under `<base>/.claude/skills/` and the
bundled commands. When the resolved candidate is a git repo and `--skill-only`
is absent, `install` calls `_auto_init_project`, which either full-builds
`.context/` or — on an enriched curated index — refreshes deterministic
artefacts only, then bootstraps CLAUDE.md, installs hooks
(`_install_project_hooks`), and wires defaults (`_wire_default_plugins_step`).
Every secondary step swallows its own errors and reports them, so the skill
copy never fails on a hook, config, or plugin snag.

## Data model

- **`DEFAULT_PLUGINS`** (`default_plugins.py:60-62`) — a tuple of frozen
  `DefaultPlugin(plugin, marketplace, repo=None, ref=None)` with a `.target`
  = `"<plugin>@<marketplace>"` property. Today: a single
  `superpowers@claude-plugins-official` (official marketplace, so no
  `extraKnownMarketplaces` / `repo` needed). Adding a default is a one-line edit.
- **Managed settings.json blocks** — plugins are *declared* under
  `enabledPlugins` in the project `.claude/settings.json` (committed, team-wide;
  user `~/.claude/settings.json` deliberately not consulted —
  `default_plugins.py:115-133`). Hooks are written under `hooks.<Event>` carrying
  the `DUMMYINDEX_AUTO_REFRESH` sentinel + managed comment so install/uninstall/
  status can find exactly their own entries (`hooks.py:48-57,160-165`).
- **Result records** (frozen dataclasses, `errors` tuples, never raise):
  `PluginWireResult`, `PluginInstallResult`, `RunResult`
  (`default_plugins.py:65-79,192-241`); `HookResult`, `HookStatus`
  (`hooks.py:276-309`).
- **Version stamp** — `.dummyindex_version` beside the skill and `__VERSION__`
  substituted into each shipped SKILL.md (`install.py:73-76,157`).

## Key decisions (additive / non-destructive)

- **Auto-init never re-clusters an enriched index** — on a council-enriched
  `.context/` it refreshes deterministic artefacts only and preserves the
  curated taxonomy; a re-cluster needs explicit `rebuild --full`/`ingest`
  (`install.py:241-277`).
- **Best-effort secondaries** — hooks, `config.json`, and plugin wiring each
  catch and report their own errors; `_install_project_hooks` always returns
  `True` (partial success), so the skill install stays green
  (`install.py:303-323,326-350,353-385`).
- **Declaration vs materialisation split** — `wire_default_plugins` writes the
  shared git-travelling declaration; `install_default_plugins` materialises the
  per-machine bits via the `claude` CLI, degrading to "deferred" when the CLI is
  absent or `DUMMYINDEX_SKIP_PLUGIN_INSTALL` is set (`default_plugins.py:175-189,287-329`).
- **Already-decided is sacrosanct** — a plugin the repo already enabled *or*
  explicitly disabled is left untouched (`default_plugins.py:115-172`); user
  hooks (no sentinel) and existing `config.json` / CLAUDE.md registration are
  never clobbered (`hooks.py:339-340`, `install.py:171-172,343-345`).
- **Subprocess behind a `Runner` seam** — `install_default_plugins` takes an
  injectable `Runner`; `default_runner` uses fixed argv, no shell, maps a
  missing executable to returncode 127, never raises (`default_plugins.py:200-223`,
  matching `conventions/coding-practices.md` §Runner seam).
- **Legacy compatibility** — `--platform` flags skipped silently
  (`args.py:82-89`); legacy `git post-commit` / `PostToolUse` auto-refresh hooks
  scrubbed on install (`hooks.py:351-369`).

## Open questions

- `DEFAULT_PLUGINS` is a single entry; the `repo`/`ref` non-official-marketplace
  path (`_install_one`, `default_plugins.py:264-274`) is exercised only by tests —
  no shipped default uses it yet.
- `_install_project_hooks` returns `True` unconditionally, so `_auto_init_project`'s
  bool return collapses to "build succeeded" regardless of hook outcome; callers
  treat it purely as the init-ran flag (`install.py:192-196,298-300`).
