---
name: dummyindex-update
description: "Update or pin dummyindex across the CLI package, selected Claude Code or Codex skill family, current repo wiring, and `.context/` version stamp. Resolves the latest GitHub release with a `main` fallback or accepts an exact version, detects uv tool, pipx, or pip user installation, force-reinstalls that ref, and reruns the host-aware installer. Refreshes deterministic artifacts non-destructively without running the council, reconciling, or replacing curated taxonomy; verifies that every layer moved and surfaces the changelog. Idempotent when already current unless forced. Use for `/dummyindex-update`, `$dummyindex-update`, update dummyindex, upgrade to latest, pin a version, fix version skew, or dummyindex is out of date."
---

# /dummyindex-update / $dummyindex-update [&lt;version|tag&gt;] — Update (or pin) dummyindex

> **Invocation:** Claude Code uses `/dummyindex-update`; Codex uses `$dummyindex-update`. With no argument the skill updates to the latest release; `<version|tag>` pins an exact version (for example, `0.24.0` or `v0.24.0`).

> **Installed from dummyindex `__VERSION__`.** This skill ships with the CLI, so updating also replaces this skill with the new version's copy.

Updating dummyindex by hand is fiddly because three layers drift independently:

| Layer | Where it lives | How it goes stale |
|---|---|---|
| **CLI package** | `dummyindex` on `PATH` (uv tool / pipx / pip `--user`) | A non-editable COPY; repo or GitHub changes never reach it until reinstalled. |
| **Skill family** | Claude: `.claude/skills/dummyindex*/`; Codex: `.agents/skills/dummyindex*/`; user or project scope, plus `.dummyindex_version` | Copied at install time; stamped with whatever version installed it. |
| **Per-repo wiring** | Claude: managed `CLAUDE.md`, hooks, and commands; Codex: active project instruction file (`AGENTS.override.md`, `AGENTS.md`, or configured fallback); both: `.context/meta.json` `dummyindex_version` | Written by `install` / `ingest`; carries the version that last touched the repo. |

You bring all three to the latest GitHub version in one pass, **non-destructively**, and prove each layer actually moved.

## Hard rules

- **Never** trigger the council, `reconcile`, or a full re-ingest. The only `.context/` write allowed is the deterministic backbone rebuild that `dummyindex install` runs on a git repo. Curated taxonomy (feature names, abstracts, conventions, audits) is left untouched.
- **Never** pass `--break-system-packages` or `sudo`. Match the install method that's already there.
- **Stop on the first failed step** and report the failing command's output. A half-updated install (new CLI, stale skills) is worse than a clean failure.
- **Idempotent.** Stop only when the CLI, every applicable selected host/scope
  skill stamp, and the current repo stamp already equal the target. A current
  CLI with stale skills or wiring continues to repair them. `--force` reinstalls
  anyway (for example, to repair a corrupt copy).

## Procedure

Run these as Bash steps, reading the output of each before the next. `REPO=MullaAhmed/dummyIndex`.

### 1. Resolve the target version

```bash
dummyindex --version            # current, e.g. 0.22.0
```

**If the user passed a version/tag** (e.g. `/dummyindex-update 0.24.0` or `v0.24.0`), use it as `<REF>` **verbatim** — accept it with or without the `v` prefix, **skip** the latest-tag resolution below, and compare the installed version against **that pinned ref** for the idempotency check (not against latest). This is how a session pins an exact version instead of always chasing latest.

**Otherwise** find the latest **release tag** (preferred — stable), falling back to `main` HEAD:

```bash
# Prefer gh; fall back to the public API; final fallback is the main branch.
gh release view --repo MullaAhmed/dummyIndex --json tagName -q .tagName 2>/dev/null \
  || curl -fsSL https://api.github.com/repos/MullaAhmed/dummyIndex/releases/latest 2>/dev/null \
       | grep -m1 '"tag_name"' | sed -E 's/.*"tag_name": *"([^"]+)".*/\1/' \
  || echo main
```

