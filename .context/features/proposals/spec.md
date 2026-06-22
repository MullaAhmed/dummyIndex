# Proposal store — spec

confidence: INFERRED

## Intent

Turn a natural-language feature request into a structured, consistency-checked
planning artifact on disk: `.context/proposals/<slug>/`. The `propose` subcommand
scaffolds four files (`proposal.json` + `spec.md` / `plan.md` / `checklist.md`
templates), then runs a deterministic, **no-LLM** consistency scan that records
which existing features the title likely touches and which `.context/conventions/*.md`
docs a plan should honor. The machine-readable `proposal.json` is the head; the
`/dummyindex-plan` skill and the build loop later enrich the prose siblings and the
`reused_symbols` field (an intentional forward-schema field, empty at scaffold time —
`models.py:26-27`).

## User-visible behavior

CLI: `dummyindex context propose --slug S --title "..." [--root DIR] [--force]`
(`cli/propose.py:25-80`). `--slug` and `--title` are both required value flags;
`--root` overrides root resolution; `--force` overwrites an existing proposal.

- Both `--slug` and `--title` required → missing either prints
  `error: --slug <slug> and --title <text> are both required` to stderr, exit `2`
  (`cli/propose.py:43-48`).
- `.context/` must exist → otherwise `error: <dir> not found. Run dummyindex ingest first.`,
  exit `2` (`cli/propose.py:53-58`).
- Unsafe slug → `ProposalSlugError`, stderr, exit `2` (`cli/propose.py:62-64`).
- Existing proposal without `--force` → `ProposalExistsError`, stderr, exit `1`
  (`cli/propose.py:65-67`).
- Success → exit `0`, prints `context propose: <dir> (4 files)`, then a
  `related features:` line and (if any) a `conventions:` line (`cli/propose.py:72-80`).

Scaffold + scan checklist (the work each `propose` run performs, in order):
- Wave 1 (independent): validate slug; resolve `.context/` root.
- Wave 2 (depends on Wave 1): `ensure_proposal` writes the four files atomically.
- Wave 3 (depends on Wave 2): `scan_consistency` ranks related features (top 5) and
  globs convention docs; `apply_consistency` folds the hits into `proposal.json`
  and rewrites the `## Consistency` block in `spec.md`.
- Wave 4 (depends on Wave 3): CLI prints path + related features + conventions.

The scan degrades gracefully: with no `features/INDEX.json` yet, `query` raises
`FileNotFoundError`, related features come back empty `()`, and only the conventions
glob is returned (`scan.py:35-43`, test `test_propose.py:137-142`).

## Contracts

Public surface, re-exported from the package `__init__.py:21-49`:

- `validate_slug(slug: str) -> str` — `store.py:36-51`. Lowercases, rejects empty /
  out-of-charset (`a-z0-9-_`) / leading-or-trailing `-`. Raises `ProposalSlugError`.
  Guards against `../` traversal.
- `proposals_root(context_dir: Path) -> Path` — `store.py:54-56`. `<ctx>/proposals`.
- `proposal_dir(context_dir: Path, slug: str) -> Path` — `store.py:59-61`.
  `<ctx>/proposals/<validated-slug>`.
- `ensure_proposal(context_dir, slug, title, *, force=False) -> tuple[str, ...]` —
  `store.py:64-101`. Creates the dir + four template files atomically; returns
  repo-relative POSIX paths. Raises `ProposalExistsError` (dir exists, no force) /
  `ProposalSlugError`.
- `read_proposal(context_dir, slug) -> Proposal` — `store.py:104-108`. Loads
  `proposal.json`; raises `FileNotFoundError` if absent.
- `apply_consistency(context_dir, slug, hits) -> Proposal` — `store.py:111-139`.
  Persists hits into `proposal.json` + `spec.md`; returns a **new** frozen `Proposal`
  (input never mutated, via `dataclasses.replace`). Idempotent — rewrites the
  `## Consistency` block in place (`store.py:206-215`).
- `scan_consistency(context_dir, title) -> ConsistencyHits` — `scan.py:23-32`.
  Reuses the `query` retrieval domain (`scan.py:11,37`); top 5 features (`scan.py:17`).
- `Proposal.to_dict() -> dict` / `Proposal.from_dict(payload) -> Proposal` —
  `models.py:29-53`. `from_dict` is tolerant: missing keys default, `status` coerces
  through `ProposalStatus`.
- `run(args: list[str]) -> int` — `cli/propose.py:25-80`. CLI entry.
- Errors: `ProposalError` (base) / `ProposalExistsError(slug, path)` /
  `ProposalSlugError(slug, reason)` — `errors.py:5-26`.

## Examples

```
$ dummyindex context propose --slug add-export --title "Add CSV export"
context propose: /repo/.context/proposals/add-export (4 files)
  related features: cli-export, formatters
  conventions:      conventions/coding-practices.md, conventions/data-access.md
```

Scaffolded `proposal.json` (`store.py:83-89`, `models.py:29-38`):

```json
{
  "schema_version": 1,
  "slug": "add-export",
  "title": "Add CSV export",
  "status": "planned",
  "related_features": [],
  "conventions": [],
  "reused_symbols": []
}
```

Re-run safety (test `test_propose.py:185-197`): second run without `--force` exits `1`;
with `--force` overwrites and `title` becomes the new value.
