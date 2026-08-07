# Project equipment toolkit — spec

`confidence: INFERRED`

## Intent

Equip is the engine that turns an indexed repository into a working agent
toolkit. A caller who has already built the context index runs one command and
gets project-tuned agents and skills written into the host's config directory,
the session hooks that keep the index and the project's behavior contract live
in every session, and a ledger recording exactly which of those artifacts the
tool owns. The hard problem it solves is ownership over time: generated files
must be refreshable across upgrades, yet a human who edits one must never have
that edit silently overwritten. Everything else — the reviewed default-plugin
base layer, the interactive plugin installer, the evaluation stage — is built on
the same ownership rule: fingerprint what we wrote, compare before touching it,
and refuse rather than clobber.

## User-visible behavior

**Toolkit verbs.** `dummyindex context equip <verb>` dispatches thirteen verbs
(`dummyindex/cli/equip/dispatch.py:9-21`). A bare `equip` is a usage error with
rc 2 — a help probe must never mutate the repo — and the sole verbless carve-out
is the read-only `equip --dry-run` preview
(`dummyindex/cli/equip/dispatch.py:102-144`,
`dummyindex/cli/equip/dispatch.py:147-153`).

Every `equip apply` writes the four core tools (`{label}-implementer`,
`{label}-tester`, `{proj}-reviewer` agents and the `{proj}-verify` skill) **plus
one specialist per shipped template** — db / security / performance / docs /
search. Specialists are abilities, not opt-ins: no `add-specialist` ask and no
proposal capability is required to get one
(`dummyindex/context/domains/equip/generate/catalog.py:62-72`,
`dummyindex/context/domains/equip/generate/catalog.py:114-144`).
`add-specialist CAPABILITY` and `apply --specialist CAPABILITY` force the
*order* rather than gate existence: a forced or manifest-carried capability
leads the specialist list so an already-applied specialist keeps its
hash-baselined identity across re-applies
(`dummyindex/cli/equip/dispatch.py:311-313`). A capability no template backs
(frontend) still falls through to manifest-only adoption
(`dummyindex/cli/equip/dispatch.py:242-248`).

`apply` refuses to write into a repo with no `.context/` directory and points at
`dummyindex ingest`; `--dry-run` is allowed through because it writes nothing
(`dummyindex/cli/equip/dispatch.py:266-272`). Per-item output lines are the
ownership decision made visible: `write`, `keep … (user-modified, preserved)`,
`keep … (evolved vN, kept)`, `skip … (existing user file, not ours)`, and
`keep … (record carried forward)`
(`dummyindex/cli/equip/dispatch.py:421-533`).

**The ledger.** `.context/equipment.json` is schema v4
(`dummyindex/context/domains/equip/constants.py:14`). Each `EquipmentItem`
records kind, name, repo-relative path, source, capabilities, grounding docs,
canary invariants, version/`origin_hash` ownership baseline, and the
marketplace/repo/ref/mechanism origin fields
(`dummyindex/context/domains/equip/models.py:81-159`). The apply write is a
**merge**: any prior record this run does not re-derive — marketplace, vendored,
adopted, or a generated record under a now-stale name — is carried forward
verbatim (`dummyindex/cli/equip/dispatch.py:513-533`).

**Lifecycle verbs.** `status` classifies each generated item against its
baseline and additionally reports items with no usage playbook and tools with no
recorded eval result (`dummyindex/cli/equip/verbs.py:74-145`). `refresh`
re-renders only pristine items and surfaces a distinct `⚠ INVARIANT_BROKEN`
alarm section for tools whose edit dropped a load-bearing convention
(`dummyindex/cli/equip/verbs.py:39-68`). `reset NAME` restores one item,
`remove NAME` drops one record (refusing a file-backed item without
`--delete-file`), `uninstall` deletes pristine files plus our hook entries, and
`patch --item NAME --from-file F` applies a JSON `{"old","new"}` edit and bumps
the version (`dummyindex/cli/equip/verbs.py:175-348`).

