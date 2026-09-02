# Managed doc homes — plan

`confidence: INFERRED`

## Where it lives

**The kernel — one classifier, no I/O** (`dummyindex/context/domains/docguard/`):

| Path | Role |
|---|---|
| `classify.py:53-117` | `classify_doc_path` — the single verdict function. Lexical only. |
| `classify.py:120-168` | `group_strays` — pairs spec+plan, disambiguates slug collisions. |
| `constants.py:33-60` | The closed sets the gate keys on (`PLANNING_SEGMENTS`, `EXCLUDED_DOCS_SUBTREES`, `ROOT_DOC_STEMS`). |
| `enums.py` | `DocKind` (proposal/audit/none), `DocRole` (spec/plan/none). |
| `models.py:21-149` | Seven frozen dataclasses: `DocClassification`, `StrayGroup`, `MoveItem`, `PlannedGroup`, `MoveSkip`, `MovePlan`, `MoveResult`. |
| `errors.py:6-44` | `DocGuardError` → `DocPathError`; `MigrationError` → `MigrationContainmentError`. |
| `__init__.py:19-33` | Public re-export surface (classifier only — `migrate` is imported by path). |

**Consumer A — migration** (batch, mutating, fail-closed):
- `docguard/migrate.py:64-91` `enumerate_strays` → `:94-162` `plan_moves` → `:165-228` `apply_moves`.
- `dummyindex/cli/migrate_docs.py:49-94` — wire-only driver; `:100-139` the `--json` exact-keyset payload; `:212-257` a local `_parse_flags` cloned from `cli/gc.py`.

**Consumer B — write-guard** (per-`Write`, read-only, fail-open):
- `docguard/decision.py:33-63` `decide` — pure classification → PreToolUse payload.
- `dummyindex/cli/guard_doc_write.py:32-96` — wire-only; lazy-imports config + classifier *inside* `_decide` (`:61`, `:67-68`).

**Shared seam and wiring:**
- `dummyindex/context/git.py:39-110` — `is_git_repo` / `run_git` / `is_tracked`. Top-level under `context/`, not inside a domain, per the cross-cutting test in `.context/conventions/folder-organization.md:69-73`.
- `dummyindex/context/domains/config.py:571-591` — `read_doc_guard_settings`, the tolerant hot-path accessor (re-derived post build-train merge: config.py grew beneath it — schema-v5 fleet/maintain work — with zero behavior change here).
- `dummyindex/context/hooks.py:245-267` — `_PRE_TOOL_USE_HOOK`; registered in `_CLAUDE_HOOKS` at `:270-278`.
- Verb registration: `dummyindex/context/enums.py:159-160`, `dummyindex/cli/__init__.py:135-136`, `dummyindex/cli/help.py:531,542`, `docs/guide/07-cli.md:592,598`.

**Tests:** `tests/context/domains/docguard/test_classify.py` (pure gate table), `test_migrate.py` (filesystem + git), `tests/context/test_git.py` (seam semantics incl. off-git degradation), `tests/cli/test_migrate_docs_cli.py`, `tests/cli/test_guard_doc_write_e2e.py` (subprocess-level; pins the two guard invariants — `test_never_returns_two:255-258`, `test_no_subprocess_on_guard_path:342-367`).

## Architecture in three sentences

A **pure functional core** (`classify.py` + `decision.py` — no filesystem, no subprocess, no state) computes every judgement about a markdown path, and two **imperative shells** consume it: `migrate.py` walks the disk and moves files, `guard_doc_write.py` reads hook JSON and prints a decision. The shells never re-derive a rule — they call `classify_doc_path`/`group_strays`, which is the whole point of the design: a **shared kernel** means the batch relocator and the live guard cannot drift into disagreeing about what a stray is. Both shells reach the outside world through narrow, named seams — `context/git.py` for every git question and `config.read_doc_guard_settings` for the two dials — so the feature adds zero cross-domain private imports and no import cycle.

The dominant pattern in the migration half is **plan/apply with whole-batch pre-validation**: `enumerate_strays` → `plan_moves` (validates *every* group and raises before anything moves, `migrate.py:115-120`) → `apply_moves` (dry-run unless `yes=True`, `migrate.py:180-181`).

## Data model

**No database, no tables, no transactions in the SQL sense** — this feature's entire persistent state is the filesystem layout of `.context/` plus two keys in `config.json`. Everything else is an in-memory record chain of frozen dataclasses.

**The in-memory chain** (each stage is immutable; `apply_moves` records the executed method via `dataclasses.replace`, `migrate.py:226` — never mutation):

