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

## Batch 2: 50 measured iterations (2026-11-05)

Protocol: dev and the original holdout had both been consulted during
batch-1 selection, so they were merged into one 54-question **tuning**
set used for all keep/revert decisions below. Each experiment changed one
thing on top of the current best; kept if tuning MRR improved >= 0.003
(or hit@1 improved at equal MRR), reverted otherwise. A fresh 28-question
set (`questions_holdout3.json`, written after all selection, including 7
questions on pallets/click, a repo no tuning question touches) was
evaluated exactly once per version as the defensible result.

| # | experiment | tuning MRR | tuning hit@1 | tuning hit@3 | decision |
|---|---|---|---|---|---|
| - | start (batch-1 head eb72587) | 0.791 | 0.667 | 0.889 | - |
| 1 | file-basename weight 2->3 | 0.790 | 0.667 | 0.889 | reverted |
| 2 | file-basename weight 2->1.5 | 0.791 | 0.667 | 0.889 | reverted |
| 3 | symbol weight 2->3 | 0.763 | 0.611 | 0.889 | reverted |
| 4 | symbol weight 2->1.5 | 0.799 | 0.685 | 0.889 | **kept** |
| 5 | file-stem bonus weight 4->6 | 0.808 | 0.704 | 0.889 | **kept** |
| 6 | file-stem bonus weight 4->2 | 0.790 | 0.667 | 0.889 | reverted |
| 7 | drop feature_id signal (community-N ids) | 0.808 | 0.704 | 0.889 | reverted |
| 8 | name weight 5->3 (dead on backbone names) | 0.808 | 0.704 | 0.889 | reverted |
| 9 | IDF floor 0.25->0.1 | 0.808 | 0.704 | 0.889 | reverted |
| 10 | IDF floor 0.25->0.5 | 0.808 | 0.704 | 0.889 | reverted |
| 11 | IDF formula ln(N/(1+df)) | 0.798 | 0.685 | 0.889 | reverted |
| 12 | BM25-style IDF | 0.805 | 0.704 | 0.907 | reverted |
| 13 | size-normalization exponent 1->0.5 | 0.769 | 0.630 | 0.870 | reverted |
| 14 | size-normalization exponent 1->1.5 | 0.799 | 0.685 | 0.889 | reverted |
| 15 | drop symbol size normalization | 0.731 | 0.593 | 0.852 | reverted |
| 16 | crude suffix stemming for substring matches | 0.794 | 0.667 | 0.907 | reverted |
| 17 | whole-word match bonus +50% | 0.799 | 0.685 | 0.889 | reverted |
| 18 | whole-word match bonus +100% | 0.799 | 0.685 | 0.889 | reverted |
| 19 | synonym expansion, full weight | 0.818 | 0.722 | 0.889 | **kept** |
| 20 | synonym expansion, half weight | 0.808 | 0.704 | 0.889 | reverted |
| 21 | directory-segment match weight 1 | 0.835 | 0.759 | 0.907 | **kept** |
| 22 | directory-segment match weight 2 | 0.811 | 0.704 | 0.907 | reverted |
| 23 | token-prefix-of-file-stem bonus 2 | 0.835 | 0.759 | 0.907 | reverted |
| 24 | token-prefix-of-file-stem bonus 1 | 0.835 | 0.759 | 0.907 | reverted |
| 25 | ablation: drop exact file-stem bonus | 0.768 | 0.630 | 0.907 | reverted |
| 26 | exact symbol-name match bonus 2 | 0.826 | 0.741 | 0.907 | reverted |
| 27 | exact symbol-name match bonus 4 | 0.817 | 0.722 | 0.907 | reverted |
| 28 | per-symbol sqrt saturation | 0.835 | 0.759 | 0.907 | reverted |
| 29 | per-symbol contribution cap 2 | 0.835 | 0.759 | 0.907 | reverted |
| 30 | count only top-10 symbol contributions | 0.836 | 0.759 | 0.907 | reverted |
| 31 | count only top-5 symbol contributions | 0.841 | 0.759 | 0.926 | **kept** |
| 32 | class symbols 1.5x | 0.838 | 0.759 | 0.926 | reverted |
| 33 | function symbols 1.5x | 0.823 | 0.722 | 0.926 | reverted |
| 34 | function symbols 1.25x | 0.823 | 0.722 | 0.926 | reverted |
| 35 | adjacent-token bigram identifier bonus 1 | 0.832 | 0.741 | 0.926 | reverted |
| 36 | adjacent-token bigram identifier bonus 2 | 0.832 | 0.741 | 0.926 | reverted |
| 37 | score *= matched-fraction^0.5 | 0.835 | 0.759 | 0.907 | reverted |
| 38 | score *= matched-fraction | 0.814 | 0.722 | 0.907 | reverted |
| 39 | max field + 0.3*rest | 0.840 | 0.759 | 0.907 | reverted |
| 40 | 'test' queries boost test-file features | 0.841 | 0.759 | 0.926 | reverted |
| 41 | pseudo-relevance feedback +3 stems @0.5 | 0.795 | 0.685 | 0.870 | reverted |
| 42 | refine symbol weight 1.5->1.25 | 0.841 | 0.759 | 0.926 | reverted |
| 43 | refine symbol top-k 5->3 | 0.823 | 0.722 | 0.926 | reverted |
| 44 | refine symbol top-k 5->7 | 0.837 | 0.759 | 0.907 | reverted |
| 45 | refine path-segment weight 1->1.5 | 0.823 | 0.722 | 0.926 | reverted |
| 46 | refine file-stem bonus 6->8 | 0.841 | 0.759 | 0.926 | reverted |
| 47 | retry size-norm exponent 1.25 on new best | 0.841 | 0.759 | 0.926 | reverted |
| 48 | retry bigram bonus 1 on new best | 0.832 | 0.741 | 0.926 | reverted |
| 49 | retry max+0.3*rest fusion on new best | 0.840 | 0.759 | 0.907 | reverted |
| 50 | ablation: drop kept synonym expansion (contribution check) | 0.841 | 0.759 | 0.926 | reverted |

Kept 5 of 50: symbol weight 2 → 1.5 (#4), file-stem bonus
4 → 6 (#5), synonym expansion (#19), directory-segment match weight 1
(#21), top-5 symbol contributions only (#31).

Tuning set (54q): MRR 0.791 → 0.841, hit@1 0.667 → 0.759, hit@3
0.889 → 0.926. The tuning number is optimistic by construction (50
selection decisions were made against it). Note: keeper #50's ablation
showed the synonym expansion's marginal contribution on the tuning set
had been absorbed by later keeps; it was retained per protocol.

### Fresh validation (holdout-3, 28 questions, evaluated once per version)

| Version | hit@1 | hit@3 | MRR |
|---|---|---|---|
| main (38c3602) | 0.643 | 0.821 | 0.740 |
| batch-1 head (eb72587) | 0.714 | 0.857 | 0.801 |
| this branch (final) | 0.714 | 0.893 | 0.821 |

Cumulative vs main: hit@1 +7.1 points, hit@3 +7.2 points, MRR +0.081 on
questions never used for selection or tuning. Batch 2's incremental gain
over batch 1 is real but modest on this set (MRR +0.020, hit@3 +3.6
points, hit@1 flat) - most of the cumulative gain came from batch 1.
Same-author, same-harness caveats apply; 28 questions is small.
