# Codebase scan — author `features/graph.json`

Run **after** the per-feature pipeline (phases 3–4), so feature names and
`spec.md` summaries are real prose rather than `community-7`. One agent, one
artifact, whole repo — this is not a per-feature stage.

You are producing the map a new teammate is shown first: **how this codebase
works, and how it uses AI**, on one screen. `.context/features/graph.html`
renders it; you write only the data.

## Why a human has to author this

The deterministic seed already on disk is honest and useless. It knows every
feature, every file count, every cross-feature call — the *shape* of the code.
It cannot know that `dispatch_batch` is an agent loop, that `openai.py` is a
dead experiment, or that the interesting fact about the billing module is that
it charges Stripe when a trial ends. Shape is extractable. Meaning is not.

So: the seed is your starting draft, not your answer. Expect to keep maybe a
third of its nodes, rename most of them, and add the entire AI surface — which
the seed cannot see at all.

## Inputs

Read in this order. Do **not** start by grepping source.

- `features/INDEX.json` — every feature, its enriched name and summary.
- `features/<id>/spec.md` — what each feature actually does. This is where
  most `service` nodes and most `detail` sentences come from.
- `features/graph.json` — the seed. Your draft.
- `map/symbols.json` — exact `path:line` for every symbol, for `sourceRef`.
- `architecture/overview.md` — stack and top-level layout.

Then, and only then, read source for the two things `.context/` does not model:
the AI surface, and third-party integrations.

## Finding the AI surface

`.context/` clusters by call graph, so an agent, the model it calls, and the
tools it can reach usually land in one undifferentiated feature. Pull them
apart by hand:

- **Where inference happens** — `generateText` / `streamText` / `generateObject`
  / `streamObject`, `messages.create`, `chat.completions`, `@ai-sdk/*`,
  `anthropic`, `openai`, `google-genai`, or the equivalent in this repo's
  language. Each distinct loop is an `agent`.
- **Which models** — the actual model ids passed at those call sites, not the
  ones in the README. A model in a config default that no code path reaches is
  not a model this codebase uses.
- **What models can call** — `tool({...})`, function/tool schemas, MCP servers,
  retrieval helpers. Each is a `tool`.
- **What it talks to** — SDK clients and HTTP calls to services the project
  does not own. Each is an `external`.
- **Where state lives** — databases, caches, vector and search indexes. Each is
  a `store`.

If the repo runs no inference at all, say so with the numbers: `stats` stays at
zero, the chip rows stay empty, and the map is entry points, services, and
stores. A scan of a compiler is not a failed scan.

## The contract

Write this exact shape to `.context/features/graph.json`:

```json
{
  "schema_version": 2,
  "confidence": "INFERRED",
  "project": {
    "name": "string (<=48)",
    "slug": "lowercase-dashed (<=48)",
    "tagline": "one line (<=80, optional)",
    "iconDomain": "favicon domain for the project, e.g. acme.com (optional)",
    "date": "YYYY-MM-DD (today)"
  },
  "stats": { "agents": 0, "models": 0, "tools": 0, "integrations": 0 },
  "topModels":       [ { "id": "gpt-4o", "label": "GPT-4o", "domain": "openai.com" } ],
  "topTools":        [ { "id": "exa", "label": "Exa", "domain": "exa.ai" } ],
  "topIntegrations": [ { "id": "stripe", "label": "Stripe", "domain": "stripe.com" } ],
  "graph": {
    "nodes": [
      { "id": "chat", "label": "Dashboard chat", "kind": "entry", "sub": "/api/chat" },
      { "id": "agent", "label": "Support agent", "kind": "agent", "sub": "streamText",
        "sourceRef": "src/agents/support.ts:42",
        "detail": "Answers tickets with order lookups (<=200, optional)" },
      { "id": "gpt4o", "label": "GPT-4o", "kind": "model", "domain": "openai.com" },
      { "id": "billing", "label": "Billing service", "kind": "service",
        "sourceRef": "src/services/billing.ts" },
      { "id": "pg", "label": "Postgres", "kind": "store", "domain": "postgresql.org" }
    ],
    "edges": [
      { "from": "chat", "to": "agent", "kind": "triggers" },
      { "from": "agent", "to": "gpt4o", "kind": "calls" },
      { "from": "billing", "to": "pg", "kind": "writes", "label": "charges on trial end" }
    ]
  }
}
```

