

---

### critic-database (data-integrity)

## Data integrity

- **Prose-rooted call/uses edges silently dropped — partial false-negative surface (`reality_check.py:474-493`).** `_load_call_edges` normalizes every node `label`, but module-level nodes in `symbol-graph.json` carry a docstring *as the label* (verified: 531 of 6084 calls/uses edges have a source label like `"Token-usage reporting over Claude Code transcripts…"`). After `clean()` these become multi-word strings that no parsed claim can match, so any legitimate `` `module` calls `X` `` claim whose subject is a docstring-labeled node resolves `ambiguous` instead of `verified`. Not a corruption (no false `contradicted`), but the plan's Open-question about label coupling (`plan.md:131-133`) understates it: the mismatch is already live for ~9% of edges, not a hypothetical future format drift.

- **Graph reads `label`, never `norm_label`, yet `norm_label` exists (`reality_check.py:478-484` vs node keys `['label','norm_label',…]`).** The graph builder already publishes a normalized field; the verifier re-implements its own `rstrip("()").lstrip(".").rsplit(".")` normalization over raw `label`. Two independent normalizers over the same data is exactly the silent-drift coupling the plan flags — a builder that populates `norm_label` correctly but changes `label` would desync verdicts with zero alert. Prefer reading `norm_label` when present.

- **Normalizer divergence: `rstrip("()")` (graph) vs `endswith("()")`+slice (claims) (`reality_check.py:481` vs `reality_check.py:411-412`).** Claim side strips a trailing `()` only as a suffix; graph side strips *all* trailing `(` and `)` chars greedily. For ordinary identifiers these agree, but they are not the same function — a label ending in a stray paren normalizes differently on each side, re-introducing match asymmetry. Two code paths claiming to "normalize the same way" (`plan.md:47-48`) should call one shared helper.

- **`has_method` verdict does not verify the method belongs to the class (`reality_check.py:265-273`).** Both `cls` and `method` are checked for existence in the flat `symbol_names` set independently; a `` class `Foo` has method `bar` `` claim is `verified` whenever *any* class named `Foo` and *any* symbol named `bar` exist anywhere in the repo — even if `bar` lives on an unrelated class. This is a false-positive (over-verification) on a name collision; the symbol-graph `method` relation (present in edges) is the correct evidence source and is not consulted.

- **`symbol_names` collisions make calls/uses over-permissive (`reality_check.py:243-258`, `_load_symbols:446-455`).** Verification keys on bare names in a flat `frozenset`; `_bare_name` discards the dotted owner. Two distinct `save` methods on different classes collapse to one name, so a call-edge between *either* pair satisfies the claim. Acceptable given the regex extracts bare names, but worth noting the verdict granularity is name-level, not symbol-level — a real claim about `A.save → B.save` can be "verified" by an unrelated `C.save → D.save` edge.

- **Write integrity is sound — atomic, schema-stamped, but bypasses the canonical helper (`reality_check.py:592-596` vs `data-access.md:5-9`).** `_atomic_write` correctly does tmp+`replace`, and reports carry `schema_version` (`reality_check.py:60,424`). However it is a private re-implementation of `write_text_atomic` (`atomic_io.py:11-24`) — the convention names that as the canonical helper and warns against per-module reimplementations. Functionally equivalent here (no EOF normalization, byte-faithful), but it sidesteps the hash-baseline contract the convention centralizes; route through `write_text_atomic`.

- **JSON outputs are not sorted-key — breaks byte-identical re-run guarantee (`reality_check.py:546`, `:640`, `:675`, `:695`).** `data-access.md:13` requires deterministic serialization (`sort_keys=True`); the reality-check writers emit `json.dumps(payload, indent=2)` *without* `sort_keys`. Report dicts are built in fixed order so they're stable, but the `feature.json`/`INDEX.json` mutations (demote/promote/mirror) round-trip an arbitrarily-ordered loaded dict and re-emit it unsorted — a key-order churn that can dirty diffs on every `--demote` run. The `_reality-check.json` artefact is also un-gitignored leaf output and should follow the sorted convention.

