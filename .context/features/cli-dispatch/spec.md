# CLI command dispatch — spec

`confidence: INFERRED`

## Intent

The CLI dispatch layer turns command-line arguments into one bounded operation,
keeps help and compatibility aliases consistent across entry points, and owns
the user-facing ordering of validation, mutation, reporting, and exit codes. It
keeps domain policy downstream while making one-run safety gates impossible to
bypass accidentally.

## User-visible behavior

The entry point keeps native stdout/stderr encodings but reconfigures both with
`errors="backslashreplace"`, so Unicode help text also works in Windows
code-page terminals (`dummyindex/__main__.py:266-270`).

`dummyindex ingest` aliases `dummyindex context init`; both accept
`--no-default-plugins` as the canonical one-run opt-out and
`--no-superpowers` as its compatibility alias
(`dummyindex/__main__.py:158-179`, `dummyindex/__main__.py:322-325`,
`dummyindex/cli/help.py:18-39`). Either spelling resolves to one boolean and is
removed before path/flag parsing, so it never persists to config
(`dummyindex/cli/init.py:87-107`). The gate returns before default-specific
config migration, trust disclosure, Claude settings writes, runner probes, or
backfill; project indexing and selected-host guidance still run because the flag
only suppresses default plugins (`dummyindex/cli/init.py:17-27`,
`dummyindex/cli/init.py:191-240`).

Claude and `both` init runs print the pinned third-party trust disclosure before
reading or reconciling plugin config, then migrate config, fold equipment intent,
backfill missing reviewed defaults when enabled, and read the resulting selected
`wired` set. That same set drives declaration and one materialization pass, so a
new default is available in the same run without installing unrelated targets
(`dummyindex/cli/init.py:29-84`). Codex-only init returns before the plugin step
and never invokes the Claude default runner (`dummyindex/cli/init.py:233-240`;
regression coverage at `tests/cli/test_init_cli.py:219-257`).

Default-plugin reporting is best-effort. Successful migration/reconciliation
and per-target enable/install/defer output go to stdout; malformed config and
per-target declaration/install failures go to stderr without failing an already
completed index build (`dummyindex/cli/init.py:46-84`). A malformed config is
validated before tolerant migration, so default mutation fails closed rather
than falling back to the built-in set (`dummyindex/cli/init.py:51-68`;
`tests/cli/test_init_cli.py:384-409`). A durable
`default_plugins_enabled=false` config remains byte-identical and makes no
settings or runner calls (`tests/cli/test_init_cli.py:410-439`).

`dummyindex context wire` is the interactive escalation surface for declared
entries. It reads config, classifies each entry, leaves satisfied targets alone,
surfaces skill/bad-target entries as manual, and prompts only for valid absent
plugins; non-TTY input without `--yes` prints a would-prompt list and never
blocks (`dummyindex/cli/wire.py:27-143`). An affirmative answer routes exactly
one selected entry through declaration and target-filtered materialization, so a
custom plugin cannot pull reviewed defaults and a reviewed default materializes
only itself (`dummyindex/cli/wire.py:191-211`;
`tests/cli/test_wire.py:188-273`). Per-entry failure is reported as
`could not wire ... (left needs-user)` and the command still returns 0 after its
summary (`dummyindex/cli/wire.py:107-143`).

`scan-check` (`ContextSubcommand.SCAN_CHECK` → `scan.run`,
`dummyindex/cli/scan.py:18`) is the validation half of the codebase-scan
authoring loop and a clean example of the wire-only contract: parse flags, call
the pure domain validator, print, return a code. It is deliberately
**all-violations-in-one-pass** rather than fail-fast, because its caller is a
model authoring `features/graph.json` freehand — one round trip per mistake
would make the loop unusable. Violations are severity-split
(`ScanViolationSeverity`, `dummyindex/context/enums.py:86-98`): `error`
breaks the contract; `warning` means a check could not run (e.g. a `symbolRef`
with no extraction artifact on disk to resolve it against — the handler feeds
`load_symbol_ref_index(features_dir)` into `validate_scan`,
`dummyindex/cli/scan.py:61`). Each error prints as
`<json.path>: <message> [<code>]`, warnings with a `warning:` prefix; `--json`
emits `{ok, path, confidence, violations[]}` where every violation carries
`severity` and `ok` reflects errors only (`dummyindex/cli/scan.py:62-88`).
Exit `0` clean or warnings-only (noting when the scan is still the uncurated
seed), `1` on error-severity violations, `2` when there is no scan to check.

