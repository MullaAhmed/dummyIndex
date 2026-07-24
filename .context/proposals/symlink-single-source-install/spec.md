# Spec — Symlink-aware single-source skill install: one real .agents/skills tree, .claude/skills symlinked

> Scaffolded by `dummyindex context propose`. Revised once after a 3-critic
> panel (reuse/architecture, risk/edge-cases, testability) — see plan.md
> footer for the critique ledger.

## Intent

A `--platform both` project install today duplicates the entire skill family:
44 identical-purpose files under `.claude/skills/dummyindex*` **and** 44 under
`.agents/skills/dummyindex*`. Users see redundant bytes in their repo and
delete one tree — losing a host. The ecosystem answer (verified 2026-07-24
against vendor docs) is one real tree plus symlinks:

- **Codex** natively discovers `.agents/skills` at every level and explicitly
  supports symlinked skill directories.
- **Cursor** reads `.agents/skills` *and* `.claude/skills`.
- **Gemini CLI** aliases `.agents/skills` for its native dirs.
- **Claude Code** reads **only** `.claude/skills` — it is the sole holdout
  forcing duplication.

So: make **link mode the default** for `dummyindex install`. Whenever the
Claude surface can be served by a link, it is: ONE real skill-family tree —
the portable `.agents/skills/` rendering — and per-family relative symlinks
on the Claude side
(`.claude/skills/dummyindex -> ../../.agents/skills/dummyindex`, one link per
family: main + the 7 `_SIBLING_SKILLS`, 8 total — always enumerated from the
constant, never a `dummyindex*` glob, which would also catch the
equip-generated `dummyindex-verify` skill that is NOT part of the family).
A repo carries one copy of the bytes; every harness discovers it.

**Migration is forced and the install is universal by default** (user
decision, 2026-07-24 — supersedes the earlier opt-in draft). The product
goal in one sentence: **once installed or updated, the project works in any
harness — Claude Code, Codex, Cursor, Gemini CLI — with no extra flags.**
Two changes deliver it:

1. **`--platform` defaults to `both`** (was `claude`). A plain
   `dummyindex install` produces the universal layout: real
   `.agents/skills/` + Claude-side links + `CLAUDE.md` + `AGENTS.md`
   guidance. `--platform claude|agents` remain as narrowing escape hatches.
   This is a deliberate compatibility break with the documented
   "defaults to claude (backward compatible)" contract
   (install-surface spec) — called out in CHANGELOG and README.
2. **Forced migration**: a plain `dummyindex install` — which is exactly
   what the `/dummyindex-update` flow runs — detecting the duplicated
   layout (a proven `.claude` family AND a proven `.agents` family at the
   same scope root) OR a claude-only layout (proven `.claude`, no
   `.agents`) **converts it** to the universal linked layout in the same
   run, evidence-gated per family. No flag needed; updating dummyindex
   heals every repo it re-installs into.

`--copy` is the escape hatch (one-run opt-out of linking, old duplicated
behavior); `--link` remains as the *strict* form (error instead of fallback
when linking is impossible). The user-facing command set for the normal
path is exactly two, flagless: `dummyindex install` and
`/dummyindex-update`.

**Direction is fixed and one-way**: links always point `.claude` → `.agents`,
never the reverse. The `.agents` rendering is the portable one — its
`_PORTABLE_HOST_PREAMBLE` (`installer/common.py:66`) already tells a Claude
Code reader "this is native vocabulary for you". The reverse direction would
feed Codex the Claude-only rendering, which is exactly the bug the portable
preamble fixed.

**Who**: dummyindex users running multiple harnesses on one repo (the
BOS-Mono/backend case that motivated this), and teams whose clones must work
in whichever harness a teammate uses.

**Security frame**: the installer's existing no-follow guards exist to stop
writing or removing through attacker-placed links. This proposal does not
weaken that model — it *narrows* one admission: a family-dir symlink that
provably belongs to dummyindex (exact lexical value, clean parent chain,
owned target) is managed; everything else keeps today's refusal behavior
byte-for-byte.