**Format hook.** When stack detection found a formatter, apply wires exactly one
`PostToolUse` hook matching `Write|Edit`, keyed by `DUMMYINDEX_EQUIP:<event>`,
whose body exits cleanly if the formatter binary is absent and swallows format
failures so a bad format never blocks an edit
(`dummyindex/context/domains/equip/generate/catalog.py:147-178`,
`dummyindex/context/domains/equip/wiring/hooks.py:31-55`). Malformed
`settings.json` degrades to a warning; the files are still written
(`dummyindex/cli/equip/dispatch.py:500-510`).

**Managed session hooks.** `dummyindex context hooks install|uninstall|status|
defer-check [--global]` manages **five** Claude Code events under the legacy
`DUMMYINDEX_AUTO_REFRESH` sentinel: `UserPromptSubmit`, `SessionStart`, `Stop`,
`PreCompact`, and `PreToolUse` (matcher `Write`)
(`dummyindex/context/hooks.py:270-276`, `dummyindex/cli/hooks.py:10-18`).
`UserPromptSubmit` is the current addition: two independent commands, the first
of which `printf`s a pre-serialized, shell-quoted JSON payload carrying
`ALWAYS_ON_TURN_REMINDER` as `additionalContext` with `suppressOutput: true`, and
the second of which shells out to `dummyindex context memory prompt-context`
(`dummyindex/context/hooks.py:105-145`). The first command deliberately carries
**no** `command -v dummyindex` self-gate so the static behavior contract still
fires under an alternate Claude profile that can read project settings but has
no `dummyindex` on PATH (`dummyindex/context/hooks.py:379-409`). Install also
wires the freshness `statusLine` write-if-absent across both scopes, and reports
an advisory nudge when the settings file is unparseable rather than clobbering
it (`dummyindex/context/hooks.py:346-376`, `dummyindex/context/hooks.py:553-562`).
Install classifies each event as installed / refreshed (body rewritten in place)
/ skipped by comparing the settings file bytes before and after, and scrubs the
retired `git post-commit` and `PostToolUse` entries on upgrade
(`dummyindex/context/hooks.py:506-551`, `dummyindex/context/hooks.py:574-611`).

**Default plugins.** The reviewed base layer declares exactly three ordered
targets: `superpowers@claude-plugins-official`, `caveman@caveman`, and
`i-have-adhd@i-have-adhd`. None is pinned — Claude Code materializes marketplaces
with `git clone --branch <ref>`, which accepts a branch or tag but never a commit
SHA, so third-party records track the upstream's latest default branch and a pin
is not expressible (`dummyindex/context/default_plugins.py:1-18`,
`dummyindex/context/default_plugins.py:165-193`). `i-have-adhd` now declares
`surfaces=("skill", "opt-in SessionStart shell command hook")` and
`runs_code=True`; both third-party defaults therefore disclose code execution
(`dummyindex/context/default_plugins.py:185-191`). Disclosure lines name repo,
"tracks latest", reviewed surfaces, code-execution status, and the one-run opt-out
`--no-default-plugins` (`dummyindex/context/default_plugins.py:196-214`;
`--no-superpowers` is its compatibility alias, `dummyindex/installer/args.py:42-43`).

Declaration and materialization are separate operations. `wire_default_plugins`
declares marketplaces and writes `enabledPlugins` decisions;
`install_default_plugins` filters the reviewed set through the declared wired
targets and effective project/local state before invoking the `claude` CLI once
per eligible target (`dummyindex/context/default_plugins.py:472-554`,
`dummyindex/context/default_plugins.py:676-760`). An explicit `false` in project
or local settings is a tombstone — neither changed nor materialized
(`dummyindex/context/default_plugins.py:328-340`,
`dummyindex/context/default_plugins.py:526-528`). A same-name marketplace whose
source differs is a conflict and is left unchanged, with one exception: a
declaration that is *exactly* a dummyindex ≤ 0.33.x full-SHA pin of the same
reviewed repo is healed to the unpinned shape, because that stale pin fails
Claude Code's clone at every session start
(`dummyindex/context/default_plugins.py:353-409`).

