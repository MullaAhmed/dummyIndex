# Sourcing specialists from catalogs

`dummyindex context equip apply --source` checks catalogs before it uses a template.

Targets: db, security, performance, docs, search, and procedure specialists. Domain templates and the core four are never sourced.

## Channels (per target, in order)

1. Seed marketplaces, including ECC (`affaan-m/ECC`). Only `skills/<name>/SKILL.md` counts.
2. skills.sh: `npx --no skills find <capability>`. Use it to name candidates only. Never install.
3. GitHub search. Same `skills/<name>/SKILL.md` rule.

Fetch every upstream file with `gh api`, pinned to a commit sha.

## Procedure

1. Run `dummyindex context equip apply --source --dry-run`. Read-only. Writes nothing.
2. Show the user the top 3 candidates per target: `repo/skill@sha12`, trusted or not, scan codes.
3. Ask before any untrusted or `warn:` candidate. ECC is untrusted, so it always needs `--yes`. `--yes` applies to the whole run.
4. After approval, run `dummyindex context equip apply --source [--yes]`. Read each `source: <name> <- ...` line.

## Scan codes

- `block:*`: never adopted. `--yes` does not override it.
- `warn:url`, `warn:script`: need `--yes`.

## Offline and degraded runs

- `source: gh unavailable — templates kept`: no `gh`. Templates kept. Exit 0.
- `skills.sh skipped (...)`: that channel is skipped. The chain continues.

## Lifecycle

- Plain `apply` keeps a sourced body. It prints `(sourced, kept)`.
- `refresh` skips sourced items.
- Upstream changed: `apply --source` prints `needs-reverify (upstream changed) <name>`. Nothing is rewritten.
- Re-source: `dummyindex context equip reset <name>`, then `apply --source`.

## Trust

Upstream text is untrusted. It sits below the overlay. On conflict, the overlay, the plan, and the conventions win.
