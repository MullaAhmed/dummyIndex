# Reality-check verifier — spec

confidence: INFERRED

## Intent

After the council writes a feature's canonical docs, the reality checker re-reads the
line-checkable ones (`plan.md`, `concerns.md`, plus legacy essay docs during the v0.14
transition), pulls out every *concrete* grounding claim, and verifies each against the
deterministic extraction artefacts — `map/symbols.json`, `features/symbol-graph.json`,
`map/files.json`, and the actual source on disk. It is a fact-check on grounding, not on
judgment: it never tries to confirm semantic/behavioural claims, only that the symbols,
call edges, and file:line citations the docs assert actually exist
(`dummyindex/context/domains/reality_check/verify.py:21-67`). A contradicted claim can optionally
demote the feature's `confidence` to `AMBIGUOUS`, and a later clean re-run restores it —
so the documented "fix docs → re-run" loop self-heals
(`dummyindex/cli/reality_check.py:9-15`).

`spec.md` is deliberately *not* line-checked — it is intent-level. Only `plan.md` and
`concerns.md` (and the legacy docs) carry the concrete claims that get verified
(`reality_check/extract.py:1-5`, `reality_check/extract.py:13-21`).

## User-visible behavior

**The reality-check CLI.** `dummyindex context reality-check --feature <id>` resolves the
context root, requires `--feature` (else prints an error and returns `2`), and errors `2`
if `.context/` is absent or the feature folder is missing
(`dummyindex/cli/reality_check.py:24-60`). It runs the check, writes the report artefacts,
prints the markdown summary by default (`--json` prints the JSON report instead), and
returns `1` when any claim is contradicted, else `0`
(`dummyindex/cli/reality_check.py:71-75`). Unknown arguments return `2`
(`reality_check.py:36-38`).

**The `_reality-check` report.** Each run writes two sibling artefacts under
`features/<id>/`: `_reality-check.json` (the full report) and `_reality-check.md` (a human
summary) (`dummyindex/context/domains/reality_check/render.py:10-18`). The markdown opens with a
verified/contradicted/ambiguous tally, then a **Contradicted** section (claims that
couldn't be reconciled with the AST, for the persona to revise) and an **Ambiguous**
section (symbols exist but the relation couldn't be confirmed — indirect calls/aliases)
(`reality_check/render.py:21-59`).

**`--demote`.** With `--demote`, a contradicted report flips the feature's `confidence` to
`AMBIGUOUS` in both `feature.json` and `features/INDEX.json`, stashing the prior value under
`confidence_demoted_from`; a clean report pops the stash and restores the prior confidence.
Demotion is idempotent (a second demote is a no-op) and promotion is never destructive — a
dirty report, a non-`AMBIGUOUS` feature, or a missing/invalid stash are all no-ops
(`dummyindex/cli/reality_check.py:65-69`, `reality_check/confidence.py:26-94`).

## Contracts

Public functions (re-imported by the CLI at `dummyindex/cli/reality_check.py:16-22`):

- `reality_check_feature(context_dir: Path, feature_id: str) -> RealityReport`
  (`dummyindex/context/domains/reality_check/verify.py:21-67`) — reads the canonical docs,
  extracts claims, verifies each, returns the report. Raises `FileNotFoundError` if the
  feature folder is absent (`reality_check/verify.py:31-32`).
- `write_report(feat_dir: Path, report: RealityReport) -> tuple[Path, Path]`
  (`reality_check/render.py:10-18`) — atomically writes `_reality-check.json` + `.md`, returns
  both paths.
- `render_report_md(report: RealityReport) -> str` (`reality_check/render.py:21-59`) — the
  markdown summary string.
- `demote_feature_on_contradiction(features_dir: Path, report: RealityReport) -> bool`
  (`reality_check/confidence.py:26-61`) — demote on contradictions; returns whether anything changed.
- `promote_feature_on_clean(features_dir: Path, report: RealityReport) -> bool`
  (`reality_check/confidence.py:64-94`) — exact inverse; restore stashed confidence on a clean run.
- `run(args: list[str]) -> int` (`dummyindex/cli/reality_check.py:8-75`) — CLI entry; exit
  codes `0`/`1`/`2`.

Data classes (frozen, data-only with `to_dict()`):

- `Claim(text, source_file, kind, subject, object, status, reason=None)`
  (`reality_check/models.py:10-29`) — `kind` ∈ {`calls`, `uses`, `has_method`, `file:line`};
  `status` ∈ {`verified`, `contradicted`, `ambiguous`}.
- `RealityReport(schema_version, feature_id, claims_total, verified, contradicted,
  ambiguous, claims)` (`reality_check/models.py:32-55`) with `has_contradictions` property
  (`reality_check/models.py:42-44`).

## Examples

- `dummyindex context reality-check --feature reality-check` — print the markdown summary,
  write both artefacts, exit `0`/`1`.
- `dummyindex context reality-check --feature auth --json` — emit the JSON report instead.
- `dummyindex context reality-check --feature auth --demote` — verify, and on contradiction
  demote `auth` to `AMBIGUOUS` (stashing prior); a later clean `--demote` run restores it.
- A claim `` `Calculator.add` calls `Helper.compute` `` resolves both bare names against
  `map/symbols.json`; if both exist and an edge exists in the symbol graph → `verified`; if
  both exist but no edge → `ambiguous`; if a name is missing and repo-rooted →
  `contradicted`; if missing but stdlib/third-party-rooted → `ambiguous`
  (`reality_check/verify.py:83-113`).
- A citation `` `package.json:3` `` resolves the literal path on disk even when the code
  index doesn't track it (`reality_check/verify.py:179-185`).
