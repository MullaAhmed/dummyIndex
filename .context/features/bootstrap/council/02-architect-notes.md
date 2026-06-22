# Architect notes — bootstrap (stage 2)

## What I changed

- Replaced the loose "Architecture in three sentences" prose with an explicit **Bounded context** section stating the single responsibility: own exactly one marker-delimited region, markers are the only anchor, everything else is opaque preserved prose.
- Promoted the implicit "Architecture" list into a **Pattern catalog** where every pattern is named and pinned to a `path:range` (marker-keyed replace, marker-count dispatch, join-normalizing append, atomic-write-via-tmp-sibling, versioned-body constant, thin-CLI-boundary).
- Added a first-class **Dependencies surfaced** section — the old plan never mentioned the five real callers.
- Tightened "Key decisions" → **Decisions (promoted)**, each tied to a location and, where true, to the downstream consumer that makes it load-bearing.
- Cut filler ("treats … as plain text", redundant data-model restatement of marker literals) and the duplicated marker-string dump (already in spec.md contracts).
- Added `context/__init__.py` re-export to "Where it lives" — it makes the markers package-public/API.

## Patterns named

- **Marker-keyed body-agnostic replace** — `bootstrap.py:80-83`.
- **Marker-count dispatch** — `bootstrap.py:48-64`.
- **Join-normalizing append** — `bootstrap.py:70-77`.
- **Atomic-write-via-tmp-sibling** — `bootstrap.py:86-89` (test `:114-118`).
- **Versioned-body constant** — `bootstrap.py:22-30`.
- **Thin-CLI-boundary** — `cli/bootstrap.py:7-25`.

## Dependencies surfaced

The managed-block convention (`BEGIN_MARKER`/`END_MARKER` + `bootstrap_claude_md`) is shared, not private. Verified callers by grep:

- **install-surface** — `installer/install.py:236-271` (co-owns the convention; bootstraps on the curated-refresh path).
- **legacy migration** — `cli/migrate.py:85-117` (strips legacy block by same markers, re-bootstraps; the live consumer of body-agnostic replace).
- **build pipeline** — `context/build/runner.py:263`.
- **preflight inventory** — `context/domains/preflight/inventory.py:164` (marker as presence sentinel).
- **public re-export** — `context/__init__.py:8-12,75-102` (markers are effectively API).

## Decisions promoted

- Markers are the contract; body is not — and this is load-bearing for `migrate.py`, not local taste.
- Surrounding content is sacred (seam-only normalization).
- Fail loud on ambiguity (raise on unbalanced / >1 block).
- Atomic or nothing.
- Terse body by contract (≤10-line pointer; the shrink's enforced ceiling).
- One target path, owned by the CLI boundary; the renderer never resolves paths.

Also reframed an open question: the substring-matching blind spot is now a three-caller risk (renderer + preflight + migrate share the probe), not a local quirk.

All symbols verified against source: `BEGIN_MARKER` (:11), `END_MARKER` (:15), `UnbalancedMarkersError` (:18), `_V0_BLOCK_BODY` (:22), `generate_managed_block` (:28), `bootstrap_claude_md` (:33), `_append_block` (:70), `_replace_block` (:80), `_atomic_write` (:86); `run` (`cli/bootstrap.py:7`).