**Interactive install.** `equip install <plugin>@<marketplace> [--yes]
[--scope project|local|user]` is the arbitrary-source path. It resolves an exact
catalog candidate over the whole discovery universe (never through query
scoring), refuses an ambiguous cross-repo target, requires `--yes` for every
untrusted source regardless of claimed inertness unless the exact target is
already enabled in this repo, requires a usage-playbook decision
(`--usage-doc PATH` or `--skip-usage-doc`), then either natively enables the
plugin or vendors a collection skill
(`dummyindex/cli/equip/install.py:62-215`,
`dummyindex/cli/equip/install.py:492-534`). A vendored skill resolves and records
a commit SHA, rejects unsafe path names, refuses to overwrite a locally edited
vendored copy or a foreign user file, and fails closed when the manifest cannot
be read (`dummyindex/cli/equip/install.py:335-446`). The native path declares the
marketplace without a ref and records `origin_ref=None`
(`dummyindex/cli/equip/install.py:171-181`,
`dummyindex/cli/equip/install.py:258-287`).

## Contracts

**Toolkit generation**

- `build_catalog(*, profile: StackProfile, conventions: tuple[str, ...],
  preflight: PreflightReport, proj: str, proposal_capabilities: tuple[str, ...] = (),
  forced_specialist_capabilities: tuple[str, ...] = ()) -> CatalogDecision` —
  the pure policy core; decides generate / adopt / hooks with no I/O
  (`dummyindex/context/domains/equip/generate/catalog.py:75-111`).
- `_all_templated_capabilities(forced: tuple[str, ...]) -> tuple[str, ...]` —
  forced capabilities followed by every template-backed capability, deduplicated;
  this is why every specialist is generated on every pass
  (`dummyindex/context/domains/equip/generate/catalog.py:62-72`).
- `wire_hooks(settings_path: Path, hooks: tuple[HookSpec, ...]) -> tuple[str, ...]`
  — installs one settings entry per `HookSpec` under `EQUIP_SENTINEL:<event>`,
  scrubbing the legacy unsuffixed sentinel first; raises `MalformedSettingsError`
  rather than clobbering (`dummyindex/context/domains/equip/wiring/hooks.py:31-55`).
- `EquipmentItem` / `EquipmentManifest` — the frozen ledger records and their
  hand-written `to_dict`/`from_dict` boundary; `invariants` is omitted when empty
  so v3 manifests stay byte-identical
  (`dummyindex/context/domains/equip/models.py:81-159`,
  `dummyindex/context/domains/equip/models.py:223-245`).
- `content_hash(text: str) -> str` — `"sha256:<hexdigest>"` over the rendered
  bytes; the ownership authority for the whole lifecycle
  (`dummyindex/context/domains/equip/lifecycle/hashing.py:17-19`).

**Managed hooks**

- `install(project_root: Path, *, scope: str = "local") -> HookResult` — installs
  the five events plus the statusLine, scrubs legacy entries, and reports
  `installed` / `refreshed` / `skipped` / `removed` / `errors` / `nudges`
  (`dummyindex/context/hooks.py:486-571`, `dummyindex/context/hooks.py:447-466`).
- `uninstall(project_root: Path, *, scope: str = "local") -> HookResult` and
  `status(project_root: Path, *, scope: str = "local") -> HookStatus` — removal
  covers current *and* legacy events; `HookStatus.all_installed` requires all five
  (`dummyindex/context/hooks.py:617-688`, `dummyindex/context/hooks.py:428-444`,
  `dummyindex/context/hooks.py:694-713`).
- `install_statusline(project_root: Path, *, scope: str = "local") -> str | None`
  — write-if-absent across both scopes; returns the wired command, the unwritable
  nudge, or `None` (`dummyindex/context/hooks.py:346-376`).
- `local_install_present(project_root: Path) -> bool` — backs the `defer-check`
  exit-code probe that lets a repo-local install suppress the global one
  (`dummyindex/context/hooks.py:420-425`, `dummyindex/context/hooks.py:287-290`).
- `write_text_atomic(path: Path, text: str) -> None` and
  `normalize_eof_newline(path: Path) -> bool` now both route through
  `_replace_bytes`, which allocates a **unique** `NamedTemporaryFile` sibling
  because hooks from two Claude profiles can update the same repo-local cache
  concurrently; the write stays byte-faithful so equip's hash baselines hold
  (`dummyindex/context/domains/atomic_io.py:13-34`,
  `dummyindex/context/domains/atomic_io.py:37-67`).

