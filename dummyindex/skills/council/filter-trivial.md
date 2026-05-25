# Trivial-feature filter

Skip the council entirely for features that don't deserve one.

## When the filter fires

A feature is **trivial** if any of:

- `member_count < 3` AND `entry_point_count == 0`. Tiny utility cluster.
- `file_count == 1` AND `entry_point_count == 0`. A single file with no real entry points.
- `name` matches `*-marker`, `typing-*`, `*-aliases`, `*-config`, `*-helpers-*`, `*-utils-*`. Naming-based skip.
- All `members` are type aliases or constants (no callable definitions).

The filter runs after the structural review (so renamed features are evaluated by their new names).

## What "skip" means

The trivial feature gets a **chairman-only** mini-treatment:

1. Single Task call to the chairman persona, with a special prompt:
   > You are the **Chairman** writing a 5-line README for a trivial utility feature `<feature_id>`. Skip the council. Write only `features/<feature_id>/README.md` with: name, one-sentence purpose, files involved, and a "not a real feature" note explaining why this didn't get the full council.
2. No `architecture.md` / `implementation.md` / etc. — just the README.
3. Log: `dummyindex context council-log --feature <id> --stage 0 --agent chairman --status skipped --note "trivial"`.

## Why filter at all

- Cost. A 1-file utility doesn't justify 5 personas + cross-review.
- Signal-to-noise. A council on a trivial feature produces filler the agent has to wade through.
- Time. On NEW-BOS/backend the trivial features are `cors-env-validator`, `empty-package-marker`, `typing-aliases`, `document-extraction`. Skipping them shaves ~$2 and ~5 min off the deep-mode run.

## Override

If the user passes `/dummyindex --no-trivial-filter`, every feature gets the full council regardless. Useful for testing or when "trivial" was misclassified.

## Output

For trivial features:
- `features/<id>/README.md` — 5-line summary.
- Log entry: stage 0, chairman, status skipped.
- No `council/` subfolder, no per-domain docs.

For non-trivial features: proceed to stage 1 (`20-stage1-perspectives.md`).
