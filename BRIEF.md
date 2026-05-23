# Project Brief — dummyIndex v2: Context Engine for Claude Code

**Status:** **Locked v1.0** as design north-star (2026-05-24). See `V0_SCOPE.md` for the buildable slice.
**Date:** 2026-05-24
**Name:** **dummyIndex** (this is an evolution of the existing dummyindex/dummyindex project, not a new product)
**Repo:** This repo — `/mnt/windows-ssd/Projects/memory/dummyindex/`
**Relationship to existing dummyindex:** dummyIndex today emits a one-shot knowledge graph (`dummyindex-out/graph.html|json|md`) for *human* exploration. dummyIndex v2 keeps that capability and adds a **persistent, agent-shaped `.context/` folder** that lets Claude Code (and any other coding agent) navigate the codebase by walking a PageIndex-style hierarchical tree instead of grepping. The graph engine, AST extraction, flow/feature hypergraphs, and HTML viewers are all reused — what's new is the on-disk contract for agent consumption, the planner, the MCP tree-walk surface, and the convention/audit subsystems.

---

## 1. Mission

Drop into any existing codebase and produce a `.context/` folder that lets a Claude Code agent answer "where do I add X?" or "what does Y touch?" **without grepping**. The agent reads a reasoning-friendly hierarchical index (PageIndex-style) instead of doing repeated file-reads and keyword searches — which both burns tokens and produces shallow understanding.

