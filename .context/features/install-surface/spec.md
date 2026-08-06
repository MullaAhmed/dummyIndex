# Install surface — spec

`confidence: INFERRED`

## Intent

Put dummyindex's skill family where each host looks for it, and — when the
target is a git repository — leave that repository ready to work in without
destroying anything the user owns. One command has to serve three different
audiences: a first-time user who wants batteries included, an upgrader whose
repo already carries a hand-curated index and hand-edited settings, and a
machine in CI that must not touch the network or prompt for anything. The
surface's whole job is deciding what it is allowed to write. It writes the
skill tree, the host guidance block, a managed set of session hooks, a
reviewed default-plugin declaration, and nothing else; every pre-existing
value — a curated feature taxonomy, a user's own hook, a user's own status
line, a plugin the user explicitly disabled — is evidence of intent and is
preserved. Failures downstream of the skill copy degrade to a printed warning
rather than aborting, because a partially wired repo is more useful than an
unwritten one.

## User-visible behavior

### `dummyindex install`

Flags, all parsed in `dummyindex/installer/args.py:84-217`:

| flag | effect |
| --- | --- |
| `--platform claude\|agents\|both` | target host, default `both`; `codex` accepted as a deprecated alias that warns once on stderr |
| `--scope user\|project` | where the skill family lands, default `user` |
| `--dir PATH` | project dir to install into / auto-init, default cwd |
| `--skill-only` | install the skill, skip project auto-init |
| `--link` / `--copy` | link-mode tri-state; mutually exclusive (exit 2) |
| `--no-onboarding`, `--defaults` | non-interactive: write `.context/config.json` defaults |
| `--no-default-plugins`, `--no-superpowers` | one-run default-plugin opt-out |
| `--dedupe user\|project` | remove a duplicate skill-family copy at that scope |
| `--force-downgrade` | let repair rewrite a copy stamped newer than this package |
| `-h`, `--help` | print usage and exit 0, before any filesystem work |

`-h`/`--help` is handled first so probing the command is never running it
(`dummyindex/installer/args.py:87-92`). Unknown flags, a missing flag value, or
an out-of-range `--scope`/`--platform`/`--dedupe` exit 2. `--link --copy` and
`--link --platform agents` also exit 2 (`args.py:190-202`). `--platform` is
normalized to the internal `claude|codex|both` token before dispatch by
`normalize_platform_arg` (`dummyindex/installer/common.py:157-180`).

A run does, in this fixed order (`dummyindex/installer/install/orchestrate.py:50-531`):

1. Validate scope/dedupe/platform; refuse to install through a managed
   directory symlink, per host, naming the `--platform` flag that skips the
   offending side (`orchestrate.py:165-250`).
2. Plan a repair pass scoped to this invocation's platforms and scope
   (`orchestrate.py:253-260`).
3. Direct-write only families that are absent or exist but are unprovable
   (`orchestrate.py:269-344`); every provable one defers to `execute_repairs`
   so nothing is written twice.
4. `execute_repairs` + print the plan (`orchestrate.py:345-347`), then backfill
   `.dummyindex_version` onto sibling real dirs (`orchestrate.py:359-362`).
5. Dispatch link mode for the Claude side (`orchestrate.py:371-442`).
6. `--dedupe` removal, if asked (`orchestrate.py:444-456`).
7. Claude slash-command aliases (`orchestrate.py:458-466`) and user-scope host
   registration in `~/.claude/CLAUDE.md` / the global Codex instruction file
   (`orchestrate.py:468-471`, `534-558`).
8. Auto-init the resolved project dir when it is a git repo and `--skill-only`
   was not passed (`orchestrate.py:473-501`).
9. Print the closing "Done. Open … and run:" block, including the
   no-git-repo explanation when init was skipped (`orchestrate.py:503-531`).

### Auto-init

`_auto_init_project` (`dummyindex/installer/install/project_init.py:28-156`)
branches on whether `.context/` is already council-enriched. Enriched: refresh
the deterministic artefacts only and print `curated index preserved — refreshed
N deterministic artefact(s) (no re-cluster)`, plus an index-desync warning when
`features/INDEX.json` disagrees with the dirs on disk (`project_init.py:75-94`).
Otherwise: full `build_all`, printing file/symbol counts (`project_init.py:120-135`).
Both paths then, for Claude-selected platforms only, install the managed hooks,
wire default plugins, and refresh equipment (`project_init.py:110-117`, `148-155`).
Codex-selected platforms get the managed `AGENTS.md` block and no Claude state.

