# Spec — Source specialists from catalogs (seed marketplaces incl. ECC, skills.sh, GitHub) before falling back to templates

## Intent

User report: equip specialists are basic templates. Equip never pulls proven skills from ECC, skills.sh or other repos.

Today `generate/` calls no discovery code. `specialists.py` fills local templates only. `discover` is Claude-only, dry-run, keyword-ranked, whole-plugin.

Goal: `equip apply --source` looks up catalogs first for each specialist. A qualified upstream skill becomes the specialist body. No qualified candidate means the template stays. Every network call is injectable. Offline runs degrade to templates and say why.

Scope is the minimal path. Reuse `list_skills`, `fetch_file`, `resolve_ref`, `search_github`, `capabilities_for`, `render_template` and the apply ownership merge. No new framework.

## Contracts

### Flag

`dummyindex context equip apply --source [--yes] [--dry-run] [--json] [--for-proposal S] [--root DIR]`

- Without `--source`, apply makes zero runner calls. `--yes` alone does not trigger sourcing.
- `--yes` approves untrusted or `warn:` top candidates in this run. It never approves a `block:` finding.
- `--dry-run --source` makes read-only runner calls and writes nothing.
- With `--json`, sourcing lines go to stderr. Stdout stays valid JSON.

### Targets

A target is a rendered specialist triple whose template `dimension` is `None` or `procedure`. Its capability must be in `templated_capabilities()`. Domain templates and the core four are never sourced.

A target whose prior item `is_sourced` is not re-sourced. It gets the upstream-change check only.

### Channels (fallback chain, per target)

1. Seeds: every `SEED_MARKETPLACES` repo, listed once per run via `list_skills(repo, root_fallback=False)`. Only `skills/<name>/SKILL.md` counts. This covers ECC when it ships `skills/`.
2. skills.sh: only when channel 1 has no qualified candidate. Run `npx --no skills find <capability>`. Parse `owner/repo@skill` tokens and an optional install count.
3. GitHub: only when channels 1–2 have no qualified candidate. `search_github("<capability> skill")`, then `list_skills(root_fallback=False)` on at most 3 repos. At most 3 searches per run.

Trust comes from the repo, never from names. A repo is trusted only when it equals a `trusted=True` seed repo. ECC is an untrusted seed, so ECC adoption always needs `--yes`.

Every `owner/repo` from skills.sh or GitHub must match `^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$`, and neither part may be `.` or `..`. Every skill name must pass `_is_safe_skill_name` and match `^[A-Za-z0-9_.-]+$`. Failures are dropped before any use.

### Match, gate, rank (pure)

- Match: `capabilities_for` on skill name plus frontmatter description, plus a sourcing-local token map for `api`, `migration`, `ci`. The global `_PLUGIN_CAPABILITY_TOKENS` table is unchanged.
- Gate: license SPDX present and not `NOASSERTION`. Repo not archived. Pinned sha resolved. Scan has no `block:` code.
- Sort key, descending: trusted, toolchain hits, installs, stars, `pushed_at`. Final tiebreak ascending: repo, skill.
- Toolchain hits: count of stack label, framework and formatter words in name plus description.
- Gates run before ranking. A rejected candidate drops out. The next qualified candidate may win.
- Return at most 3. Adopt only the first.

### Fetch bound and pinning

- Shortlist by name match. Fetch `SKILL.md` for at most 5 candidates per channel per target.
- Per repo, once per run: `repo_meta` (`gh api repos/<repo>`) and `resolve_ref`.
- `resolve_ref` returns `None`: drop every candidate of that repo with reason `no sha`. Never fetch with `ref=None`.
- Fetch with `fetch_file(repo, path, ref=sha)`. `None` or `SourceError` drops the candidate.

### Scan (pure, deterministic)

Upstream text is LF-normalized once on fetch. `scan_body(text)` scans that full file, frontmatter included. It applies NFKC and whitespace collapse before marker matching. Codes:

- `block:invisible-unicode`: U+200B–U+200F, U+202A–U+202E, U+2060–U+2064, U+2066–U+2069, U+E0000–U+E007F, or U+FEFF after the first character.
- `block:injection`: fixed marker list, case-insensitive. Examples: `ignore previous instructions`, `ignore all previous`, `disregard prior instructions`, `<|im_start|>`.
- `block:pipe-to-shell`: `curl`/`wget` piped into `sh`/`bash`, or `iex` with `iwr`/`irm`.
- `block:html-comment`: any `<!--` in the body.
- `block:remote-image`: a markdown image whose target starts `http`, `https` or `data:`.
- `block:bad-frontmatter`: after one BOM, line 1 is not exactly `---`, or no closing `---` line exists.
- `block:empty` (blank body) and `block:oversize` (over 64 KiB).
- `warn:url`: any `http://` or `https://` link.
- `warn:script`: a `scripts/` path, or a `.sh`/`.py`/`.ps1` invocation.