**Success metric:** On a representative codebase, a Claude Code agent given the same task with `.context/` available uses **≥50% fewer tool calls at no worse than baseline implementation quality**. (Tokens follow tool calls; quality is the constraint we hold steady. The [Codebase-Memory paper](https://arxiv.org/abs/2603.27277) showed a 10× token cut but quality dropped 92%→83%; we deliberately trade some of that compression back for parity-or-better quality. We measure both per phase and refuse to ship a phase that regresses quality, even if it cuts tokens.)

---

## 2. Why this exists (vs dummyindex, Aider, etc.)

| Tool | What it gives the agent | What it doesn't |
|---|---|---|
| **dummyindex** (current) | One-shot knowledge graph as HTML/JSON for human exploration | Not designed for agent retrieval at task time; not a stable on-disk contract |
| **Aider repo-map** | Token-budgeted ranked symbol summary, refreshed per turn | Lives in Aider; not portable; not feature-aware; flat |
| **Cursor `@codebase`** | Vector RAG over file chunks | Black box; no reasoning trace; chunk artifacts |
| **OpenViking** | Filesystem-style memory with L0/L1/L2 tiers | Document-oriented; not code-aware |
| **PageIndex** | Hierarchical reasoning index for docs | Not code-aware; not feature/flow-aware |
| **dummyIndex v2** (this) | Persistent `.context/` folder: PageIndex-style code tree + feature/flow graphs + conventions + playbooks + MCP for tree-walk retrieval | — |

The wedge: **persistent, reasoning-navigable, code-shaped, plan-aware**. Not a viewer, not a vector store, not an inline summarizer.

---

## 3. Architecture pillars

1. **Deterministic-first.** Anything derivable from AST/git/config is computed without LLM calls. LLM calls are reserved for summaries, naming, and convention inference. Borrowed wholesale from dummyindex's two-tier design.
2. **PageIndex-style hierarchical tree.** The index is a JSON tree with `node_id`, `title`, `summary`, `type`, `start`, `end`, `children`. The agent walks it via MCP, not via embeddings. ([PageIndex methodology](https://github.com/VectifyAI/PageIndex))
3. **Three-tier loading** ([OpenViking](https://github.com/volcengine/OpenViking)). Each node has an `abstract` (1 sentence), `overview` (≤200 tokens), `detail` (full file/range). The agent pulls the smallest tier that answers the question.
4. **Confidence-tagged** (dummyindex-derived). Every edge and inference labeled `EXTRACTED` / `INFERRED` / `AMBIGUOUS`. The agent sees what's known vs guessed.
5. **Personalized ranking** ([Aider's PageRank trick](https://aider.chat/docs/repomap.html)). Given a task description, score nodes by relevance and surface a short list.
6. **Live, incremental** (dummyindex cache, SHA-256 keyed). Re-runs only re-process changed files. `--watch` mode rebuilds on save.
7. **Plan-aware** ([KARIMO-influenced](https://github.com/opensesh/KARIMO)). The same engine that indexes also drafts feature plans that *reference* concrete node IDs, so the executor inherits real anchors instead of re-discovering them.

---

## 4. The `.context/` folder layout

```
.context/
├── INDEX.md                    # Hand-readable TOC + how to use this folder
├── PROJECT.md                  # Mission, audience, deployment, owners (LLM-summarized)
├── tree.json                   # PageIndex-style hierarchical reasoning tree (root of MCP traversal)
├── tree.html                   # Optional human viewer (reuses dummyindex's D3 viewer)
│
├── conventions/                # LEARNED from code, not stated
│   ├── naming.md               # "Components: PascalCase under app/components/"
│   ├── style.md                # Quirks: tabs vs spaces, comment style, ordering
│   ├── patterns.md             # "Repositories live in <pkg>/repo/, return Result<T,E>"
│   └── anti-patterns.md        # Mined from git: reverts, "fix" commits, removed code
│
├── stack/
│   ├── languages.md            # Languages + versions
│   ├── frameworks.md           # React, Django, etc. with versions and entry points
│   ├── databases.md            # Schemas, connection points, migration tooling
│   ├── infrastructure.md       # Docker/K8s/Vercel/AWS surface
│   └── dependencies.md         # Direct deps with role: runtime vs dev vs test
│
├── architecture/
│   ├── overview.md             # 1-page architecture write-up
│   ├── data-model.md           # ER diagram + table-to-class map
│   ├── api-surface.md          # All endpoints, handlers, contracts
│   ├── boundaries.md           # Module/service boundaries; what's allowed to talk to what
│   └── diagrams/               # Mermaid + generated SVG
│
├── flows/                      # Hyperedges from entry → terminals (dummyindex's flow synth)
│   ├── index.md
│   ├── <flow-slug>.md          # e.g. "login-flow.md" — files + symbols + ordering
│   └── flows.json
│
├── features/                   # Product-level capabilities (dummyindex's feature synth)
│   ├── index.md
│   ├── <feature-slug>.md       # e.g. "billing.md" — symbols, files, owners, deps
│   └── features.json
│
├── capabilities/               # Installed skills, agents, plugins, MCPs — see §9
│   ├── INDEX.md
│   ├── capabilities.json
│   ├── routing.md              # When to use which capability
│   ├── skills/<name>.md
│   ├── agents/<name>.md
│   ├── mcps/<server>.md
│   ├── plugins/<plugin>.md
│   ├── hooks/<name>.md
│   └── clis/<cmd>.md
│
├── map/
│   ├── files.json              # Path → role, summary, size, churn
│   ├── symbols.json            # Every class/fn/component/const with path:line, kind, summary
│   ├── pagerank.json           # Centrality scores for cold-start ranking
│   ├── god-nodes.md            # Highly connected hubs (touch with care)
│   └── hot-paths.md            # High-churn + high-centrality = "danger zones"
│
├── templates/                  # Operation templates (§10) — parameterized blueprints
│   ├── feature-addition.yaml
│   ├── update.yaml
│   ├── bug-fix.yaml
│   ├── refactor.yaml
│   ├── reorganise.yaml
│   ├── migration.yaml
│   ├── audit.yaml
│   ├── dependency-bump.yaml
│   ├── performance.yaml
│   ├── deprecate-remove.yaml
│   ├── documentation.yaml
│   └── test-backfill.yaml
│
├── playbooks/                  # Generated human-readable narratives derived from templates
│   ├── add-feature.md
│   ├── add-endpoint.md
│   ├── add-migration.md
│   ├── add-component.md
│   └── fix-bug.md
│
├── plans/                      # Staged feature plans (KARIMO-style)
│   └── <draft-slug>.md         # PRD-lite + impact set + acceptance checks
│
├── audit/
│   ├── confidence.md           # EXTRACTED vs INFERRED breakdown
│   ├── stale.md                # Docs reference symbols that no longer exist
│   ├── conflicts.md            # CLAUDE.md says X, code does Y
│   └── coverage.md             # Symbols without tests; tests without symbols
│
├── cache/                      # SHA-256 file-keyed semantic extractions (gitignored)
└── meta.json                   # Schema version, last run, fingerprints, model used
```

**Design notes:**
- Everything except `cache/` is checked in. The folder is the contract.
- Every JSON file has a matching `*.schema.json` so contents are validatable.
- Markdown files are for *humans and LLMs*; JSON files are for *programs and MCP*.

---

## 5. The PageIndex-style tree (the heart)

`tree.json` is the primary retrieval surface. Schema:

```jsonc
{
  "node_id": "n-0",
  "kind": "project|dir|module|file|class|function|component|constant|route|table",
  "title": "dummyindex",
  "path": "/",
  "range": null,                       // for file/symbol nodes: [start_line, end_line]
  "abstract": "Knowledge graph builder for code, docs, and media.",  // L0 (1 sentence)
  "overview_ref": "PROJECT.md#L1-L80", // L1 (loaded by reference, ≤200 tokens)
  "detail_ref": null,                  // L2 (file or range, loaded on demand)
  "confidence": "EXTRACTED",
  "labels": ["entry", "core"],         // free-form tags
  "evidence": ["pyproject.toml", "README.md"],
  "children": [ /* recursive */ ]
}
```

**Levels (typical):**
- L0 Project → L1 top-level dir → L2 module → L3 file → L4 symbol

**Retrieval flow (MCP-driven):**
1. Agent calls `walk(task_description)` → tool returns top-K root branches with their `abstract`s and a PageRank-personalized score.
2. Agent picks a branch, calls `expand(node_id)` → tool returns that node's `overview_ref` content and its immediate children's `abstract`s.
3. Recurse until the agent reaches a leaf (a symbol) and calls `open(node_id)` → returns `detail_ref` (the actual code range).

This is the [PageIndex tree-walk](https://github.com/VectifyAI/PageIndex) adapted to code. No vectors. Every decision the agent makes is interpretable.

**Chunking heuristic (where PageIndex's "natural sections" need translating for code):**
Docs have TOC/headings; code doesn't. dummyIndex's tree boundaries come from the AST, not from token windows:
- **File node:** always created (carries path, language, imports, exports).
- **Class node:** created when present; carries method children.
- **Function node:** created at module scope or as class methods; created for *exported* lambdas/closures only — internal closures are folded into their parent.
- **Big-file fallback:** if a file has no classes and >N (default 600) lines of top-level code, split by top-level region comments (e.g. `// region: routes`) or, lacking those, by contiguous symbol groups.
- **Constants & components:** treated as function-like leaves for tree purposes; `kind` distinguishes them.

The shape of the tree determines retrieval quality, so the heuristic is configurable per project in `meta.json` (and audit-logged when it fires).

---

## 6. CLAUDE.md bootstrap (first-run)

On first run in a repo, dummyIndex:

1. Detects existing `CLAUDE.md` (or runs `/init` semantics if missing).
2. **Appends, never overwrites** a managed block:

```markdown
<!-- dummyindex:begin (managed — do not hand-edit; regenerate with `dummyindex bootstrap`) -->
# dummyIndex — extension of your decision-making for this project

**dummyIndex is part of how you think in this repo.** For this project, your project-specific decisions — what the user actually means, how to plan, which tools/skills/agents to use, which files to touch, which conventions apply — defer to dummyIndex. Its outputs are *inputs to your reasoning*: you still author the response, but you don't form interpretations or pick tools without consulting it, because dummyIndex has indexed context you don't carry.

## How to handle a request

For any non-trivial request:

1. **Call `dummyindex route "<user request>"`** via MCP. This returns:
   - `normalized_prompt` — the codebase-aware rewrite of the request → **use this as your working prompt**, not the raw user message
   - `follow_ups` — surgical disambiguation questions → if non-empty, surface them and wait
   - `context_refs` — `.context/` node IDs the work touches → reference these, don't re-discover via grep
   - `conventions` — naming/style/pattern rules that apply → follow them
   - `capability_refs` — skills, agents, plugins, MCPs to use, with reasons → invoke as directed
   - `tool_choices` — resolved tool decisions (Edit vs Write, which MCP, which Bash) → use these
   - `steps` — ordered plan with dependencies and acceptance checks → execute in order
   - `impact_ranked` — files most likely to need edits → focus here
2. **Execute the plan.** Invoke the named skills/agents/MCPs in step order.
3. **On step failure:** call `route_again(step_id, failure_reason)` for an updated plan — don't improvise.
4. **Don't override casually.** You may diverge from dummyIndex's decisions, but only with a stated reason ("convention conflict between dummyIndex output and observed code at file:line"). Log divergences in `.context/audit/conflicts.md`.

For trivial reads ("what does this function do?") and chat-only messages, skip the route call.

## Individual decision points (if you only need one)

| Decision | Call |
|---|---|
| Interpret the user's prompt | `normalize(message)` |
| Form a plan from an interpretation | `plan_steps(interpretation)` |
| Pick a skill/agent/plugin for a step | `pick_capability(step)` |
| Decide which files to touch | `rank_impact(plan)` |
| Apply project conventions | `conventions(scope)` |
| Ask the user for missing info | `surgical_followups(interpretation)` |

`route()` is the bundled composition. Individual calls exist for refinement.

## Where to find context without MCP

- `.context/INDEX.md` — folder map and navigation guide
- `.context/features/<name>.md` — feature-scoped context
- `.context/flows/<name>.md` — end-to-end execution paths
- `.context/capabilities/INDEX.md` — installed tooling and when to use which
- `.context/conventions/` — naming, style, patterns, anti-patterns
- `.context/playbooks/<task>.md` — recipes for common changes
- `.context/tree.json` — hierarchical reasoning tree (walk via MCP; don't load wholesale)

## Full MCP surface

`route(request)`, `route_again(step_id, reason)`, `normalize(message)`, `plan_steps(interpretation)`, `pick_capability(step)`, `rank_impact(plan)`, `conventions(scope)`, `surgical_followups(interpretation)`, `walk(task)`, `expand(node_id)`, `open(node_id)`, `find_symbol(name)`, `find_flow(query)`, `feature(name)`, `inventory(kind?)`, `rebuild(scope)`, `audit()`.

## Rebuild

After non-trivial changes: `dummyindex rebuild --changed` (incremental) or `dummyindex rebuild` (full).

## Convention

If the index disagrees with the code, the code wins — log in `.context/audit/conflicts.md` and re-run.

## /dummyindex skill (one-shot graph exploration, separate)

The existing `/dummyindex` skill at `~/.claude/skills/dummyindex/SKILL.md` remains available for ad-hoc knowledge-graph exploration (HTML viewer, communities, god-nodes). Trigger with `/dummyindex` for `dummyindex-out/{graph.html,graph.json,GRAPH_REPORT.md}`. That skill is for *humans exploring*; the routing above is for *you executing*.
<!-- dummyindex:end -->
```

The block is **managed and idempotent**: re-running `dummyindex bootstrap` updates only the content between the markers; everything else in CLAUDE.md is left untouched.

---

## 7. Feature planning flow (KARIMO-influenced)

`dummyindex plan "add team invitations"` →

1. **Ranks** files/symbols by relevance to the prompt (personalized PageRank).
2. **Drafts** `.context/plans/team-invitations.md` containing:
   - One-paragraph PRD
   - Impact set: list of files and symbols that will likely change, by `node_id`
   - Re-use candidates: existing functions/components that solve sub-problems
   - Conventions to honor (pulled from `.context/conventions/`)
   - Acceptance checks (tests to write or extend)
   - Risk callouts (god-nodes touched, hot-paths crossed)
3. **Returns** the plan path. Claude Code can then implement against concrete anchors instead of re-discovering them.

Crucial property: the plan is *valid* against the index at write-time. A linter can later flag plans whose node IDs no longer exist (stale plans).

---

## 8. dummyIndex as an extension of CLAUDE.md

**dummyIndex doesn't intercept Claude Code — it extends Claude's project-aware decision-making via instructions in CLAUDE.md.** The managed block (§6) positions dummyIndex as a *first-class part of how Claude decides things in this repo*: every decision Claude would otherwise make from base reasoning + grep is, for this project, informed by a dummyIndex call. dummyIndex's view is privileged because it has indexed context Claude doesn't.

### 8.1 Decision points that route through dummyIndex

The CLAUDE.md directive enumerates the specific decisions that defer to dummyIndex. Each maps to an MCP call; each returns a decision Claude incorporates into its reasoning rather than a final answer that bypasses Claude.

| Decision Claude makes | dummyIndex call | What it returns |
|---|---|---|
| **Interpret the user's prompt** | `normalize(message)` | A codebase-aware rewrite of the request with concrete `node_id` and feature references resolved (e.g. "add tests" → "add pytest unit + integration tests targeting `n-svc-invite-create` and `n-svc-invite-accept` under `tests/billing/`, following `.context/conventions/testing.md`"). |
| **Form a plan** | `plan_steps(interpretation)` | A structured plan: ordered steps, each with action type, target node IDs, dependencies, and acceptance checks. |
| **Choose which skill/agent/plugin to use** | `pick_capability(step)` | The capability (skill name, agent name, MCP tool, plugin) best suited to the step, with reason and alternatives ranked. |
| **Decide which files to touch** | `rank_impact(plan)` | Personalized PageRank over the impact set: the files most likely to need edits, ordered by relevance. |
| **Apply conventions** | `conventions(scope)` | The naming, style, and pattern rules that apply to the files in scope, pulled from `.context/conventions/`. |
| **Ask the user for missing info** | `surgical_followups(interpretation)` | Up to 3 binary or single-fact questions that flip the plan; never open-ended. |

`route(message)` is the **convenience composition** of all six: one round trip that returns a complete bundle. Claude can either call `route` once for the whole shape of the work, or call individual decision points for refinement (e.g. "Claude already has an interpretation, just wants `pick_capability` for step 4").

### 8.2 Why this is an "extension," not a sidecar

These calls are not optional retrieval. The CLAUDE.md directive frames them as *part of how Claude decides in this repo*, in the same way that following the project's coding style or running tests before declaring done is part of how Claude works. dummyIndex's outputs are inputs to Claude's reasoning — Claude still picks the words, structures the response, makes the actual edits — but Claude doesn't *form an interpretation* or *pick a tool* without consulting dummyIndex first, because for this project that's the canonical way to do it.

Practical implication: when a user says "add team invitations," Claude doesn't free-associate from training; it calls `normalize` and gets back the codebase-grounded version, then plans from that. The improvement vs. plain Claude Code isn't a separate retrieval step bolted on — it's that *Claude's reasoning loop runs through dummyIndex* for this project.

#### Why route() instead of CLAUDE.md `@import` of the `.context/` files?

The most obvious alternative is: skip MCP entirely, just `@import .context/INDEX.md`, `.context/features/*.md`, etc. into CLAUDE.md and let Claude reason directly. Four reasons `route()` is the right primitive even though `@import` is available and we use it for the lightweight files:

1. **Selection, not loading.** The tree (`tree.json`) and per-feature/flow files together are far too large to load into context wholesale on a non-trivial codebase. `route()` returns *only the relevant subset* for the current request (the impact set is ~5–20 nodes, not thousands).
2. **Pre-resolution of decisions Claude would otherwise re-derive.** Plain `@import` gives Claude raw material; `route()` returns *resolved decisions*: which capability to use, which tool, which files in priority order, which conventions apply. That's a non-trivial reasoning step pre-computed once on the dummyIndex side instead of re-derived in every Claude turn.
3. **Freshness.** Claude's CLAUDE.md context is captured at session start; the `.context/` folder is regenerated incrementally. `route()` reads the current state — `@import` reads whatever was loaded at the start of the session.
4. **Reasoning-trace audit.** Every `route()` call's input/output is loggable to `.context/audit/routing.log`. `@import` is invisible to the audit subsystem.

The split: `@import` the lightweight summary files (`INDEX.md`, `conventions/*.md`, `capabilities/INDEX.md`) so Claude has a baseline without any MCP calls. Use `route()` (and individual decision-point tools) for *targeted* per-turn decisions that need the full index.

**Caveat on compliance.** CLAUDE.md directives are soft preferences Claude follows when convenient, not enforced rules. Real-world compliance with "use `normalized_prompt` as the working prompt" will be high for top-level decisions and degrade for fine-grained ones (e.g. Edit vs Write tool choice). The success metric in §1 — ≥50% tool-call reduction at no worse than baseline quality — is set against measured behavior, not assumed perfect compliance. We'll learn what Claude actually defers to and what it ignores in Phase 3 evals, then tighten the directive language accordingly.

### 8.3 The bundled `route()` output

For the common case (single instruction, full pipeline), Claude calls `route(message)` and gets:

```jsonc
{
  // Original message echoed
  "raw_request": "add a stripe webhook for successful payments",

  // dummyIndex's codebase-aware rewrite — Claude uses THIS as the working prompt
  "normalized_prompt": "Add a webhook handler at app/webhooks/stripe.py for `payment_intent.succeeded` events. Verify signature with HMAC-SHA256 using STRIPE_WEBHOOK_SECRET. Update the existing `payments` table (n-tbl-payments) via the PaymentRepo (n-cls-payment-repo). Mirror the existing GitHub webhook pattern at app/webhooks/github.py (n-mod-webhook-github).",

  "follow_ups": [],                          // empty if no ambiguity

  // Nodes Claude should reference, not re-discover
  "context_refs": [
    "feature:billing",
    "n-tbl-payments",
    "n-cls-payment-repo",
    "n-mod-webhook-github"
  ],

  // Conventions that apply (auto-pulled from .context/conventions/)
  "conventions": [
    "naming.md#L42 — webhook handlers: snake_case in app/webhooks/<provider>.py",
    "testing.md#L18 — pytest with httpx test client; fixtures from tests/conftest.py",
    "security.md#L7 — all webhook secrets via os.environ.get with KeyError on missing"
  ],

  // Capabilities (skills/agents/plugins/MCPs) Claude should use, with reasons
  "capability_refs": [
    {"kind": "skill",  "name": "tdd-workflow",      "reason": "repo rule: tests-first for new endpoints"},
    {"kind": "agent",  "name": "security-reviewer", "reason": "external-facing webhook; signature verification critical"},
    {"kind": "mcp",    "name": "github",            "reason": "open draft PR at end"}
  ],

  // Tool choices per-step (informs Claude's Bash vs MCP vs Edit decisions)
  "tool_choices": {
    "edit": "Edit",                           // not Write — files exist nearby to pattern-match
    "test_run": "Bash: pytest tests/webhooks/test_stripe.py -xvs",
    "pr_open": "mcp__plugin_github_github__create_pull_request"
  },

  // The plan itself
  "steps": [
    {"id": "s1", "action": "write_test_first", "target": "tests/webhooks/test_stripe.py",
     "skill": "tdd-workflow", "context_refs": ["n-mod-webhook-github"]},
    {"id": "s2", "action": "scaffold", "target": "app/webhooks/stripe.py",
     "guidance": "Mirror n-mod-webhook-github structure"},
    {"id": "s3", "action": "implement", "depends_on": ["s1", "s2"]},
    {"id": "s4", "action": "run_agent", "agent": "security-reviewer", "scope": ["s2", "s3"]},
    {"id": "s5", "action": "open_pr",  "mcp": "github", "depends_on": ["s4"]}
  ],

  // Impact set ranked by personalized PageRank
  "impact_ranked": [
    {"path": "app/webhooks/stripe.py",        "score": 1.00, "kind": "new"},
    {"path": "tests/webhooks/test_stripe.py", "score": 0.92, "kind": "new"},
    {"path": "app/repos/payment_repo.py",     "score": 0.61, "kind": "touch"},
    {"path": "app/config.py",                 "score": 0.34, "kind": "touch"}
  ],

  "acceptance_checks": [
    "Tests in tests/webhooks/test_stripe.py pass",
    "Signature verification present (HMAC-SHA256, STRIPE_WEBHOOK_SECRET)",
    "No new symbol violates .context/conventions/naming.md",
    "security-reviewer agent reports no CRITICAL/HIGH issues"
  ]
}
```

Every field is a *decision dummyIndex has made on Claude's behalf for this repo*. Claude treats `normalized_prompt` as the prompt to work from, `tool_choices` as the resolved tool decisions, and `capability_refs` as the agents/skills to invoke. Claude can still override any of these — but the directive in CLAUDE.md says: don't override casually, because dummyIndex sees the repo and you don't.

Claude executes the plan by invoking the named capabilities in order. Each step's outcome feeds the next. On step failure, Claude can call `route_again(step_id, failure_reason)` to get an updated plan rather than discarding the original.

The plan is **machine-checkable**: a CI hook can verify that referenced `node_id`s and capabilities still exist before allowing execution, so stale plans surface as errors instead of bad edits.

### 8.4 "Surgical follow-ups" — what they are and aren't

> *Surgical* means: a binary choice or a single-fact disambiguation that flips the plan. Not "what do you mean?" — never that.

| Bad (open-ended) | Good (surgical) |
|---|---|
| "What are you trying to do?" | "Webhook for `payment_intent.succeeded` only, or all `payment_intent.*` events?" |
| "Where should this go?" | "There's an existing `app/webhooks/` (Python) and `apps/api/webhooks/` (Node) — which?" |
| "What should the endpoint return?" | "Return 200 immediately and queue, or process inline?" |

Hard cap: **≤3 follow-ups per request**. If the planner can't surface ≤3 surgical questions, it proceeds with its best interpretation and notes assumptions in the plan.

### 8.5 Configurability (the directive is text, not code)

Everything about the directive is editable by the user:

- **Routing policy.** The CLAUDE.md block defaults to "consult dummyIndex for non-trivial requests; skip for trivial reads." A stricter policy (`route_policy = "always"`) or looser (`route_policy = "on_request"`, only when user prefixes with `/dummyindex`) can be set in `.context/meta.json` and re-bootstrapped.
- **Plan confirmation.** In interactive sessions, Claude can be instructed to surface the plan summary and wait for `/approve` / `/edit` / `/cancel`. In non-interactive sessions (CI, batch), the directive switches to auto-execute. Configurable per project.
- **Capability allowlist / denylist.** `.context/meta.json` can restrict which skills/agents/plugins the router is allowed to suggest (useful for orgs with security policies on third-party tooling).
- **Removal.** Delete the managed block and the directive is gone. dummyIndex still works as a library/CLI; Claude just won't reach for it on its own anymore.

### 8.6 Why CLAUDE.md and not hooks/wrappers

- **CLAUDE.md is the canonical Claude Code instruction surface.** Using it keeps dummyIndex aligned with Claude's architecture rather than fighting it.
- **Auditable.** Anyone reading CLAUDE.md sees exactly what dummyIndex asks Claude to do; nothing hidden in hooks or wrappers.
- **Portable.** Cursor / Codex / Gemini that read CLAUDE.md (or their equivalents) inherit the same directive automatically.
- **Composable.** Plays nicely with other CLAUDE.md content, nested CLAUDE.md files in subdirs, and project-level memory. dummyIndex owns one block; the rest is untouched.

---

## 9. Capabilities inventory

For the orchestrator (§8) to name skills/agents/plugins, it has to *know* what's installed. dummyIndex scans and indexes the available tooling into `.context/capabilities/`.

### 9.1 What gets scanned

| Source | Examples | Path(s) |
|---|---|---|
| User-level Claude Code skills | `frontend-design`, `tdd-workflow`, `dummyindex` | `~/.claude/skills/**/SKILL.md` |
| Project-level skills | per-repo skills | `./.claude/skills/**/SKILL.md` |
| User-level agents | `code-reviewer`, `security-reviewer`, `planner` | `~/.claude/agents/**/*.md` |
| Project-level agents | repo-specific | `./.claude/agents/**/*.md` |
| MCP servers | `github`, `supabase`, `vercel`, `linear` | `~/.claude.json` + `./.mcp.json` |
| Hooks | session-start, pre-tool-use, post-tool-use | `~/.claude/settings.json` + `./.claude/settings.json` |
| Plugins | `everything-claude-code`, `vercel`, `obsidian` | per-plugin manifests |
| External CLIs | `gh`, `vercel`, `supabase`, `gcloud` | discovered via `which` + `--help` parsing (best-effort, opt-in) |

### 9.2 `.context/capabilities/` layout

```
.context/capabilities/
├── INDEX.md                    # All capabilities at a glance, grouped by kind
├── capabilities.json           # Machine-readable; what route() reads
├── routing.md                  # Decision rules: when X over Y
├── skills/<name>.md            # one file per skill
├── agents/<name>.md            # one file per agent
├── mcps/<server>.md            # one per MCP server, listing its tools
├── plugins/<plugin>.md         # one per plugin
├── hooks/<name>.md
└── clis/<cmd>.md               # one per detected external CLI (opt-in)
```

### 9.3 Per-capability schema

Each capability entry (markdown frontmatter + JSON in `capabilities.json`):

```yaml
name: tdd-workflow
kind: skill
trigger: "/tdd"                        # how to invoke
location: ~/.claude/skills/tdd/SKILL.md
scope: user                            # user|project|plugin
purpose: |
  Enforces tests-first workflow.
when_to_use:
  - "Writing a new feature with measurable behavior"
  - "Fixing a bug that lacks a regression test"
when_not_to_use:
  - "Pure refactors with no behavior change"
  - "Documentation-only edits"
inputs: ["feature description", "target files"]
outputs: ["test file(s)", "minimal implementation", "coverage report"]
cost_hint: "moderate"                  # cheap|moderate|expensive
related: ["code-reviewer", "tdd-guide"]
last_scanned: 2026-05-24T00:00:00Z
content_hash: sha256:...
```

### 9.4 Routing rules

`routing.md` encodes meta-rules learned over time (and bootstrapped from heuristics):

- "For UI work, prefer `frontend-design` skill over generic code edits."
- "For any code that handles user input, run `security-reviewer` agent before declaring done."
- "Prefer `gh` MCP over shelling to `gh` CLI when both available."
- "Never invoke `everything-claude-code:e2e` for changes under `docs/`."

These start as hand-authored defaults and grow via the session-learning hook (§11.12).

### 9.5 Rescan triggers

- **On `dummyindex init`** — full scan.
- **On user command** `dummyindex capabilities rescan`.
- **On filesystem change** to any tracked source (watched in `--watch` mode).
- **On first use of an unknown capability** — lazy scan to populate.

Capabilities are SHA-256 cached like code files; only changed ones re-summarize. Same LLM-tier model routing as §11 applies — leaf summaries default to Haiku, the `routing.md` synthesis uses Sonnet.

### 9.6 Conflict handling

When two capabilities overlap (e.g. user has both `everything-claude-code:tdd` and `claude-code-guide:tdd`), `routing.md` resolves via:
1. Project-scope wins over user-scope.
2. More specific (`when_to_use` includes current task keywords) wins over general.
3. Explicit user override in `meta.json` always wins.

Unresolved ties become a surgical follow-up: "I have two `tdd` skills available — `everything-claude-code:tdd` and `claude-code-guide:tdd`. Which do you prefer for this project?"

---

## 10. Operation templates

`route()` doesn't synthesize plans from scratch every time. It classifies the request against a library of **operation templates** — parameterized blueprints for common change types — and instantiates the matching one with values pulled from the index. Templates make plans more consistent, reviewable, and machine-checkable, and they're where blast-radius reasoning, tool prescriptions, and test-case suggestions live.

### 10.1 The bundled template library

Stored at `.context/templates/<op>.yaml` (defaults shipped by dummyIndex, overridable per project):

| Template | When to use |
|---|---|
| `feature-addition` | Add a new capability that doesn't exist (page, endpoint, component, job, integration). |
| `update` | Modify an existing feature's behavior, copy, parameters, or wiring. |
| `bug-fix` | Diagnose a reported defect, write a regression test, patch. |
| `refactor` | Restructure code without behavior change (rename, extract, inline, move). |
| `reorganise` | Move files/modules across the structure (the same kind of work as the previous session's "prune frontend repo"). |
| `migration` | Schema, data, or API contract migration with zero-downtime + rollback. |
| `audit` | Review a feature, module, or surface against criteria (security, performance, accessibility, conventions). |
| `dependency-bump` | Upgrade a library, including breaking-change scan + adapter edits. |
| `performance` | Optimize a hot path identified by `.context/map/hot-paths.md` or a profile. |
| `deprecate-remove` | Sunset a feature: usage scan, callout, removal, follow-up cleanups. |
| `documentation` | Write or update docs that should mirror code state. |
| `test-backfill` | Add tests to symbols currently covered by zero (per `.context/audit/coverage.md`). |

Users add custom templates by dropping a YAML file with the same schema into `.context/templates/`. The router auto-discovers and indexes them.

### 10.2 Template schema

Every template carries the same fields the user asked for — files changed, blast radius, tools, test cases — plus a few extras the router needs:

```yaml
name: feature-addition
version: 1
description: Add a new capability that doesn't already exist.

when_to_use:
  - User asks to "add", "create", "introduce" a feature/page/endpoint/component
  - No existing feature node matches the request

when_not_to_use:
  - Existing feature node matches → use `update` template
  - Pure restructure → use `refactor` or `reorganise`

required_inputs:
  - feature_name
  - one_line_description
  - target_module   # optional; dummyIndex infers from features/structure

# What the executor will touch. Concrete paths are filled in at instantiation
# time from the index — these are slots, not literals.
files:
  to_create:
    - "{target_module}/{feature_slug}.{ext}"            # implementation
    - "tests/{target_module}/test_{feature_slug}.{ext}" # tests
    - ".context/features/{feature_slug}.md"             # feature manifest
  to_modify:
    - "{target_module}/__init__.{ext}"                  # export wiring
    - "{router_file}"                                   # route/handler registration
    - "CHANGELOG.md"                                    # if present in repo
  to_review:
    - "Files with TODO comments referencing the feature"
  must_not_touch:
    - "Anything in .context/meta.json#never_touch"      # respects KARIMO-style guardrails

# Computed at instantiation from impact graph + flows + features
blast_radius:
  scope: feature                                        # module | feature | system
  derive_from:
    - rank_impact(plan)
    - feature(feature_slug)
    - flow_overlap(target_module)
  signals_to_check:
    - "Modifies schema? → escalate scope to system"
    - "Adds public API surface? → escalate scope to system"
    - "Touches a god-node? → escalate risk by one tier"
    - "Crosses a hot-path? → escalate risk by one tier"
  risk_score: low                                       # default; signals may upgrade
  required_reviewers:
    high: ["security-reviewer", "code-reviewer"]
    medium: ["code-reviewer"]
    low: []

# Tools & capabilities — these flow into route()'s capability_refs and tool_choices
tools:
  capabilities:
    - {kind: skill, name: tdd-workflow,      reason: "tests-first per repo rule"}
    - {kind: agent, name: code-reviewer,     reason: "post-implementation review"}
    - {kind: agent, name: security-reviewer, when: "blast_radius.scope == system"}
  mcps:
    - {name: github, when: "open draft PR at end"}
  cli:
    - {cmd: pytest, when: "after each implementation step"}

steps:
  - {id: s1, action: write_test_first,   target: tests/..., skill: tdd-workflow}
  - {id: s2, action: scaffold,           target: "{target_module}/..."}
  - {id: s3, action: implement,          depends_on: [s1, s2]}
  - {id: s4, action: register,           target: "{router_file}"}
  - {id: s5, action: write_manifest,     target: ".context/features/{feature_slug}.md"}
  - {id: s6, action: run_agent,          agent: code-reviewer, scope: [s2, s3]}
  - {id: s7, action: run_agent,          agent: security-reviewer, when: "blast_radius.scope == system"}
  - {id: s8, action: open_pr,            mcp: github, depends_on: [s6]}

test_cases:
  unit:
    - "Happy path: feature returns expected output for typical input"
    - "Boundary: empty / null / max-size / unicode inputs"
    - "Error: invalid inputs produce the project's canonical error type"
  integration:
    - "Integrates with {upstream_module} without breaking {existing_flow_id}"
    - "Persists state correctly across the storage layer"
  e2e:
    - "Full user flow from entry point to terminal succeeds"
  regression:
    - "Adjacent features in the same Leiden community still pass"
    - "Files in the personalized PageRank impact set pass their existing tests"
  security:
    when: "blast_radius.scope == system"
    cases:
      - "External inputs validated"
      - "Authn/authz enforced at handler boundary"
      - "No secrets in logs or error responses"

acceptance:
  - "All test_cases passing"
  - "Coverage ≥ 80% on new code"
  - "code-reviewer: no CRITICAL/HIGH findings"
  - "security-reviewer: passed (if invoked)"
  - "No new violations vs .context/conventions/"
  - ".context/features/{feature_slug}.md exists and validates against schema"
```

### 10.3 How `route()` uses templates

When Claude calls `route(message)`:

1. **Classify.** A lightweight Haiku call picks the best-matching template by comparing the message and `.context/INDEX.md` snapshot against each template's `when_to_use` / `when_not_to_use`. If confidence is low, surface a surgical follow-up: "I see this as a `feature-addition` — is that right, or is it `update` to existing billing?"
2. **Instantiate.** Fill the template's slots ({feature_slug}, {target_module}, {router_file}, etc.) with values from the index. Concrete file paths replace the slot syntax.
3. **Compute blast radius.** Run `rank_impact`, `feature`, and flow-overlap calls; apply the `signals_to_check` rules to upgrade scope/risk. Populate `affected_features`, `affected_flows`, `god_nodes_touched`, `hot_paths_crossed`.
4. **Resolve tools.** Walk `tools.capabilities` and `tools.mcps`, applying `when` conditions; cross-reference `.context/capabilities/` to confirm each named capability is actually installed (fall back to the listed alternatives if not).
5. **Generate test cases.** Use the template's test-case patterns plus index-derived specifics (e.g. fill `{upstream_module}` from the feature manifest; pick concrete flow IDs from `.context/flows/`).
6. **Return** the instantiated plan as `route()`'s output (matches the §8.3 JSON shape).

### 10.4 Why templates over free-form plans

- **Consistency.** Two requests of the same type produce comparable plans, which makes diffs reviewable and outcomes evaluable.
- **Coverage of important fields.** Free-form planning forgets blast radius and test cases on average. Templates make them mandatory.
- **Auditability.** A CI hook can verify "every plan tagged `feature-addition` produced a feature manifest and ≥3 test cases" — that's hard for free-form plans.
- **Tunable.** Teams adjust templates without retraining anything. "All `migration` plans must include a rollback step" is one YAML edit.
- **Failure recovery.** When a plan fails partway, `route_again` can re-instantiate from the same template with the failed step's outcome as input, instead of starting over.

### 10.5 Edge cases and escape hatches

- **No matching template.** Router returns a synthesized plan (the §8.3 shape, free-form) and tags it `template: null`. Audit logs these so the library can grow over time.
- **Composite work.** A request that spans templates (e.g. "remove the legacy webhook AND add the new one") is split into a sequence of instantiated templates with shared context.
- **Template conflict.** If two templates match, `routing.md` (§9.4) breaks the tie, or it becomes a surgical follow-up.
- **Per-project overrides.** A project can override any bundled template by dropping a YAML file with the same `name` into `.context/templates/`. Project-scope always wins over bundled.

---

## 11. MCP surface

**Cross-tool compatibility.** `.context/` is the universal output — any agent that can read files (Cursor, Codex, Aider, Gemini CLI, OpenCode) can use `INDEX.md`, `tree.json`, and the per-feature/flow Markdown files directly. The MCP server below is the *fast path* for Claude Code (and any MCP-capable client); non-MCP tools fall back to reading the folder. Both modes are first-class — we don't degrade the Markdown to MCP-only stubs.

The surface is grouped by purpose. ECC's "cap MCPs <10" wisdom is intentionally stretched here because each tool is a discrete decision point Claude can call independently — the alternative (one fat `route` only) would force Claude into an all-or-nothing pattern.

**Decision-point tools** (called by Claude as part of its own reasoning loop):

| Tool | Decision it informs |
|---|---|
| `route(request)` | Bundled call: returns the full decision packet (`normalized_prompt`, `follow_ups`, `context_refs`, `conventions`, `capability_refs`, `tool_choices`, `steps`, `impact_ranked`, `acceptance_checks`). |
| `route_again(step_id, reason)` | Re-plan from a failed step without discarding the rest of the plan. |
| `normalize(message)` | Codebase-aware rewrite of the user's prompt. |
| `plan_steps(interpretation)` | Ordered steps with dependencies and acceptance checks. |
| `pick_capability(step)` | Best skill/agent/plugin/MCP for a step, with ranked alternatives. |
| `rank_impact(plan)` | Personalized PageRank over the file/symbol graph for the plan. |
| `conventions(scope)` | Naming/style/pattern rules that apply to the files in scope. |
| `surgical_followups(interpretation)` | ≤3 binary or single-fact disambiguation questions. |
| `classify_template(message)` | Picks the best-matching operation template (§10) and returns confidence + alternatives. |
| `instantiate_template(name, inputs)` | Fills a template's slots from the index and returns the realized plan. |

**Tree-walk tools** (PageIndex retrieval, §5):

| Tool | Purpose |
|---|---|
| `walk(task)` | Top-K root branches scored for relevance (tree-walk entry). |
| `expand(node_id)` | Children + overview of a node. |
| `open(node_id)` | Detail tier: the actual code/text range. |
| `find_symbol(name, kind?)` | Direct lookup by name. |
| `find_flow(query)` | Matching flow hyperedges. |
| `feature(name)` | Feature manifest. |

**Inventory & lifecycle:**

| Tool | Purpose |
|---|---|
| `inventory(kind?)` | Lists installed capabilities (skills/agents/plugins/MCPs). |
| `rebuild(scope?)` | Rebuilds full or changed-only. |
| `audit()` | Conflicts, stale entries, coverage gaps. |
| `plan(task)` | Writes a deliberate (CLI-invoked, non-routed) plan draft to `.context/plans/`. |

---

## 12. Features beyond the user's spec

Numbered for discussion. Cull anything that doesn't earn its complexity.

1. **Convention learner.** Don't ask the user to write conventions — derive them. "97% of files in `app/components/` are PascalCase `.tsx` with default export" → write that into `naming.md` with the evidence count.
2. **Anti-pattern miner.** Parse `git log` for reverts, `fix:` commits, and removed code. The lesson learned is more useful than the rule.
3. **Conflict detector.** Compare CLAUDE.md / READMEs / docstrings against AST truth. Flag drift in `.context/audit/conflicts.md` so the agent doesn't act on stale guidance.
4. **Hot-path / danger-zone map.** `churn × centrality`. Where a small mistake has outsized blast radius.
5. **Test↔symbol coverage overlay.** Every symbol gets a `tested_by: [...]` list. Symbols with zero links are easy wins or risks.
6. **Feature-flag inventory.** Auto-detect LaunchDarkly/GrowthBook/Statsig/custom flag usage and surface a flag → call-site map. (Pairs well with the user's previously-stated preference for shipping behind flags.)
7. **API contract index.** Parse OpenAPI/GraphQL schema/protobuf and link each operation to its handler symbol(s).
8. **DB schema index.** Parse migrations (Alembic, Prisma, Drizzle, golang-migrate, Rails) into an ER model and link tables to repo classes / ORM models.
9. **Boundary linter.** If `architecture/boundaries.md` says "domain/billing must not import from web/admin," surface violations.
10. **PR pre-flight.** Given a diff, walk the impact set and re-run only relevant audits. Cheaper than full re-index per PR.
11. **Plan staleness checker.** When a plan's referenced `node_id`s change, flag and offer to re-plan.
12. **Session learning hook.** End-of-session, parse the transcript for "Claude searched for X 3 times" → add X as a labelled node so future searches are 1-shot. (ECC's instinct system, scoped to the index.)

---

## 13. What we lift from dummyindex

Directly reusable (per the codebase scan):
- `pipeline/extract.py` — tree-sitter AST extraction for 25+ languages
- `pipeline/build.py` — NetworkX graph construction
- `pipeline/detect.py` — file discovery + classification + `.ignore`
- `pipeline/cache.py` — SHA-256 file-keyed cache
- `pipeline/structure.py` — folder→file→class→function tree with cross-edges (≈ our PageIndex tree skeleton)
- `analysis/flows.py` — flow hypergraph synthesis
- `analysis/features.py` — feature hypergraph synthesis
- `analysis/cluster.py` — Leiden community detection
- `analysis/analyze.py` — god-nodes, surprising connections
- `runtime/watch.py` — file watcher
- `runtime/serve.py` — MCP stdio server pattern

What we replace / build new:
- A `.context/` writer (dummyindex writes `dummyindex-out/`; different shape, different audience)
- The PageIndex tree builder + summarizer
- The CLAUDE.md bootstrap and managed block
- The convention/anti-pattern/conflict mining passes
- The planner (`dummyindex plan`)
- A leaner MCP surface focused on tree-walking, not graph queries
- The audit subsystem
- Per-language naming inference passes

---

## 14. Non-goals (Phase 1)

- No vector embeddings. Deliberate — PageIndex's pitch is reasoning over similarity.
- No real-time pair-programming UI. The `.context/tree.html` viewer is optional.
- No multi-repo / monorepo cross-linking. Out of scope until single-repo wins.
- No automated code editing. dummyIndex writes plans; Claude Code executes.
- No replacement for CLAUDE.md. We *augment* it, never overwrite.

**LLM cost & model routing (load-bearing — must not blow up on first run):**

dummyIndex prompts the user on first run with an interactive model + budget chooser, stores the choice in `.context/meta.json`, and respects it on every subsequent run. No silent defaults that surprise the bill.

```
$ dummyindex init
Detected: 1,247 source files, 312k LOC across Python, TypeScript, SQL.
Estimated summaries: 1,247 L0 abstracts + 142 L1 overviews + 6 L2 deep-dives.

Choose a model profile:
  1. Haiku-only      — cheapest, ~$0.40 projected, slightly weaker summaries
  2. Mixed (default) — Haiku for leaves, Sonnet for parents, ~$1.80 projected
  3. Sonnet-only     — uniform high quality, ~$6.20 projected
  4. Opus parents    — Opus for module/feature summaries, Sonnet for files, Haiku for leaves, ~$14.50 projected
  5. Custom          — pick per tier
Budget cap (refuses to start if exceeded): [$3.00]
```

- **Tier routing:** L0 abstracts (1 sentence per node, deterministic stub OK when content is small) → Haiku by default. L1 overviews (parents: dir/module/file/class) → Sonnet by default. L2 deep-dives (only god-nodes / entry points / explicitly requested) → Sonnet, or Opus if the user opted in.
- **Hard cap.** `dummyindex init` projects spend before any LLM call and refuses to start if projected > budget. `--dry-run` shows the projection without spending.
- **Incremental re-runs** reuse dummyindex's SHA-256 cache; unchanged files cost zero.
- **Depth is configurable.** `--depth=file` (cheapest, file-level only) up to `--depth=symbol` (every class/function summarized). Default `--depth=class`.
- **Re-prompt on profile change.** `dummyindex reconfigure` re-runs the chooser; existing summaries are kept unless re-tiered.

#### Per-turn routing cost (separate from indexing)

`route()` runs LLM calls **per Claude turn** (not just at index time), so it has its own cost profile and its own opt-in:

- **Default routing model: Haiku 4.5.** All six decision-point sub-tools (`normalize`, `plan_steps`, `pick_capability`, `rank_impact`, `conventions`, `surgical_followups`) default to Haiku, because they operate over already-summarized index content — not raw source — and don't need a frontier model.
- **Per-tool override.** `.context/meta.json` lets the user upgrade specific sub-tools to Sonnet or Opus (e.g. `plan_steps: sonnet` if plans are weak; `normalize: haiku` to keep cheap). Same interactive chooser pattern as §11 indexing config.
- **Cached interpretations.** `normalize(message)` is content-hash cached. Repeated identical user messages within a session cost zero.
- **Bypass thresholds.** A length/keyword heuristic on the raw message decides whether to invoke `route()` at all. Short questions, conversational replies, and direct file lookups skip routing entirely.
- **Per-turn budget cap.** `.context/meta.json` can set `route_max_tokens_per_turn`. The MCP tool refuses if the projected spend would exceed it and falls back to returning context refs only (skipping the LLM-powered decisions).
- **Estimated cost.** Haiku-default `route()` is roughly $0.003–$0.01 per Claude turn on a medium repo. Sonnet-everywhere would be ~10×. Opus would be ~30–50×. The interactive chooser shows projected per-1000-turns spend so the user picks with eyes open.

---

## 15. Phased roadmap

**Phase 0 — Skeleton (1 PR)**
- New Python package, CLI entry, `.context/` writer, `meta.json`, schema versioning.
- Reuse dummyindex's `detect` + `extract` directly to produce a flat `map/symbols.json`.
- Generate a placeholder `INDEX.md`, `tree.json` with L0+L1 only.

**Phase 1 — Tree + bootstrap (2–3 PRs)**
- Hierarchical `tree.json` builder (deterministic skeleton; LLM only for summaries).
- CLAUDE.md managed-block writer (with idempotent updates).
- `dummyindex init`, `dummyindex rebuild`, `dummyindex rebuild --changed`.
- Convention learner v1 (naming only).

**Phase 2 — MCP + planner (2–3 PRs)**
- MCP server: `walk`, `expand`, `open`, `find_symbol`, `rank`.
- Personalized PageRank.
- `dummyindex plan` writes deliberate plan drafts.

**Phase 3 — Capabilities inventory + routing (2–3 PRs)**
- Scan `~/.claude/skills`, `./.claude/skills`, agents, MCP servers, hooks, plugins → `.context/capabilities/`.
- MCP `inventory()`, `route()`, `route_again()`, plus the six decision-point sub-tools (`normalize`, `plan_steps`, `pick_capability`, `rank_impact`, `conventions`, `surgical_followups`).
- CLAUDE.md managed block gains the routing directive (idempotent regeneration).
- Default `routing.md` rule set; `route_policy` config in `meta.json`.
- Eval: same task, with vs without routing — measure plan accuracy and end-to-end tool calls.

**Phase 3.5 — Operation templates (1–2 PRs)**
- Ship the 12 bundled templates listed in §10.1.
- MCP `classify_template()`, `instantiate_template()`.
- Wire template selection into `route()` so plans default to template-instantiated form when match confidence is high.
- Project-override discovery: `.context/templates/*.yaml` in repo takes precedence over bundled.
- Eval: plan completeness (blast-radius computed? test cases present? required reviewers chosen?) for template-routed vs free-form plans.

**Phase 4 — Flows, features, audit (2–3 PRs)**
- Reuse dummyindex's flow + feature synthesis, emit `.context/flows/`, `.context/features/`.
- Conflict detector, stale detector, hot-path map.

**Phase 5 — Watch + session learning (1–2 PRs)**
- `--watch` rebuilds on save.
- Session-end hook: mine transcript for repeated searches → add labels; mine repeated capability invocations → strengthen `routing.md` rules.

**Phase 6 — Polish**
- API contract index, DB schema index, feature-flag inventory, boundary linter.

Each phase ends with an eval: same task, measured tool-calls and tokens with/without `.context/`. We don't ship a phase that doesn't move the metric.

---

## 16. Open questions for the user

**Resolved (2026-05-24):**
- ✅ Location: this repo (`/mnt/windows-ssd/Projects/memory/dummyindex/`).
- ✅ Name: dummyIndex (v2 of the existing project).
- ✅ CLAUDE.md bootstrap: links both the new `.context/` tool AND the existing `/dummyindex` skill — see §6.
- ✅ Model + budget: interactive chooser on first run, user-configurable, Opus available, sensible mixed default — see §11.

**Still to resolve (deferred to Phase 0 scoping):**
1. **Languages, phase 1.** Start with Python + TypeScript only, or take dummyindex's 25-language reach from day one? My recommendation: Python + TS for v2.0 (where most agent-coded projects live), then expand.
2. **Plan handoff.** Plans drafted by dummyIndex — checked in (`.context/plans/`) or ephemeral (`.claude/plans/`, gitignored)? Recommendation: checked in by default, opt-out for solo work.
3. **Live mode default.** Should `--watch` be the default `dummyindex` behavior, or opt-in? Recommendation: opt-in; default to incremental rebuild on demand to avoid surprising LLM spend.

---

## 17. References

- [PageIndex](https://github.com/VectifyAI/PageIndex) — tree-based reasoning retrieval
- [OpenViking](https://github.com/volcengine/OpenViking) — L0/L1/L2 tiered context
- [ECC](https://github.com/affaan-m/ECC) — skill/instinct organization patterns
- [KARIMO](https://github.com/opensesh/KARIMO) — PRD-driven plan→execute split
- [safishamsi/dummyindex](https://github.com/safishamsi/dummyindex) — upstream knowledge graph engine
- [Aider repo map](https://aider.chat/docs/repomap.html) — PageRank-ranked symbol summaries
- [Codebase-Memory paper (2026)](https://arxiv.org/abs/2603.27277) — 83% answer quality at 10× fewer tokens via tree-sitter KG
- [CodeCompass paper (2026)](https://arxiv.org/html/2602.20048v1) — static dep graph via MCP for agentic navigation
- [Claude Code best practices, 2026](https://code.claude.com/docs/en/best-practices) — CLAUDE.md hierarchy and content strategy