Equipment refresh is a silent no-op unless `.context/equipment.json` exists; when
it does, PRISTINE generated tools whose fresh render differs are re-rendered and
re-baselined, USER_MODIFIED ones are skipped forever
(`project_init.py:159-200`, delegating to
`dummyindex/context/domains/equip/lifecycle/status.py:221-313`).

### Managed hooks written into `.claude/settings.json`

`install(project_root, scope=...)` (`dummyindex/context/hooks.py:486-571`)
writes **five events, ten commands**, every one carrying the `_MANAGED_COMMENT`
header that embeds the `DUMMYINDEX_AUTO_REFRESH` sentinel
(`hooks.py:64-73`):

- **UserPromptSubmit** — 1 entry, no matcher, 2 commands (`hooks.py:120-145`):
  1. `printf` of a pre-built, shell-quoted JSON payload whose
     `additionalContext` is `ALWAYS_ON_TURN_REMINDER` — the compact per-turn
     recurrence of the output + skill-routing contracts
     (`hooks.py:110-131`, `dummyindex/context/output/bootstrap.py:78-92`).
     This command deliberately has **no** `command -v dummyindex` self-gate, so
     it still fires on an alternate Claude profile with no CLI on PATH.
  2. `dummyindex context memory prompt-context --root "$CLAUDE_PROJECT_DIR"`
     (`hooks.py:132-143`) — gated, `2>/dev/null || true`, stdout deliberately
     *not* redirected because it carries the second UserPromptSubmit JSON. It
     reads the hook's own stdin, extracts skill directives from the prompt, and
     emits bounded correction feedback from the local feedback cache; it prints
     nothing when there is no feedback and swallows every exception
     (`dummyindex/cli/memory.py:96-128`).
- **SessionStart** (matcher `*`) — 1 entry, 4 commands (`hooks.py:147-198`):
  `context plan-update`, `context memory session-start`, `context gc signal`
  (all three under the degraded-mode gate that echoes
  `dummyindex CLI not found on PATH — drift reporting disabled` once,
  `hooks.py:95-99`), and `context memory mine` under the silent gate with
  `>/dev/null 2>&1` — historical mining is SessionStart-only, writes only the
  bounded gitignored feedback cache, and is never allowed to speak
  (`hooks.py:185-196`, `dummyindex/cli/memory.py:87-94`).
- **Stop** (matcher `*`) — 2 commands: `context memory nudge` and
  `context reconcile-gate`. stderr muted, stdout **not** — the gate's
  `decision: block` JSON must reach Claude Code (`hooks.py:200-227`).
- **PreCompact** (matcher `*`) — 1 command: `context memory breadcrumb`, fully
  silent (`hooks.py:229-243`).
- **PreToolUse** (matcher `Write` only) — 1 command: `context guard-doc-write`,
  stdout preserved for its `permissionDecision: deny` JSON
  (`hooks.py:245-267`). Edit/MultiEdit are deliberately unmatched: they require
  the target to pre-exist, so they cannot create a fresh doc leak.

Install is idempotent and reports honestly: a body rewritten in place lands in
`HookResult.refreshed`, a byte-identical one in `skipped`, decided by a
before/after `read_bytes()` comparison rather than by comparing against the
canonical body — which would mis-report forever once a user co-locates their own
hook in the managed entry (`hooks.py:532-551`). Hooks the user wrote themselves
(no sentinel) are never touched. Legacy `PostToolUse` entries and the legacy
`git post-commit` hook are scrubbed on a local install (`hooks.py:509-527`,
`574-611`).

`scope="global"` writes `~/.claude/settings.json` with every command wrapped by
`_guard_body` (`hooks.py:379-409`): the `defer-check` guard is inserted right
after the self-gate, and for the ungated static UserPromptSubmit command a
silent gate plus the guard are inserted after the managed comment — so a repo's
own `--local` install always overrides the global one.

