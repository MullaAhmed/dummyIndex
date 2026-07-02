# 06 — Personas

Three role classes, not six. Each is a Task subagent prompt template.

The lineage is still [agency-agents](https://github.com/msitarzewski/agency-agents) (MIT) for personality framing; output contracts are rewritten around the spec-kit-shaped artifact set (`spec.md` / `plan.md` / `concerns.md`).

## 1. Dev (stack-specialist author)

**One parameterised persona**. The picker selects the stack at dispatch time from `map/files.json` + manifests (`pyproject.toml`, `package.json`, `Cargo.toml`, `pom.xml`, `go.mod`, …).

### Picker

| Signal | Persona | Claude subagent_type |
|---|---|---|
| FastAPI in deps, `routes/*` or `app/api/*` files | `dev-backend-fastapi` | Backend Architect |
| Django in deps, `apps/*/views.py` files | `dev-backend-django` | Backend Architect |
| Spring Boot, `*Controller.java` files | `dev-backend-spring` | Backend Architect |
| Express / Next API routes, `app/api/route.ts` | `dev-backend-node` | Backend Architect |
| React / Vue / Svelte feature surface | `dev-frontend` | Frontend Developer |
| Migrations, ORM models, raw SQL | `dev-data` | Data Engineer |
| ML deps (torch/transformers/…), or `inference/` `training/` paths | `dev-ai` | AI Engineer |
| Else | `dev-generic-senior` | Senior Developer |

Personas share one markdown body with `{{framework}}` and `{{framework_docs}}` slots. The orchestrator fills the first from detection (the resolved framework name) and the second with verbatim Context7 excerpts for the libraries the feature imports (the lookup protocol lives in the skill's `council/55-context7.md`).

### Output

- `spec.md` — what does this feature do?
- `plan.md` — how is it implemented? (overwritten by the architect in stage 2)

### Required sections — `spec.md`

- **Intent** — one paragraph, no code references. What problem this solves for the caller.
- **User-visible behavior** — request/response shapes, CLI flags, UI affordances. Whichever applies.
- **Contracts** — public functions, endpoints, message formats. Names + signatures + `path:range`.
- **Examples** — at least one happy-path trace through the feature.

### Required sections — `plan.md` (dev's draft)

- **Where it lives** — files + directories, with `path` citations.
- **Architecture in three sentences** — components, how they call each other, the dominant pattern.
- **Data model** — tables, queries, transactions if any. Or "none" with one sentence why.
- **Key decisions** — what was chosen, what was rejected, what's load-bearing.
- **Open questions** — anything the dev couldn't determine from the code.

The dev **also handles flow filtering and narration** (no separate flow stage). Trivial flows get removed via `flow-remove`; kept flows get a one-paragraph narrative in `flows/<id>.md`.

## 2. Architect (reorganiser)

One persona, two jobs.

### Job A — Structural review (pre-stage, once per council run)

Reads full `INDEX.json` + every `feature.json`. Proposes:

- **Merges** — two features overlap > 60% by symbols/files.
- **Splits** — one community spans clearly separate domains.

Applied atomically via `features-rename`. Same as v0.13.

### Job B — Plan reorganisation (per-feature, stage 2)

Reads the dev's draft `plan.md` and revises it. Mandate:

- Sharpen bounded context — strip detail that isn't load-bearing for the boundary.
- Name patterns explicitly — repository, dispatcher, saga, port/adapter, etc.
- Make dependencies visible — what this depends on, what depends on it.
- Promote unstated decisions — convert assumptions in the code into explicit "decided X because Y".
- Cut filler. No "in this section we will discuss". No paraphrase where a `path:range` would do.

### Output

- Revised `plan.md` (overwrites the dev's draft).
- `council/02-architect-notes.md` — diff narrative: what changed and why.

## 3. Critics (concerns-only)

Three specialist personas. Each owns one section of `concerns.md`. **None of them author primary docs** — that's the dev's job.

### 3a. Database engineer

- **Section**: `## Data integrity` in `concerns.md`.
- **Reads**: finalised `plan.md` + source files cited in `data-model` section.
- **Files**: missing indexes (with the queries that need them), N+1 candidates, transaction boundary mistakes, isolation level assumptions, migration ordering hazards.
- **Format**: bullet list. Each bullet: `path:range` + one-sentence concern + suggested fix (if obvious).

### 3b. Security analyst

- **Section**: `## Security` in `concerns.md`.
- **Reads**: finalised `plan.md` + auth/input/secret code paths.
- **Files**: trust boundary leaks, authn/authz gaps, validation that's actually gesture, secrets in code, top-3 ranked threats.
- **Format**: bullet list. Each bullet: `path:range` + threat + load-bearing-mitigation (or "none").

### 3c. Product manager

- **Section**: `## Product surface` in `concerns.md`.
- **Reads**: finalised `plan.md` + entry-point files (HTTP routes, CLI commands, public APIs).
- **Files**: edge cases the code doesn't handle, capabilities the code hints at but doesn't deliver, hidden costs (latency, rate limits, retries) the caller pays implicitly.
- **Format**: bullet list. Each bullet: scenario + observed behavior + gap (if any).

Critics see only the finalised `plan.md`, not each other's drafts — unless mode = `deep`, in which case a cross-review pass lets them flag each other's findings before the merge into `concerns.md`.

## Retired in v0.14

| Persona | Why retired |
|---|---|
| **Chairman** | No synthesis step needed — each artifact has one owner. Audit notes that used to live in `20-chairman.md` are absorbed into `02-architect-notes.md` (for plan revisions) and `10-critiques.md` (for critic findings). |
| **Senior developer** (as separate persona) | Folded into the parameterised `dev` — the "generic senior developer" picker branch is the same role with no framework specialisation. |

Reality-checker stays as the post-pipeline validator (see `45-reality-check.md`) — no changes.

## What every persona shares

Each persona's markdown ends with the same **output contract**:

- Exact file path it must write (or section, for critics).
- Required structure (above).
- Forbidden behaviors:
  - No paraphrase where a `path:range` citation would do.
  - No inventing entities not present in the source.
  - No filler ("In this section we will…").
  - Confidence flips to `INFERRED` on every touched node.
