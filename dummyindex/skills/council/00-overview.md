# Council overview

How dummyindex turns deterministic feature scaffolding into rich, debated, agent-authored documentation.

## The pattern

For every non-trivial feature in `features/INDEX.json`:

1. **Stage 1 — Perspectives.** Five personas read the feature independently and write their domain's take.
2. **Stage 2 — Cross-review.** Each persona reviews the four other (anonymized) perspectives.
3. **Stage 3 — Synthesis.** The chairman integrates everything into canonical docs.

Followed by:

4. **Flow refinement.** Senior dev filters trivial flows + narrates the kept ones.
5. **Reconcile.** `refresh-indexes` regenerates derived markdowns.

## Where each piece lives

```
features/<feature_id>/
├── council/
│   ├── 01-architect.md           # Stage 1
│   ├── 02-senior-developer.md    # Stage 1
│   ├── 03-database-engineer.md   # Stage 1
│   ├── 04-security-analyst.md    # Stage 1
│   ├── 05-product-manager.md     # Stage 1
│   ├── 10-reviews.md             # Stage 2 (concatenated)
│   ├── 20-chairman.md            # Stage 3 audit trail
│   └── _council-log.json         # Resumption state
├── README.md                     # Stage 3 — chairman's overview
├── architecture.md               # Stage 3 — chairman's refinement
├── implementation.md             # Stage 3 — chairman's refinement
├── data-model.md                 # Stage 3 — chairman's refinement
├── security.md                   # Stage 3 — chairman's refinement
├── product.md                    # Stage 3 — chairman's refinement
└── flows/
    ├── <flow_id>.json            # deterministic
    └── <flow_id>.md              # narrated by senior dev (or removed)
```

## Modes

| Mode | What runs | Wall time (14 features) | Default? |
|---|---|---|---|
| **light** | Chairman synth only — no stage 1 perspectives | ~5 min | No |
| **standard** | Architect + 1 relevant specialist + chairman, no stage 2 | ~10-15 min | **Yes** |
| **deep** | All 5 personas + stage 2 cross-review + chairman | ~45-60 min | No |

Mode passed via `/dummyindex --mode light|standard|deep`.

**Why standard is default:** `deep` is genuinely expensive (an hour of wall time on a medium repo, ~$25). Standard gets you 80% of the depth in 25% of the time. Use `deep` when you want maximum rigor (e.g., before a major refactor) or `--recouncil <feature_id> --mode deep` to deep-dive a single feature.

## Sequencing

```
Phase 0: dummyindex ingest (deterministic backbone)
   │
Phase 1: Structural review
   ├── Dispatch ONE architect (over INDEX.json + all feature.jsons)
   ├── Architect emits a regrouping plan
   └── Skill applies via features-rename
   │
Phase 2: Per-feature council (loop over features)
   │   skip if feature trivial (see filter-trivial.md)
   │   skip if _council-log.json shows complete + source unchanged
   │
   ├── Stage 1 (5 personas in PARALLEL via Task tool)
   ├── Stage 2 (4 reviewers in PARALLEL)
   └── Stage 3 (chairman, SEQUENTIAL — needs everything)
   │
Phase 3: Flow refinement (per feature, senior dev decides keep/discard)
   │
Phase 4: dummyindex context refresh-indexes
```

## Dispatching agents

For each persona:

1. Read the persona markdown (`skills/agents/<persona>.md`).
2. **Extract `subagent_type:` from its frontmatter.** This is the Claude Code Task subagent type the persona should run as. Defaults to `general-purpose` if absent.
3. Read the feature context (`feature.json`, sample source files).
4. Build the Task prompt: persona instructions (the full markdown body) + feature context + "write your stage-1 output to `features/<id>/council/0N-<persona>.md`".
5. Dispatch `Task` with the persona's `subagent_type`. Block until the persona logs `complete`.

### Persona → subagent_type mapping (from each persona's frontmatter)

| Persona file | subagent_type |
|---|---|
| `agents/architect.md` | `Backend Architect` |
| `agents/senior-developer.md` | `Senior Developer` |
| `agents/database-engineer.md` | `Data Engineer` |
| `agents/security-analyst.md` | `Security Engineer` |
| `agents/product-manager.md` | `general-purpose` (no PM-specific type) |
| `agents/chairman.md` | `Agents Orchestrator` |

**Why specialist subagent types vs. general-purpose**: Anthropic's specialists are tuned for their domain (the Backend Architect instinctively reaches for bounded-context analysis; Security Engineer thinks adversarially by default). Using them on top of our persona markdown stacks the strengths — built-in domain reflexes + our `.context/` output contract.

The persona markdown still carries the **output contract** — section structure, file paths, forbidden behaviors. The specialist provides the **domain reflexes**.

For stages 1 and 2, dispatch personas **in parallel** — that's the cost win.

## Logging discipline

Every agent invocation, at start AND end, calls:

```bash
dummyindex context council-log --feature <id> --stage <N> --agent <persona> --status started|complete|failed
```

The skill consults the log to:
- Skip work already complete (resumption).
- Detect partial failures.
- Show progress to the user.

## What this gives the agent reading `.context/` later

- `README.md` — overview, no jargon.
- Per-domain deep dive for any of the 5 angles.
- `council/` audit trail — see the original perspectives + disagreements.
- `flows/` — narrated call sequences.

A future Claude reading any one section can drill down or up at will.
