# Playbook — add an HTTP endpoint

## 1. Find the existing endpoint pattern
- In `tree.json`, look for `api/`, `routes/`, `handlers/`, `controllers/`, or `webhooks/` directories.
- Pick a peer endpoint of the same kind (GET / POST / webhook / etc.) and read it.

## 2. Validate against project conventions
- File naming: see `conventions/naming.md`.
- Handler shape: mirror the peer's signature, error handling, response shape.

## 3. Inputs and outputs
- If a request/response schema exists (Pydantic, Zod, OpenAPI), define one for the new endpoint and add to whatever common schemas module is in use.
- For URL params and query strings, follow the project's typed-parsing pattern.

## 4. Auth and rate limits
- Check whether the peer endpoint uses an auth middleware / decorator. If yes, apply the same.
- Check for a rate-limit pattern (e.g. `@throttle`, `RateLimiter`) and apply if relevant.

## 5. Tests
- Mirror the peer's test file. Cover: happy path, validation failure, auth failure (if applicable), 5xx handling.

## 6. Register the route
- New endpoint must be importable / discoverable. Find where the peer endpoint is registered (router, blueprint, app.include_router, etc.) and add yours.

## 7. Re-index
- `dummyindex context rebuild --changed` refreshes the deterministic map (preserves curated feature docs). If you added new files, also run the reconcile procedure (`dummyindex context reconcile` → place/enrich → `reconcile-stamp`, see `council/65-reconcile.md`) so a feature owns them.
