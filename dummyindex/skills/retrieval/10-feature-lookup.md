# Feature lookup

How an agent walks `features/INDEX.json` → a specific feature's docs.

## Input

The agent has a task or question. Examples:
- "Add a new endpoint for password reset."
- "Why does the checkout flow fail with a 500?"
- "Audit the auth feature for IDOR vulnerabilities."
- "Refactor the user model to support multi-tenant."

## Step 1 — Read `features/INDEX.json`

It's small (a few KB even on a 100-feature repo). Read the whole thing in one go.

```json
{
  "features": [
    {
      "feature_id": "authentication",
      "name": "Authentication",
      "summary": "User login, JWT validation, session creation.",
      "member_count": 38,
      "file_count": 12,
      "entry_point_count": 6,
      "flow_count": 5,
      "confidence": "INFERRED",
      "path": "features/authentication/"
    },
    …
  ]
}
```

## Step 2 — Reason

Look at the names + summaries. Pick the features whose summary semantically matches the task. Use the counts as a tiebreaker (bigger features have more surface area; smaller features are focused).

Examples:

- **Task: "password reset"** → likely `authentication`. Also possibly `email-delivery` if separate.
- **Task: "checkout 500"** → `checkout` + maybe `payments` + maybe `users` (auth dependency).
- **Task: "audit auth"** → `authentication`. Optionally `users` (identity).
- **Task: "multi-tenant user model"** → `users` + `tenancy` + every feature that mentions `user_id`.

Pick 1–3 features. **Don't pick more than 5** — re-evaluate if you're tempted.

## Step 3 — Read each chosen feature's `feature.json`

```json
{
  "feature_id": "authentication",
  "name": "Authentication",
  "summary": "...",
  "members": ["app_auth_jwt", "app_auth_login", ...],
  "files": ["app/auth/jwt.py", "app/auth/login.py", ...],
  "entry_points": ["app_auth_login_handler"],
  "flow_ids": ["flow-001", "flow-004"],
  "confidence": "INFERRED"
}
```

This is the machine context. `members` and `files` tell you the scope.

## Step 4 — Read the feature's `README.md`

This is the chairman's synthesized overview. One page. Use this to **confirm** you picked the right feature, and to **navigate** within it.

The README points at:
- `architecture.md` — design + patterns
- `implementation.md` — code idioms + gotchas
- `data-model.md` — schemas + queries
- `security.md` — trust + threats
- `product.md` — user-facing capabilities
- `flows/<flow-id>.md` — narrated sequences

## Step 5 — Pick the right domain section

Based on the task:

| Task signal | Read |
|---|---|
| Adding/modifying behavior | `architecture.md` then `implementation.md` |
| Performance / scale | `implementation.md` + `data-model.md` |
| Security / compliance | `security.md` |
| User-facing change | `product.md` |
| Specific sequence ("what happens when…") | `flows/*.md` (pick by `entry_point_label`) |
| Schema / migration | `data-model.md` |

## Step 6 — When the docs disagree with the code

If a feature's `confidence` is `INFERRED` but the source has clearly changed since the council ran, the auto-refresh hooks should already have triggered a rebuild. If not:

```bash
dummyindex context check --auto-refresh --quiet
```

This is also the case to flag: "the docs claim X but `path:line` shows Y — please advise / I'll rebuild."

## Anti-patterns

- ❌ Reading every `feature.json` upfront. Use INDEX.json's summaries to pick.
- ❌ Reading every section file of a chosen feature. Pick one or two by task type.
- ❌ Skipping straight to `flows/` without confirming the feature is right.
- ❌ Reading source before reading the relevant section file.

## Next

If the task needs symbol-level work (where is `X` defined?), see `20-symbol-lookup.md`.
If the task is about a specific flow, see `30-flow-trace.md`.
