# Phase 3.5 — Reality check

After the per-feature pipeline produces `plan.md` + `concerns.md`, but before
flow narration in Phase 4, run a fact-check on those concrete claims. `spec.md`
is intent-level and is **not** line-checked — it carries no `path:range` claims
worth verifying.

## Why this exists

`plan.md` and `concerns.md` carry concrete claims. Prose is where personas — even
careful ones — slip in claims that read true but don't match the code:

> "`UserService.authenticate()` calls `JWTValidator.verify()` to confirm the token signature."

If the AST shows `UserService.authenticate()` actually calls `TokenService.check_signature()`, that sentence is wrong. The reality-check step catches this *before* it becomes the agent's canonical reference.

## What runs

```bash
dummyindex context reality-check --feature <feature_id> --demote
```

The CLI:

1. Reads the line-checkable docs in `features/<feature_id>/` (`plan.md`,
   `concerns.md`). `spec.md` is intent-level and is skipped.
2. Pulls every concrete claim of the form:
   - `` `X` calls `Y` `` / `` `X` uses `Y` ``
   - `` `X` has method `Y` ``
   - `` `path/to/file.py:42` ``
3. For each claim, checks:
   - **Calls / uses:** both symbols exist in `map/symbols.json`, AND there's a `calls` (or `uses`) edge between them in `features/symbol-graph.json`.
   - **Has method:** both names exist as symbols.
   - **File:line:** the file exists and has at least N lines.
4. Writes `features/<feature_id>/_reality-check.{json,md}`.
5. With `--demote`, if any claim is `contradicted`, flips the feature's `confidence` to `AMBIGUOUS` in `feature.json` + `INDEX.json`.

## Per-feature loop

For each feature that finished Phase 3 in this run:

```
dummyindex context reality-check --feature <id> --demote
```

If the report has `contradicted > 0`:

1. Log via council-log: `--stage 3 --agent reality-checker --status complete --note "contradictions: N"`.
2. Read `_reality-check.md` to see which claims failed.
3. Decide:
   - If the feature ran in mode `deep` and contradiction count is high (>2), schedule a re-council via `/dummyindex --recouncil <feature_id>` after the current pass.
   - Otherwise, leave the `AMBIGUOUS` confidence stamped and surface in the final Phase 6 report so the user knows which features need a manual look.

## Library-API claims (Context7, optional)

The CLI verifies claims against **this repo's** AST. It can't tell you whether a
claimed *external library* API still exists. When `plan.md` or `concerns.md`
asserts a specific library API — e.g. "uses Django's `select_related` to avoid
N+1", "wraps the handler in FastAPI's `Depends`" — confirm the API still exists
at the pinned version via the Context7 protocol in `council/55-context7.md`:
resolve the library id, fetch the topic for that API, and check the symbol is
present (not renamed / removed / deprecated).

- API confirmed present → leave the claim as-is.
- API missing / renamed / deprecated → treat it like an AST contradiction: note
  it in `_reality-check.md` and demote the feature's `confidence` to `AMBIGUOUS`
  for the original persona to revisit.

> If your runtime exposes `mcp__context7__*`, confirm library-API claims as
> above; otherwise fall back to AST-only verification and skip the library check.
> The `.context/` artifacts have the same shape either way — only the quality of
> the prose changes.

## What we deliberately don't fact-check

- Semantic claims ("X is faster than Y", "Z is thread-safe").
- Architectural opinions ("we should refactor X into Y").
- Implementation guidance in playbooks.

The reality check verifies grounding, not judgment. The council is still the authority on what to think; the reality-checker only asks "does this match the AST?"

## Output

`features/<id>/_reality-check.json` schema:

```json
{
  "schema_version": 1,
  "feature_id": "...",
  "claims_total": 12,
  "verified": 9,
  "contradicted": 2,
  "ambiguous": 1,
  "claims": [
    {
      "text": "`App` calls `helper`",
      "source_file": "plan.md",
      "kind": "calls",
      "subject": "App",
      "object": "helper",
      "status": "verified",
      "reason": null
    },
    {
      "text": "`X` calls `Y`",
      "source_file": "concerns.md",
      "kind": "calls",
      "subject": "X",
      "object": "Y",
      "status": "contradicted",
      "reason": "symbol object not found in map/symbols.json"
    }
  ]
}
```

Statuses:

- `verified` — the claim matches the AST.
- `contradicted` — the claim disagrees with the AST. Demote the feature.
- `ambiguous` — both symbols exist but no direct edge, OR the file exists but we can't be sure of the line. Worth a manual look.

## Gating

After Phase 3.5, no feature with `contradicted > 0` should remain at `confidence: INFERRED`. The contract: anything still labeled `INFERRED` has been fact-checked. Anything labeled `AMBIGUOUS` is awaiting a re-council.
