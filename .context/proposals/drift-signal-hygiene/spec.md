# Spec — Classify mtime noise out of drift, add drift ack CLI, JSON output, and a labeled badge split

> Scaffolded by `dummyindex context propose`. Flesh out the intent
> and contracts below, then keep the **Acceptance** checklist honest.

## Intent

Field sessions on curated indexes (BOS-Mono frontend/backend, Jun–Aug 2026) show a
recurring loop: the SessionStart badge and drift report count rows the user cannot act
on or dismiss — "im still seeing 13 drifts?", "fix the 24 drifts" → "i still see 24
drift", "can i clear git stash or will it fix the 158 drift?". Two failure classes:

1. **History-moved noise.** A rebase/checkout/stash rewrites mtimes; files whose bytes
   match what the docs were written against still show as stale. Today the only filter
   is `_content_unchanged` against `cache/manifest.json` — but on a curated index that
   manifest is frozen at the last *full* build (see proposal
   `enriched-refresh-manifest-stamp`), so it cannot express "the docs describe *this*
   byte state".
2. **No dismissal path.** When a row is a false positive for this machine/workflow,
   there is no CLI to record that judgement; the assistant must answer "No CLI 'mark
   verified'" and the row resurfaces every session.

Also: the hook prints one undifferentiated `[ctx: N drift]` where N mixes mtime rows
with commit-anchored signals — users read it as one number and it goes stale mid-session.

Who: every agent + human working in a curated `.context/` repo (dummyindex's own repo
currently shows the orphaned-anchor variant of this confusion).

## Contracts

- **Row classification.** `compute_drift` gains a per-row basis check. New cached
  artifact `.context/cache/doc-basis.json` (gitignored, same tier as
  `cache/freshness-badge`) maps `feature_id → {rel_path: blob_sha}` and is written by
  `context reconcile-stamp` (the moment docs are declared fresh). Row classes:
  - `edited` — current blob sha differs from the basis sha (real change since the docs
    were declared fresh).
  - suppressed — current sha equals the basis sha → history moved under the index;
    never rendered as an mtime row.
  - Fallback chain when no basis entry exists: manifest sha (`_manifest_shas`) →
    legacy mtime-only behaviour. Absent both → conservative report (row stays).
- **DriftReport extension.** `DriftReport` gains `edited_rows` semantics via a new
  field `suppressed_count: int = 0` (frozen dataclass stays backward-compatible; all
  existing defaults preserved). `rows` keeps meaning "renderable mtime rows".
- **Ack store.** New verb `dummyindex context drift-ack --feature <id> [--path <rel>]`
  `[--reason <text>] [--list] [--clear]`. Writes append-only entries to
  `.context/cache/drift-acks.json`: `{feature_id, path?, acked_sha, reason?, ts}`.
  An ack suppresses a row only while the file's blob sha equals `acked_sha` — any edit
  auto-expires the ack. Off-git repos work identically using content sha256 instead of
  blob sha.
- **JSON output.** `plan-update --json` prints a stable envelope:
  `{"edited": [...], "anchored": {"unassigned_new_files": [...], "awaiting_enrichment":
  [...], "drifted_features": [...]}, "suppressed": N, "acked": N}` — exit code stays 0,
  stdout-only, no change when `--json` absent.
- **Badge split.** `compute_badge` renders labeled counts:
  `[ctx ✓]` unchanged; otherwise `[ctx: E edited · A anchored]` (segments omitted when
  zero; `anchored` = unassigned + awaiting + extra drifted features, de-duplicated as
  today). The statusline reader (`statusline.py`) consumes the same cache file — string
  format only, no parser change expected, verified by test.
- **Summary relabel.** `render_drift_summary` mtime section header becomes
  a new "### Edited since docs" section header (addition — mtime rows are headerless today) and gains a one-line note when `suppressed_count > 0`
  ("N mtime-touched files matched their doc-basis and were suppressed").
- **Invariants.** No LLM calls; deterministic; off-git safe; every new cache file is
  atomic-written via `write_text_atomic`; nothing in `cache/` is ever committed.

## Acceptance

- [ ] `python -m pytest tests/context/test_drift.py -k basis` green: a file whose blob sha
      equals its basis entry is suppressed even when mtime is newer than all feature docs.
- [ ] `python -m pytest tests/context/test_drift.py -k ack` green: an acked row disappears;
      editing the file makes it reappear (ack expiry).
- [ ] `python -m pytest tests/cli/test_plan_update_json.py` green: `--json` envelope has
      exactly the documented keys; plain mode output byte-identical to before on a
      no-drift repo.
- [ ] `python -m pytest tests/cli/ -k badge` green: badge shows `[ctx: 2 edited · 1 anchored]`
      shape; `[ctx ✓]` when clean.
- [ ] `stamp_reconciled` writes `doc-basis.json` (test in `tests/context/build/test_reconcile.py`);
      refused stamps do not touch it.
- [ ] Full suite green: `python -m pytest tests/ -q --tb=short`.

<!-- dummyindex:consistency:begin -->
## Consistency

**Related features:**

- `tree-enrich`
- `session-memory`
- `install-surface`
- `build-loop`
- `equip`

**Conventions to honor:**

- `conventions/coding-practices.md`
- `conventions/data-access.md`
- `conventions/folder-organization.md`
- `conventions/naming.md`
- `conventions/testing.md`

<!-- dummyindex:consistency:end -->