- **Demote/promote idempotency and inverse-pairing are correct (`reality_check.py:610-678`).** Verified: demote no-ops once `confidence == AMBIGUOUS` (`:631`) and only stashes a valid prior with no existing stash (`:634-639`); promote acts only on AMBIGUOUS + valid stash and pops it (`:667-674`). Inverse pairing holds. Minor inconsistency: demote compares `prior == ConfidenceLevel.AMBIGUOUS` (enum, `:631`) while promote compares `payload.get("confidence") != ConfidenceLevel.AMBIGUOUS.value` (string, `:667`); both happen to work via the `str, Enum` mixin (`enums.py:16`) but the asymmetry is fragile — if `ConfidenceLevel` ever drops the `str` mixin, line 631's comparison silently becomes always-False and demotion would re-stash a real prior over AMBIGUOUS. Pin both to `.value`.

- **`--demote` mirror is not transactional across two files (`reality_check.py:640-644`, `:675-677`).** `feature.json` is written atomically, then `_mirror_confidence_to_index` writes `INDEX.json` atomically — but the pair is not atomic together. A crash between the two leaves `feature.json` at AMBIGUOUS with `INDEX.json` still showing the old confidence (or vice-versa on promote). No relational DB to enforce this, but the gap means the two confidence mirrors can disagree; mirror failure is also silent (`:686-687` returns on missing index). Low likelihood, but it is a genuine cross-artefact consistency hole the plan's "mirror through `_mirror_confidence_to_index`" framing (`plan.md:67-69`) treats as a single guaranteed step.

- **Claim dedup key can collapse semantically distinct file:line claims (`reality_check.py:194`, `:214-215`).** `_extract_claims` dedupes on `(kind, subject.lower, object.lower)`; for `file:line` the object is the line *number*. `` `foo.py:42` `` cited in two docs with different surrounding `text` dedup to one claim — fine. But `Foo.bar` vs `foo.BAR` (calls) collapse via `.lower()`, and Python is case-sensitive, so a real claim about `Config` and one about `config` merge and only the first survives. Edge case, but the lowercase key trades a small false-negative risk for dedup.


---

### critic-security (security)

## Security

Adversarial lens: feature-id path traversal, doc-driven file reads outside repo, ReDoS in claim regexes. Local CLI, low-moderate surface — top threats, all cited to `path:range`.

- **Feature-id path traversal — arbitrary directory escape via `--feature` (`reality_check.py:148`, `cli/reality_check.py:39-45,62`).** `--feature` value reaches `context_dir / "features" / feature_id` with no `..`/`/`/absolute rejection and no under-root containment check. `--feature ../../../../etc` or `--feature /abs/path` (absolute RHS discards prefix per `pathlib`) escapes `.context/`; the `.is_dir()` guard (`:149`) gates existence only. Same id reaches demote/promote (`:622`,`:659`) + `read_feature_files` (`dev_pick.py:333`), so `--demote` can atomically rewrite `feature.json`/`INDEX.json` outside the tree. Fix: reject `/ \ .. NUL` and assert `feat_dir.resolve()` is under `(context_dir/"features").resolve()`.

- **Doc-driven file read outside repo root — citation escape (`reality_check.py:331-335`, `:291-294`).** `on_disk = repo_root / path_str` with `path_str` verbatim from a `` `…:NN` `` token; `_FILE_LINE_RE` class `[\w./\-]+` (`:82-83`) admits `../`. A doc line `` `../../../../etc/passwd:1` `` opens + line-counts an arbitrary host file. Existence/line-count oracle (no bytes in report), not content exfil, but reads occur on attacker-driven paths. Fix: containment-check `on_disk.resolve()` (and the `:334-335` branch) under `repo_root.resolve()`.

- **`repo_root` attacker-influenced via `meta.json` `root` (`reality_check.py:181`,`:526-534`).** `_repo_root_from_meta` reads `root` unvalidated; a tampered `meta.json` repoints citation resolution anywhere readable, compounding the escape. Validate it's an existing dir; fall back to `context_dir.parent` on disagreement.