`graph` (`ContextSubcommand.GRAPH` → `graph.run`,
`dummyindex/cli/__init__.py:110`, `dummyindex/cli/graph.py:19-184`) is the
read-only query half of graph consumption: seven bounded verbs
(`callers-of|callees-of|impact|path|neighbors|dead-code|community`) over
`features/symbol-graph.json`, dispatched wire-only to
`context.domains.graph_query`. Per-verb arity and flag scoping are validated
before any filesystem read (`--depth` only for `impact`, `--hops` only for
`neighbors`; integer flags must be >= 1). Exit `0` when the query was answered
— a valid empty answer counts, since zero callers is exactly what `dead-code`
hunts; `1` for an unknown or ambiguous symbol, no path between endpoints, or
an empty community; `2` on usage errors or a missing/invalid graph artifact
(with a pointer to `dummyindex ingest`). `--json` switches the renderer from
the markdown default. Its help block sits in the canonical usage template
(`dummyindex/cli/help.py:258-284`).

The maintenance/fleet/evolve family joined the closed alphabet as four members
— `MAINTAIN = "maintain"`, `FLEET = "fleet"`
(`dummyindex/context/enums.py:148-149`) and `DRIFT_ACK = "drift-ack"`,
`EVOLVE = "evolve"` (`dummyindex/context/enums.py:156-157`) — each registered
in `_HANDLERS` like every other verb
(`ContextSubcommand.MAINTAIN: maintain.run` … `EVOLVE: evolve.run`,
`dummyindex/cli/__init__.py:126-135`, handler imports at `:28-39`). The wire
modules (`dummyindex/cli/maintain.py`, `fleet.py`, `drift_ack.py`,
`evolve.py`) follow the standard contract — parse argv, lazy-import their
domain inside `run`, print, return a code — and their usage blocks live in the
canonical template (`dummyindex/cli/help.py:514-542` maintain,
`:543-585` fleet, `:586-645` evolve, `:673-686` drift-ack). No dispatcher
logic changed to admit them: enum membership, one table row, and a help block
are the whole integration, which is exactly why the
`test_every_enum_member_has_a_handler` guard stays total.

### `reconcile-stamp` anchor and meta errors

`--heal-orphaned` is an explicit opt-in
(`dummyindex/cli/reconcile.py:81-86`). An orphaned anchor (history rewritten)
normally refuses; with the flag and no `--to`, the stamp re-baselines at HEAD
with a loud warning instead (`dummyindex/cli/reconcile.py:108-131`); without
it the refusal is unchanged. Documented in the canonical usage
(`dummyindex/cli/help.py:189-202`).

An unusable `meta.json` gets a fix-specific error: a newer `schema_version`
prints ``error: meta.json was written by a newer dummyindex — upgrade
dummyindex (<read_meta message>)``; missing/unreadable/corrupt keeps
``error: no readable meta.json to stamp. Run `dummyindex ingest` first.``
Both go to stderr, exit `1`, and write nothing
(`dummyindex/cli/reconcile.py:154-167`, `dummyindex/cli/reconcile.py:199-221`;
`tests/context/build/test_reconcile.py:917-953`).