`confidence: "INFERRED"` is load-bearing, not decoration. It is the flag that
stops `dummyindex context refresh-indexes` from overwriting your work with the
seed. Omit it and the next rebuild silently discards this whole stage.

## Rules

These keep every scan readable. They are enforced by `scan-check`, so breaking
one is a round trip, not an opinion.

- **Caps.** `topModels` ≤ 3, `topTools` ≤ 10, `topIntegrations` ≤ 10,
  `graph.nodes` ≤ 60, `graph.edges` ≤ 120. One map holds everything — AI flows
  *and* business logic. Big maps are welcome (the viewer pans); aim for 20–40
  nodes on a substantial codebase. Rich, not sparse — but every node must earn
  its place.
- **One node per agent** when there are ≤ 10 agents. Merge only when they are
  numerous and near-identical, and then say so in `sub`
  (`"12 near-identical scrapers"`). Chain them with `agent → agent` edges when
  one feeds the next.
- **`kind`** is one of: `entry` (trigger / route / page / CLI / webhook),
  `cron` (scheduled job, queue worker), `agent`, `model`, `tool`,
  `service` (internal business-logic module the project owns),
  `store` (DB / cache / index), `external` (3rd-party API).
- **`group`** (≤ 24 chars) tags related nodes into one labelled stack. Group by
  feature/domain the way a team would say it — "Billing", "Ingestion", "Setup
  pipeline" — not by folder. Use 2–3 groups of 3–6 nodes; leave hub-and-spoke
  nodes ungrouped. A group's first node picks its column, so write the group in
  reading order.
- **Lengths.** node `label` ≤ 28, `sub` ≤ 40, edge `label` ≤ 24,
  `detail` ≤ 200, `sourceRef` ≤ 120.
- **Edge `kind`** is one of `calls` / `reads` / `writes` / `triggers`. Set it on
  every edge — the viewer reveals it when a flow is traced. Add an edge `label`
  only when a specific phrase says more than the verb ("charges on trial end").
  **Put the business logic on edges.** Labels are always visible, so a map where
  every edge is labelled is a map nobody reads.
- **`domain`** is a bare favicon host — `openai.com`, `anthropic.com`, `exa.ai`,
  `clickhouse.com` — with no scheme and no path. Add it to anything a
  recognisable company or product owns; omit it for internal nodes (entries,
  crons, services, internal tools). Use the product domain for models
  (`gemini.google.com` for Gemini, `claude.ai` for Claude).
- **`sourceRef`** is the repo path, plus `:line` where a line is meaningful.
  Put one on every node the repo owns — it is what lets a teammate jump from
  the map to the code. Take exact lines from `map/symbols.json`; do not guess.
- **`detail`** is one sentence of what the node does, shown on click.
- **Referential integrity.** Node ids are unique; every edge endpoint names an
  existing node.

## Procedure

1. Read the inputs above. Draft the map on paper first: which 20–40 boxes, and
   which 2–3 groups.
2. `Write` the complete JSON to `.context/features/graph.json`.
3. Validate, and fix everything it reports:

   ```bash
   dummyindex context scan-check
   ```

   It prints every violation in one pass, each with a JSON path
   (`graph.nodes[7].kind: 'microservice' is not one of entry, cron, …`). Re-run
   until it exits `0`.
4. Re-render the viewer around the finished scan:

   ```bash
   dummyindex context refresh-indexes
   ```

   This preserves your `INFERRED` scan and rebuilds `graph.html` from it.

## Checks before you call this done

- Could a new engineer answer "what does this project do?" from the node labels
  alone? If the map reads as a list of module names, it is still the seed.
- Does at least one edge carry a real business-logic phrase?
- Is every model id one you saw at an actual call site?
- Do `stats` match the node counts by kind?
- Does `scan-check` exit `0`?

## Skip logic

- Mode `light`: skip. The deterministic seed stays, and the viewer says so.
- Otherwise: run once, after phase 4.
- If `features/graph.json` already has `confidence: "INFERRED"` and no feature
  has been renamed or added since, skip — it is already authored.

## Output

- `.context/features/graph.json` — the curated scan, `confidence: "INFERRED"`.
- `.context/features/graph.html` — re-rendered by `refresh-indexes`. Opens
  directly in a browser; no server, no network.