The `.context/` freshness badge is wired, not offered: `install_statusline`
writes `{"type": "command", "command": "dummyindex context statusline"}` only
when **neither** local nor global settings already define a truthy `statusLine`,
and returns an add-it-by-hand nudge instead of clobbering an unparseable
settings file (`hooks.py:329-376`).

### Reviewed default plugins

Three, ordered and validated at import time — duplicate targets and a default
with no reviewed surfaces raise (`dummyindex/context/default_plugins.py:148-193`):

- `superpowers@claude-plugins-official` — skills only, `runs_code=False`.
- `caveman@caveman` (`JuliusBrussee/caveman`) — skills, commands, SessionStart
  and UserPromptSubmit Node command hooks, `runs_code=True`.
- `i-have-adhd@i-have-adhd` (`ayghri/i-have-adhd`) — one skill plus an *opt-in*
  SessionStart shell hook, `runs_code=True`.

There is no commit pin: Claude Code materialises marketplaces with
`git clone --branch <ref>`, which takes a branch or tag but never a SHA, so
third-party defaults track the upstream default branch and the docstring says so
(`default_plugins.py:1-18`). Before any config read, settings write, or CLI
probe, the installer prints one `default plugin trust ->` line per third-party
source naming repo, reviewed surfaces, code-execution status, and the
`--no-default-plugins` escape (`default_plugins.py:196-215`,
`project_init.py:321-324`).

Declaration and materialisation are separate passes. `wire_default_plugins`
only classifies and writes settings — a `kind=skill` entry or a malformed
`<plugin>@<marketplace>` target is reported needs-user, an already-decided
plugin is satisfied, and a `false` in project *or* local settings is a tombstone
that is never re-enabled (`default_plugins.py:472-572`).
`install_default_plugins` then probes the `claude` CLI once and shells out per
eligible target; an unavailable CLI, or `DUMMYINDEX_SKIP_PLUGIN_INSTALL` set,
defers every target instead of failing (`default_plugins.py:676-761`,
`117`). Neither raises — a malformed or unwritable `settings.json` cannot fail
an otherwise-successful init.

`--no-default-plugins` is an early return in `_wire_default_plugins_step`
(`project_init.py:300-303`): an opted-out run performs no trust disclosure, no
config migration, no settings I/O, and no runner probe.

### Link mode

A flagless install is universal and linked: one real tree under
`.agents/skills/<family>`, with the Claude side pointed at it by one relative
symlink per family. The eight families are enumerated from `_SIBLING_SKILLS`
(main + 7), never a `dummyindex*` glob — a glob would wrongly capture the
equip-generated `dummyindex-verify` skill
(`dummyindex/installer/link/families.py:16-24`). AUTO links when a
capability-and-resolution pre-probe succeeds and falls back to copy otherwise;
LINK is strict and exits 1; COPY writes the old duplicated trees and never
converts a linked layout back (`dummyindex/installer/link/orchestrate.py:130-220`).
Classification is a closed `FamilyLinkState` alphabet that fails closed to
FOREIGN on any `OSError`/`RuntimeError`
(`dummyindex/installer/link/classify.py:199-336`,
`dummyindex/installer/link/models.py:17-47`), and replacement uses a
temp-link-first rename-aside dance that re-verifies ownership before deleting
(`dummyindex/installer/link/create.py:251-317`).

### `dummyindex uninstall`

`--platform`, `--scope`, `--dir`, `-h/--help` only; install-only flags are
rejected rather than silently accepted (`args.py:220-287`). `--platform`
defaults to `both`, matching install, so a flagless uninstall removes what a
flagless install wrote (`dummyindex/installer/uninstall.py:22-36`). It removes
the skill family and Claude slash-command aliases, sweeps the now-dangling owned
family links, and leaves project guidance, hooks, and plugin state alone.
Hook removal is a separate call: `hooks.uninstall` scrubs sentinel-bearing
entries under both current and legacy events and preserves a settings file it
cannot parse (`hooks.py:617-688`).

## Contracts

