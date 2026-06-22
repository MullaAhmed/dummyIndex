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
registers the skill in `~/.claude/CLAUDE.md` only if not already present
(`install.py:157-181`). Stale prior-version markdowns and `*.tmpl` twins are
purged on upgrade (`install.py:89-90,135-142`).

Auto-init runs when the resolved candidate is a git repo (`.git/` dir or
submodule/worktree `.git` file) and `--skill-only` is not set
(`install.py:187-195`). On a fresh/deterministic-only index it full-builds
`.context/`; on an *enriched* curated index it takes the non-destructive
refresh path (refresh deterministic artefacts only, never re-cluster), printing
a "curated index preserved" line and a desync warning if INDEX.json disagrees
with disk (`install.py:248-277`). Both paths then bootstrap the project
CLAUDE.md, install hooks, and wire default plugins. `--defaults` /
`--no-onboarding` additionally writes a default `.context/config.json`
(never clobbering an existing one) (`install.py:194-195,326-350`).

### Uninstall

`dummyindex uninstall` removes the main skill, its companions and version stamp,
every sibling skill dir, and the bundled commands from the chosen scope, then
prunes now-empty parents; prints the first removed path or `nothing to remove`
(`uninstall.py:12-86`).

### Default plugins (enable + install)

At init, `_wire_default_plugins_step` resolves whether to wire defaults
(CLI `--no-superpowers` > persisted `config.wire_superpowers` > on), then
*declares* each `DEFAULT_PLUGINS` entry (`superpowers@claude-plugins-official`)
into the project `.claude/settings.json` and *materialises* it via the `claude`
CLI (`install.py:353-385`, `default_plugins.py:60-62,82-91`). Declaration is
idempotent — a target the repo already decided (present in `settings.json` or
`settings.local.json`, true or false) is left as-is (`default_plugins.py:115-172`).
Materialisation is best-effort: a missing `claude` CLI, or `DUMMYINDEX_SKIP_PLUGIN_INSTALL`
set, defers to Claude Code's next session; a CLI rejection is recorded, never
raised (`default_plugins.py:287-329`).

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
- `resolve_enabled(*, cli_opt_out, config_value) -> bool` (`default_plugins.py:82-91`).
- `wire_default_plugins(project_root, *, enabled=True) -> PluginWireResult`
  (`default_plugins.py:136-172`).
- `install_default_plugins(project_root, *, enabled=True, runner=None) -> PluginInstallResult`
  (`default_plugins.py:287-329`); `Runner = Callable[[list[str], Path], RunResult]`
  via `default_runner` seam (`default_plugins.py:200-223`).
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
