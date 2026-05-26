# Context7 lookup protocol (MCP companion)

A reusable companion the other procedures point at. Context7 gives
**per-library, always-current API documentation** so personas don't invent
patterns that look right but don't match canonical advice.

This is the single source of truth for *how* to do a Context7 lookup. The
conventions phase, `/specify`, the critics, and reality-check all reference this
file rather than repeating the steps.

## Graceful fallback (read first)

> If your runtime exposes `mcp__context7__*`, use it as described below;
> otherwise fall back to single-shot reasoning from the source and skip the
> Context7 lookup. The `.context/` artifacts have the same shape either way —
> only the quality of the prose changes.

No Context7 call is ever mandatory. A missing MCP server is not a failure; the
pipeline runs exactly as v0.14 without it.

## The two tools

| Tool (verbatim prefix) | Purpose |
|---|---|
| `mcp__context7__resolve-library-id` | Map a framework/library name → a Context7 library id. |
| `mcp__context7__get-library-docs` | Fetch focused docs for a resolved id, narrowed to a topic. |

Both tools are under the `mcp__context7__*` namespace. If neither is exposed,
take the fallback above.

## Protocol

1. **Resolve the library id.** From the framework/library in question (the
   `framework` field of `dev-pick`, or a library name read off the feature's
   imports / the repo manifests), call `mcp__context7__resolve-library-id` with
   that name. Pick the best-matching id from the result.
   - If resolution is ambiguous or returns nothing → fall back, skip the lookup.

2. **Fetch focused docs.** Call `mcp__context7__get-library-docs` for the
   resolved id, narrowed to the **specific API surface the feature imports**
   (e.g. a topic like `select_related` for Django ORM, `Depends` for FastAPI,
   `@Transactional` for Spring). Do not pull the whole manual — request the
   smallest topic that covers the symbols actually in use.

3. **Quote verbatim, attributed.** Lift the **exact excerpt** (a few lines —
   signature + the one canonical usage note) into the dispatch prompt or the doc
   you're authoring. Mark it as a Context7 excerpt so a later reader knows the
   provenance:

   ```
   > [Context7 — <library id>, topic "<topic>"]
   > <verbatim excerpt>
   ```

4. **Use it, don't restate it.** The excerpt grounds the persona's claims; it is
   not itself the deliverable. The persona still writes its own prose, citing
   `path:range` for what *this* repo does, and uses the Context7 excerpt only to
   confirm the canonical API shape.

## Which libraries to look up

Look up only the libraries the feature **actually imports** — not every
dependency in the manifest. Sources for "what's imported":

- `map/files.json` + `map/symbols.json` — the feature's import surface.
- Repo manifests (`pyproject.toml`, `package.json`, `pom.xml`, `go.mod`, …) for
  version pins, which matter to the critics (CVE-adjacent, deprecated APIs).

Cap the lookups: the dominant framework plus at most 2–3 directly-imported
libraries per feature. More than that and you're documenting the ecosystem, not
the feature.

## Where this protocol is wired

| Call site | What it grounds |
|---|---|
| `council/15-conventions.md` (Phase 1.5) | Seed `coding-practices.md` / `testing.md` with canonical framework docs. |
| `agents/dev.md` + `council/20-specify.md` | Fill the `{{framework_docs}}` slot in the dev dispatch. |
| `agents/critic-database.md` | Current ORM / migration conventions for the detected ORM. |
| `agents/critic-security.md` | CVE-adjacent advice for the pinned library versions. |
| `council/45-reality-check.md` | Confirm a claimed library API still exists. |

Every one of those sites repeats the graceful-fallback clause locally so the
guard is never lost when a procedure is read in isolation.