- **ReDoS — checked, CLEARED (`reality_check.py:74-88`).** All four regexes use single non-overlapping class quantifiers (`[\w.]*`,`[\w]*`,`[\w./\-]+`,`\d+`) — no nested quantifiers/quantified alternation/backreferences, linear-time. `re.finditer` over docs (`:208-215`) safe on adversarial input. No fix; flagged so future regex edits stay known-sensitive.

- **Name-level verdict, not provenance — over-verification (`reality_check.py:243-273`).** Flat-`frozenset` keying lets a doc earn a false `verified` for `has_method`/calls/uses via any same-named symbol anywhere. Undermines the `verified`/`--demote` trust signal the tool exists to produce; symbol-graph owner/method relation is the sound source, unconsulted.

- **No size/symlink guard on read targets (`reality_check.py:164`,`:294`).** `errors="ignore"` reads + uncapped `sum(1 for _ in resolved.open("rb"))` with no symlink rejection; combined with traversal, a citation to a FIFO/huge/`/dev` path can hang or balloon the line count. Pair containment check with `is_symlink()` rejection + a line/byte bound.

## Critic — product-surface (stage 3, critic-product)

Scope: false-positive/negative UX, report actionability, `--demote` surprises, claim-coverage limits. Bullets `scenario — observed — gap`.

- **Clean `--demote` silently re-promotes confidence (`cli/reality_check.py:65-69`, `reality_check.py:648-678`).** A clean run restores a stashed confidence (AMBIGUOUS→HIGH) but `render_report_md` (`:551-589`) prints only verdict counts. The most surprising side effect of `--demote` — a confidence *write on a clean report* — is invisible in the output. Report should state the confidence transition.

- **`--demote` does two directions under a one-direction name (`cli/reality_check.py:11-14`,`:65-69`).** Named/documented as the contradiction→AMBIGUOUS demotion, but the same flag promotes on a clean run. No opt-out: a manually-set confidence after a contradiction is silently overwritten by the stash on the next clean `--demote`.

- **Zero-claim feature = clean pass / false "all good" (`reality_check.py:419-431`,`:551-561`).** No backtick-shaped claims → `claims_total=0`, exit 0, "0 verified". No distinction between "checked and grounded" and "nothing was checkable"; a prose-only doc passes trivially.

- **Only four claim grammars are checkable; doc prose is invisible (`reality_check.py:74-88`).** Regexes match only `` `A` calls/uses `B` ``, `` `Cls` has method `m` ``, `` `path:NN` ``. Narrative claims and un-backticked citations are never extracted, so a doc with wrong prose still passes. The report never states its coverage, so "verified" over-reads.

- **High ambiguous bucket has no triage priority (`reality_check.py:577-588`).** Given the docstring-label (~9%, `concerns.md:3`), name-collision (`:11`), and "no direct call edge" (`:259-263`) ambiguities, many legit claims land Ambiguous. Listed flat with "—"/generic reasons; for dozens of claims this is an undifferentiated wall with no tool-limitation-vs-real-drift ranking.

- **`has_method` contradiction can be a false positive indistinguishable from a real one (`reality_check.py:265-273`).** A genuinely-existing method under a different spelling / dynamically added → "method not in symbols" contradiction; remediation copy (`:567-570`) tells the persona to "revise or remove" a possibly-true statement. No confidence qualifier on contradiction verdicts.

- **`file:line` verified = in-bounds, not content-correct (`reality_check.py:291-302`).** `` `foo.py:42` `` is verified whenever the file has ≥42 lines; never checks line 42 still holds the cited symbol. Citations rot silently after edits while staying "verified" — the strongest-sounding verdict is the weakest guarantee, and the report doesn't say so.

- **Contradictions raised against orphaned legacy docs (`reality_check.py:62-71`).** `_CANONICAL_DOCS` still scans five v0.14 essays; a stale `security.md` left in a re-councilled feature yields claims with `source_file` pointing at a doc outside the `plan.md`+`concerns.md` workflow, muddying which file to edit.

No cross-review dispute — these amplify the prior Data-integrity (`concerns.md:3,9,11,17,19`) and Security (`:33`) findings on the user-facing surface; cited inline above.