- `parse_install_args(args: list[str]) -> tuple[str, Path | None, bool, bool, bool, bool, str, str | None, bool, LinkMode]`
  — **ten** values: `(scope, project_dir, skill_only, no_onboarding, defaults,
  no_default_plugins, platform, dedupe, force_downgrade, link_mode)`. Help
  exits 0; every invalid input exits 2 (`dummyindex/installer/args.py:84-217`).
  `dummyindex/__main__.py:292-316` unpacks exactly these ten and forwards them
  by keyword.
- `parse_uninstall_args(args: list[str]) -> tuple[str, Path | None, str]`
  (`dummyindex/installer/args.py:220-287`).
- `normalize_platform_arg(value: str) -> str` — `agents`→`"codex"`,
  `claude`/`both` unchanged, `codex` accepted with a once-per-process stderr
  deprecation notice, anything else `ValueError`
  (`dummyindex/installer/common.py:157-180`).
- `install(*, scope="user", project_dir=None, skill_only=False, no_onboarding=False, defaults=False, no_default_plugins=False, no_superpowers=False, platform="both", dedupe=None, force_downgrade=False, link_mode=LinkMode.AUTO) -> None`
  (`dummyindex/installer/install/orchestrate.py:50-531`). `platform` here is the
  **internal** vocabulary: it goes straight to `platforms_for()` without
  normalization, so a direct API call with `"agents"` exits 1
  (`orchestrate.py:131-135`, `common.py:141-149`). `uninstall()` is asymmetric —
  it normalizes first and therefore accepts `"agents"`
  (`uninstall.py:43-47`).
- `render_skill(text: str, *, platform: str) -> str` — substitutes
  `__VERSION__`, strips whole lines matching the `test-anchor:<id>:begin|end`
  comment shape from **every** rendered copy, and prepends the portable-host
  preamble for `codex` after the YAML frontmatter
  (`dummyindex/installer/common.py:197-223`; the regex is line-anchored and
  narrow by design, `common.py:36-45`).
- `is_owned_copy(path: Path) -> bool` — the ownership predicate every rewrite,
  duplicate report, and dedupe gates on: a `.dummyindex_version` stamp or the
  legacy `## Codex host compatibility` heading, never a bare dir-name match
  (`dummyindex/installer/common.py:336-353`).
- `plan_repairs(*, project_root, user_home, target_scope, selected_platforms, skill_only=False, force_downgrade=False, package_version=PACKAGE_VERSION) -> RepairPlan`
  / `execute_repairs(plan) -> RepairExecutionResult` / `dedupe(scope, *, project_root, user_home, selected_platforms=None) -> DedupeResult`
  (`dummyindex/installer/repair.py:331-446`, `447-492`, `493-604`), over the one
  four-root scanner `scan_installed_copies` (`repair.py:185-214`).
- `run_link_install(scope_root, *, link_mode=LinkMode.AUTO, symlink_fn=os.symlink, allowed_symlinks=frozenset()) -> LinkInstallResult`
  — call exactly once per invocation, after `.agents/skills/**` is real and
  `execute_repairs` has landed (`dummyindex/installer/link/orchestrate.py:130-220`).
- `hooks.install(project_root: Path, *, scope: str = "local") -> HookResult` and
  `hooks.uninstall(...) -> HookResult`; `HookResult` carries
  `installed / skipped / removed / errors / refreshed / nudges`
  (`dummyindex/context/hooks.py:447-466`, `486-571`, `617-688`).
- `hooks.status(project_root: Path, *, scope: str = "local") -> HookStatus` —
  five booleans, and `all_installed` requires **all five**:
  `claude_user_prompt_submit`, `claude_session_start`, `claude_stop`,
  `claude_pre_compact`, `claude_pre_tool_use`
  (`dummyindex/context/hooks.py:428-444`, `694-713`).
- `hooks.install_statusline(project_root: Path, *, scope: str = "local") -> str | None`
  — returns the wired command, the unwritable nudge, or `None` for "already
  configured, untouched" (`dummyindex/context/hooks.py:346-376`).
- `hooks.local_install_present(project_root: Path) -> bool` — backs the global
  hooks' `defer-check` guard (`dummyindex/context/hooks.py:420-425`).