Help is a read-only contract. Top-level help lists the canonical flag before the
alias and labels the alias explicitly (`dummyindex/__main__.py:88-262`), while
`usage_for` extracts the exact context-subcommand block and falls back to full
usage only defensively (`dummyindex/cli/help.py:742-762`). Tests require both
`-h` and `--help` to return 0 without filesystem mutation for every context
subcommand (`tests/cli/test_subcommand_help.py:23-49`).

`context hooks status` reports all five managed Claude events, including the
per-turn `UserPromptSubmit` output/skill contract; its exit status is successful
only when that event plus SessionStart, Stop, PreCompact, and PreToolUse are all
present. Install/refresh output uses the same event name, so a 0.34-era
four-event project visibly reports the additive upgrade rather than silently
remaining partial (`dummyindex/cli/hooks.py`, `dummyindex/context/hooks.py`).

### `rebuild` post-success reporting and legacy CLAUDE.md folding

Every `rebuild` that ran a build or refresh — `--changed` rebuilt,
enriched-preserved, or bare/full — prints the `.context/` layout-migration
outcome after its summary via `_print_migration`
(`dummyindex/cli/rebuild.py:102-103`, `:133`, `:156-157`, `:138-145`). Lines,
two-space prefixed, in order: up to five `removed <path>` then `… and N more
removed`; `backed up to .context/<path>` (same cap); `warning: migration
<error>` (same cap); and, on the enriched path only, one uncapped
``warning: <artifact> failed (<error>); version stamp not advanced — fix the
cause, then run `dummyindex context rebuild --changed` `` per failed required
artefact (`dummyindex/context/build/upgrade.py:577-615`). All go to stdout and
the exit stays `0`; an empty migration, or the no-change `--changed` skip,
prints nothing extra.

Every successful exit — including that skip — then folds a dangling legacy root
`CLAUDE.md` into the canonical `.claude/CLAUDE.md` via `_fold_legacy_claude_md`
over `migrate_claude_md_location` (`dummyindex/cli/rebuild.py:21-36`). The
`has_foldable_legacy_claude_md` guard keeps rebuild from ever *creating*
guidance or touching an active Codex instruction candidate; failures are
warn-and-continue on stderr with the rebuild's exit code unchanged
(`tests/cli/test_rebuild_migration.py`).

### Rule-copy canary (`tests/cli/test_cli_doc_sync_policy_canary.py`)

A second doc-sync guard beside `test_cli_doc_sync.py`, reusing that module's
`_DEFAULT_PLUGIN_DOCS`/`_DOC_IDS` rather than forking the seam. The existing
guard asserts token *presence*; this one asserts the three docs that restate
`ALWAYS_ON_OUTPUT_POLICY` in prose (`docs/COMMANDS.md`, `docs/guide/07-cli.md`,
`dummyindex/skills/skill.md`) still carry each load-bearing rule's *statement*.

Ported from ponytail's `scripts/check-rule-copies.js` (MIT) — specifically its
`INVARIANTS` fallback for surfaces too long to byte-compare. Not byte equality:
the prose is deliberately different per doc.

Two marker-delimited regions bound what is scanned — `test-anchor:policy-restatement`
around the restatement paragraph and `test-anchor:policy-selfapply` around the
`i-have-adhd` reviewed-source bullet. Scoping matters: an earlier version
scanned whole 28–55 KB files and reddened on correct prose 500 lines away. The
markers are stripped at render time by `render_skill` so they never reach an
installed `SKILL.md`, with `test_render_skill_strips_test_anchor_markers`
as the actual guarantee (the strip regex is line-anchored and would miss an
inline marker).

Honest scope, stated in the module docstring: it catches a **dropped** rule
statement reliably, and a **named set** of inversions. General contradiction
detection in free prose is out of reach for a regex canary.

## Contracts

- `init.run(args: list[str]) -> int` parses the shared plugin opt-out, host,
  root, depth, docs, and force flags; builds the index; writes selected-host
  guidance; installs Claude hooks when applicable; and only then runs the
  default-plugin boundary for Claude-enabled hosts
  (`dummyindex/cli/init.py:87-242`). Usage/validation failures return `2`; a
  completed build remains `0` when best-effort guidance, hook, or plugin work
  reports a recoverable failure.
