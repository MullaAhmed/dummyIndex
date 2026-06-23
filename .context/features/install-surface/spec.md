# Install surface — spec

confidence: INFERRED

## Intent

Give `dummyindex install` / `uninstall` a single, idempotent surface that copies
the Claude Code skill family into a scope root and — when that scope points at a
git repo — auto-inits the project: builds `.context/`, writes a managed
CLAUDE.md block, installs the SessionStart/Stop/PreCompact hooks, and enables a
small opinionated set of default plugins. Every secondary step is best-effort
and non-destructive: a snag in hooks, config, or plugin wiring is reported but
never fails the skill copy, and an existing curated `.context/` is refreshed
deterministically rather than re-clustered (`install.py:241-277`).

## User-visible behavior

### Install

`dummyindex install` copies `SKILL.md` (with `__VERSION__` substituted to the
package version) and its `agents/`/`council/`/`retrieval/` companions into
`<base>/.claude/skills/dummyindex/`, where `base` is `~` for `--scope user` or
the resolved `--dir` (else cwd) for `--scope project` (`install.py:63-92`). It
also drops the sibling top-level skills `dummyindex-remember|plan|equip|build|audit|update`
each in its own dir (`install.py:94-155`), copies the bundled `/tokens` slash
command (`common.py:49-66`), stamps `.dummyindex_version`, and — for user scope —
registers the skill in `~/.claude/CLAUDE.md` only if not already present. The
"already present" probe matches the registration sentinel substring
`"**dummyindex** ("` (the unique opening of the `_SKILL_REGISTRATION` bullet),
not a bare `"dummyindex"` mention — so a user CLAUDE.md that merely names
dummyindex without carrying the managed block still gets the block appended, and
an already-registered file is left untouched (`install.py:167-186`). Stale
prior-version markdowns and `*.tmpl` twins are purged on upgrade
(`install.py:89-90,135-142`).

Auto-init runs when the resolved candidate is a git repo (`.git/` dir or
submodule/worktree `.git` file) and `--skill-only` is not set
(`install.py:187-195`). On a fresh/deterministic-only index it full-builds
`.context/`; on an *enriched* curated index it takes the non-destructive
refresh path (refresh deterministic artefacts only, never re-cluster), printing
a "curated index preserved" line and a desync warning if INDEX.json disagrees
with disk (`install.py:255-274`). Both paths then **reconcile** the project
CLAUDE.md, install hooks, and wire default plugins. CLAUDE.md is consolidated
through `reconcile_claude_md(project_root)`: any pre-existing root
`./CLAUDE.md` (legacy block, hand-written user content, or both) is folded —
above a single fresh managed block — into the canonical `.claude/CLAUDE.md`,
and the root file is then deleted, fixing the onboarding-dangling bug where a
fresh install left a stale root CLAUDE.md alongside the managed one. The full-
build path reaches the helper inside `build_all` (`bootstrap=True`,
`runner.py:262-267`) and prints "managed block written" off `result.bootstrapped`
(`install.py:300-301`); the enriched-preserved branch calls
`reconcile_claude_md` directly and prints the result's `message`
(`install.py:276-277`). `--defaults` / `--no-onboarding` additionally writes a
default `.context/config.json` (never clobbering an existing one)
(`install.py:198-199,334-354`). On every repo install — including a plain
re-install (the `/dummyindex-update` path, no flags) — `_migrate_existing_config`
(`install.py:361`) upgrades a *stale* existing config in place (pre-v2 schema or a
renamed value like legacy `opus-4.7`) via `config.migrate_config_in_place`, a
value-preserving migration that leaves a current config untouched. Immediately
after, `_reconcile_wired_step` (`install.py`) folds equip-installed plugins back
into `config.wired` via `config.reconcile_wired_with_equipment` — so a v1→v2
migration (which reseeds `wired` from defaults only) never silently drops a
plugin the user equipped. Best-effort and idempotent: silent on a repo with
nothing to fold, and it never fails the install.

### Uninstall

`dummyindex uninstall` removes the main skill, its companions and version stamp,
every sibling skill dir, and the bundled commands from the chosen scope, then
prunes now-empty parents; prints the first removed path or `nothing to remove`
(`uninstall.py:12-86`).

### Default plugins (reconcile the declared `wired` list)

At init, `_wire_default_plugins_step` resolves whether wiring is on
(CLI `--no-superpowers` > persisted `config.wired` non-empty > on; an empty
`wired` is the opt-out), then **reconciles the declared `wired` list** against
the project `.claude/settings.json`. The declared set is the loaded
`config.wired` when a config exists, else `default_wired()` (seeded from
`DEFAULT_PLUGINS` — `superpowers@claude-plugins-official`)
(`install.py:353-395`, `default_plugins.py:155-162`).

