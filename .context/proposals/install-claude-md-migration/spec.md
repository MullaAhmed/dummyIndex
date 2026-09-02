# Spec — Wire legacy root CLAUDE.md migration into the fresh-install/bootstrap path

## Intent

A project onboarded by an old dummyindex (pre-v0.7.2 layout) carries a legacy
root-level `CLAUDE.md`. Today it is folded into the canonical
`.claude/CLAUDE.md` only by `context refresh-indexes` and Claude-platform
installs (`build_all(bootstrap=True)`, enriched-reinstall branch). Two surfaces
still leave it dangling:

1. `dummyindex context bootstrap` writes `.claude/CLAUDE.md` but never touches
   a legacy root file.
2. A Codex-only auto-init install (`--platform codex`) passes
   `bootstrap=False` / guards on `use_claude`, so a dummyindex-generated root
   file survives.

3. `context rebuild` (bare full and `--changed`, including its
   enriched-preserved and no-change early exits) refreshes the index but
   never folds a legacy root file.

(User decision 2026-08-25: rebuild IS in scope. Open question 1 resolved YES.)

## Contracts

**Reused seam (no new domain logic).** All folding goes through the existing
chain: `migrate_claude_md_location(out_root)` (`dummyindex/cli/migrate.py:74`)
→ `reconcile_claude_md(out_root)` (`dummyindex/context/output/claude_md.py:96`,
returns frozen `ClaudeMdReconcileResult` at :56 with closed-alphabet
`ClaudeMdAction` = created|consolidated|updated|noop at :33). The helper
already guarantees marker validation before any write, write-then-delete
ordering, idempotent merge (R4), inode-safety (R1), and non-fatal degradation
to `NOOP` + warnings for unreadable/malformed/unwritable inputs.

**Shared guard predicate.** Three consumers need the same two-condition test,
so it lives once next to the wrapper it guards: NEW wire-only
`has_foldable_legacy_claude_md(out_root: Path) -> bool` in
`dummyindex/cli/migrate.py` — True iff `(out_root / "CLAUDE.md").exists()`
AND `not is_project_instruction_path(root, out_root)`
(`dummyindex/codex_guidance.py:111`; Codex config can name CLAUDE.md as a
`project_doc_fallback_filenames` candidate via
`configured_project_doc_fallback_filenames`, :37). Guard 1 exists because
reconcile folds ANY root file (even purely user-authored text) and returns
`CREATED` when no canonical exists; guard 2 because folding would delete the
user's active Codex instruction file and move its content where Codex never
reads.

**Surface 3 — `context rebuild` (`dummyindex/cli/rebuild.py`).**
After every successful rebuild exit — `--changed` skipped (:60),
`--changed` enriched-preserved (:63), `--changed` rebuilt (:71), bare/full
build (:100) — run the guarded fold and keep the printed output style of the
migration wrapper. Rebuild gains fold hygiene only; it still never CREATES
guidance (bootstrap semantics stay exclusive to init/install/bootstrap).

Degradation semantics are part of the contract: every degradation inside
`reconcile_claude_md` is returned (`NOOP` + warnings), not raised; the CLI
wrapper prints the message to stdout and warnings to stderr
(`dummyindex/cli/migrate.py:87-89`). Decision on Open question 2: **fold
failure never changes the exit code** — warn-and-continue, exit stays 0. The
precedent is the defensive best-effort prints in the installer
(`dummyindex/installer/install/project_init.py:99-100,145-146`), not the
dispatcher exception→exit-code rule in
`.context/conventions/coding-practices.md`.

**Surface 1 — `context bootstrap` (`dummyindex/cli/bootstrap.py`).**
Applies to platform `claude|both` only. After all platform writes succeed and
before `return 0`: under the shared predicate, call
`migrate_claude_md_location(out_root)`. The fold runs after both host files are
written so `--platform both` stays one logical operation. Platform
`agents`/`codex` bootstrap performs NO fold (cross-host file surgery is outside
that command's per-host contract).

**Surface 2 — installer auto-init
(`dummyindex/installer/install/project_init.py`).** Both branches fold under
the shared predicate when the Claude reconcile did not already run:

- Enriched-preserved branch: extend the `if use_claude:` reconcile block
  (:95-100) to also run for a Codex-only reinstall when the guard passes.
- Full-build branch: after successful `build_all(...)` (:120-130), fold under
  the shared predicate when `use_claude` is false. Print style follows the
  neighboring lines (`CLAUDE.md (proj) ->  {message}`, :98).

**Known seam behaviors preserved as-is (pre-existing, unchanged by this
proposal):** atomic rewrite via `write_text_atomic` does not preserve a prior
file mode (NamedTemporaryFile 0600, `dummyindex/context/domains/atomic_io.py`)
— same as today's refresh-indexes fold; reconcile reads use universal newlines,
so a CRLF canonical gets LF-normalized; an in-scope symlinked root loses the
link while content is preserved; there is no size cap on folded content.

**Non-goals.** No change to `reconcile_claude_md`, `bootstrap_claude_md`,
`build_all`, or `atomic_io`; no new CLI flags; no size/budget cap on folds; no
behavior change for repos without a legacy root `CLAUDE.md`.

## Acceptance

- [ ] Bootstrap, default platform, tree WITH legacy root `CLAUDE.md` (with a
      dummyindex managed block): exits 0, root file deleted, user content
      folded above the managed block in `.claude/CLAUDE.md`.
- [ ] Degradation path: root file with unbalanced markers → still exit 0,
      `migration warning:` printed to stderr, root file left in place.
- [ ] Bootstrap on a tree with NO root `CLAUDE.md`: exits 0 and prints no
      `migration:` stdout line.
- [ ] `--platform agents` bootstrap WITH a legacy root file: exits 0 and the
      root file is untouched (no fold).
- [ ] `--platform both` bootstrap WITH a legacy root file: exits 0, AGENTS.md
      managed block present AND fold happened.
- [ ] Guard 2: root `CLAUDE.md` listed as a configured Codex fallback doc →
      bootstrap leaves it untouched.
- [ ] Codex-only auto-init install (fresh-repo harness of
      `test_install_codex_auto_init_writes_agents_without_claude_integrations`,
      `tests/test_install.py:1667`) with pre-seeded legacy root file: root
      deleted, content inside `.claude/CLAUDE.md`.
- [ ] Enriched-preserved codex reinstall (curated `.context/` seeded like
      `_make_enriched_context`, `tests/context/output/test_claude_md_build.py:114`)
      with pre-seeded legacy root file: same fold outcome.
- [ ] `context rebuild --changed` on a tree WITH a legacy root file (seeded
      AFTER the index build): exits 0 and folds it; on a tree WITHOUT one,
      output carries no migration line.
- [ ] Bare `context rebuild` (fresh non-enriched tree, or with `--full`) with
      a legacy root file: folds it on success.
- [ ] Full suite green: `uv run pytest -q`; `uv run ruff check .` passes.

## Open questions

1. ~~Should `context rebuild` / `rebuild --changed` also fold?~~ RESOLVED by
   user 2026-08-25: YES — Surface 3 added.
2. ~~Fold-failure exit code~~ — RESOLVED during critique: warn-and-continue,
   exit 0 (see Contracts).
