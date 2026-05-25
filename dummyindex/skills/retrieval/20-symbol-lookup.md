# Symbol lookup

How an agent resolves a symbol name to `path:line` using `map/`.

## Input

A symbol name. Examples:
- `validate_jwt`
- `UserService`
- `process_payment`
- `_internal_helper` (with leading underscore)

## Step 1 — Read `map/symbols.json`

Flat list of every symbol in the codebase:

```json
{
  "symbols": [
    {
      "node_id": "app_auth_validate_jwt",
      "kind": "function",
      "name": "validate_jwt",
      "path": "app/auth/jwt.py",
      "range": [42, 87],
      "parent_id": "app_auth_jwt_py",
      "exported": true
    },
    …
  ]
}
```

Search by `name` (exact or substring). Case-sensitive by default; case-insensitive if needed.

## Step 2 — When multiple matches

For each match:
- Note the `path`, `range`, `parent_id`, `kind`, `exported`.

Disambiguate by:
- `exported: true` first (public API).
- Then by `kind` (class > function > method) if the query suggests a kind.
- Then by `path` (project root paths over deep nested ones).

## Step 3 — Resolve `parent_id`

To find the symbol's containing class/file, follow `parent_id` recursively. `tree.json` makes this efficient — walk from the symbol's node_id upward via the parent chain.

## Step 4 — Read source

Use the `Read` tool with `offset` and `limit`:

```
Read(file_path="<absolute>/app/auth/jwt.py", offset=42, limit=46)
```

(`limit = range[1] - range[0] + a few lines for context`).

## When the symbol isn't in the map

- Could be in a language without tree-sitter coverage (the LLM-fallback extraction may have missed it).
- Could be dynamically generated.
- Could be in a file that's gitignored or in `.dummyindexignore`.

Fall back to a targeted grep, but only after confirming `map/symbols.json` doesn't have it:

```
grep -rn "def validate_jwt\|class ValidateJwt" <repo>/
```

## Cross-references

`features/symbol-graph.json` has every edge. To find callers of a symbol:

```python
calls_into = [
    edge["source"]
    for edge in graph["links"]
    if edge["target"] == "app_auth_validate_jwt"
    and edge.get("relation") in ("calls", "uses")
]
```

Then resolve each `source` node_id via `map/symbols.json` for `path:line`.

## When to use this vs. feature lookup

- **Symbol lookup** — task names a specific identifier you need to find or modify.
- **Feature lookup** — task is about a capability or behavior.

Often you do both: feature lookup first to understand context, then symbol lookup for the exact site to edit.

## Anti-patterns

- ❌ Grepping the source tree for symbols before checking `map/symbols.json`.
- ❌ Loading `map/symbols.json` and dumping the whole list into context — filter to relevant ones first.
- ❌ Trusting a `parent_id` chain without confirming the file path actually exists (stale index possibility — `dummyindex context check`).
