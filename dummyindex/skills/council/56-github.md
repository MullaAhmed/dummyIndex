# GitHub release-check protocol (MCP companion)

A reusable companion the security critic points at. A GitHub MCP server gives
**real release history** for a dependency — what version is current, and what the
notes between the pinned version and latest actually say. Neither the repo's AST
nor Context7 (current API docs) carries this: Context7 tells you *how* an API
looks today; the changelog tells you *what changed* and *whether the pin is
stale*.

This is the single source of truth for *how* to do a GitHub release lookup. The
security critic references this file rather than repeating the steps.

## Graceful fallback (read first)

> If your runtime exposes a GitHub MCP server (any `*github*` tool namespace —
> commonly `mcp__github__*` or `mcp__plugin_github_github__*`), use it as
> described below; otherwise fall back to single-shot reasoning from the repo
> manifests and skip the release check. The `.context/` artifacts have the same
> shape either way — only the quality of the prose changes.

No GitHub call is ever mandatory. A missing MCP server is not a failure; the
pipeline runs exactly as v0.15 without it.

## The tools

Use whichever GitHub-shaped tools your runtime exposes — the stems below are
stable across the standalone (`mcp__github__*`) and plugin
(`mcp__plugin_github_github__*`) namespaces. If none is present, take the
fallback above.

| Tool stem | Purpose |
|---|---|
| `search_repositories` | Resolve a library name → its `owner/repo` when you don't already know it. |
| `get_latest_release` | The current release for an `owner/repo` — how far ahead of the pin. |
| `list_releases` | Walk the releases between the pinned version and latest to read the notes. |
| `get_release_by_tag` | Fetch one specific release's notes by tag. |

## Protocol

1. **Only for pinned deps the feature actually imports.** Read the pins from the
   repo manifests (`pyproject.toml`, `package.json`, `pom.xml`, `go.mod`, …) for
   the libraries this feature imports — not every dependency in the manifest.
   Cap it at the dominant framework plus at most 2–3 directly-imported libraries.

2. **Resolve the repo.** If you don't already know the library's `owner/repo`,
   call `search_repositories` to find it. If the match is ambiguous or low
   confidence → fall back, skip this library (do **not** guess a repo; a wrong
   repo yields wrong notes, which is worse than no notes).

3. **Measure the distance.** Call `get_latest_release` for the resolved repo and
   compare to the pinned version. A pin within a minor of latest is unremarkable;
   a pin many majors behind is a concrete, citable concern.

4. **Read the notes that matter.** Use `list_releases` / `get_release_by_tag` to
   read the release notes **between the pinned version and latest**, looking only
   for security-relevant or breaking entries (CVE fixes, advisory references,
   "removed", "deprecated", auth/validation changes). Quote the exact line —
   never paraphrase a CVE into existence.

5. **Use it, don't restate it.** A release note grounds a concern; it is not the
   concern. The critic still writes its own bullet citing `path:range` for the
   code that depends on the stale/affected API, with the release note as the
   evidence the pin is risky.

## What this grounds (and what it does not)

- ✅ "Pinned `<lib>` `X.Y` is N majors behind latest `A.B`; the `A.0` notes flag a
  security fix in the auth path this feature uses (`path:range`)."
- ❌ Inventing a CVE or advisory not present in the notes.
- ❌ Flagging a stale pin with no line of code that depends on the affected API —
  version distance alone is not a security finding.

## Where this protocol is wired

| Call site | What it grounds |
|---|---|
| `agents/critic-security.md` | Whether a feature's pinned dependencies are stale and whether the notes since the pin carry security-relevant fixes. |

The call site repeats the graceful-fallback clause locally so the guard is never
lost when the persona is read in isolation.
