# Playbook — add an HTTP endpoint

## 1. Find the existing endpoint pattern
- In `tree.json`, look for `api/`, `routes/`, `handlers/`, `controllers/`, or `webhooks/` directories.
- Pick a peer endpoint of the same kind (GET, POST, webhook, etc.). Read it.

## 2. Validate against project conventions
- File naming: see `conventions/naming.md`.
- Handler shape: mirror the peer's signature, error handling, and response shape.

## 3. Inputs and outputs
- If a request or response schema exists (Pydantic, Zod, OpenAPI), define one for the new endpoint.
- Add it to the common schemas module in use.
- For URL params and query strings, follow the project's typed-parsing pattern.

## 4. Auth and rate limits
- Check whether the peer endpoint uses an auth middleware or decorator. If yes, apply the same.
- Check for a rate-limit pattern (e.g. `@throttle`, `RateLimiter`). Apply it if relevant.

## 5. Tests
- Mirror the peer's test file. Cover: happy path, validation failure, auth failure (if applicable), and 5xx handling.

## 6. Register the route
- The new endpoint must be importable and discoverable.
- Find where the peer endpoint is registered: router, blueprint, `app.include_router`, etc. Add the new endpoint there.

## 7. Re-index
- `dummyindex context rebuild --changed` refreshes the deterministic map. It preserves curated feature docs.
- If you added new files, also run `dummyindex context reconcile`.
- Then invoke `/dummyindex --recouncil` on Claude or `$dummyindex --recouncil` on Codex to place and enrich.
- Then run `reconcile-stamp` so a feature owns them. The reconciliation procedure ships inside that installed skill.