Benign prose (plain `curl` without a pipe, accented letters) yields no code.

### Approval

- Auto-adopt only when trusted and the scan is empty.
- Untrusted or any `warn:` code needs `--yes`.
- Any `block:` code rejects. `--yes` does not override it.
- No approval: keep the template. Print `source: <name> needs --yes: <owner/repo/skill>@<sha12> [codes]`.
- Every adoption prints `source: <name> <- <owner/repo/skill>@<sha12> [codes]`.

### Sourced body

Written at the template spec's own path: `.context/equipment/<spec-name>.md`. Composition:

1. Frontmatter from `sourced-overlay.md.tmpl`: `name: <spec-name>`, our own fixed `description`, `version: 1.0.0`. No upstream frontmatter key survives.
2. `## Repo overlay`: stack, framework, the four command slots, conventions. It carries the literals `## Ground yourself first (mandatory, before any edit)` and `Stay inside the planned scope.`
3. `## Upstream skill: <owner>/<repo>/<skill>@<sha12>`.
4. Upstream body verbatim after LF normalization: every character after the closing frontmatter line.

`render_template` fills the overlay first. Then `{{name}}` and `{{description}}` are replaced. `{{upstream}}` is replaced last, so upstream `{{...}}` text stays literal.

### Manifest item

Built with `dataclasses.replace` on the template item. `source` stays `generated`. Same `name`, `path`, `kind`, `capabilities`, `grounded_in`, `subagent_type`. Changed fields:

- `origin_repo = owner/repo`, `origin_ref = <full sha>`, `marketplace = <seed name> | skills.sh | github`.
- `capability_id = owner/repo/skill`, `package_source = <SKILL.md repo path>`, `package_version = <sha12>`.
- `package_sha256` = sha256 of the LF-normalized upstream text (UTF-8).
- `invariants` = the two overlay literals. `origin_hash = content_hash(body)`.

`is_sourced(item)` = `source is generated` and `origin_ref is not None`. No schema change. Generated items keep native adapters, lifecycle management and the forced-capability carry-forward.

### Ownership and lifecycle

- `--source` swaps the template triple for the sourced triple before `_apply_write`. Existing rules then apply. A pristine template is replaced. A user-edited body is preserved. A symlinked target is skipped.
- Plain `apply` keeps a pristine sourced item. It prints `(sourced, kept)`. `_apply_dry_run` prints the same.
- `refresh` skips a sourced item and lists it in `skipped_evolved`.
- `reset <name>` restores the template. It clears `origin_repo`, `origin_ref`, `marketplace`, `mechanism`. Package fields come from the fresh item.
- A deleted sourced body is MISSING. Apply writes the fresh template item back, without origin fields.

### Upstream change (only on `apply --source`)

For each prior `is_sourced` item: `resolve_ref(origin_repo)`. Same sha: no line, no fetch. New sha: fetch `package_source` at it. Different sha256: print `needs-reverify (upstream changed) <name>`. Equal sha256: no line. Nothing is rewritten. The pin holds.

### Degrade

- No `gh` (`gh --version` non-zero): print `source: gh unavailable — templates kept`. No further `gh` call. Exit 0.
- skills.sh non-zero or no tokens: print `source: skills.sh skipped (<first stderr line or "no results">)`. Chain continues.
- `search_github` degraded: reuse its warning text.
- Any other per-candidate failure: drop it with one reason line.

### Seams

- Network: `plugins/sources.py` through `discover._RUNNER`, read at call time.
- `npx` argv[0] = `shutil.which("npx")` or `"npx"`. The query is a `Capability` value only. No free text reaches a `.cmd` shim.
- Pure scan/split/match/rank: new `plugins/sourcing.py`. Pure compose/item: new `generate/sourced.py`.
- CLI orchestration: new `cli/equip/source.py`, called from `_run_apply`.

## Decisions