## Contracts

### Layer moves first (no behavior change)

To keep the import graph acyclic (`repair.py` already imports `install.py` at
module level, `repair.py:60`), the shared bottom layer grows:

- Move `_remove_owned_tree_no_follow` from `uninstall.py` to `common.py`.
- Move the ownership-evidence trio — `_read_stamp`,
  `_has_legacy_codex_heading`, `is_owned_copy`, plus `_VERSION_STAMP_NAME`
  and `_LEGACY_CODEX_HEADING_RE` — from `repair.py` to `common.py`.
  `repair.py` and `uninstall.py` re-export so existing importers
  (`install.py:147`, tests) are untouched.

**Import law** (acyclic by construction): `link.py` imports **only**
`common.py`; `install.py`, `repair.py`, `uninstall.py` import `link.py`.

### New module: `dummyindex/installer/link.py`

- `FamilyLinkState(str, Enum)` — closed alphabet per
  `conventions/coding-practices.md` (`__str__ = str.__str__`):
  - `NOT_A_LINK` — a real directory (or a regular file that is not a
    materialized link).
  - `OURS_HEALTHY` — symlink whose readlink value, compared as
    `PurePath(os.readlink(p)).parts` (never raw strings — Windows readlink
    round-trips normalize separators), equals `relative_link_value()` **or**
    resolves to `family_link_target()`; parent chain clean (below); target
    `is_owned_copy()`.
  - `OURS_DANGLING` — matching link value, parent chain clean, and the
    target **positively confirmed absent** (lstat parent chain ok + target
    lstat = ENOENT). An unstatable target is never DANGLING.
  - `MATERIALIZED` — a **regular file** whose exact content equals
    `relative_link_value(family)`: the `core.symlinks=false` Windows checkout
    shape. The content IS ownership proof — replaceable under `--link`,
    reported elsewhere with the `git config core.symlinks true` + re-checkout
    remediation.
  - `MISSING` — path absent entirely. Link mode creates here with no
    ownership evidence needed (an empty path is safe to fill); this is also
    the crash-recovery state.
  - `FOREIGN` — everything else, including: any parent-chain symlink, any
    other link value, absolute links that don't resolve to the target, and
    **any `OSError`/`RuntimeError` during classification (fail closed,
    mirroring `_same_root`, `repair.py:651`)**. Never written, never removed.
- `FamilyLinkClassification` — frozen dataclass record: `family`, `path`,
  `state`, `detail`. `classify_family_link(claude_family_dir, scope_root) ->
  FamilyLinkClassification`. **Parent-chain rule**: state can only be
  `OURS_*`/`MATERIALIZED`/`MISSING` when
  `_first_symlink_component(scope_root, family_dir.parent,
  allowed_symlinks=<host-root allowlist>)` is `None` — a symlinked `.claude`
  or `.claude/skills` at project scope forces `FOREIGN` even when the leaf
  link looks perfect (else a `.claude -> /victim` layout makes heal/sweep
  unlink inside the victim tree). **Scope-root rule**: classification always
  runs against the copy's own scope root (`_scope_root(copy)`,
  `repair.py:669`), never the invocation's root.
- `family_link_target(scope_root, family) -> Path`;
  `relative_link_value(family) -> str` = `../../.agents/skills/<family>`.
