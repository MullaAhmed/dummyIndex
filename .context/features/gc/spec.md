# Context-hygiene garbage collection

`confidence: EXTRACTED`

GC enumerates only `proposals/` and `audits/`. It reports signals and a pre-council `Recommendation` (delete, close, review, keep). `Disposition` stays the council verdict. The host judges and confirms deletion. Source: `dummyindex/context/domains/gc/recommend.py:18`.

Guards block retirement on durable references, changed hashes, interrupted closeout or missing fixtures. `force_partial` and `allow_untracked` never bypass the knowledge guard. Dry run runs the same guards without lock or `rmtree`. `--yes` re-runs them. Only `.context/INDEX.md` is skipped as a durable reference. Source: `dummyindex/context/domains/gc/delete.py:188`, `dummyindex/context/domains/proposals/retirement.py:108`.

`gc closeout --draft` writes under `.context/cache/gc/`, never overwrites, and an unedited draft fails. Source: `dummyindex/context/domains/proposals/draft.py:49`.

Orphaned anchor nudges once per session; shallow clones stay silent. Evolution files under `.context/gc/` are never listed or deleted. Future cleanup adds `Candidate` rows with a new `CandidateKind`. Source: `dummyindex/context/domains/gc/anchor.py:94`, `dummyindex/context/domains/gc/scan.py:43`.
