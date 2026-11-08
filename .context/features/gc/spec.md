# Context-hygiene garbage collection

`confidence: EXTRACTED`

GC enumerates only `proposals/` and `audits/`. It reports signals and a pre-council `Recommendation` (delete, close, review, keep). `Disposition` stays council verdict. Host confirms deletion. Source: `dummyindex/context/domains/gc/recommend.py:18`.

Guards block retirement on durable references, changed hashes, interrupted closeout, missing fixtures. `force_partial` and `allow_untracked` never bypass knowledge guard. Dry run, without `--yes`, runs the same guards without lock or `rmtree`. The reference scan skips `.context/INDEX.md` and `.context/fleet/` run state. Source: `dummyindex/context/domains/gc/delete.py:178`, `dummyindex/context/domains/gc/delete.py:188`, `dummyindex/context/domains/proposals/retirement.py:108`.

`gc closeout --draft` writes under `.context/cache/gc/`, never overwrites. Unedited drafts fail; blank discard reasons rejected. Source: `dummyindex/context/domains/proposals/draft.py:49`, `dummyindex/context/domains/proposals/closeout.py:172`.

Orphaned anchor nudges once per session; shallow clones stay silent. Evolution files under `.context/gc/` are never listed or deleted. Future cleanup adds `Candidate` rows with new `CandidateKind`. Source: `dummyindex/context/domains/gc/anchor.py:94`, `dummyindex/context/domains/gc/scan.py:43`, `dummyindex/context/domains/gc/enumerate.py:36`, `dummyindex/context/domains/gc/models.py:18`, `dummyindex/context/domains/gc/enums.py:23`.