- `create_family_links(scope_root, *, symlink_fn=os.symlink) -> LinkResult`
  (frozen; tuple fields `created`, `replaced`, `skipped`, `errors`). Per
  family, the **safe replacement dance** (fixes both the crash window and
  the classify→remove TOCTOU in one move):
  1. Create the symlink at a sibling temp name
     (`.<family>.dummyindex-link.tmp`) — this also probes symlink capability
     **before anything is destroyed**. `target_is_directory=True` on Windows.
  2. If a proven copy exists at the family path: **rename it aside** (atomic
     — a racing writer now misses), re-verify `is_owned_copy` **on the
     renamed tree**, then `os.replace`/rename the temp link into place, then
     delete the renamed tree last (`_remove_owned_tree_no_follow`).
  3. `MISSING` → rename temp link into place directly. `OURS_HEALTHY` →
     leave untouched (idempotent; result counts it in neither `created` nor
     `replaced`). `MATERIALIZED` → replace (content is proof). Absolute
     link that resolves correctly → normalize to the relative value, count
     as `replaced`. `FOREIGN` / unproven real dir → skip + report, never
     touched.
  4. **Replacement evidence is the stamp, not the heading**: a real dir is
     replaced only when `.dummyindex_version` is present (heading-only →
     report; mirrors the install-surface concerns.md dedupe finding). Print
     the "hand-edits to this installed copy are not preserved" caveat on
     every replace.
  5. After creating each link, **verify it resolves** to the realpath of the
     `.agents` family. Mismatch (the dotfiles case: `~/.claude ->
     ~/dotfiles/claude` makes `../..` land in `~/dotfiles/`) → remove the
     just-created link, report with a dotfiles-specific hint. Never leave a
     known-broken link behind.
  6. Error isolation per family: `FileExistsError` → re-classify and
     replace-or-report that family, continue the loop. `OSError` with
     EPERM/`winerror` shape → abort remaining creations, report with the
     Windows Developer-Mode/`core.symlinks` hint, **name every family left
     uncovered**; already-created links stay.
- **Host-root allowlist is passed in, never inferred** (revised 2026-07-24
  after audit): every public entry point takes a keyword-only
  `allowed_symlinks: frozenset[Path] = frozenset()` that **fails closed** by
  default. An earlier draft inferred user scope as `scope_root ==
  Path.home()`, which let a spoofed `HOME` (CI runners, containers,
  `direnv`) flip a checked-in `.claude -> /victim` symlink from FOREIGN to
  OURS at *project* scope — an environment variable deciding whether the
  security gate applies. `repair.py:653` takes `scope` explicitly for this
  exact reason. **Wave 3 obligation**: `install.py` knows the real scope and
  must pass the host-root allowlist at user scope — including a passthrough
  on `run_link_install` / the capability pre-probe, which currently always
  fail closed and would otherwise force copy-mode for every user-scope
  install with a dotfiles-symlinked `~/.claude`.
- `verify_family_links(scope_root) -> tuple[FamilyLinkClassification, ...]`
  — read-only sweep (repair/check/uninstall reporting).
- `remove_dangling_family_links(scope_root) -> tuple[Path, ...]` — the shared
  sweep used by **both** `uninstall` and `dedupe` after removing a codex
  family: unlink `OURS_DANGLING` leftovers only, re-running the parent-chain
  check **immediately before each unlink** (mirrors `execute_repairs`'
  re-preflight, `repair.py:339`). `FOREIGN` untouched.
