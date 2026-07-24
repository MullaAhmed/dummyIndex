# Codebase scan — author `features/graph.json`

Run **after** the per-feature pipeline (phases 3–4), so feature names and
`spec.md` summaries are real prose rather than `community-7`. One agent, one
artifact, whole repo — this is not a per-feature stage.

You are producing the map a new teammate is shown first: **how this codebase
works, and how it uses AI**, on one screen. `.context/features/graph.html`
renders it; you write only the data.

## Why this is an edit, not a blank page

The deterministic seed on disk is a **ranked shortlist**, not a dump.
Extraction runs personalized PageRank over `features/symbol-graph.json`
(entry-point symbols seeded hardest, test files down-weighted, shortlist
written to `features/seed-rank.json`), and the seed's node selection and
ordering are rank-driven: the features and entry points it kept are the ones
the call graph leans on hardest. Every seed node carries
`evidence: "EXTRACTED"` and — wherever a ranked symbol resolves — a
`symbolRef` pinning it to a real symbol-graph node.

What the seed still cannot know is meaning. It cannot know that
`dispatch_batch` is an agent loop, that `openai.py` is a dead experiment, or
that the interesting fact about the billing module is that it charges Stripe
when a trial ends. Shape is extractable; meaning is not. And it cannot see
the AI surface at all.

So the job is: **edit the ranked shortlist.** Keep the nodes that earn their
place, rename and merge the ones whose labels read as module names, drop the
noise, promote the AI surface the seed cannot see, and put verbs and business
logic on the edges. Do not discard the seed and invent boxes from a blank
page — a node you invent has no `symbolRef` to stand on, and a map that
throws away a ranked draft usually rediscovers it, badly.

## Inputs

Read in this order. Do **not** start by grepping source.

- `features/graph.json` — the ranked seed. Your draft.
- `features/graph-communities.json` — one card per symbol-graph community:
  stable `slug`, `size`, owning `feature`, one-line `summary`, top `members`
  by PageRank with `path:line`. This is the **group scaffold**: `group` tags
  come from these cards (or from `features/INDEX.json` features), never from
  improvisation.
- `features/INDEX.json` — every feature, its enriched name and summary.
- `features/<id>/spec.md` — what each feature actually does. This is where
  most `service` renames and most `detail` sentences come from.
- `map/symbols.json` — exact `path:line` for every symbol, for `sourceRef`.
- `architecture/overview.md` — stack and top-level layout.

Then, and only then, read source for the two things `.context/` does not
model: the AI surface, and third-party integrations. While you hunt,
`dummyindex context graph callers-of <symbol>` / `neighbors <symbol>` answer
"is this actually wired in?" with file:line citations — and `--json` gives
you exact node ids to reuse as `symbolRef` values.

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
      { "id": "chat", "label": "Dashboard chat", "kind": "entry", "sub": "/api/chat",
        "symbolRef": "routes_chat_post", "evidence": "EXTRACTED" },
      { "id": "agent", "label": "Support agent", "kind": "agent", "sub": "streamText",
        "sourceRef": "src/agents/support.ts:42", "symbolRef": "support_run_agent",
        "evidence": "INFERRED",
        "detail": "Answers tickets with order lookups (<=200, optional)" },
      { "id": "gpt4o", "label": "GPT-4o", "kind": "model", "domain": "openai.com",
        "evidence": "INFERRED" },
      { "id": "billing", "label": "Billing service", "kind": "service",
        "sourceRef": "src/services/billing.ts", "symbolRef": "billing-charge",
        "evidence": "INFERRED" },
      { "id": "pg", "label": "Postgres", "kind": "store", "domain": "postgresql.org",
        "evidence": "INFERRED" }
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

Optional means absent: a field you did not set is **omitted**, never emitted
as `null` or `""`.

## Rules

These keep every scan readable. They are enforced by `scan-check`, so breaking
one is a round trip, not an opinion.

- **Caps.** `topModels` ≤ 3, `topTools` ≤ 10, `topIntegrations` ≤ 10,
  `graph.nodes` ≤ 120, `graph.edges` ≤ 240. One map holds everything — AI
  flows *and* business logic. Aim for 40–80 nodes on a substantial codebase
  (the viewer pans; rich beats sparse) — the headroom above that is for
  promoting the AI surface, not for keeping plumbing. Every node must earn
  its place.
