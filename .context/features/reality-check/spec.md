# reality-check — spec

`confidence: INFERRED`

## Intent

Fact-check a feature's *curated prose docs* against the *deterministic extraction backbone* and the *real source on disk*. Report and optionally act on divergences. After the council writes docs, prose drifts from code. It re-reads line-checkable docs. It pulls out concrete grounding claims: a call relation, a `path:line` citation, or "class X has method Y". Each claim gets a verdict: `verified`, `contradicted`, or `ambiguous`. A contradiction can self-heal the index by demoting the feature's `confidence` to `AMBIGUOUS`. A later clean run restores it.

The cardinal rule lives in `_is_external_reference` (`verify.py:266-288`) and `_resolve_cited_path` (`verify.py:195-264`). **Absence is never proof of falsehood when the referent lives outside the repo.** A token rooted in stdlib or third-party code, or a basename matching several files, is `ambiguous`, never `contradicted`. The checker fact-checks *grounding*, not judgment. Semantic and behavioral claims are deliberately not extracted.

**Trust boundary (the inputs are untrusted).** `.context/` docs, their `path:line` citations, `meta.json["root"]`, and the `--feature` id are all LLM-authored or CLI-supplied. Never trust them as filesystem paths. Every cited path and the repo root are treated as adversarial:

