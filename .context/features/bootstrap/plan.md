# Bootstrap renderer — plan

confidence: INFERRED

## Bounded context

The renderer owns **exactly one marker-delimited region** of `<root>/.claude/CLAUDE.md` and nothing else. Its single responsibility: converge that region on the current short pointer to `.context/HOW_TO_USE.md`, idempotently, without ever touching surrounding text. The markers `BEGIN_MARKER`/`END_MARKER` are the *only* anchor — body text is never matched, parsed, or trusted. Everything outside the region is opaque user prose the renderer must preserve byte-for-byte.

## Where it lives

- `dummyindex/context/output/bootstrap.py` — the renderer: markers, versioned body, marker-counting branch logic, atomic write (`:1-89`).
- `dummyindex/cli/bootstrap.py` — the `context bootstrap` CLI verb: arg/scope parsing, target resolution, error→exit-code mapping (`:7-25`).
- `dummyindex/cli/common.py` — shared `parse_path_and_root` + `resolve_context_root`, reused for scope resolution (`:13-45`).
- `dummyindex/context/__init__.py` — re-exports `BEGIN_MARKER`, `bootstrap_claude_md`, `generate_managed_block` as the package's public surface (`:8-12,75-102`).
- `tests/context/output/test_bootstrap.py` — per-branch unit suite (`:1-141`); `tests/test_skills_doc_hygiene.py` asserts the block prose describes reconcile correctly.

## Pattern catalog (named, located)

- **Marker-keyed body-agnostic replace** — `_replace_block` (`bootstrap.py:80-83`). The span is `existing[:begin_idx] + managed + existing[end_idx:]` where `end_idx = index(END_MARKER) + len(END_MARKER)`. Anchoring on markers, never body, is what makes legacy migration free (see Dependencies).
- **Marker-count dispatch** — `bootstrap_claude_md` (`bootstrap.py:48-64`). `begin_count`/`end_count` over the existing text pick exactly one of: create-file, append-block, replace-in-place, or raise. Counts unequal *or* >1 block ⇒ `UnbalancedMarkersError`.
- **Join-normalizing append** — `_append_block` (`bootstrap.py:70-77`). Only the seam between existing content and the new block is normalized (trailing `\n\n`/`\n`/none → one blank line); the prefix is untouched.
- **Atomic-write-via-tmp-sibling** — `_atomic_write` (`bootstrap.py:86-89`). `.tmp` write + `os.replace` ⇒ no torn or leftover file. Proven by `test_bootstrap.py:114-118`.
- **Versioned-body constant** — `_V0_BLOCK_BODY` surfaced by `generate_managed_block` (`bootstrap.py:22-30`), with `block_body` injectable on `bootstrap_claude_md` for tests.
- **Thin-CLI-boundary** — `run` (`cli/bootstrap.py:7-25`): resolve scope → delegate → map the one domain exception to exit `3`. No business logic at the boundary.

## Dependencies surfaced

The managed-block convention is **not private to this feature** — `BEGIN_MARKER`/`END_MARKER` + `bootstrap_claude_md` are a shared contract with five callers. Any change to the marker strings or the region invariant is a cross-feature break.

- **install-surface** (`installer/install.py:236-271`) — auto-init calls `bootstrap_claude_md(project_root/".claude"/"CLAUDE.md")` on the curated-index refresh path. **Shared owner of the managed-block convention.**
- **legacy migration** (`cli/migrate.py:85-117`) — strips a managed block from the legacy `<root>/CLAUDE.md` by the *same markers*, then re-bootstraps under `<root>/.claude/CLAUDE.md`. Relies directly on marker-keyed replace being body-agnostic; this is the live consumer of that decision, not a hypothetical.
- **build pipeline** (`context/build/runner.py:263`) — bootstraps CLAUDE.md as the final build step.
- **preflight inventory** (`context/domains/preflight/inventory.py:164`) — probes `BEGIN_MARKER in claude_md` to detect whether a repo is already bootstrapped. Reads the marker as a presence sentinel.
- **public re-export** (`context/__init__.py`) — markers + functions are package-public, so the marker strings are effectively API.

Contract for callers: the target is always `<out_root>/.claude/CLAUDE.md`; the only raised exception is `UnbalancedMarkersError`; the call is idempotent on content.

## Decisions (promoted)

- **Markers are the contract; body is not.** Replace keys on stable begin/end markers, so a legacy/larger block migrates to the current short pointer in place without rewriting unrelated content (`bootstrap.py:80-83`). This decision is *load-bearing for migrate.py*, not local taste.
- **Surrounding content is sacred.** Append normalizes only the seam; replace stitches exact pre/post slices. Enforced by the mid-file test (`test_bootstrap.py:72-87`).
- **Fail loud on ambiguity.** Unbalanced counts or >1 block raise rather than guess, forcing manual resolution (`bootstrap.py:48-59`).
- **Atomic or nothing.** `.tmp` + `replace` guarantees no torn/leftover file (`bootstrap.py:86-89`).
- **Terse body by contract.** The block stays a ≤10-line pointer to `HOW_TO_USE.md`; the short-pointer + hygiene tests enforce the ceiling the shrink established (`test_bootstrap.py:121-132`). Duplicating navigation here was the bug the shrink fixed.
- **One target path, owned by the CLI boundary.** `cli/bootstrap.py:18` fixes `<out_root>/.claude/CLAUDE.md`; the renderer never resolves paths, keeping scope logic in `cli/common.py`.

## Open questions

- Marker matching is substring-based (`count`/`index` in `bootstrap.py:48-49,81-82`). A marker appearing inside a fenced code block in surrounding prose would be miscounted — and **preflight inventory and migrate share this blind spot** since they use the same substring probe. Acceptable today, undocumented, but now a *three-caller* risk.
- Only `_V0_BLOCK_BODY` exists; there is no recorded migration ladder beyond marker-keyed replacement, so future body-format invariants are implicit. The shared re-export makes a future version bump an API-visible event.
