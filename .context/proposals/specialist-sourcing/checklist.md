# Checklist — Source specialists from catalogs (seed marketplaces incl. ECC, skills.sh, GitHub) before falling back to templates

> Tick `- [x]` only after verifying. Tests use injected runners and inline fixtures only. No network.

## Wave 1 — adapters, lifecycle guards, overlay template
- [x] `list_skills(root_fallback=)`, `find_skills_sh`, `repo_meta` + tests (dummyindex/context/domains/equip/plugins/sources.py, tests/context/domains/equip/test_equip_sources.py)
- [x] `is_sourced`, refresh skip, reset clears origin + tests (dummyindex/context/domains/equip/lifecycle/status.py, tests/context/domains/equip/test_equip_lifecycle.py)
- [x] Overlay template with both invariant literals and `{{upstream}}` last (dummyindex/skills/equip/templates/sourced-overlay.md.tmpl)

## Wave 2 — pure core
- [x] `SkillCandidate`, `split_frontmatter`, `scan_body`, `matches`, `qualifies`, `rank`, `needs_approval` + tests (dummyindex/context/domains/equip/plugins/sourcing.py, tests/context/domains/equip/test_equip_sourcing.py)
- [x] `compose_body`, `sourced_item` + tests (dummyindex/context/domains/equip/generate/sourced.py, tests/context/domains/equip/test_equip_sourced.py)

## Wave 3 — orchestration
- [ ] `source_rendered`: degrade, upstream check, channel chain, caches, shortlist, approval, output routing (dummyindex/cli/equip/source.py)

## Wave 4 — surfaces
- [ ] `--source`/`--yes` wiring, sourced keep in `_apply_write` and `_apply_dry_run`, usage line + CLI tests with `_install_sourcing_runner` (dummyindex/cli/equip/dispatch.py, tests/cli/equip/test_equip_source_apply.py)
- [ ] Help text and CLI guide for `--source`/`--yes` (dummyindex/cli/help.py, docs/guide/07-cli.md)
- [ ] Skill companion + one pointer line under `## Plugin manager` (dummyindex/skills/equip/sourcing.md, dummyindex/skills/equip/SKILL.md)

## Wave 5 — regression + reconcile
- [ ] Full suite green; fix only breakage from waves 1–4 (`python -m pytest tests/ -q --tb=short`)
- [ ] Reconcile equip feature docs; no proposal/audit paths (.context/features/equip/spec.md, .context/features/equip/plan.md, .context/features/equip/concerns.md)

## Wave 6 — acceptance
- [ ] Acceptance: `apply` and `apply --yes` without `--source` leave the recording runner empty.
- [ ] Acceptance: trusted clean seed fixture is adopted at `.context/equipment/<proj>-db-specialist.md` with `origin_ref`, `package_sha256`, `source=generated`.
- [ ] Acceptance: composed body ends with the LF-normalized upstream body exactly, no upstream frontmatter key, literal upstream `{{name}}`.
- [ ] Acceptance: ECC fixture needs `--yes`; with `--yes` output has `<- affaan-m/ECC/`.
- [ ] Acceptance: each `block:` fixture rejected with and without `--yes`; clean second candidate adopted.
- [ ] Acceptance: benign `curl` and accented text scan empty; `warn:url` needs `--yes`.
- [ ] Acceptance: rank order, gates, shuffled tie and cap of 3 hold.
- [ ] Acceptance: `split_frontmatter` handles CRLF and BOM; `scan_body` on a missing fence gives `block:bad-frontmatter`.
- [ ] Acceptance: skills.sh parser handles ANSI, drops `../x`, rc 127 gives reason; `npx` argv[0] follows patched `shutil.which`.
- [ ] Acceptance: chain skips skills.sh and search when a seed qualifies; ≤3 searches, ≤3 repos each.
- [ ] Acceptance: one `repos/<r>` and one `commits/HEAD` per repo; ≤5 seed `SKILL.md` fetches per target.
- [ ] Acceptance: `gh` rc 127 exits 0 with `gh unavailable — templates kept` and no later `gh api`; skills.sh rc 127 still adopts a seed.
- [ ] Acceptance: user-edited template body byte-preserved by `apply --source`.
- [ ] Acceptance: plain `apply` prints `(sourced, kept)`; `refresh` lists the item in `skipped_evolved`.
- [ ] Acceptance: `reset` restores template and clears origin; deleted body plus `apply` writes template without origin.
- [ ] Acceptance: upstream check silent on same sha; `needs-reverify (upstream changed)` on new text; body unchanged.
- [ ] Acceptance: `--source --dry-run` leaves `.context/` and `.claude/` byte-identical; ≤3 candidate lines per target.
- [ ] Acceptance: `--source --json` stdout parses as JSON.
- [ ] Acceptance: discover tests unchanged; help and `docs/guide/07-cli.md` name `--source` and `--yes`.
