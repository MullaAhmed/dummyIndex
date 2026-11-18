# Context7 lookup protocol (MCP companion)

A reusable companion that other procedures point at. Context7 gives **per-library, always-current API documentation**. Personas use it so they do not invent patterns that look right but do not match canonical advice.

This is the single source of truth for *how* to do a Context7 lookup. The conventions phase, `/specify`, the critics, and reality-check all reference this file rather than repeating the steps.

## Graceful fallback (read first)

> If your runtime exposes a Context7 MCP server, use it as described below. Any tool in a `*context7*` namespace counts. Common namespaces are `mcp__context7__*` and `mcp__plugin_context7_context7__*`. If the server is missing, use single-shot reasoning from the source and skip the Context7 lookup. The `.context/` artifacts have the same shape either way. Only the quality of the prose changes.

No Context7 call is ever mandatory. A missing MCP server is not a failure. The pipeline runs exactly as v0.14 without it.

## The two tools

Context7 ships under more than one namespace. The namespace depends on the install method: a standalone server or a plugin. The docs-fetch tool has two names. Use whichever Context7-shaped tools your runtime exposes. Match by capability, not by one exact string:

| Capability | Tool name(s) seen in the wild |
|---|---|
| Map a framework/library name → a Context7 library id. | `mcp__context7__resolve-library-id` · `mcp__plugin_context7_context7__resolve-library-id` |
| Fetch focused docs for a resolved id, narrowed to a topic. | `mcp__context7__get-library-docs` · `mcp__plugin_context7_context7__query-docs` |

Both live under a `*context7*` namespace. If no Context7-shaped tool is exposed, take the fallback above.

## Protocol

1. **Resolve the library id.** Start from the framework or library in question. Its name comes from the `framework` field of `dev-pick`, or from the feature's imports or the repo manifests. Call the **resolve-library-id** tool in whichever namespace your runtime exposes (see the table above) with that name. Pick the best-matching id from the result.
   - If resolution is ambiguous or returns nothing, fall back and skip the lookup.

2. **Fetch focused docs.** Call the **docs-fetch** tool (`get-library-docs` or `query-docs`, per the table above) for the resolved id. Narrow it to the **specific API surface the feature imports**. For example, use a topic like `select_related` for Django ORM, `Depends` for FastAPI, or `@Transactional` for Spring. Do not pull the whole manual. Request the smallest topic that covers the symbols in use.

3. **Quote verbatim, attributed.** Copy the **exact excerpt** into the dispatch prompt or the doc you author. Keep it to a few lines: the signature and the one canonical usage note. Mark it as a Context7 excerpt, so a later reader knows its source.

   ```
   > [Context7 — <library id>, topic "<topic>"]
   > <verbatim excerpt>
   ```

4. **Use it, do not restate it.** The excerpt grounds the persona's claims. It is not the deliverable. The persona still writes its own prose. It cites `path:range` for what *this* repo does. It uses the Context7 excerpt only to confirm the canonical API shape.

## Which libraries to look up

Look up only the libraries that the feature **imports**. Do not look up every dependency in the manifest. Find the sources for "what is imported":

- `map/files.json` + `map/symbols.json` — the feature's import surface.
- Repo manifests (`pyproject.toml`, `package.json`, `pom.xml`, `go.mod`, …) for version pins. The critics need the pins to judge CVE-adjacent and deprecated APIs.

Cap the lookups. Look up the dominant framework and at most 2–3 directly-imported libraries per feature. More than that documents the ecosystem, not the feature.

## Where this protocol is wired

| Call site | What it grounds |
|---|---|
| `council/15-conventions.md` (Phase 1.5) | Seed `coding-practices.md` / `testing.md` with canonical framework docs. |
| `agents/dev.md` + `council/20-specify.md` | Fill the `{{framework_docs}}` slot in the dev dispatch. |
| `agents/critic-database.md` | Current ORM / migration conventions for the detected ORM. |
| `agents/critic-security.md` | CVE-adjacent advice for the pinned library versions. |
| `council/45-reality-check.md` | Confirm a claimed library API still exists. |

Every one of those sites repeats the graceful-fallback clause locally. The guard is never lost when a procedure is read in isolation.