1. Opt-in flag `apply --source`, not a new verb. Existing apply tests stay offline.
2. One adopted skill per specialist. Top 3 print as alternates. Alternates are not adoptable in v1.
3. Domain templates are never sourced. Upstream skills carry procedure, not project knowledge.
4. Sourced items carry only the two overlay invariants. Template-specific invariants are dropped. `reset` restores them.
5. Only `skills/<name>/SKILL.md` layouts are sourced. Root-dir guesses, single-file agents and nested plugin layouts are out.
6. Sourced items stay `source=generated` with origin fields set. This keeps adapters, lifecycle and carry-forward unchanged. Today only vendored installs set `origin_ref`, so `is_sourced` is unambiguous.
7. Body lives only at the canonical `.context/equipment/` path. Native pointers come from existing adapters.
8. No `npx skills add`. skills.sh only names candidates. Fetch always uses pinned `gh api` contents.
9. `npx --no` refuses to install the skills CLI. npm 6 is out of scope.
10. skills.sh output format is assumed: `owner/repo@skill` tokens, optional count like `1.2K`. Parsing is tolerant.
11. Channels form a fallback chain to bound calls. Seeds: about 14 list calls plus per-shortlisted-repo meta and sha.
12. `--yes` is run-wide. Every adoption prints repo, sha and codes. Dry-run shows the same set first.
13. Library: sourcing never calls `library.store`. Adopted names join `applied`; `--lesson-file` stores them via `store_items`.
14. Upstream change is report-only. Re-source: `equip reset <name>`, then `apply --source`.
15. No recency gate, no star floor. Untrusted always needs `--yes`.
16. Code carries short docstrings only. No long comments.
17. Upstream text is LF-normalized before hash, scan and compose. This matches the LF-normalized package identity rule.
18. `warn:url` gating means most real skills need `--yes`. Rare auto-adoption is the intended safe default.

## Acceptance

- [ ] `apply` and `apply --yes` without `--source` leave a recording fake runner empty.
- [ ] `apply --source`, trusted clean seed fixture: body at `.context/equipment/<proj>-db-specialist.md`; item has `origin_ref` = fixture sha, `package_sha256` = sha256 of fixture text, `source=generated`.
- [ ] Composed body ends with the LF-normalized upstream body exactly. It holds no upstream frontmatter key. Upstream `{{name}}` text stays literal.
- [ ] ECC fixture candidate without `--yes`: template stays; output has `needs --yes`. With `--yes`: adopted; output has `<- affaan-m/ECC/`.
- [ ] Each `block:` code fixture is rejected with and without `--yes`; output names the code; a clean second candidate is adopted instead.
- [ ] Benign `curl` prose and accented text yield an empty scan. A `warn:url` body needs `--yes`.
- [ ] Rank: trusted beats higher-star untrusted; equal trust orders by toolchain, installs, stars; unlicensed, archived and no-sha drop; shuffled full ties give one order; at most 3 returned.
- [ ] `split_frontmatter`: CRLF and BOM inputs split correctly; `scan_body` on a missing fence yields `block:bad-frontmatter`.
- [ ] skills.sh parser: ANSI stdout yields `(repo, skill, installs)`; unsafe `../x` repo dropped; rc 127 yields no refs plus reason.
- [ ] `npx` argv[0] equals the patched `shutil.which` result; `"npx"` when it returns `None`.
- [ ] Channel chain: no skills.sh or search argv when a seed qualifies; at most 3 searches and 3 repos each otherwise.
- [ ] Two targets on one repo record exactly one `repos/<r>` and one `commits/HEAD` argv. Eight seed name matches record at most 5 seed `SKILL.md` fetches.
- [ ] `gh --version` rc 127: exit 0, templates written, output `gh unavailable — templates kept`, no later `gh api` argv.
- [ ] skills.sh rc 127 with seeds serving: seed candidate adopted; output has `skills.sh skipped`.
- [ ] A user-edited template body is byte-preserved by `apply --source`.
- [ ] Plain `apply` after sourcing keeps body and item; output `(sourced, kept)`. `refresh` lists it in `skipped_evolved`.
- [ ] `reset <name>` restores the template; origin fields are `None`. Deleting the body then `apply` writes the template without origin fields.
- [ ] Upstream check: same sha prints nothing and fetches nothing; new sha with new text prints `needs-reverify (upstream changed)`; body bytes unchanged.
- [ ] `apply --source --dry-run`: `.context/` and `.claude/` trees are byte-identical before and after; at most 3 candidate lines per target.
- [ ] `apply --source --json`: stdout parses as JSON.
- [ ] `capabilities_for` and discover tests are unchanged; `dispatch` help and `docs/guide/07-cli.md` name `--source` and `--yes`.
- [ ] `python -m pytest tests/ -q --tb=short` is green.

<!-- dummyindex:consistency:begin -->
## Consistency

**Related features:**

- `equip`
- `extraction-pipeline`
- `source-docs`

**Conventions to honor:**

- `conventions/coding-practices.md`
- `conventions/data-access.md`
- `conventions/folder-organization.md`
- `conventions/naming.md`
- `conventions/testing.md`

<!-- dummyindex:consistency:end -->
