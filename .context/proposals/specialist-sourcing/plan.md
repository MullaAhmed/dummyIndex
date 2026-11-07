# Plan — Source specialists from catalogs (seed marketplaces incl. ECC, skills.sh, GitHub) before falling back to templates

Code rule for every task: short docstrings only. No long comments. No new framework. Every new test module sets `pytestmark` (`unit` for pure, `integration` for CLI, as `tests/cli/equip/test_equip_reuse.py`).

## Tasks

1. **Network adapters.** `dummyindex/context/domains/equip/plugins/sources.py`, behind the existing `Runner` seam:
   - `list_skills(..., root_fallback: bool = True)`. `False` tries only `skills/`. Existing callers unchanged.
   - `SkillsShRef(repo, skill, installs: int | None)` and `find_skills_sh(capability, *, runner) -> tuple[tuple[SkillsShRef, ...], str | None]`. argv `[shutil.which("npx") or "npx", "--no", "skills", "find", capability]`. Strip ANSI. Regex `owner/repo@skill`. Parse `1.2K` / `3,400` counts. Validate repo and skill charsets. Non-zero exit or zero refs returns `()` plus the first stderr line or `no results`.
   - `RepoMeta(stars, pushed_at, license, archived)` and `repo_meta(repo, *, runner) -> RepoMeta | None` via `gh api repos/<repo>`. Non-zero returns `None`. Bad JSON raises `SourceError`.
   - Tests in existing `tests/context/domains/equip/test_equip_sources.py` with a fake runner: root_fallback off, ANSI parse, count parse, unsafe repo dropped, rc 127, Windows `which` patch, `repo_meta` parse and rc 1.
   Reuse `RunResult`, `default_runner`, `SourceError`, `_is_safe_skill_name`.

2. **Lifecycle guards.** `dummyindex/context/domains/equip/lifecycle/status.py`:
   - `is_sourced(item)`: `source is GENERATED and origin_ref is not None`.
   - `refresh`: skip `is_sourced` next to the `is_evolved` skip; add to `skipped_evolved`.
   - `reset`: when the target `is_sourced`, also set `origin_repo`, `origin_ref`, `marketplace`, `mechanism` to `None`.
   - Tests in existing `tests/context/domains/equip/test_equip_lifecycle.py`: refresh skip, reset clears origin and restores body.

3. **Overlay template.** New `dummyindex/skills/equip/templates/sourced-overlay.md.tmpl`. Frontmatter `name: {{name}}`, `description: {{description}}`, `version: 1.0.0`. `## Repo overlay` with `{{stack}}`, `{{framework}}`, four command slots, `{{conventions}}`, plus both invariant literals. Last line `{{upstream}}`.

4. **Pure sourcing core.** New `dummyindex/context/domains/equip/plugins/sourcing.py`:
   - `SkillCandidate` frozen dataclass: repo, skill, path, channel, marketplace, trusted, installs, meta, ref, text, description.
   - `split_frontmatter(text) -> tuple[str, str] | None` returning (description, body). Input is LF-normalized. One BOM stripped. Line 1 exactly `---`. Closing `---` required. Body is every character after the closing line.
   - `scan_body(text) -> tuple[str, ...]` on the full file. `split_frontmatter` returning `None` yields `block:bad-frontmatter`. NFKC plus whitespace collapse before marker match.
   - `matches(skill, description, capability) -> bool`: `capabilities_for(PluginEntry(...))` plus local `_EXTRA_TOKENS` for api, migration, ci.
   - `qualifies(c) -> bool` and `rank(cands, capability, toolchain) -> tuple[SkillCandidate, ...]`, at most 3.
   - `needs_approval(c, codes) -> bool`: `not c.trusted` or any `warn:` code.
   - Tests: new `tests/context/domains/equip/test_equip_sourcing.py`. Inline constants; invisible chars as `\u` escapes. Cover every code, negative controls, frontmatter cases, rank order and gates, shuffled tie, cap of 3.
   Reuse `capabilities_for` (`plugins/discover.py`), `PluginEntry` (`plugins/marketplace.py`).

5. **Pure compose.** New `dummyindex/context/domains/equip/generate/sourced.py`:
   - `compose_body(*, overlay, name, description, repo, skill, ref, body) -> str`. Replace `{{name}}`, `{{description}}`, then `{{upstream}}` last.
   - `sourced_item(template_item, *, repo, skill, ref, path, upstream_text, marketplace, content) -> EquipmentItem` via `dataclasses.replace`.
   - Tests: new `tests/context/domains/equip/test_equip_sourced.py`: verbatim body tail, no upstream frontmatter key, literal `{{name}}` in upstream, both invariants present, item fields.
   Reuse `render_template` (`generate/render.py`), `content_hash` (`lifecycle/hashing.py`).

