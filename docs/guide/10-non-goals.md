# 10 — Non-goals

What dummyindex deliberately does **not** do. Stating these prevents scope creep.

## Not a code generator (but a tooling generator)

dummyindex itself never writes production code. On Claude, it may generate the
consumers — project-tuned agents, skills, and hooks under `.claude/`. On Codex,
it uses already available native agents and writes no Claude equipment. The
line is deliberate:

- **dummyindex** plans, optionally equips Claude tooling, and orchestrates. It
  does not author source files.
- **Dispatched agents** — Claude generated/specialist agents or Codex native
  built-ins/custom agents — author source files one checklist item at a time.
- Agents that consume `.context/` may write code; dummyindex doesn't. That boundary holds.

## Not an LSP server

- No real-time go-to-definition for IDEs.
- No type checking.
- No autocomplete suggestions.
- For LSP needs, use a real LSP server. dummyindex provides the static map, not the IDE protocol.

## Not a search engine in the traditional sense

- No full-text search index.
- No fuzzy matching.
- No vector embeddings.
- **Retrieval is PageIndex-style reasoning over the tree** — see [12 — Retrieval](./12-retrieval.md).
- Agents only grep when they need raw string occurrence (rare) — the tree answers most questions.

## Not a refactoring tool

- dummyindex itself does not edit source files.
- It identifies opportunities (noted in `plan.md`, filed in `concerns.md`) but does not act on them.
- Dispatched host agents may edit source, but only when the build skill assigns a
  specific checklist item — not autonomously.

## Not a CI/CD step

- Not designed to run in CI.
- Not designed to gate PRs.
- It's an agent-time artifact, not a build-time artifact.
- (CI may run `rebuild --changed` to keep `.context/` fresh, but that's optional.)

## Not multi-repo (today)

- One `.context/` per repo.
- No cross-repo features at v1.
- If you have a monorepo with multiple distinct apps, run dummyindex per app (use `--root` to target each).
- Cross-repo / workspace mode is on the roadmap.

## Not a graph database

- `symbol-graph.json` is NetworkX node-link JSON.
- Not queryable like Neo4j.
- Not indexed for ad-hoc traversal.
- If you need that, export to Neo4j separately. dummyindex doesn't.

## Not the source of truth for code semantics

- The code is the source of truth for **what runs**.
- `.context/` is the source of truth for **what the code means**, **how it's organized**, and **why**.
- When `.context/` disagrees with the code, the code wins for facts; `.context/`
  is reconciled. Deterministic maps may be rebuilt, while curated feature prose
  follows the reconcile workflow so a refresh does not discard it.

## Not a security audit

- The security analyst persona (and the on-demand `/dummyindex-audit` or
  `$dummyindex-audit` panel — see [08 — Skill](./08-skill.md)) surface threat
  surface and risks.
- It does NOT certify the code as secure.
- It does NOT replace a real security review by a human.
- Use it as a starting point for one.

## Not a metrics dashboard

- No "code health score".
- No "this is a 7/10 codebase".
- Subjective metrics belong in agents' prose, not in numbers.

## Persona prompts are model-agnostic

- No Claude-model-specific instructions in agent personas.
- Personas work with any reasonably-capable LLM.
- Claude may persist a selected Claude label. Codex explicitly uses `current`,
  meaning the running session model. The personas themselves stay model-agnostic.

## Not free at scale

- Deep-mode council on a 100-feature monorepo will cost real money — one-time.
- Cost controls are tiered modes + caching + skip-trivial + the free SessionStart drift check.
- The drift check (`plan-update`) is free (no LLM); the session reconciles docs as part of normal work; only a full council run is separately metered.

## Not a replacement for documentation a human writes

- READMEs aimed at end users live elsewhere (the project's top-level README).
- API documentation aimed at consumers stays where it is.
- `.context/` is for **agents and contributors** working on the code itself.

## Not a static snapshot

- It's a **living document** kept current through reconciliation. Claude adds
  managed hook signals; Codex relies on its active project instruction file and
  explicit skills.
- A stale `.context/` is a bug, not a state we tolerate.