Normalise the tag (a `v` prefix is fine for the pip ref; strip it only when
comparing version numbers). **Do not stop merely because the CLI already equals
the target.** First inventory the selected host/scope skill stamps and the
applicable `.context/meta.json` stamp as described in step 3. Only print
`already up to date (X.Y.Z)` and stop when every applicable selected layer
already equals the target and the user did not pass `--force`. A current CLI
with a stale skill or repo stamp must continue to step 3. When the target is
`main` and has no comparable release version, continue rather than guessing.
`--force` reinstalls every selected layer even when versions match (including a
downgrade to a pinned older ref).

### 2. Detect the install method and update the CLI when needed

Probe in order and use the **first** that lists `dummyindex`:

```bash
uv tool list 2>/dev/null | grep -q '^dummyindex'   && echo "method=uv"
pipx list 2>/dev/null    | grep -q 'package dummyindex' && echo "method=pipx"
# else: pip --user (the common default)
```

If the running CLI differs from the comparable target, or the user passed
`--force`, reinstall from the resolved ref (`<REF>` = the tag from step 1, or
`main`):

- **uv tool:** `uv tool install --force "git+https://github.com/MullaAhmed/dummyIndex.git@<REF>"`
- **pipx:** `pipx install --force "git+https://github.com/MullaAhmed/dummyIndex.git@<REF>"`
- **pip --user:** `python3 -m pip install --user --force-reinstall --no-cache-dir --upgrade "dummyindex @ git+https://github.com/MullaAhmed/dummyIndex.git@<REF>"`

If the running CLI sits inside a virtualenv (check `python3 -c 'import sys; print(sys.prefix)'` / `which dummyindex`), reinstall into that environment instead of `--user`. When in doubt, mirror exactly where `which dummyindex` resolves.

If the CLI already equals a release target and this is not `--force`, skip only
the package reinstall; continue to step 3 so stale skills or repo wiring are
repaired.

### 3. Refresh the skills + the current repo's wiring

Before the early-exit decision in step 1 and before running the installer,
preserve the host and scope of the skill being updated:

- Claude Code uses `--platform claude`; Codex uses `--platform codex`. Use
  `--platform both` only when the user explicitly maintains both integrations.
- A family under `~/.claude/skills/` or `~/.agents/skills/` is user-scoped. A
  family under the current repo's `.claude/skills/` or `.agents/skills/` is
  project-scoped and needs `--scope project --dir <repo>`.
- If the user intentionally has different hosts in different scopes, run the
  installer once per host/scope pair instead of moving either family.

From the repo root, run the **newly installed** CLI's installer with the
selected values:

```bash
dummyindex install --platform <claude|codex|both> --scope <user|project> [--dir <repo>]
```

This re-copies the selected skill family (including this update skill),
restamps its `.dummyindex_version`, and — when the target is a git repo —
touches `.context/`. Claude refreshes its managed guidance, commands, and hooks;
Codex refreshes the active project instruction file and does not require
`.claude/` state. **On a
curated index (council-enriched feature names, abstracts, conventions),
`install` takes the non-destructive path: it refreshes only the deterministic
artefacts and advances `.context/meta.json`'s `dummyindex_version` stamp,
leaving the curated taxonomy untouched.** Only a brand-new or
deterministic-only index is full-built. If the target is not a git repo,
`install` skips the per-repo step on its own; that is expected, not an error.

**When Claude is selected, `install` also refreshes this repo's
equip-generated tools.** When the repo is equipped (`.context/equipment.json`
present), the per-repo step runs `equip refresh` against the just-installed
templates — so the generated agents, the `<proj>-verify` skill, and any
capability specialists track the new version, not just the `dummyindex*` skill
family and wiring. This is the SAME hash-baselined, never-clobber refresh as
`dummyindex context equip refresh`: only PRISTINE generated tools whose render
actually changed are re-rendered and re-baselined; a tool you hand-edited
(USER_MODIFIED) is kept untouched. It prints an `equipment -> refreshed N …`
line. Best-effort — if the refresh hits a snag the update still succeeds (the
skills and backbone already moved). An unequipped repo is a silent no-op. A
Codex-only install uses native subagent fallback and is not expected to refresh
Claude-generated equipment. To preview the Claude refresh, run
`dummyindex context equip refresh --dry-run` before updating.

