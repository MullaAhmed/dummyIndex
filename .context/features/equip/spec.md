# Project equipment toolkit — spec

`confidence: INFERRED`

## Intent

Equip turns a repository's indexed context into a project-specific Claude Code
toolkit, keeps generated tools refreshable without overwriting user edits, and
provides a controlled path for declaring, installing, and tracking plugins or
vendored skills. It also supplies a narrow batteries-included default set while
keeping arbitrary third-party discovery behind the stricter dynamic trust gate.

## User-visible behavior

`dummyindex context equip` exposes apply, specialist, discovery, install,
verification, lifecycle, and evaluation verbs. The generated toolkit is recorded
in `.context/equipment.json`; generated agents and skills live under `.claude/`,
and native plugin decisions live in Claude settings. `EquipmentItem` records the
path, source, capabilities, grounding, version/hash ownership baseline, and plugin
origin fields, while `EquipmentManifest` serializes the ordered item ledger
(`dummyindex/context/domains/equip/models.py:81-159`,
`dummyindex/context/domains/equip/models.py:223-245`).

The default-plugin surface declares exactly three ordered reviewed targets:
`superpowers@claude-plugins-official`, pinned
`caveman@caveman`, and pinned `i-have-adhd@i-have-adhd`. Third-party records
carry immutable full-SHA refs plus reviewed surfaces and `runs_code` metadata;
the disclosure renderer names that provenance before callers mutate settings or
probe a runner (`dummyindex/context/default_plugins.py:118-223`). Declaration
and materialization are separate: `wire_default_plugins` writes pinned
marketplace declarations and effective `enabledPlugins` decisions, then
`install_default_plugins` filters the reviewed set through the declared wired
targets and effective project/local state before invoking Claude once per
eligible target (`dummyindex/context/default_plugins.py:448-530`,
`dummyindex/context/default_plugins.py:645-729`). An explicit `false` in project
or local settings is a tombstone; it is neither changed nor materialized
(`dummyindex/context/default_plugins.py:337-349`,
`dummyindex/context/default_plugins.py:682-697`).

Interactive `equip install <plugin>@<marketplace>` remains the arbitrary-source
path. It resolves an exact catalog candidate, requires `--yes` for every
untrusted source regardless of claimed inertness, requires a usage-playbook
decision, then either enables a native marketplace plugin or vendors a
collection skill (`dummyindex/cli/equip/install.py:62-215`,
`dummyindex/context/domains/equip/plugins/install_plan.py:36-53`). A vendored
skill resolves and records a commit SHA, rejects unsafe path names, and refuses
to overwrite user-owned content (`dummyindex/cli/equip/install.py:335-446`);
the native dynamic path still declares the marketplace without a ref and records
`origin_ref=None` (`dummyindex/cli/equip/install.py:158-209`,
`dummyindex/cli/equip/install.py:258-287`).

## Contracts

- `default_wired() -> tuple[WiredEntry, ...]` adapts the ordered built-in set to
  declarative config entries (`dummyindex/context/default_plugins.py:226-244`).
- `describe_default_plugin_trust() -> tuple[str, ...]` renders pinned source,
  reviewed surfaces, code-execution status, and the canonical one-run opt-out
  wording for each third-party default
  (`dummyindex/context/default_plugins.py:205-223`).
- `wire_default_plugins(wired: tuple[WiredEntry, ...], project_root: Path, *,
  enabled: bool = True, runner: Runner | None = None) -> PluginWireResult`
  declares reviewed marketplaces before enabling targets, preserves false
  tombstones, refuses a same-name/different-source built-in marketplace, and
  reports per-target results without raising
  (`dummyindex/context/default_plugins.py:357-389`,
  `dummyindex/context/default_plugins.py:448-530`).
- `install_default_plugins(project_root: Path, *, wired:
  tuple[WiredEntry, ...] | None = None, enabled: bool = True, runner: Runner |
  None = None) -> PluginInstallResult` materializes only selected,
  effectively-true reviewed defaults through a fixed-argv runner and reports
  installed, deferred, skipped, and error buckets
  (`dummyindex/context/default_plugins.py:565-599`,
  `dummyindex/context/default_plugins.py:645-729`).
- `add_marketplace(settings_path: Path, *, name: str, repo: str, ref: str |
  None = None) -> bool` and `enable_plugin(settings_path: Path, *, plugin: str,
  marketplace: str) -> bool` are atomic settings primitives. The former is an
  upsert primitive; callers that require identity-conflict refusal must check
  before calling it (`dummyindex/context/claude_plugins.py:105-124`,
  `dummyindex/context/claude_plugins.py:142-155`).
- `build_install_plan(candidates: tuple[Candidate, ...]) -> InstallPlan`
  selects native versus vendor installation and gates every untrusted candidate
  (`dummyindex/context/domains/equip/plugins/install_plan.py:36-53`).
- `analyze_blast_radius(entry: PluginEntry, *, trusted: bool) -> BlastRadius`
  reports declared code surfaces and source tier; those attacker-controlled
  declarations inform disclosure but never waive the untrusted-source gate
  (`dummyindex/context/domains/equip/plugins/blast_radius.py:23-37`,
  `dummyindex/context/domains/equip/plugins/install_plan.py:36-48`).
- `resolve_ref(repo: str, *, runner: Runner = default_runner) -> str | None`
  resolves collection HEAD to a commit SHA, and `list_skills(repo: str, *, ref:
  str | None = None, runner: Runner = default_runner) -> tuple[SkillRef, ...]`
  enumerates safe, sorted collection members at that ref
  (`dummyindex/context/domains/equip/plugins/sources.py:149-166`,
  `dummyindex/context/domains/equip/plugins/sources.py:194-226`).
- `run_install(rest: list[str]) -> int` is the wire-only CLI boundary for exact
  dynamic installs. It returns `2` for usage errors, `1` for resolution,
  approval, transport, or write failures, and `0` after a successful native or
  vendored install (`dummyindex/cli/equip/install.py:62-215`).

## Examples

For a fresh Claude-enabled project, the caller first prints
`describe_default_plugin_trust()`, reads `default_wired()`, and passes that set
to `wire_default_plugins`. The reconciler checks project and local settings,
declares the two pinned third-party marketplaces only when their names are
unclaimed or identical, enables missing targets, and leaves any explicit false
target untouched (`dummyindex/context/default_plugins.py:337-389`,
`dummyindex/context/default_plugins.py:448-530`). One subsequent
`install_default_plugins(..., wired=wired)` pass defers all eligible targets when
Claude is unavailable or attempts each independently when it is available
(`dummyindex/context/default_plugins.py:670-729`).

For `equip install tool@marketplace`, `run_install` resolves the exact candidate
and calls `build_install_plan`; an untrusted source without `--yes` stops before
settings or manifest mutation (`dummyindex/cli/equip/install.py:89-148`). If the
candidate is a collection, equip resolves HEAD to a SHA, fetches `SKILL.md` at
that ref, writes only through the never-clobber guard, and records the pinned
vendored item (`dummyindex/cli/equip/install.py:335-446`).