- `run_link_install(...)` — the link-mode orchestration (validity gate +
  sequencing + the AUTO/LINK/COPY tri-state), hosted here so `install.py`
  (735 lines, already over the repo's >600-line split threshold) gains only
  a dispatch call. Performs one **capability pre-probe** (create + remove a
  probe symlink under `.claude/skills/`) before any conversion: probe
  failure → AUTO falls back to copy mode for the whole run (one warning +
  Windows hint, nothing destroyed), strict LINK exits 1.

### CLI surface — link is the default; tri-state control

- `parse_install_args` (`installer/args.py:72`) grows **two** flags —
  `--link` (strict) and `--copy` (opt-out) — which resolve to **one** new
  tuple field, the `LinkMode`; the pre-existing tuple is 9-wide, so it
  becomes **10-wide** (an earlier draft of this line said 11, adding the two
  flags as separate fields — arithmetic erratum, corrected 2026-07-24);
  `__main__.py:289-312` forwards. **The `platform` default flips
  `"claude"` → `"both"`** in `parse_install_args`, `install()`, and — for
  symmetry, so a flagless uninstall removes what a flagless install wrote —
  `parse_uninstall_args` **and** `uninstall()` (the parser is named
  explicitly: "flagless" is a property of the command line, so CLI symmetry
  is what the rationale actually requires; decided 2026-07-24). Parse-time
  rejections (exit 2, the parser's code per conventions): `--link --copy`
  together ("pick one"); `--link --platform agents` ("linking writes the
  Claude side — select claude or both").
- **Transitive consequence of the platform flip** (documented break): a
  flagless `--defaults` / `--no-onboarding` install now writes
  `"model": "current"` into `.context/config.json` where prior releases
  wrote `"sonnet-4.6"`, because `default_config`'s `portable_model` branch
  fires for `both` and `current` is the only model valid for a both-host
  config (`onboard.py` rejects `--platform both` with any other model).
  `--platform claude` or interactive onboarding keeps a pinned Claude model.
- **Uninstall removes family directories wholesale** (decided 2026-07-24,
  after audit): no `is_owned_copy` gate is added to sibling removal —
  `install()` stamps only the *main* family dir, so all 7 siblings are
  unstamped and a gate would orphan every sibling for the entire installed
  base. Locked by a characterization test so a future gate is a conscious
  reversal, not drift.
- `install(..., link_mode: LinkMode = LinkMode.AUTO)` — `LinkMode(str,
  Enum)`: `AUTO` (default) / `LINK` (strict) / `COPY`. Runtime validity
  errors exit 1, matching `install.py:78-94`:
  - **AUTO + `both`** (the common case, and the update flow): write
    `.agents` for real, link the Claude side. On a duplicated layout, the
    proven `.claude` families are converted (the rename dance below) —
    **this is the forced migration**. On symlink incapability (the temp-link
    probe fails EPERM before anything is destroyed): fall back to copy mode
    for the whole run with a one-line warning + the Windows hint — an
    update must never brick a Windows checkout.
  - **AUTO + `claude`** (now always an explicit narrowing): when a proven
    **current** `.agents` family exists at the same scope root → link to it
    (converting a duplicated `.claude` copy). Otherwise → copy, unchanged
    from today (nothing to link to; claude-only installs don't create
    `.agents`). Note the default-both flip means a **claude-only layout
    under a flagless install/update is itself a migration case**: the run
    writes `.agents` for real and converts the proven `.claude` families to
    links — that is how "update makes an old repo universal" happens.
  - **AUTO + `agents`**: real `.agents` tree as today. Never touches
    `.claude/**` (host-scoping rule is not weakened by migration); a
    detected duplicated layout is *reported* with the `--platform both`
    remediation.
  - **LINK (strict)**: same as AUTO but errors (exit 1) where AUTO would
    fall back or skip — EPERM, no `.agents` family to link to (message
    names `--platform both`, plus `--force-downgrade` when the stamp
    direction is newer/unknown, so the remediation actually remediates).
  - **COPY**: today's behavior exactly — real trees, no links created, a
    linked layout is left as-is (links are still admitted by the preflight
    and reported, never converted back).
  - **Sequencing is pinned** in every linking path: `plan_repairs` →
    direct-write loop → `execute_repairs` → **then** `create_family_links`
    — links are created only after every rewrite has landed, so
    `execute_repairs` can never write Claude-rendered files through a fresh
    link into `.agents`. The Claude-side
    `_install_skill_family(base, "claude", src)` call is skipped when
    linking. `/tokens` command copy, CLAUDE.md registration, hooks, and
    auto-init run unchanged.
  - User scope works, with the dotfiles resolution check from
    `create_family_links` step 5 deciding correct-vs-refused (AUTO falls
    back to copy there too, with the dotfiles hint).

### Forced-migration semantics (what "update converts the repo" means)

- Trigger: any AUTO/LINK install whose selected platforms include claude,
  at a scope root where the Claude family is a proven **real** copy and a
  proven `.agents` family exists (or is being written this run).
- Per-family evidence gate is unchanged from the rename dance:
  `.dummyindex_version` stamp required (heading-only → report, skip);
  the "hand-edits to this installed copy are not preserved" caveat prints
  on every conversion. **Note the delta vs repair**: repair never rewrites
  an equal-stamp copy; forced migration DOES convert an equal-stamp copy —
  that is the point ("force"). The caveat line makes it visible.
- Unproven / FOREIGN / hand-rolled Claude family dirs are never converted —
  reported with the remediation, exactly like repair.
- Migration output: one `migrated ->` line per converted family, mirroring
  the `skill installed ->` format, so the update transcript shows exactly
  what changed.

### The preflight admission (the security-sensitive change — own task, own tests)

`install()`'s preflight (`install.py:104-146`) today exits 1 on ANY managed
family-dir symlink at project scope — so on a linked repo, every plain
`dummyindex install` (i.e. the `/dummyindex-update` flow) hard-fails before
repair even plans. Fix, narrowly:

- The preflight admits a family dir iff `classify_family_link` returns
  `OURS_HEALTHY` / `OURS_DANGLING` / `MATERIALIZED` — in **every** link
  mode (AUTO, LINK, COPY). Everything else (FOREIGN, deeper companion-dir
  links under a real family) keeps today's refusal byte-for-byte.
- The **write path stays unconditional**: `_install_skill_family` never
  writes when the family dir is a symlink — even an OURS link. Writes
  through links are never OK; link mode replaces links via the rename dance,
  it does not write through them.
- The **direct-write loop** (`install.py:157-170`) consults
  `classify_family_link` first: `OURS_DANGLING` under COPY → report with
  the remediation (today it would crash — `mkdir(exist_ok=True)` raises
  `FileExistsError` on a dangling symlink, `install.py:268`); under
  AUTO/LINK → healed by `create_family_links`. `MISSING`/unproven-real
  behavior unchanged.

### Repair / duplicates / dedupe (`installer/repair.py`) — classify and report, never write links

Repair gains **no link-write path** — all link creation/healing lives in
`create_family_links` (single write owner; an AUTO/LINK run heals by
construction, being idempotent — and AUTO is the default, so a plain
update-flow reinstall both heals links and migrates duplicated copies):

- `plan_repairs`: Claude copies classify first. `OURS_HEALTHY` → report
  `linked -> .agents (current)`; never a rewrite candidate; staleness is
  evaluated and repaired on the codex row only. `OURS_DANGLING` /
  `MATERIALIZED` → report (healed by the same run's `create_family_links`
  under AUTO/LINK; remediation named under COPY). A proven **real** Claude
  copy alongside a proven `.agents` family → reported as
  `migration candidate` (converted by the same run when claude is
  selected). `FOREIGN` → today's refusal path, message unchanged.
- `_find_duplicate_families` (`repair.py:620`): pairing is same-host across
  scopes, so a link and its own target never pair (different host rows).
  The real interplay: user-scope real Claude copy + project-scope Claude
  link **is** a genuine duplicate (two Claude surfaces) and stays reported.
  Exclude a pair only when one side's link resolves into the other side's
  scope root (`_same_root`-style, fail closed) — one physical copy seen
  twice.
- `dedupe`: removing a linked side removes **the link only** (lock the
  existing `_remove_skill_family` no-follow behavior, `uninstall.py:110`,
  with a test); never the target. After dedupe removes a **codex** family,
  run `remove_dangling_family_links` on that scope root — dedupe must not
  orphan the Claude links uninstall would have cleaned.

### Uninstall (`installer/uninstall.py`)

- `--platform claude` on a linked layout removes the 8 links (existing
  no-follow behavior — lock with tests).
- `--platform agents`/`both`: after removing the codex family, call
  `remove_dangling_family_links` — dummyindex-owned links never dangle after
  a dummyindex uninstall or dedupe. Foreign links untouched.
- **The agents-only narrowing warns about the collateral** (decided
  2026-07-24): because the Claude side is *links into* the `.agents` tree,
  `--platform agents`/`codex` (claude NOT selected) that sweeps ≥1 link
  prints a stderr warning naming the now-gone Claude Code surface plus the
  `install --platform claude` recovery command. Not printed under
  `--platform both` (everything was asked to go). The narrowing still touches
  zero real Claude-side bytes (`tokens.md`, CLAUDE.md registration, hooks all
  survive) — only the dead links are swept.

### check --versions (`cli/check.py`)

Stamps keep reading through links (correct today). Label gains ` (linked)`
when the family dir classifies `OURS_*`, and ` (materialized link)` for
`MATERIALIZED` with its remediation — a coherent-versions report on a linked
layout is self-explanatory.

### Out of scope

- No change to guidance blocks, hooks, default plugins, or equip. No
  `.claude/commands/` linking (one host-specific file). `~/.codex/skills`
  untouched. No config persistence of the link choice (`--copy` is per-run;
  a durable opt-out can follow if anyone asks).

## Open questions

*(none — resolved during drafting, the critique round, and one user
decision)*
- Direction: `.claude → .agents`, fixed (see Intent).
- **Default is link mode with forced migration** (user decision 2026-07-24;
  supersedes the panel-reviewed opt-in draft). `--copy` opts out per run;
  `--link` is the strict form.
- Repair heals nothing itself: heal = idempotent `create_family_links` on
  any AUTO/LINK run. One write owner.

## Acceptance

- [ ] **Flagless = universal**: plain
      `dummyindex install --scope project --dir <repo>` (NO --platform)
      on a fresh repo yields: the 8 enumerated families (main +
      `_SIBLING_SKILLS`, derived from the constant in the test) real under
      `.agents/skills/` (each stamped = package version) and each Claude-side
      family path `is_symlink()` with readlink parts equal to
      `../../.agents/skills/<family>`, resolving to its family. No enumerated
      family exists as a real dir under `.claude/skills/`. Both `CLAUDE.md`
      and `AGENTS.md` guidance written. The repo is discoverable by Claude
      Code, Codex, Cursor, and Gemini CLI with no further commands.
- [ ] **Forced migration (duplicated layout)**: on a repo with proven real
      families under BOTH `.claude/skills/` and `.agents/skills/` (equal
      current stamps), a flagless `install` converts every proven Claude
      family to a link, prints one `migrated ->` line + the hand-edits
      caveat per family, and leaves `.agents` as the only real tree.
      Heading-only and unproven Claude copies are skipped + reported,
      never converted.
- [ ] **Forced migration (claude-only layout)**: on a repo with only a
      proven `.claude` family (today's most common install), a flagless
      `install` writes `.agents` for real, converts the `.claude` families
      to links, and writes `AGENTS.md` — one command makes an old repo
      universal.
- [ ] Idempotency: a second identical run exits 0 and its `LinkResult`
      reports 0 created / 0 replaced (primary observable); link inode and
      `st_mtime_ns` unchanged (secondary).
- [ ] AUTO + `--platform claude` with a proven current `.agents` family
      links to it (converting a duplicated real copy); with none it copies
      exactly as today. Strict `--link --platform claude` with no `.agents`
      family exits 1 printing the `--platform both` fix; with a
      newer/unknown stamp the message also names `--force-downgrade`.
- [ ] Parse rejections, exit 2: `--link --platform agents` and
      `--link --copy`.
- [ ] AUTO + `--platform agents` never touches `.claude/**`; a duplicated
      layout is reported with the `--platform both` remediation.
- [ ] `--copy` regression: full existing suite passes; a characterization
      test proves COPY mode never calls `create_family_links` (DI/spy seam)
      and leaves an existing linked layout as-is (reported, not converted
      back); one-time PR evidence: `diff -r` of `--skill-only` trees from
      merge-base (default) vs HEAD (`--copy`) is empty (skill-only excludes
      timestamped `.context/`).
- [ ] Repair on a linked layout: plain `install --platform both` succeeds
      (preflight admits OURS links), does NOT convert links to copies,
      reports `linked -> .agents (current)`, and repairs a stale `.agents`
      target in place with links untouched.
- [ ] Dangling link: an AUTO rerun heals it (via `create_family_links`);
      a `--copy` rerun reports it with the exact remediation and does NOT
      crash in the direct-write loop.
- [ ] `MATERIALIZED` (regular file with the exact link value — simulated
      `core.symlinks=false` checkout): AUTO/`--link` replaces it;
      `--copy` and `check --versions` report it with the
      `git config core.symlinks` remediation.
- [ ] FOREIGN refusals unchanged: foreign leaf link, foreign absolute link,
      symlinked `.claude`, and symlinked `.claude/skills` all classify
      FOREIGN and are refused/report-only with today's message shape in both
      modes (existing tests keep passing; new parent-chain rows added).
- [ ] Crash-window recovery: killing the dance between steps leaves either
      the renamed-aside tree or the temp link; a `--link` rerun converges to
      a healthy link (MISSING state fills; temp artifacts cleaned).
- [ ] `uninstall --platform both --scope project` on a linked layout leaves
      neither links nor families; `uninstall --platform agents` removes the
      real tree AND the now-dangling owned links; `dedupe` removing a codex
      family does the same sweep; `dedupe` on a linked Claude side removes
      the link only, never the target.
- [ ] Cross-scope duplicate: user-scope real Claude copy + project-scope
      Claude link is still reported as a duplicate; a pair that resolves to
      one physical copy is not.
- [ ] `check --versions` on a linked layout reports coherent versions with
      `(linked)` labels.
- [ ] Symlink incapability (DI `symlink_fn` raising EPERM — no
      monkeypatching `os.symlink`, which `Path.symlink_to` does not route
      through on py3.10): under AUTO the capability pre-probe fails before
      anything is destroyed and the whole run falls back to copy mode with
      one warning + the Windows `core.symlinks`/Developer-Mode hint — the
      install still succeeds and both hosts work (update never bricks a
      Windows checkout). Under strict `--link` the same condition exits 1.
      Mid-loop failure (Nth-call raiser): abort remaining creations, keep
      already-created links, name every uncovered family, `.agents` stays
      valid, a rerun converges.
- [ ] User scope: plain user-scope AUTO lifecycle passes; with a
      dotfiles-symlinked `~/.claude`, the resolution check cleans the broken
      link, prints the dotfiles hint, and AUTO falls back to copy for that
      run (no infinite heal churn).
- [ ] Link-mode installs still write `/tokens` command (regular file),
      CLAUDE.md registration, hooks/settings, and run auto-init.
- [ ] New test modules carry `@pytest.mark.unit`/`integration` markers
      (strict markers); real-symlink tests sit behind a capability guard
      (skip when `os.symlink` unavailable), simulated-failure tests do not.
- [ ] **GATE** Live-host verification: in a scratch git repo with the linked
      layout, a fresh Claude Code session lists and invokes `/dummyindex`
      (proves Claude Code follows the family-dir symlink); a fresh `codex`
      session in the same repo lists/invokes `$dummyindex` from
      `.agents/skills` (or Cursor's skill picker shows the family).
- [ ] Full suite green (`pytest`), ruff clean, on this branch.

<!-- dummyindex:consistency:begin -->
## Consistency

**Related features:**

- `install-surface`
- `tree-enrich`
- `equip`
- `codex-guidance`
- `council`

**Conventions to honor:**

- `conventions/coding-practices.md`
- `conventions/data-access.md`
- `conventions/folder-organization.md`
- `conventions/naming.md`
- `conventions/testing.md`

<!-- dummyindex:consistency:end -->
