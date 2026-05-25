# 05 — Multi-agent council

The deep-dive layer. Inspired by Karpathy's `llm-council` (peer-ranked debate) and agency-agents (persona-driven specialists).

## The three stages

### Stage 1 — Independent perspectives

- Five personas read the feature **in parallel**.
- Each gets the same input: `feature.json`, sample source files, the flow traces.
- None see each other's output.
- Each writes ONE markdown file with their domain's take.

Outputs (per feature):
- `council/01-architect.md`
- `council/02-senior-developer.md`
- `council/03-database-engineer.md`
- `council/04-security-analyst.md`
- `council/05-product-manager.md`

### Stage 2 — Cross-review (anonymized)

- Each persona reviews the **other four** perspectives.
- Author identity is stripped: they see "Perspective A", "Perspective B", …
- Per perspective they note: agreements, contradictions, gaps the reviewer's domain can fill, factual claims to verify.
- Output: `council/10-reviews.md` (a single matrix file).

### Stage 3 — Chairman synthesis

- A chairman persona reads all 5 perspectives + the review matrix.
- Resolves contradictions where possible.
- Flags unresolved contradictions as "open questions".
- Writes the **canonical docs**:
  - `README.md` — synthesized overview (1-2 pages).
  - `architecture.md` — architect's section, post-review.
  - `implementation.md` — senior dev's section, post-review.
  - `data-model.md` — DBA's section, post-review.
  - `security.md` — security's section, post-review.
  - `product.md` — PM's section, post-review.
- Logs the synthesis decisions to `council/20-chairman.md`.

## Why this beats single-pass enrichment

- **Domain isolation**. The security analyst doesn't water down threats to keep the architect happy.
- **Cross-check**. The architect spots when the DBA missed a transaction boundary; the DBA spots when the senior dev's "clean abstraction" hides a query plan disaster.
- **Open questions surface**. Things no single agent could answer alone get flagged for humans.
- **Audit trail**. The full debate is on disk. Trust is verifiable.

## Council modes

User-selectable per run:

| Mode | Stage 1 | Stage 2 | Stage 3 | Cost (14-feature repo) |
|---|---|---|---|---|
| **light** | — | — | Chairman synth from `feature.json` only | ~$1–2 |
| **standard** | Architect + 1 relevant specialist | — | Chairman synth | ~$3–6 |
| **deep** (default) | All 5 personas | Cross-review | Chairman synth | ~$18–30 |

- Specialist relevance for `standard`: pick DBA if SQL/migrations detected, security if auth boundaries detected, PM if HTTP routes detected, etc.

## Skip-trivial filter

- Some features don't deserve a council.
- Skip if: `member_count < 3`, `file_count < 2`, `entry_point_count == 0` AND name suggests utility (matches `*-utils-*`, `typing-*`, `*-marker`, `*-config`).
- Trivial features get a one-paragraph `README.md` from a chairman-only template.

## Resumption

- Each council writeback updates `council/_council-log.json`.
- A re-run skips stages already complete for that feature.
- Force re-run with `--force`.

## Cache

- Each feature's source files are content-hashed.
- If all hashes match the last council, the council is skipped (`README.md` and friends survive).
- If any file changed, the affected sections are re-run (architect/senior dev always; specialists per relevance).

## Regrouping (architect's special privilege)

- Before stage 1 of every feature, a **structural review** runs once:
  - One architect agent reads the full `INDEX.json` + every `feature.json`.
  - Proposes merges (two features overlap heavily) and splits (one community spans multiple domains).
  - Chairman approves the plan.
  - `features-rename` is called for each rename in the plan.
- Per-feature councils run on the **regrouped** features. So `docs-and-llm-lifecycle` (20 flows!) might become `docs` + `llm-lifecycle` + `telemetry` first.

## The debate file

`council/10-reviews.md` records, per perspective:

```
## Perspective A (Architect's view)

### Senior Developer's review
- Agrees: "bounded context isolation" claim grounded in app/auth/ structure.
- Disagrees: "trade-off: consistency over availability" — code shows eventual consistency
  in `app/services/notifications.py:42`, contradicting the architect's claim.
- Gap: architect didn't mention the circular dependency between AuthService and UserService.

### Database Engineer's review
- ...
```

The chairman reads this and resolves with: "Resolved: I'm taking senior dev's view on consistency model. Architect's wording updated."
