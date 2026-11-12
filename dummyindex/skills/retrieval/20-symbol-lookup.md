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

Search by `name` (exact or substring). Matching is case-sensitive by default. Use case-insensitive matching if needed.

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
- Could be in a file that is gitignored or in `.dummyindexignore`.

Fall back to a targeted grep, but only after confirming `map/symbols.json` does not have it:

```
grep -rn "def validate_jwt\|class ValidateJwt" <repo>/
```

## Cross-references

The symbol graph retains every extracted edge. Ask for a bounded answer:

```bash
dummyindex context graph callers-of app_auth_validate_jwt --limit 20
dummyindex context graph neighbors app_auth_validate_jwt --hops 1 --limit 20
```

`callers-of` follows incoming `calls`. `neighbors` also exposes other relation
kinds, including `uses`. Results cite definitions and edge sites. Both commands
read legacy JSON or a sharded graph transparently. Do not load the full artifact
into the conversation or interpret a storage manifest as an empty graph.

Programmatic consumers use
`dummyindex.export.storage.read_graph_payload(path)` to reconstruct the logical
node-link payload. Original direction is `_src` / `_tgt`. Undirected NetworkX
`source` / `target` ordering is not call direction.

## When to use this vs. feature lookup

- **Symbol lookup** — task names a specific identifier you need to find or modify.
- **Feature lookup** — task is about a capability or behavior.

Often you do both: feature lookup first to understand context, then symbol lookup for the exact site to edit.

## Anti-patterns

- ❌ Grepping the source tree for symbols before checking `map/symbols.json`.
- ❌ Loading `map/symbols.json` and dumping the whole list into context — filter to relevant ones first.
- ❌ Trusting a `parent_id` chain without confirming the file path exists (stale index possibility — `dummyindex context check`).