- `wire_default_plugins(wired, project_root, *, enabled=True, runner=None) -> PluginWireResult`
  and `install_default_plugins(project_root, *, wired=None, enabled=True, runner=None) -> PluginInstallResult`
  (`dummyindex/context/default_plugins.py:472-572`, `676-761`);
  `default_wired() -> tuple[WiredEntry, ...]`
  (`default_plugins.py:227-235`); `resolve_enabled(*, cli_opt_out: bool, config_value: bool | None) -> bool`
  (`default_plugins.py:272-282`).
- `reconcile_default_plugins(context_dir: Path, *, platform: str) -> bool`,
  `reconcile_wired_with_equipment(context_dir: Path) -> bool`,
  `migrate_config_in_place(context_dir: Path) -> bool`,
  `default_config(*, platform: str = "claude") -> Config`
  (`dummyindex/context/domains/config.py:622-661`, `567-621`, `540-566`, `424-479`).

## Examples

Happy path — `dummyindex install` in a fresh git repo, user scope, both hosts:

```
$ dummyindex install
```

1. `parse_install_args([])` → `("user", None, False, False, False, False,
   "both", None, False, LinkMode.AUTO)` (`args.py:84-217`); `__main__` forwards
   all ten (`__main__.py:292-316`).
2. `platforms_for("both")` → `("claude", "codex")`; `base = Path.home()`;
   `project_root = cwd.resolve()`; the user-scope Claude allowlist is
   `{~/.claude, ~/.claude/skills}` (`orchestrate.py:132-164`).
3. Per host, `verify_family_links` + `_symlinked_skill_install_directory` find
   no unsafe symlink, so nothing is refused (`orchestrate.py:165-250`).
4. `plan_repairs` finds no existing stamped copy → empty plan. Every Claude
   family classifies MISSING and `_all_claude_families_missing` is true, so the
   Claude write is *deferred*; the `.agents` tree is written for real by
   `_install_skill_family` (`orchestrate.py:253-344`).
5. `execute_repairs` is a no-op; `_backfill_sibling_stamps` runs per host.
6. `run_link_install` probes symlink capability, succeeds, and
   `create_family_links` fills all 8 Claude slots with
   `../../.agents/skills/<family>` links; the deferred real write never happens
   (`orchestrate.py:371-442`).
7. `_install_commands` copies the slash-command aliases; `~/.claude/CLAUDE.md`
   gets the skill registration; the global Codex instruction file gets its
   managed pointer (`orchestrate.py:458-471`, `534-558`).
8. cwd is a git repo and `--skill-only` was absent → `_auto_init_project`:
   `.context/` is absent, so `build_all` runs and prints
   `built (N files, M indexed, K symbols)`; `CLAUDE.md (proj)` and the Codex
   block are written (`project_init.py:120-146`).
9. `_install_project_hooks` → `hooks.install(project_root)` writes the five
   events / ten commands and, since neither settings file defines one, the
   `statusLine`. Printed as
   `hooks -> installed: claude/UserPromptSubmit, claude/SessionStart,
   claude/Stop, claude/PreCompact, claude/PreToolUse, claude/statusLine`
   (`project_init.py:203-223`, `hooks.py:486-571`).
10. `_wire_default_plugins_step` prints two trust lines, reconciles
    `.context/config.json`, declares the three defaults in
    `.claude/settings.json`, then materialises them via the `claude` CLI —
    or defers all three when it is absent (`project_init.py:288-356`).
11. `equipment` is silent (no `.context/equipment.json`), and the run closes
    with `Done. Open Claude Code + Codex in <cwd> and run:` followed by both
    invocation lines (`orchestrate.py:503-523`).

Re-running the same command is byte-stable: repair proves the copies current,
`install_hook_entry` finds identical bodies so all five events land in
`HookResult.skipped` (printed as `hooks -> already current (5)`), the
`statusLine` is left alone, and every default plugin is already decided so it
lands in `already` (`hooks.py:532-563`, `default_plugins.py:472-572`).

Verified against `tests/context/test_hooks.py:77-135` (per-prompt contract
shape), `:1088-1116` (the two feedback commands are independent, bounded, and
Stop is unchanged at two commands), `:1133-1168` (the dynamic prompt command
runs under `/bin/sh`, emits valid UserPromptSubmit JSON, and prints nothing on
malformed stdin), and `:1191-1204` (`status` true for all five events).