> Earlier versions of this skill claimed `install` ran a "non-destructive `build_all`". That was false — a bare `build_all` re-clusters and would shatter a curated index. The installer now guards the curated case explicitly (preserve-on-enriched), so the claim above is finally true.

> Do **not** reach for `dummyindex ingest`, `context reconcile`, or `--recouncil` here — those regenerate curated content and violate the hard rules.

### 4. Verify every layer moved, then report

```bash
dummyindex --version                                            # layer 1: CLI
# layer 2: run the path(s) matching the selected host and scope:
cat ~/.claude/skills/dummyindex/.dummyindex_version             # Claude, user
cat .claude/skills/dummyindex/.dummyindex_version               # Claude, project
cat ~/.agents/skills/dummyindex/.dummyindex_version             # Codex, user
cat .agents/skills/dummyindex/.dummyindex_version               # Codex, project
# layer 3 (only if the repo has .context/):
test -f .context/meta.json && grep -o '"dummyindex_version": *"[^"]*"' .context/meta.json
```

The CLI, every selected host/scope skill stamp, and every applicable repo layer
must now equal the target version. Do not treat an unselected host's older stamp
as a failure. The repo stamp (layer 3) lives in `.context/meta.json` and advances
on the non-destructive deterministic refresh `install` runs — so a curated
repo's stamp moves without a re-ingest. If `.context/meta.json` exists but its
`dummyindex_version` did not reach the target, **say so loudly** and surface the
command output — do not claim success.

**Layer 3b — generated tools (equipped repos with Claude selected only), a
verified layer, not a hope.** Step 3's `install` refreshes the repo's
equip-generated tools and prints an `equipment -> …` line, but that refresh is
*best-effort* (it swallows errors so a snag never fails the update). Confirm it
actually ran: if Claude is selected and the repo is equipped
(`.context/equipment.json` exists) but **no `equipment ->` line appeared** in
step 3's output, the refresh was skipped — run it explicitly and surface the
result rather than assuming the toolkit is current:

```bash
# only when equipped AND step 3 printed no `equipment ->` line:
test -f .context/equipment.json && dummyindex context equip refresh
```

`equip refresh` is idempotent and never-clobber (PRISTINE tools whose render changed are re-rendered + re-baselined; USER_MODIFIED tools are kept), so re-running it is safe. If it reports an `⚠ … INVARIANT_BROKEN` alarm, surface that — a generated tool was hand-edited in a way that dropped a load-bearing convention. Do **not** claim the generated toolkit is current if the refresh was skipped and you did not re-run it.

Then show what changed: read the top entry of `CHANGELOG.md` in the repo (or `gh release view --repo MullaAhmed/dummyIndex` for the release notes) and summarise it. Finish with a compact before→after table:

```
dummyindex updated: 0.22.0 → 0.23.0
  CLI package   0.22.0 → 0.23.0  ✓
  skill family  0.22.0 → 0.23.0  ✓  (<host>, <scope>)
  this repo     0.22.0 → 0.23.0  ✓  (.context/ backbone refreshed, curated content untouched)
  equip tools   refreshed N generated tool(s) to the new templates (M user-modified kept)
                # or: N/A (Codex-only; no Claude equipment refresh)
What's new: <one-line summary of the new CHANGELOG entry>
```

## Notes

- **Self-update:** because step 3 runs the new CLI's `install`, this skill file is replaced by the new version's copy. The next `/dummyindex-update` or `$dummyindex-update` invocation uses the updated procedure.
- **No GitHub access:** if both `gh` and the API are unreachable, step 1 falls back to `main` — still an update, just unversioned-by-tag. Tell the user you used `main` rather than a release.
- **Repairing a stale CLI:** the classic failure is "I edited dummyindex but the `dummyindex` command still behaves like the old version." `--force` re-runs the whole flow even when versions match, which fixes a copy that drifted from its tag.
