# reality-check — spec

`confidence: INFERRED`

## Intent

Fact-check a feature's *curated prose docs* against the *deterministic extraction backbone* and the *real source on disk*, then report — and optionally act on — divergences. After the council writes a feature's docs, prose drifts from code; this domain re-reads the line-checkable docs, pulls out the concrete grounding claims (a call relation, a `path:line` citation, a "class X has method Y"), and assigns each a verdict: `verified`, `contradicted`, or `ambiguous`. A contradiction can self-heal the index by demoting the feature's `confidence` to `AMBIGUOUS`; a later clean run restores it.

The cardinal rule is encoded in `_is_external_reference` (`verify.py:205-227`) and `_resolve_cited_path` (`verify.py:157-202`): **absence is never proof of falsehood when the referent lives outside the repo**. A token rooted in stdlib/third-party, or a basename matching several files, is `ambiguous` — never `contradicted`. The checker fact-checks *grounding*, not judgment; semantic/behavioral claims are deliberately not extracted.

## User-visible behavior

CLI: `dummyindex context reality-check --feature <id> [--json] [--demote]` (`cli/reality_check.py:8-75`).

- Requires `--feature <id>`; missing → exit `2` with `--feature <id> is required` (`cli/reality_check.py:39-45`).
- Missing `.context/` → exit `2`, "Run `dummyindex ingest` first" (`cli/reality_check.py:48-54`).
- Unknown feature folder → `FileNotFoundError` caught → exit `2` (`cli/reality_check.py:56-60`).
- Always writes both `features/<id>/_reality-check.json` and `_reality-check.md` (`cli/reality_check.py:62-63`).
- `--json` prints the report dict; otherwise prints the rendered Markdown (`cli/reality_check.py:71-74`).
- `--demote`: contradictions → `demote_feature_on_contradiction`; clean → `promote_feature_on_clean` (`cli/reality_check.py:65-69`).
- **Exit code is the signal**: `1` when contradictions exist, else `0` (`cli/reality_check.py:75`). This is what lets a council loop branch on the result.

## Contracts

Public surface re-exported from the package `__init__.py:58-101` (import path `dummyindex.context.domains.reality_check` unchanged):

- `reality_check_feature(context_dir: Path, feature_id: str) -> RealityReport` — orchestrator; reads docs, extracts, verifies, summarizes. Raises `FileNotFoundError` if the feature folder is absent. (`verify.py:21-67`)
- `write_report(feat_dir: Path, report: RealityReport) -> tuple[Path, Path]` — atomic JSON+MD write. (`render.py:10-18`)
- `render_report_md(report: RealityReport) -> str` — human summary string. (`render.py:21-59`)
- `demote_feature_on_contradiction(features_dir: Path, report: RealityReport) -> bool` — flips confidence to `AMBIGUOUS`, stashes prior under `confidence_demoted_from`, mirrors to `INDEX.json`; idempotent. (`confidence.py:26-61`)
- `promote_feature_on_clean(features_dir: Path, report: RealityReport) -> bool` — exact inverse; restores stashed confidence on a clean report. (`confidence.py:64-94`)
- `Claim` — frozen dataclass, fields `text/source_file/kind/subject/object/status/reason`, with `to_dict()`. (`models.py:10-29`)
- `RealityReport` — frozen dataclass with counts + `claims` tuple; `has_contradictions` property; `to_dict()`. (`models.py:32-55`)
- `SCHEMA_VERSION = 1`, `DEMOTED_FROM_KEY = "confidence_demoted_from"` constants. (`models.py:7`, `confidence.py:21`)

## Examples

Claim kinds and their verdict rules:

- Call: `` `_extract_claims` calls `_push` `` → `verified` iff both names are symbols **and** a `calls`/`uses` edge exists in `symbol-graph.json` (`verify.py:83-113`). Both exist, no edge → `ambiguous`.
- `path:line`: `` `verify.py:67` `` → resolved via 4-step precedence, then checked `1 ≤ line ≤ line_count` (`verify.py:125-152`).
- has_method: `` class `RealityReport` has method `to_dict` `` → both names in symbols → `verified` (`verify.py:115-123`).
- External: `` `claim` uses `os.environ` `` → `os` not a repo module → `ambiguous`, never `contradicted` (`verify.py:205-227`).
