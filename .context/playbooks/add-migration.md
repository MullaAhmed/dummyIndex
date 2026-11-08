# Playbook — add a database migration

## 1. Identify the migration tool
- Look for `alembic/`, `migrations/`, `prisma/`, `drizzle/`, `db/migrate/`, or similar in `tree.json`.
- Read the most recent migration to see naming and structure.

## 2. Generate the migration scaffold
- Use the project's tool: `alembic revision`, `prisma migrate dev`, `npx drizzle-kit generate`, etc.
- Find the command in `PROJECT.md`, or by inspecting the tool's config.

## 3. Write the schema change
- Write up and down (or migrate and rollback). Both must be exercised.
- Match style of recent migrations: column naming, defaults, indexes.

## 4. Update the corresponding model / schema
- Find the application-level model in `map/symbols.json`. It lists the class.
- Add the field or change with matching types.

## 5. Backfill if needed
- For non-null columns on existing tables, choose an order.
- Option one: backfill data first, then add NOT NULL.
- Option two: add nullable, then backfill in a follow-up.

## 6. Test
- If the project has a test database, run migrations against it in CI.
- Add a fixture covering the new state if a model assertion exists.

## 7. Re-index
- `dummyindex context rebuild --changed` refreshes the deterministic map. It preserves curated feature docs.
- If you added new files, also run `dummyindex context reconcile`.
- Then invoke `/dummyindex --recouncil` on Claude or `$dummyindex --recouncil` on Codex to place and enrich.
- Then run `reconcile-stamp` so a feature owns them. The reconciliation procedure ships inside that installed skill.

## Risks worth flagging to the user
- Migrations that lock tables for >100ms on large tables. Call this out before merging.
- Schema changes without rollback paths.