`wire_default_plugins(wired, project_root, *, enabled=True, runner=None)` takes
the `tuple[WiredEntry, ...]` (no `config` import — a base-layer module) and is
**non-interactive and never-blocking**: it only classifies and reports, never
calls `input()`. Per entry, against settings *presence* only:
- a `kind=plugin` already decided (present in `settings.json`/`settings.local.json`,
  true or false) → **satisfied** (`already`), left as-is;
- a `kind=plugin` declared but absent → **acted** (`enabled`): `enable_plugin`
  writes `true`, then `install_default_plugins` best-effort materialises it;
- a `kind=skill` entry, a malformed `<plugin>@<marketplace>` target, or an
  install the CLI rejected → **needs-user** (`needs_user`), reported and never
  dropped — but never prompted here (the interactive `dummyindex context wire`
  command is the prompting surface) (`default_plugins.py:294-366`).

`WiredEntry.version` is recorded/surfaced only — settings.json has no installed
version, so the reconciler never synthesises a "stale" verdict. Materialisation
is best-effort: a missing `claude` CLI, or `DUMMYINDEX_SKIP_PLUGIN_INSTALL` set,
defers to Claude Code's next session; a CLI rejection is recorded, never raised
(`default_plugins.py:481-523`).

### Hooks wired

Init installs three managed Claude Code hooks under the `DUMMYINDEX_AUTO_REFRESH`
sentinel: **SessionStart** (drift report + session-memory block), **Stop**
(memory nudge + reconcile-gate), **PreCompact** (breadcrumb). Install is
idempotent, scrubs legacy `git post-commit` / `PostToolUse` entries, preserves
user-authored hooks, and surfaces an emit-only statusLine nudge — it never
auto-refreshes the backbone (`hooks.py:89-165,329-412`).

## Contracts

- `parse_install_args(args) -> tuple[str, Optional[Path], bool, bool, bool, bool]`
  — `(scope, project_dir, skill_only, no_onboarding, defaults, no_superpowers)`;
  `--help`/`-h` prints usage and `sys.exit(0)`; unknown flag → `sys.exit(2)`;
  legacy `--platform` skipped silently (`args.py:39-93`).
- `install(*, scope="user", project_dir=None, skill_only=False, no_onboarding=False, defaults=False, no_superpowers=False) -> None`
  (`install.py:20-216`).
- `uninstall(*, scope="user", project_dir=None) -> None` (`uninstall.py:12-86`).
- `_auto_init_project(project_root, *, no_superpowers=False) -> bool`
  (`install.py:219-300`).
- `_install_commands(base) -> list[str]` / `remove_commands(base) -> list[str]`
  (`common.py:49-78`); `_skill_src(name="skill.md") -> Path` (`common.py:45-46`).
- `resolve_enabled(*, cli_opt_out, config_value) -> bool` (`default_plugins.py:199-208`).
- `wire_default_plugins(wired, project_root, *, enabled=True, runner=None) -> PluginWireResult`
  (`default_plugins.py:294-366`) — takes the declared `tuple[WiredEntry, ...]`
  first; classify-and-report only, never prompts. Companion pure helper
  `classify_wired_entry(entry, *, is_present) -> WiredClass` is the single
  satisfied/acted/needs-user rule, shared with `status` and `wire`
  (`default_plugins.py:270-291`).
- `default_wired() -> tuple[WiredEntry, ...]` — `DEFAULT_PLUGINS` adapted to
  `WiredEntry`, the seed for `config.wired` (`default_plugins.py:155-162`).
- `install_default_plugins(project_root, *, enabled=True, runner=None) -> PluginInstallResult`
  (`default_plugins.py:481-523`); `Runner = Callable[[list[str], Path], RunResult]`
  via `default_runner` seam (`default_plugins.py:401-417`).
- `describe_wire_result(result) -> (info, warn)` / `describe_install_result(result) -> (info, warn)`
  (`default_plugins.py:94-112,332-352`).
- `hooks.install(project_root, *, scope="local") -> HookResult` /
  `hooks.uninstall(...)` / `hooks.status(...) -> HookStatus`
  (`hooks.py:329-412,457-523,529-542`).
- `__main__.main()` dispatches `install`/`uninstall` (`__main__.py:245-267`);
  `TOP_LEVEL_COMMANDS` is the command alphabet (`__main__.py:40-47`).

## Examples

```bash
dummyindex install                       # user scope; auto-init cwd if a git repo
dummyindex install --dir ./repo --defaults   # project init, non-interactive config
dummyindex install --skill-only          # skill only; no project init
dummyindex install --no-superpowers      # init but don't wire/install default plugins
dummyindex uninstall --scope project --dir ./repo
DUMMYINDEX_SKIP_PLUGIN_INSTALL=1 dummyindex install   # defer plugin materialisation
```
