# Bootstrap renderer — plan

confidence: INFERRED

## Where it lives

- `dummyindex/context/output/bootstrap.py` — the renderer: markers, body, marker-counting/append/replace logic, atomic write (`:1-89`).
- `dummyindex/cli/bootstrap.py` — the `context bootstrap` CLI verb: arg/scope parsing, target path, error→exit-code mapping (`:1-25`).
- `dummyindex/cli/common.py` — shared `parse_path_and_root` + `resolve_context_root` reused for scope resolution (`:13-45`, `:103+`).
- `tests/context/output/test_bootstrap.py` — unit suite for every branch (`:1-141`); `tests/test_skills_doc_hygiene.py` asserts the block prose describes reconcile correctly.

## Architecture in three sentences

The renderer treats `.claude/CLAUDE.md` as plain text owning one marker-delimited region, so it counts begin/end markers to choose between create-file, append-block, or replace-in-place, and writes atomically through a `.tmp` sibling. The body is a single versioned constant (`_V0_BLOCK_BODY`) surfaced by `generate_managed_block`, with `block_body` injectable for tests. The CLI is a thin boundary that resolves the scope to `<root>/.claude/CLAUDE.md`, delegates to `bootstrap_claude_md`, and maps `UnbalancedMarkersError` to a stderr message + exit `3`.

## Data model

- `BEGIN_MARKER` = `<!-- dummyindex:begin (managed — do not hand-edit; regenerate with \`dummyindex context bootstrap\`) -->` (`:11-14`).
- `END_MARKER` = `<!-- dummyindex:end -->` (`:15`).
- `managed` = `f"{BEGIN_MARKER}\n{body}\n{END_MARKER}"`, where `body` is the rstripped `block_body` or `generate_managed_block()` (`:38-39`).
- Span keying on replace: `[:begin_idx] + managed + [end_idx:]`, where `end_idx = index(END_MARKER) + len(END_MARKER)` (`:80-83`).

## Key decisions (preserve surrounding content)

- **Marker-keyed, body-agnostic replace.** Replacement is anchored on stable markers, not body text, so a legacy/larger block migrates to the current short pointer without ever rewriting unrelated content (`:80-83`).
- **Surrounding content is sacred.** Append normalizes only the join (trailing `\n\n`/`\n`/none → one blank line) and replace stitches the exact pre/post slices, verified by the mid-file test (`:70-77`, `:80-83`, `tests/context/output/test_bootstrap.py:72-87`).
- **Fail loud on ambiguity.** Unbalanced or >1 blocks raise rather than guess, forcing manual resolution (`:48-59`).
- **Atomic write.** `.tmp` + `replace` guarantees no torn or leftover file (`:86-89`, `tests/context/output/test_bootstrap.py:114-118`).
- **Terse body by contract.** Block stays a ≤10-line pointer to `HOW_TO_USE.md`; the hygiene/short-pointer tests enforce the ceiling that the shrink established (`tests/context/output/test_bootstrap.py:121-132`).

## Open questions

- `BEGIN_MARKER`/`END_MARKER` matching is substring-based (`count`/`index`); a marker appearing inside a fenced code block in surrounding prose would be miscounted — acceptable today but undocumented.
- Only `_V0_BLOCK_BODY` exists; there is no recorded migration ladder beyond marker-keyed replacement, so any future body-format invariants are implicit.
