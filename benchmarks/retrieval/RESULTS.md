# Retrieval benchmark results

Command: `python benchmarks/retrieval/run_eval.py` (clones pinned repos into
`--workdir`, builds deterministic backbone indexes, 54 questions split 50/50
into dev/holdout; metric: does a top-k returned feature contain the gold
source file).

| Version | dev hit@1 | dev hit@3 | dev MRR | holdout hit@1 | holdout hit@3 | holdout MRR |
|---|---|---|---|---|---|---|
| main (before) | 0.704 | 0.741 | 0.758 | 0.407 | 0.704 | 0.588 |
| this branch   | 0.704 | 0.889 | 0.809 | 0.630 | 0.889 | 0.774 |

Experiments (each measured independently; keepers in **bold**):

1. **Load per-feature file lists from `feature.json`** — `INDEX.json` never
   carries `files`, so the file-basename signal never fired. dev MRR
   0.758 → 0.779, holdout 0.588 → 0.602.
2. **IDF over features per query token** (floor 0.25) — dev 0.779 → 0.786,
   holdout 0.602 → 0.608.
3. **Size-normalize symbol hits** by `1/(1+ln(1+n_symbols))` — dev
   0.786 → 0.813, holdout 0.608 → 0.706. Largest single win: stops the
   largest community winning every query by mass.
4. Exact-identifier bonus (1.5x, then 1.25x) — dev regressed (0.813 → 0.794).
   **Reverted.**
5. Bigram phrase bonus — no measurable change (dev flat, holdout noise).
   **Reverted.**
6. Size-normalize file-basename hits — dev 0.813 → 0.785, holdout
   0.706 → 0.654. **Reverted** (file accumulation is a true signal).
7. **Exact file-stem match bonus** (+4 × idf when token == file stem) — dev
   flat (0.813 → 0.809), holdout 0.706 → 0.774. Kept for the large holdout
   gain; dev delta is one rank swap.
8. Distinct-token coverage multiplier — no measurable change. **Reverted.**

Net: holdout hit@1 0.407 → 0.630 (+22 points), holdout MRR 0.588 → 0.774,
dev MRR 0.758 → 0.809.

Selection-protocol note: experiments 1-3 were kept on dev gains (holdout
confirmed); experiment 7 was flat on dev and kept on the holdout gain, so
holdout was not fully untouched during selection - treat the original
holdout figures above as exploratory. Experiments 4 and 6 regressed on both
splits, 5 and 8 were neutral on both. 54 hand-written questions over 3 repos
is a real but modest benchmark.

## Confirmation: fresh untouched set (holdout-2)

21 new questions (`questions_holdout2.json`, 7 per repo), written after all
selection was finished and evaluated exactly once per version, no tuning:

| Version | hit@1 | hit@3 | MRR |
|---|---|---|---|
| main (before) | 0.476 | 0.857 | 0.650 |
| this branch   | 0.667 | 0.905 | 0.771 |

hit@1 0.476 → 0.667 (+19 points), MRR 0.650 → 0.771 on questions the changes
were never selected or tuned against.