```
path ──classify_doc_path──> DocClassification
   └──group_strays──> StrayGroup (slug, base_slug, kind, spec_path, plan_path, collision)
        └──plan_moves──> MovePlan{ groups: PlannedGroup[ moves: MoveItem ], skipped: MoveSkip[] }
             └──apply_moves──> MoveResult{ moved: MoveItem[method], skipped: MoveSkip[], dry_run }
```

**Persisted artifacts written by the migration:**
- `.context/proposals/<slug>/proposal.json` — via `proposals.store.write_proposal_json` with `ProposalStatus.DONE`, written only when absent (`migrate.py:254-257`).
- `.context/proposals/<slug>/{spec.md,plan.md}` — the relocated files themselves.
- `.context/audits/<slug>/` — scaffolded by `audit.workspace.ensure_audit` with neutral stamped mode/model constants (`migrate.py:55-56, 243-252`); the report lands on `report.md`.

**Config schema (v2 → v3)**, `config.py:228, 318-320`: `doc_guard_enabled: bool = True`, `doc_guard_allow: tuple[str, ...] = ()`. Two read paths deliberately coexist — strict `Config.from_dict` (raises `ConfigError` on a bad type) for normal use, and the tolerant `read_doc_guard_settings` (`config.py:571-591`, never raises, defaults `(True, ())`) for the Write hot path.

**Transaction analogue:** `plan_moves` pass 1 is the "prepare" phase — every slug validated by its kind's validator and every source/target realpath-contained (`migrate.py:116-120`), raising before pass 2 builds anything. There is **no rollback**: once `apply_moves` starts, a mid-batch failure leaves earlier moves applied. This is survivable only because each individual move is either a `git mv` or a `Path.replace` into a fresh directory, and re-running is idempotent (`test_migrate.py:test_idempotent_second_run_finds_nothing`).

## Key decisions

**Decided: the guard never exits 2 — it speaks only through JSON.** A PreToolUse hook that exits non-zero *blocks* the tool. A classifier false positive that blocked writes would wedge a session with no escape, so `run` wraps everything in a bare `except Exception: return 0` (`guard_doc_write.py:39-42`) and even an arg-parse failure falls through to cwd rather than erroring (`:85-96`). **Rejected:** inheriting `reconcile_gate.run`'s `return 2` arg-error branch — stated explicitly at `guard_doc_write.py:16-17`. The asymmetry is load-bearing: the *guard* fails open, the *migration* fails closed (`migrate_docs.py:83-88` → exit 2), because one runs unattended on every keystroke-adjacent write and the other runs deliberately with `--yes`.

**Decided: classification is location-gated to `docs/`.** A `*-design.md` or `YYYY-MM-DD-*.md` filename is a stray *only* under `docs/` (`classify.py:88-90`); `src/widget-design.md` is never touched. **Rejected:** filename-shape-only heuristics — they would fire on vendored and source-adjacent markdown. **Trade-off, accepted:** a real false-negative surface — a planning doc written to repo-root `PLAN.md`, to `specs/` at the root, or under `.claude/` is invisible to both consumers.

**Decided: unplaceable strays fail open rather than deny.** When a stem carries no alphanumeric content, `_derive_slug` returns `None` (`classify.py:216-217`) and `decide` returns `{}` (`decision.py:46-50`) rather than emitting a `None/spec.md` deny. The rule: *the guard only ever blocks when it can name where the doc belongs.*

**Decided: `slugify`'s `"audit"` fallback is treated as a failure, not a value.** `audit/workspace.py:slugify` always returns something charset-safe, falling back to the generic `"audit"` sentinel — which would silently collapse every symbol-only filename onto one home. `_derive_slug` pre-checks for alphanumeric content to defeat that (`classify.py:206-221`), and applies `validate_slug` defensively on top.

**Decided: `is_git_repo` is branched on before `is_tracked`, once per batch.** `is_tracked` degrades to `True` when there is no repo (`git.py:85-92`, preserved verbatim from `gc/delete.py:_is_tracked`), so it cannot distinguish "untracked in a repo" from "no repo". `apply_moves` resolves git presence once up front (`migrate.py:186`) and `_relocate` branches non-git → `Path.replace` with **zero** git calls, tracked → `git mv`, untracked → replace + `git add` (`migrate.py:260-284`). A `git mv` that unexpectedly refuses falls back rather than aborting the batch (`:277-281`).

**Decided: realpath containment is reimplemented locally, not imported.** `migrate.py:330-344` `_is_within` duplicates the `gc/delete.py` containment pattern. **Trade-off, stated in the code:** ~10 duplicated lines bought in exchange for the feature's zero-cross-domain-private-imports invariant. The same reasoning produced `context/git.py` as an *extracted* seam — the difference is that git access needed three call shapes and a documented degradation contract, while containment is one predicate.