**Default plugins**

- `default_wired() -> tuple[WiredEntry, ...]` — the ordered built-ins adapted to
  declarative config entries, `kind=plugin`, no version pin
  (`dummyindex/context/default_plugins.py:227-235`).
- `describe_default_plugin_trust() -> tuple[str, ...]` — pure disclosure renderer
  for third-party defaults (`dummyindex/context/default_plugins.py:196-214`).
- `classify_wired_entry(entry: WiredEntry, *, is_present: Callable[[str], bool])
  -> WiredClass` — the single satisfied / acted / needs-user rule, pure, shared by
  the reconciler, `status`, and the interactive `wire` command
  (`dummyindex/context/default_plugins.py:448-469`).
- `wire_default_plugins(wired, project_root, *, enabled=True, runner=None)
  -> PluginWireResult` — classify-and-declare only; never calls `input()`, never
  executes the Claude CLI (`runner` is an unused compatibility parameter), never
  raises (`dummyindex/context/default_plugins.py:472-554`).
- `install_default_plugins(project_root, *, wired=None, enabled=True, runner=None)
  -> PluginInstallResult` — materializes only selected, effectively-true, and
  marketplace-ready defaults; a missing `claude`, a `DUMMYINDEX_SKIP_PLUGIN_INSTALL`
  env value, or an injected-runner-free skip degrades to `deferred`
  (`dummyindex/context/default_plugins.py:676-760`).
- `default_runner(argv: list[str], cwd: Path) -> RunResult` — fixed argv, no
  shell, 60-second timeout, missing executable surfaces as returncode 127
  (`dummyindex/context/default_plugins.py:589-605`).

**Plugin policy and settings primitives**

- `build_install_plan(candidates: tuple[Candidate, ...]) -> InstallPlan` — pure;
  selects native versus vendor and gates *every* untrusted candidate on `--yes`
  because declared surfaces are attacker-controlled input
  (`dummyindex/context/domains/equip/plugins/install_plan.py:36-53`).
- `analyze_blast_radius(entry: PluginEntry, *, trusted: bool) -> BlastRadius` —
  reports declared surfaces, whether any run code, and the source tier; disclosure
  only, never a waiver (`dummyindex/context/domains/equip/plugins/blast_radius.py:33-38`).
- `resolve_ref(repo: str, *, runner: Runner = default_runner) -> str | None` and
  `list_skills(repo: str, *, ref: str | None = None, runner: Runner = default_runner)
  -> tuple[SkillRef, ...]` — the pinning and enumeration seam for vendoring
  (`dummyindex/context/domains/equip/plugins/sources.py:149-166`,
  `dummyindex/context/domains/equip/plugins/sources.py:194-226`).
- `add_marketplace(settings_path, *, name, repo, ref=None) -> bool` and
  `enable_plugin(settings_path, *, plugin, marketplace) -> bool` are idempotent
  mechanism-level upserts. `add_marketplace` **overwrites** a same-name entry;
  callers needing identity-conflict refusal must check first
  (`dummyindex/context/claude_plugins.py:105-124`,
  `dummyindex/context/claude_plugins.py:142-155`).
- `run_install(rest: list[str]) -> int` — the wire-only CLI boundary: `2` for
  usage errors, `1` for resolution / approval / transport / write failures, `0`
  after a successful native or vendored install
  (`dummyindex/cli/equip/install.py:62-215`).

**Eval**