- `_wire_default_plugins_step(project_root: Path, *, platform: str,
  no_default_plugins: bool) -> None` owns the default action order: one-run gate,
  disclosure, strict validation, migration/reconciliation, selected-set
  declaration, selected-set materialization, then result rendering
  (`dummyindex/cli/init.py:17-84`).
- `rebuild.run(args: list[str]) -> int` returns `2` for `BuildScopeError`,
  unknown args, or a bare rebuild of a curated index; `0` on every
  build/refresh/skip path (`dummyindex/cli/rebuild.py:39-135`).
- `reconcile.run_stamp(args: list[str]) -> int` returns `2` for unknown args,
  missing `.context/`, or invalid `--to`; `1` for a refusal or unusable meta;
  `0` on stamp or off-git no-op (`dummyindex/cli/reconcile.py:77-196`).
  `_newer_schema_error(context_dir: Path) -> str | None` returns `read_meta`'s
  message only when it contains `_NEWER_SCHEMA_MARKER`
  (`dummyindex/cli/reconcile.py:199-221`).
- `wire.run(args: list[str]) -> int` validates root/arguments and dispatches the
  interactive reconciler; absent `.context/` is exit `2`, while absent config is
  a graceful exit `0` (`dummyindex/cli/wire.py:27-44`,
  `dummyindex/cli/wire.py:68-79`).
- `_wire(out_root: Path, context_dir: Path, *, auto_yes: bool,
  prompt: Callable[[str], str]) -> int` classifies the full ledger, prompts or
  reports, and prints a deterministic count summary
  (`dummyindex/cli/wire.py:47-143`).
- `_wire_plugin(out_root: Path, entry: WiredEntry) -> bool` passes the same
  one-entry tuple to declaration and materialization. Declaration errors,
  needs-user results, or install errors return `False`
  (`dummyindex/cli/wire.py:191-211`).
- `graph.run(args: list[str]) -> int` parses verb, operands, and flags; loads
  the symbol graph; resolves each operand by node id, bare name, or
  `path.py:name` suffix; and maps domain outcomes to exits: answered `0`,
  unknown/ambiguous symbol, no path, or empty community `1`, usage or artifact
  errors `2` (`dummyindex/cli/graph.py:19-184`).
- `usage_for(sub: ContextSubcommand) -> str` returns every canonical help block
  beginning with the exact subcommand token, including nested verb lines
  (`dummyindex/cli/help.py:742-762`).
- `_print_help() -> None` renders top-level commands and canonical/legacy flag
  wording; `main() -> None` dispatches install/uninstall directly and maps
  top-level `ingest` to context `init`
  (`dummyindex/__main__.py:88-262`, `dummyindex/__main__.py:265-342`).

## Examples

`dummyindex context init . --platform both --no-hooks` builds `.context/` and
both managed guidance surfaces, prints the two pinned third-party disclosures,
reconciles an opted-in config, declares all selected targets, probes Claude once,
and attempts each selected target once. Integration coverage asserts each
marketplace-add precedes its matching install and the disclosure exists before
the first runner call (`tests/cli/test_init_cli.py:155-217`).

`dummyindex ingest . --no-default-plugins` dispatches to context `init`, builds
the index, and returns before any default-specific config/settings/runner action.
The compatibility spelling `--no-superpowers` follows the identical path; both
leave an existing config and settings file byte-for-byte unchanged
(`tests/cli/test_init_cli.py:352-383`).

`dummyindex context wire --root REPO --yes` over a config containing only
`caveman@caveman` declares its pinned marketplace, enables it, and invokes only
that target's runner sequence. The selected tuple prevents superpowers or
i-have-adhd from being installed as a side effect
(`tests/cli/test_wire.py:218-273`).
