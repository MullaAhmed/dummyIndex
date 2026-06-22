# Playbook — add a database migration

## 1. Identify the migration tool
- Look for `alembic/`, `migrations/`, `prisma/`, `drizzle/`, `db/migrate/`, or similar in `tree.json`.
- Read the most recent migration to see naming and structure.

## 2. Generate the migration scaffold
- Use the project's tool (`alembic revision`, `prisma migrate dev`, `npx drizzle-kit generate`, etc.). Find the command in `PROJECT.md` or by inspecting the migration tool's config.

## 3. Write the schema change
- Up and down (or migrate / rollback). Both must be exercised.
- Match style of recent migrations: column-naming, defaults, indexes.

## 4. Update the corresponding model / schema
- Find the application-level model (`map/symbols.json` will have the class). Add the field / change with matching types.

## 5. Backfill if needed
- For non-null columns on existing tables, decide: backfill data first, then add NOT NULL? Add nullable and backfill in a follow-up?

## 6. Test
- If the project has a test database, run migrations against it in CI. Add a fixture covering the new state if a model assertion exists.

## 7. Re-index
- `dummyindex context rebuild --changed` refreshes the deterministic map (preserves curated feature docs). If you added new files, also run the reconcile procedure (`dummyindex context reconcile` → place/enrich → `reconcile-stamp`, see `council/65-reconcile.md`) so a feature owns them.

## Risks worth flagging to the user
- Migrations that lock tables for >100ms on large tables — call this out before merging.
- Schema changes without rollback paths.
