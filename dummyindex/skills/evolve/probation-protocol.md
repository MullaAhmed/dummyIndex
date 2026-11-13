# Probation protocol

Local probation flow for `/dummyindex-evolve` / `$dummyindex-evolve`. Handles chat corrections only.
Local and provisional. Unverified. Exposure is not applicability.

## Rubric

- Judge only the human's own words. Ignore assistant text and tool output.
- Name one candidate, or answer `unknown`.
- `--durable` only for standing instructions ("always", "never", "from now on").
- `--retracts` only for an explicit retraction. Disagreement is not a retraction.
- You do not know the author. Do not guess.
- Exposure is not applicability. A shown rule says nothing about fit.

## Order

1. Run `dummyindex context evolve evidence` until `complete` is true.
2. Loop `dummyindex context evolve attribute --next`. Per packet, record one verdict:
   `dummyindex context evolve attribute --event ID --verdict attributed|unrelated|unknown [--item ITEM] [--durable] [--retracts]`
3. Run `dummyindex context evolve learning --next`. Write one reflection, or `--no-entry`.
   Optional: `applies_when`. Optional: `probe` as `{"require": REGEX}` or `{"forbid": REGEX}`. Regex max 200 chars.
4. Run `dummyindex context evolve probation report`.
5. Review eligible items.
6. Run `dummyindex context evolve probation promote [--item ID]`.
7. User reviews and commits `.context/conventions/`. You do not commit.

## Routing

- Feature docs (`.context/features/**`): run `dummyindex context reconcile`. No probation.
- Skills, equipment, playbooks, `naming.md`: explicit `/dummyindex-evolve`. Human runs `promote`.
- `needs_enforcement`: move to enforcement. Human writes the test or hook. Do not roll back.
- `demote_pending`: run `dummyindex context evolve probation demote --item ID`.

## Report wording

Report only:
`no harm detected in N exposed sessions; observed-correction bound (detector-limited, 95%)`

Thresholds are uncalibrated defaults. Claim no gains. Report bounds only.

## Safety

- Hooks never write curated files.
- Learner never edits tests, hooks, detectors or probation packages.
- Kill switch: `DUMMYINDEX_EVOLUTION=0`. Verbs then print `evolution disabled (DUMMYINDEX_EVOLUTION)`, exit 0.