- **Path confinement.** Every concrete-path return branch of `_resolve_cited_path` routes through `resolve_under_root`, re-exported from `pipeline/io`. It checks against the trusted `repo_root`, or `feat_dir` for the feature-own-doc branch. A citation resolving outside that root is `contradicted` without ever opening the target (`verify.py:250-264`). Cases: an absolute path, a `../` escape, or an in-repo symlink whose realpath leaves the tree. So the verifier is not a filesystem read oracle. In-root symlinks resolve before the check and stay legitimate. Only escaping symlinks are rejected. A post-resolution symlink swap remains a documented residual; see `concerns.md`.
- **Trusted repo root.** `repo_root` is the resolved git toplevel (`_trusted_repo_root` / `_git_toplevel`, via `is_git_repo`/`resolve_git_dir`, `verify.py:437-488`). It is not any ancestor of `context_dir`, which would admit `/`. An untrusted `meta.json["root"]` is honored only when it resolves to exactly that toplevel. Anything else, such as a poisoned `"/"`, falls back to the anchor. With no git toplevel at all, the historical `context_dir.parent` fallback applies.
- **Read-target guard.** Before line-counting, the resolved file passes `is_safe_read_target(..., max_bytes=_MAX_CITED_FILE_BYTES)`, a 16 MiB limit (`verify.py:29,175-180`). A symlink, non-regular file (FIFO/device), or oversize blob is `ambiguous`, never streamed.
- **Feature-id guard.** A `feature_id` containing `/`, `\`, `..`, or NUL is rejected. Rejection happens at the CLI boundary (`cli/reality_check.py:50-57`), with non-zero exit and no out-of-`features/` write. It also happens inside `reality_check_feature` via `_reject_unsafe_feature_id` (`verify.py:36-49`). So neither entry point trusts the value.

## User-visible behavior

CLI: `dummyindex context reality-check --feature <id> [--json] [--demote]` (`cli/reality_check.py:8-75`).

- Requires `--feature <id>`; missing → exit `2` with `--feature <id> is required` (`cli/reality_check.py:40-48`).
- A `--feature` containing `/`, `\`, `..`, or NUL → exit `2`, `error: invalid --feature …` (`cli/reality_check.py:50-57`). Rejected before any read or write, so the value can never become a path-traversal write primitive.
- Missing `.context/` → exit `2`, "Run `dummyindex ingest` first".
- Unknown feature folder → `FileNotFoundError` caught → exit `2`.
- Always writes both `features/<id>/_reality-check.json` and `_reality-check.md` (`cli/reality_check.py:73-74`).
- `--json` prints the report dict, otherwise the rendered Markdown.
- `--demote`: contradictions → `demote_feature_on_contradiction`; clean → `promote_feature_on_clean` (`cli/reality_check.py:76-89`).
- The CLI then prints the applied confidence delta as one line on **stderr**. Forms: `demoted <prior>→AMBIGUOUS`, `restored AMBIGUOUS→<value>`, or `unchanged` when nothing was touched.
- The delta comes from the widened `ConfidenceTransition | None` return. A bare bool could not carry the prior value or distinguish the three cases.
- **Exit code is the signal**: `1` when contradictions exist, else `0`. A council loop branches on this result.

## Contracts

Public surface re-exported from the package `__init__.py:58-101`. The import path `dummyindex.context.domains.reality_check` is unchanged.

- `reality_check_feature(context_dir: Path, feature_id: str) -> RealityReport` — orchestrator; reads docs, extracts, verifies, summarizes. Raises `FileNotFoundError` if the feature folder is absent, or `ValueError` if `feature_id` is a path-traversal attempt (`_reject_unsafe_feature_id`). (`verify.py:51-99`)
- `write_report(feat_dir: Path, report: RealityReport) -> tuple[Path, Path]` — atomic JSON and MD write through the unified `write_text_atomic` writer. The local `_atomic_write` is retired. `_reality-check.json` is dumped with `sort_keys=True`. (`render.py:11-22`)
- `render_report_md(report: RealityReport) -> str` — human summary string. (`render.py:25-62`)
- `demote_feature_on_contradiction(features_dir: Path, report: RealityReport) -> ConfidenceTransition | None` — flips confidence to `AMBIGUOUS`, stashes prior under `confidence_demoted_from`, mirrors to `INDEX.json`. Idempotent: a second call on an already-AMBIGUOUS feature returns `None`. Returns a `ConfidenceTransition(kind="demoted", from_value, to_value)` describing the change, or `None` when nothing was touched. (`confidence.py:57-108`)
- `promote_feature_on_clean(features_dir: Path, report: RealityReport) -> ConfidenceTransition | None` — exact inverse of demote. Restores stashed confidence on a clean report. Returns `ConfidenceTransition(kind="restored", …)` or `None`. (`confidence.py:110-157`)
- `ConfidenceTransition` — frozen dataclass `(kind, from_value: str | None, to_value: str)` carrying the delta back to the CLI. `kind` is `TRANSITION_DEMOTED` (`"demoted"`) or `TRANSITION_RESTORED` (`"restored"`). `from_value` is `None` when feature.json had no prior value. (`confidence.py:42-54`)
- `Claim` — frozen dataclass, fields `text/source_file/kind/subject/object/status/reason`, with `to_dict()`. (`models.py:10-29`)
- `RealityReport` — frozen dataclass with counts + `claims` tuple; `has_contradictions` property; `to_dict()`. (`models.py:32-55`)
- `SCHEMA_VERSION = 1`, `DEMOTED_FROM_KEY = "confidence_demoted_from"` constants. (`models.py:7`, `confidence.py:31`)

**Atomic two-file confidence mirror.** `demote`/`promote` no longer write `feature.json` then mirror `INDEX.json` as two independent read-modify-writes. Both now go through `_commit_confidence_change` (`confidence.py:160-203`). `_mirror_confidence_to_index` stages INDEX.json's bytes to a `.tmp` sibling **before** any replace. It returns `(index_path, index_tmp, matched)`, or `None` when INDEX is absent or unreadable. The feature.json bytes stage to *its* `.tmp`. Only then do the two `Path.replace` calls run back-to-back. Consequences:

- **INDEX is staged and committed before the stash is popped from disk.** A raise *before the first replace* leaves both files untouched. So a demotion's stash can never be lost mid-write.- **Best-effort, not crash-atomic.** The two `Path.replace` calls are distinct syscalls. A crash strictly *between* them leaves INDEX.json lagging feature.json by one transition. The next run reconciles it, because the mirror is idempotent. This narrowed window is documented as best-effort, not claimed crash-atomic.
- **Zero-match signal.** `_mirror_confidence_to_index` / `_commit_confidence_change` return a `matched` bool. `True` if any INDEX entry matched `feature_id`. `False` when none did. It surfaces a mirror that landed nowhere, instead of a silent no-op.
- Both `feature.json` and `INDEX.json` are dumped `sort_keys=True` for stable serialization.

## Examples

Claim kinds and their verdict rules:

- Call: `` `_extract_claims` calls `_push` `` → `verified` iff both names are symbols **and** a `calls`/`uses` edge exists in `symbol-graph.json` (`verify.py:115-145`). Both exist, no edge → `ambiguous`.
- `path:line`: `` `verify.py:67` `` → resolved via 4-step precedence (each branch confinement-checked), guarded by `is_safe_read_target`, then checked `1 ≤ line ≤ line_count` (`verify.py:157-193`). An out-of-root citation → `contradicted` with no open.
- has_method: `` class `RealityReport` has method `to_dict` `` → both names in symbols → `verified` (`verify.py:147-155`).
- External: `` `claim` uses `os.environ` `` → `os` not a repo module → `ambiguous`, never `contradicted` (`verify.py:266-288`).
