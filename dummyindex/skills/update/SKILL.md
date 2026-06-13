---
name: dummyindex-update
description: Update an installed dummyindex to the latest version from GitHub, across all three layers — the CLI package, the `~/.claude/skills/dummyindex*` skill family, and the current repo's wiring (commands, SessionStart hook, `.context/` version stamp). Resolves the latest release tag on `MullaAhmed/dummyIndex` (falls back to `main`), detects how the CLI was installed (uv tool / pipx / pip --user) and force-reinstalls it from that tag, then re-runs `dummyindex install` to refresh every skill and the per-repo wiring with a NON-DESTRUCTIVE deterministic backbone rebuild — never the council, never reconcile, never touching curated `.context/` taxonomy. Verifies the version actually moved on every layer and surfaces the new CHANGELOG entry. Idempotent: a no-op when already current unless `--force`. Triggers — `/dummyindex-update`, "update dummyindex", "upgrade dummyindex to the latest version", "dummyindex is out of date", "bump dummyindex in this repo".
allowed-tools: Read, Bash
---

# /dummyindex-update — Update dummyindex to the latest version

> **Installed from dummyindex `__VERSION__`.** This skill ships with the CLI, so updating also replaces this skill with the new version's copy.

Updating dummyindex by hand is fiddly because three layers drift independently:

| Layer | Where it lives | How it goes stale |
|---|---|---|
| **CLI package** | `dummyindex` on `PATH` (uv tool / pipx / pip `--user`) | A non-editable COPY; repo or GitHub changes never reach it until reinstalled. |
| **Skill family** | `~/.claude/skills/dummyindex*/` + `.dummyindex_version` | Copied at install time; stamped with whatever version installed them. |
| **Per-repo wiring** | `<repo>/.claude/commands/`, the SessionStart drift hook, `.context/meta.json` `dummyindex_version` | Written by `install` / `ingest`; carries the version that last touched the repo. |

You bring all three to the latest GitHub version in one pass, **non-destructively**, and prove each layer actually moved.

## Hard rules

- **Never** trigger the council, `reconcile`, or a full re-ingest. The only `.context/` write allowed is the deterministic backbone rebuild that `dummyindex install` runs on a git repo. Curated taxonomy (feature names, abstracts, conventions, audits) is left untouched.
- **Never** pass `--break-system-packages` or `sudo`. Match the install method that's already there.
- **Stop on the first failed step** and report the failing command's output. A half-updated install (new CLI, stale skills) is worse than a clean failure.
- **Idempotent.** If the installed version already equals the target, report it and stop — unless the user passed `--force` (then reinstall anyway, e.g. to repair a corrupt install).

## Procedure

Run these as Bash steps, reading the output of each before the next. `REPO=MullaAhmed/dummyIndex`.

### 1. Resolve the target version

```bash
dummyindex --version            # current, e.g. 0.22.0
```

Find the latest **release tag** (preferred — stable), falling back to `main` HEAD:

```bash
# Prefer gh; fall back to the public API; final fallback is the main branch.
gh release view --repo MullaAhmed/dummyIndex --json tagName -q .tagName 2>/dev/null \
  || curl -fsSL https://api.github.com/repos/MullaAhmed/dummyIndex/releases/latest 2>/dev/null \
       | grep -m1 '"tag_name"' | sed -E 's/.*"tag_name": *"([^"]+)".*/\1/' \
  || echo main
```

Normalise the tag (a `v` prefix is fine for the pip ref; strip it only when comparing version numbers). If the target equals the current version and the user did **not** pass `--force`, print `already up to date (X.Y.Z)` and **stop**.

### 2. Detect the install method and reinstall the CLI

Probe in order and use the **first** that lists `dummyindex`:

```bash
uv tool list 2>/dev/null | grep -q '^dummyindex'   && echo "method=uv"
pipx list 2>/dev/null    | grep -q 'package dummyindex' && echo "method=pipx"
# else: pip --user (the common default)
```

Reinstall from the resolved ref (`<REF>` = the tag from step 1, or `main`):

- **uv tool:** `uv tool install --force "git+https://github.com/MullaAhmed/dummyIndex.git@<REF>"`
- **pipx:** `pipx install --force "git+https://github.com/MullaAhmed/dummyIndex.git@<REF>"`
- **pip --user:** `python3 -m pip install --user --force-reinstall --no-cache-dir --upgrade "dummyindex @ git+https://github.com/MullaAhmed/dummyIndex.git@<REF>"`

If the running CLI sits inside a virtualenv (check `python3 -c 'import sys; print(sys.prefix)'` / `which dummyindex`), reinstall into that environment instead of `--user`. When in doubt, mirror exactly where `which dummyindex` resolves.

### 3. Refresh the skills + the current repo's wiring

From the repo root, run the **newly installed** CLI's installer:

```bash
dummyindex install
```

This re-copies the entire skill family (including this `/dummyindex-update`), restamps `~/.claude/skills/dummyindex/.dummyindex_version`, refreshes `<repo>/.claude/commands/`, reinstalls the SessionStart drift hook, and — when the CWD is a git repo — touches `.context/`. **On a curated index (council-enriched feature names, abstracts, conventions), `install` takes the non-destructive path: it refreshes only the deterministic artefacts and advances `.context/meta.json`'s `dummyindex_version` stamp, leaving the curated taxonomy untouched.** Only a brand-new or deterministic-only index is full-built. If the CWD is not a git repo, `install` skips the per-repo step on its own; that is expected, not an error.

> Earlier versions of this skill claimed `install` ran a "non-destructive `build_all`". That was false — a bare `build_all` re-clusters and would shatter a curated index. The installer now guards the curated case explicitly (preserve-on-enriched), so the claim above is finally true.

> Do **not** reach for `dummyindex ingest`, `context reconcile`, or `--recouncil` here — those regenerate curated content and violate the hard rules.

### 4. Verify every layer moved, then report

```bash
dummyindex --version                                            # layer 1: CLI
cat ~/.claude/skills/dummyindex/.dummyindex_version             # layer 2: skills
# layer 3 (only if the repo has .context/):
test -f .context/meta.json && grep -o '"dummyindex_version": *"[^"]*"' .context/meta.json
```

All present layers must now equal the target version. The repo stamp (layer 3) lives in `.context/meta.json` and now advances on the non-destructive deterministic refresh `install` runs — so a curated repo's stamp moves without a re-ingest. If `.context/meta.json` exists but its `dummyindex_version` did not reach the target, **say so loudly** and surface the command output — do not claim success.

Then show what changed: read the top entry of `CHANGELOG.md` in the repo (or `gh release view --repo MullaAhmed/dummyIndex` for the release notes) and summarise it. Finish with a compact before→after table:

```
dummyindex updated: 0.22.0 → 0.23.0
  CLI package   0.22.0 → 0.23.0  ✓
  skill family  0.22.0 → 0.23.0  ✓
  this repo     0.22.0 → 0.23.0  ✓  (.context/ backbone refreshed, curated content untouched)
What's new: <one-line summary of the new CHANGELOG entry>
```

## Notes

- **Self-update:** because step 3 runs the new CLI's `install`, this skill file is replaced by the new version's copy. The next `/dummyindex-update` invocation uses the updated procedure.
- **No GitHub access:** if both `gh` and the API are unreachable, step 1 falls back to `main` — still an update, just unversioned-by-tag. Tell the user you used `main` rather than a release.
- **Repairing a stale CLI:** the classic failure is "I edited dummyindex but the `dummyindex` command still behaves like the old version." `--force` re-runs the whole flow even when versions match, which fixes a copy that drifted from its tag.
