# Flow trace

How an agent follows a flow narrative to the actual source.

## When to use

The task is about a **sequence**: "what happens when a user logs in?", "trace the checkout from cart to receipt", "what triggers an email send?".

Don't use this for symbol-level questions (`20-symbol-lookup.md` is faster) or feature-level questions (`10-feature-lookup.md` first).

## Step 1 — Find the right feature

Use `10-feature-lookup.md` to identify the feature containing the flow. Read its `README.md`.

The README's "Entry points" section + the `flow_ids` in `feature.json` are your shortlist.

## Step 2 — Pick the right flow

Each `flows/<flow-id>.json` has an `entry_point_label`. Match by name:

- Task says "user logs in" → look for `flow_id` with entry_point_label `login()` or `handle_login()` or `POST /login`.
- Task says "checkout" → look for `entry_point_label` `checkout()` or `place_order()`.

If multiple flows match, pick the one with the most relevant `files[]` overlap with the task.

## Step 3 — Read the narrated flow markdown

`features/<feature_id>/flows/<flow_id>.md` (senior dev wrote this):

```markdown
# Flow: User login

`confidence: INFERRED`

**Entry point:** `login_handler()` (`app/routes/auth.py:42`)

**What triggers this flow:** HTTP POST to `/api/auth/login`.

## Step-by-step
1. **`login_handler`** (`app/routes/auth.py:42`) — parses the request body…
2. **`AuthService.authenticate`** (`app/services/auth.py:18`) — looks up the user…
3. **`PasswordHasher.verify`** (`app/security/hasher.py:55`) — bcrypt comparison…
4. **`SessionFactory.create`** (`app/auth/session.py:31`) — generates JWT + writes session row.

## Returns
- 200 + `{"token": "..."}` on success.
- 401 + `{"error": "invalid_credentials"}` on auth failure.

## Failure modes
- DB unreachable → 503 with retry-after header.
- Rate limit exceeded → 429.
- Invalid request body → 400 with field-level errors.
```

## Step 4 — Follow citations to source

The narrative cites `path:range` for every step. Use the `Read` tool to load the actual function when:
- The task requires modifying the step.
- The narrative is ambiguous and you need confirmation.
- The narrative is `confidence: INFERRED` and you're about to act on a high-stakes claim.

## Step 5 — Cross-reference with the call graph

`features/symbol-graph.json` confirms the sequence. For each step in the narrative, you can verify the `calls` edge exists:

```python
{"source": "app_auth_login_handler", "target": "app_auth_authenticate", "relation": "calls"}
```

If a step doesn't have a matching edge in the graph, the narrative may have drifted from the code. Re-run `dummyindex context check --auto-refresh`.

## When the flow doesn't exist

- The deterministic flow detector may have missed it (decorator-wrapped entry, dynamic dispatch).
- Or the senior dev's filter discarded what looked like a flow but was actually meaningful.

If you can't find a flow that should exist:

1. Check `features/<id>/feature.json` — is the entry point in `entry_points`?
2. Check `flows/` — was it discarded? (No JSON for it means yes.)
3. If discarded incorrectly: re-run the council for that feature with `/dummyindex --recouncil <feature_id>`.
4. If never detected: the call graph likely missed an edge — flag for human follow-up, then fall back to symbol-level walking.

## Anti-patterns

- ❌ Reading the flow `.json` instead of the narrated `.md`. The narrative has the prose; the JSON is just the spine.
- ❌ Following the flow `.md` blindly without spot-checking `path:line`. The narrative is `INFERRED`; the code is truth.
- ❌ Reconstructing a flow from `tree.json` when a narrated flow `.md` exists.
