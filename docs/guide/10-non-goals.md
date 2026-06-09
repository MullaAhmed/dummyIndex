# 10 — Non-goals

What dummyindex deliberately does **not** do. Stating these prevents scope creep.

## Not a code generator (but a tooling generator)

dummyindex itself never writes production code. What changed in v0.15: it now *generates the consumers* — project-tuned agents, skills, and hooks grounded in `.context/` and rendered into `.claude/`. Those generated agents, dispatched by the `/dummyindex-build` skill, write the code. The line is deliberate:

- **dummyindex** plans, equips tooling, and orchestrates. It does not author source files.
- **The generated agents** (the core implementer / tester / reviewer plus any generated capability specialist — db / security / performance / docs / search) author source files — but only when explicitly dispatched by the skill layer, one checklist item at a time.
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
- The generated tooling (equip-produced implementer/tester agents and capability specialists) may edit source, but only when explicitly dispatched by `/dummyindex-build` on a specific checklist item — not autonomously.

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
- When `.context/` disagrees with the code, the code wins for facts; `.context/` is regenerated.
- The agent's first action when it detects disagreement is to trigger a rebuild.

## Not a security audit

- The security analyst persona surfaces threat surface and risks.
- It does NOT certify the code as secure.
- It does NOT replace a real security review by a human.
- Use it as a starting point for one.

## Not a metrics dashboard

- No "code health score".
- No "this is a 7/10 codebase".
- Subjective metrics belong in agents' prose, not in numbers.

## Not vendor-specific within Anthropic

- No Claude-model-specific instructions in agent personas.
- Personas work with any reasonably-capable LLM.
- The session's model is what runs.

## Not free at scale

- Deep-mode council on a 100-feature monorepo will cost real money — one-time.
- Cost controls are tiered modes + caching + skip-trivial + the free SessionStart drift check.
- The drift check (`plan-update`) is free (no LLM); the session reconciles docs as part of normal work; only a full council run is separately metered.

## Not a replacement for documentation a human writes

- READMEs aimed at end users live elsewhere (the project's top-level README).
- API documentation aimed at consumers stays where it is.
- `.context/` is for **agents and contributors** working on the code itself.

## Not a static snapshot

- It's a **living document** kept current by the SessionStart drift hook + per-session reconciliation.
- A stale `.context/` is a bug, not a state we tolerate.