- A trigger-accuracy `equip evolve-loop` (propose → eval → keep-best search over
  a tool's `description`) is **contraindicated** — two falsification experiments
  (2026-07-05) scored 1.00 in every baseline/tuned × search/held-out cell (no
  headroom) and the description tuner overfit the suite both times, per arXiv
  2603.28052, the memory note `meta-harness-vs-dummyindex-verdict.md`, and the
  upstream corroboration
  `meta-harness@44b9942:experimental/harbor_meta_harness/README.md`
  (probe-before-loop; the upstream pilot rewards task-outcome only, trigger
  accuracy appears nowhere).

## Examples

**Happy path — `dummyindex context equip apply` on an indexed Python repo.**
`run` peels the `apply` verb and calls `run_apply`, which pulls flags and
resolves the root (`dummyindex/cli/equip/dispatch.py:109-117`,
`dummyindex/cli/equip/dispatch.py:177-200`). `_run_apply` confirms `.context/`
exists, reads the prior manifest once, builds the preflight report and drops
equip's own generated stems from the project-agent list so they cannot be
re-adopted as user agents, detects the stack, lists convention docs, and computes
`forced` as the explicit `--specialist` ask plus every specialist already carried
in the manifest (`dummyindex/cli/equip/dispatch.py:266-313`). `build_catalog`
returns four core specs plus five specialists plus one `ruff` `PostToolUse` hook;
`render_generated_set` renders each to `(item, rel_path, content)`
(`dummyindex/cli/equip/dispatch.py:315-333`). `_apply_write` then walks the
rendered set: an item whose recorded baseline classifies user-owned is carried
forward verbatim and printed as `keep … preserved`; a pristine-but-evolved item is
kept; a pristine or missing one is rewritten, inheriting any refresh-bumped
version from the manifest via `set_frontmatter_version` + a fresh `content_hash`;
an unrecorded foreign file at the target path is skipped
(`dummyindex/cli/equip/dispatch.py:421-467`). Adoptions are appended as
manifest-only records deduped against this run's names, hooks are wired after the
files, every unre-derived prior record is carried forward, the merged manifest is
written, and starter eval suites are seeded silently
(`dummyindex/cli/equip/dispatch.py:476-545`). The final line reports written /
adopted / hook events / carried / skipped / preserved / evolved counts and the
manifest path (`dummyindex/cli/equip/dispatch.py:560-567`).

**Happy path — `dummyindex context hooks install`.** Local scope scrubs a
sentinel-bearing `git post-commit` and any legacy `PostToolUse` entries, then
installs the five managed events in order, classifying each by a byte-level
before/after comparison of `.claude/settings.json` so a co-located user hook
never makes an unchanged install report "refreshed" forever
(`dummyindex/context/hooks.py:506-551`). The first `UserPromptSubmit` command
carries only the managed comment and the `printf` of the pre-quoted JSON payload,
so from the next prompt onward the turn reminder arrives as a system reminder
beside the user's text (`dummyindex/context/hooks.py:110-145`). Finally the
freshness badge is wired if and only if neither scope already defines a
`statusLine` (`dummyindex/context/hooks.py:553-562`).

**Happy path — reviewed defaults during init.** The caller prints
`describe_default_plugin_trust()`, reads `default_wired()`, and passes that set to
`wire_default_plugins`. For each entry the reconciler reads the effective
project/local state, returns early on a `false` tombstone, declares the unpinned
marketplace (healing a legacy SHA pin, refusing any other conflict), and writes
`true` only when the target was absent
(`dummyindex/context/default_plugins.py:511-548`). One subsequent
`install_default_plugins(..., wired=wired)` pass selects the declared, effectively
enabled, marketplace-ready targets, defers all of them when `claude --version`
fails, and otherwise attempts each independently so one CLI rejection does not
block the rest (`dummyindex/context/default_plugins.py:701-760`).

**Happy path — `equip install tool@marketplace --usage-doc docs/tool.md`.**
`run_install` collects catalogs, resolves the exact candidate, refuses an
ambiguous cross-repo match, and calls `build_install_plan`; an untrusted source
without `--yes` and without a prior enable stops before any settings or manifest
mutation (`dummyindex/cli/equip/install.py:89-145`). A collection candidate takes
the vendor branch: resolve HEAD to a SHA, locate the named `SKILL.md` at that ref,
fetch it, refuse if the prior vendored copy is user-owned or the target is a
foreign file, write through `write_text_atomic`, and record a pinned `VENDORED`
item (`dummyindex/cli/equip/install.py:335-446`). A native candidate probes
`git ls-remote` (warn, never block), writes the marketplace + enable, records the
`MARKETPLACE` item for in-repo scopes only, and upserts `config.wired`
(`dummyindex/cli/equip/install.py:158-215`,
`dummyindex/cli/equip/install.py:449-490`).