6. **CLI orchestration.** New `dummyindex/cli/equip/source.py`, entry `source_rendered(rendered, prior, *, project_root, profile, proj, conventions, approve, dry_run, out) -> tuple[rendered, adopted_names]`:
   - Read `discover._RUNNER` at call time.
   - `available_tools` first. No `gh`: print the degrade line, return `rendered` unchanged.
   - Upstream check for prior `is_sourced` items (spec rule).
   - Targets per spec. Seeds listed once with `root_fallback=False`. Chain to skills.sh, then GitHub (≤3 searches, ≤3 repos each).
   - Per repo cache for `repo_meta` and `resolve_ref`. Shortlist ≤5 per channel per target. Fetch at sha. LF-normalize, scan, split, rank.
   - Adopt or print the needs-`--yes` line. Print top ≤3 per target. `out` is stdout, or stderr under `--json`.
   Reuse `list_skills`, `fetch_file`, `resolve_ref`, `search_github`, `available_tools`, `find_skills_sh`, `repo_meta` (sources.py); `SEED_MARKETPLACES` (marketplace.py); `SPECIALIST_TEMPLATES`, `templated_capabilities` (specialists.py); `render_template`; task 4–5 functions.

7. **Apply wiring.** `dummyindex/cli/equip/dispatch.py`:
   - `run_apply`: `pull_bool_flag` for `source` and `yes`. Pass both to `_run_apply`.
   - `_run_apply`: after `render_generated_set`, when `source`, call `source_rendered`. Add adopted names to `applied`.
   - `_apply_write`: keep branch becomes `state is PRISTINE and (is_evolved(prior_item) or is_sourced(prior_item))`; label `(sourced, kept)` for sourced.
   - `_apply_dry_run`: same predicate prints `(sourced, kept)`.
   - Module usage docstring: one line for `--source [--yes]`.
   - Tests: new `tests/cli/equip/test_equip_source_apply.py`. Helper `_install_sourcing_runner(monkeypatch, *, repos, skills_sh_out, gh_ok=True, npx_rc=0, record)`; copy the shape of `_install_fake_runner` in `tests/context/domains/equip/test_equip_discover_cli.py`, do not import it. Set `HOME`/`USERPROFILE` to `tmp_path`. argv table: `gh --version`; `gh api repos/<r>/contents/skills`; `gh api repos/<r>/contents/<path>?ref=<sha>` (base64); `gh api repos/<r>/commits/HEAD`; `gh api repos/<r>`; `gh search code …`; `gh search repos …`; `<npx> --no skills find <cap>`; anything else `RunResult(1, "", "")`. Cover every CLI acceptance item in the spec.

8. **Help + docs.** `dummyindex/cli/help.py` equip block and `docs/guide/07-cli.md` apply section: `--source`, `--yes`, channel chain, degrade lines, reset path.

9. **Skill companion.** New `dummyindex/skills/equip/sourcing.md`: run `apply --source --dry-run` first, show top 3 with trust and codes, ask before `--yes`, ECC needs `--yes`, offline meaning, reset path. One pointer line in `dummyindex/skills/equip/SKILL.md` under `## Plugin manager`. No other line changes.

10. **Regression.** `python -m pytest tests/ -q --tb=short`. Fix only breakage from tasks 1–9. Likely spots: `test_shared_preparation.py`, `test_cli_doc_sync.py`, `test_equip_verb_required.py`.

11. **Reconcile feature docs.** `.context/features/equip/spec.md` (sourcing behavior), `plan.md` (pipeline step, seams), `concerns.md` (upstream text in prompts, assumed skills.sh format, run-wide `--yes`, weaker overlay canary, body-then-manifest write order, `warn:url` makes auto-adoption rare by design). No proposal or audit paths.

## Reused symbols

`list_skills`, `fetch_file`, `resolve_ref`, `search_github`, `available_tools`, `RunResult`, `default_runner`, `_is_safe_skill_name` (plugins/sources.py); `SEED_MARKETPLACES`, `PluginEntry` (plugins/marketplace.py); `capabilities_for` (plugins/discover.py); `render_template` (generate/render.py); `SPECIALIST_TEMPLATES`, `templated_capabilities` (generate/specialists.py); `content_hash` (lifecycle/hashing.py); `is_evolved`, `refresh`, `reset` (lifecycle/status.py); `_apply_write`, `_apply_dry_run`, `_run_apply`, `run_apply` (cli/equip/dispatch.py); `pull_bool_flag` (cli/equip/common.py); `store_items` (cli/equip/library_verbs.py).

## Critique outcome

Folded: lifecycle gates are GENERATED-only, so sourced items stay `generated` with origin fields; `root_fallback=False` for seeds; channel chain; strict frontmatter; five new `block:` codes; charset validation; no-sha drop; sourcing-local tokens; compose split to `generate/`; explicit fake-runner argv table; targeted acceptance items.
Left: `install.py` vendor-fetch refactor (two-call composition is enough); global API call counter (chain plus caps bound it); star floor for untrusted (`--yes` already gates).