- **`symbolRef`** pins a box to the extraction layer: a node `id` from
  `features/symbol-graph.json` or a community `slug` from
  `graph-communities.json` (≤ 120 chars). Put one on **every node the repo
  owns** — keep the seed's, and for nodes you add or rename take ids from the
  community cards' `members[].id` or from `dummyindex context graph … --json`
  output. Never type one from memory: `scan-check` resolves each ref against
  the artifacts, and an unresolved ref is an error. Models, externals, and
  third-party stores don't get one.
- **`evidence`** goes on every node, one of two values. `EXTRACTED` — the
  node survived from the seed **verbatim** (same id, label, kind).
  `INFERRED` — you added, renamed, merged, or otherwise reshaped it.
  Renaming a seed node flips it to `INFERRED`; that is the point — the flag
  records exactly where judgment entered the map, and the viewer renders the
  two distinctly.
- **One node per agent** when there are ≤ 10 agents. Merge only when they are
  numerous and near-identical, and then say so in `sub`
  (`"12 near-identical scrapers"`). Chain them with `agent → agent` edges when
  one feeds the next.
- **`kind`** is one of: `entry` (trigger / route / page / CLI / webhook),
  `cron` (scheduled job, queue worker), `agent`, `model`, `tool`,
  `service` (internal business-logic module the project owns),
  `store` (DB / cache / index), `external` (3rd-party API).
- **`group`** (≤ 24 chars) tags related nodes into one labelled stack. Every
  group must map to a real community card in `graph-communities.json` (or a
  feature in `features/INDEX.json` when one card is too fine-grained) — the
  display name may read better than the slug ("Billing", not
  `billing-charge-invoice`), but the *membership* must correspond to a
  grouping the code actually has. Do not invent a grouping the graph cannot
  back. At 40–80 nodes use roughly 4–8 groups of 3–8 nodes; leave
  hub-and-spoke nodes ungrouped. A group's first node picks its column, so
  write the group in reading order.
- **Lengths.** node `label` ≤ 28, `sub` ≤ 40, edge `label` ≤ 24,
  `detail` ≤ 200, `sourceRef` ≤ 120, `symbolRef` ≤ 120.
- **Edge `kind`** is one of `calls` / `reads` / `writes` / `triggers`. Set it
  on every edge — the viewer reveals it when a flow is traced. The seed only
  knows `triggers` and `calls`, so part of the edit is re-verbing: a service
  that persists flips to `writes`, one that loads an artifact to `reads`. Add
  an edge `label` only when a specific phrase says more than the verb
  ("charges on trial end"). **Put the business logic on edges.** Labels are
  always visible, so a map where every edge is labelled is a map nobody reads.
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

1. Read the inputs above. Then go through the seed node by node and decide,
   for each: **keep** (it earns its place and the label already reads as
   prose — leave it byte-identical, `evidence: "EXTRACTED"` and all),
   **rework** (right box, wrong words — rename or merge it, set
   `evidence: "INFERRED"`), or **drop** (plumbing that doesn't change the
   story).
2. Add what the seed cannot see: agents, models, tools, stores, externals,
   crons. Every added node is `INFERRED`; the repo-owned ones still get a
   `sourceRef` **and** a `symbolRef`.
3. Group with `graph-communities.json`: pick the 4–8 communities/features
   that tell the story and tag their nodes; leave the rest ungrouped.
4. Re-verb the edges, and put the business logic on the few that deserve a
   label.
5. `Write` the complete JSON to `.context/features/graph.json`.
6. Validate, and fix everything it reports:

   ```bash
   dummyindex context scan-check
   ```

   It prints every violation in one pass, each with a JSON path
   (`graph.nodes[7].kind: 'microservice' is not one of entry, cron, …`),
   including any `symbolRef` that doesn't resolve. Warnings (a check that
   could not run, e.g. no extraction artifact on disk to resolve refs
   against) are printed but don't fail. Re-run until it exits `0`.
7. Re-render the viewer around the finished scan:

   ```bash
   dummyindex context refresh-indexes
   ```

   This preserves your `INFERRED` scan and rebuilds `graph.html` from it.

## Checks before you call this done

- Could a new engineer answer "what does this project do?" from the node labels
  alone? If the map reads as a list of module names, it is still the seed.
- Does every repo-owned node carry a `symbolRef` that resolves, and every node
  an `evidence` value?
- Is any node still marked `EXTRACTED` that you actually touched? Renamed or
  merged means `INFERRED`.
- Does every `group` correspond to a `graph-communities.json` card or an
  `INDEX.json` feature?
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
