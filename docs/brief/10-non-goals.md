# 10 — Non-goals

What dummyindex deliberately does **not** do. Stating these prevents scope creep.

## Not a code generator

- dummyindex does not write production code.
- It writes documentation of code that already exists.
- Agents that consume `.context/` may write code, but dummyindex doesn't.

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

- It does not edit source files.
- It does not suggest specific code changes.
- It identifies opportunities (the senior dev persona may note them in `implementation.md`) but does not act.

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
- Cost controls are tiered modes + caching + skip-trivial + hook-driven incremental refresh.
- The auto-refresh loop is free (no LLM); only council is metered.

## Not a replacement for documentation a human writes

- READMEs aimed at end users live elsewhere (the project's top-level README).
- API documentation aimed at consumers stays where it is.
- `.context/` is for **agents and contributors** working on the code itself.

## Not a static snapshot

- It's a **living document** kept current by the auto-refresh loop.
- A stale `.context/` is a bug, not a state we tolerate.