**Decided: migrated proposals get `write_proposal_json`, not `ensure_proposal`.** `ensure_proposal` would scaffold template `spec.md`/`plan.md`/`checklist.md` that collide with the very files being relocated, and an in-flight-looking checklist would make the context-hygiene GC read a finished, migrated artifact as live work. The narrow writer emits only `proposal.json` at terminal `status: done` (`migrate.py:254-257`), byte-identical to `ensure_proposal`'s output (`test_migrate.py:test_proposal_json_byte_stable_and_round_trips`).

**Decided: `--force` fills, it never clobbers.** `_is_present` is `is_file() and st_size > 0` (`migrate.py:347-354`) — an empty placeholder may be filled, a non-empty target is skipped and reported. Combined with the symlink skip in `enumerate_strays` (`:82-89`) and the containment guard, the migration has no path to destroying user content.

**Decided: the guard matches `Write` only.** `Edit`/`MultiEdit` require the target to already exist, so they can only maintain an existing doc — they cannot create a fresh leak (`hooks.py:246-248`, re-asserted at `guard_doc_write.py:49-52`). This halves the hook's blast radius for free.

**Decided: the guard does no I/O beyond one small JSON read.** No git, no subprocess, no full `Config` construction on the hot path — `read_doc_guard_settings` reads two keys and never raises (`config.py:571-591`). Pinned by a test that monkeypatches `subprocess.run` to raise and proves the deny still fires (`test_guard_doc_write_e2e.py:342-367`).

**Decided: default-on everywhere, with a per-repo escape hatch.** `read_doc_guard_settings` returns `(True, ())` for an absent or malformed config, so the guard engages before `.context/` even exists; `doc_guard_allow` globs exempt legitimately-published paths (`guard_doc_write.py:75`). **Known consequence, accepted:** when enabled, the guard denies the superpowers `writing-plans` skill's default writes to `docs/superpowers/{plans,specs}`.

**Decided: the hook rides the existing managed-hooks list rather than a bespoke installer.** Appending `("PreToolUse", _PRE_TOOL_USE_HOOK)` to `_CLAUDE_HOOKS` (`hooks.py:275`) gives install/uninstall/status/`all_installed` for free, and because `_LEGACY_CLAUDE_EVENTS` is `("PostToolUse",)` (`hooks.py:281`) the legacy scrub leaves it alone. It is built from `_SILENT_GATE`, so a global install still gets the defer-check wrapper; stderr is muted but **stdout is not**, since the deny JSON must reach Claude Code (`hooks.py:252-258`).

## Open questions

1. **The git seam has one consumer, not the three it was built for.** `git.py:11-20` names the migration domain, the write-guard, and "eventually `gc`" — but the guard deliberately never calls it (no subprocess on the hot path), and `gc/delete.py:224` still carries its own private `_is_tracked`. Whether gc is meant to migrate onto the seam, or whether the seam is over-built for a single caller, is not answerable from the code.

2. **Nothing invalidates downstream `.context/` artifacts after a migration.** `.context/architecture/overview.md:23-37` still links `docs/specs/…`, `docs/internal/specs/…`, and `docs/superpowers/specs/…` paths that no longer exist on disk in this repo — the migration relocated them and no code wires `migrate-docs` to a `rebuild --changed` or a reconcile. Unclear whether that edge was omitted deliberately (migration is rare, operator re-runs rebuild by hand) or simply missed.

3. **Collision suffixes are computed per-run and are not stable across a partial migration.** `_disambiguate` (`classify.py:236-243`) consults only the slugs used *in this run* — never what already exists under `.context/proposals/`. If `foo` and `foo-2` are enumerated together and only `foo` lands, a second run sees the survivor alone, assigns it the base slug `foo`, finds that home already exists, and skips it (`migrate.py:127-136`) — so it never migrates. Running `--force` at that point would fill the *first* proposal's home with the second doc's files. Whether this sequence is considered reachable, or is guarded by an assumption I could not find, is undetermined.

4. **`doc_guard_allow` glob semantics are unspecified.** Matching is `fnmatch(rel_path, glob)` (`guard_doc_write.py:75`), where `*` crosses `/`. Whether authors are expected to write `docs/superpowers/**` (which `fnmatch` does not treat specially) or `docs/superpowers/*` (which happens to work because `*` spans separators) is not documented anywhere in the code.

5. **A deny is unobservable.** The guard prints only the decision payload and has no `--json`, no counter, and no log. There is no way to answer "how often does this fire, and on what?" — which matters for tuning `PLANNING_SEGMENTS` and for detecting a false-positive regime in the field.

6. **Audit groups carrying both a spec and a plan member produce two files** — the plan member onto `report.md` and the spec member onto `spec.md` (`migrate.py:299-306`). The comment says this is "so no data is dropped," but whether an audit workspace is intended to hold a `spec.md` at all (the audit skill's own workspace shape) is not determinable from this feature's code.
