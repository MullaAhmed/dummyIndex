# CLI command dispatch — spec

`confidence: INFERRED`

## Intent

The CLI dispatch layer turns command-line arguments into one bounded operation.
It keeps help and compatibility aliases consistent across entry points.
It owns the order of validation, mutation, reporting, and exit codes.
One-run safety gates cannot be bypassed by accident.

## User-visible behavior

The entry point preserves stdout/stderr encodings and escapes unrepresentable
characters, so Unicode help works in Windows code-page terminals.

`dummyindex ingest` aliases `dummyindex context init`. Both accept
`--no-default-plugins` as the canonical one-run opt-out. `--no-superpowers` is its
compatibility alias (`dummyindex/__main__.py:152-173`, `dummyindex/__main__.py:338-341`,
`dummyindex/cli/help.py:21-42`). Either spelling resolves to one boolean, removed
before path and flag parsing. It never persists to config (`dummyindex/cli/init.py:87-107`).

The gate returns before default-specific config migration, trust disclosure, Claude
settings writes, runner probes, or backfill. Project indexing and selected-host
guidance still run, because the flag only suppresses default plugins
(`dummyindex/cli/init.py:17-27`, `dummyindex/cli/init.py:180-229`).

Claude and `both` init runs print the pinned third-party trust disclosure before
any plugin config read or reconciliation. Init then migrates config,
folds equipment intent, and backfills missing reviewed defaults when enabled.
It reads the resulting selected `wired` set. That same set drives declaration and
one materialization pass. A new default becomes available in the same run.
Unrelated targets are not installed (`dummyindex/cli/init.py:29-84`).

Codex-only init returns before the plugin step, never invoking the Claude default
runner (`dummyindex/cli/init.py:121-129`, `dummyindex/cli/init.py:197-229`;
regression coverage at `tests/cli/test_init_cli.py:219-255`).

Default-plugin reporting is best-effort. Success output goes to stdout. Malformed config
and per-target failures go to stderr. Neither fails a completed index build
(`dummyindex/cli/init.py:46-84`).

Config is validated before tolerant migration. Default mutation therefore fails
closed instead of falling back to the built-in set (`dummyindex/cli/init.py:51-68`;
`tests/cli/test_init_cli.py:324-347`). A durable `default_plugins_enabled=false`
config stays byte-identical, with no settings or runner calls
(`tests/cli/test_init_cli.py:350-374`).

`dummyindex context wire` is the interactive escalation surface for declared entries.
Satisfied targets stay untouched. Skill and bad-target
entries are surfaced as manual. It prompts only for valid absent plugins. Without
`--yes`, non-TTY input prints a would-prompt list and never blocks
(`dummyindex/cli/wire.py:46-173`).

An affirmative answer routes one selected entry through declaration and
target-filtered materialization. A custom plugin cannot pull reviewed defaults.
A reviewed default materializes only itself (`dummyindex/cli/wire.py:221-244`;
`tests/cli/test_wire.py:197-282`). A per-entry failure prints
`could not wire ... (left needs-user)`. The command still returns 0 after its summary
(`dummyindex/cli/wire.py:137-173`).

`scan-check` (`ContextSubcommand.SCAN_CHECK` → `scan.run`, `dummyindex/cli/scan.py:25`)
is the validation half of the codebase-scan authoring loop. It is wire-only. It calls
the pure domain validator and prints.

It reports all violations in one pass, not fail-fast. The caller is a model writing
`features/graph.json` by hand. One round trip per mistake is unusable.

Violations are split by severity (`ScanViolationSeverity`,
`dummyindex/context/enums.py:93-105`). An `error` breaks the contract. A `warning`
means a check could not run. Example: a `symbolRef` has no extraction artifact on disk.
The handler feeds `load_symbol_ref_index(features_dir)` into `validate_scan`
(`dummyindex/cli/scan.py:68`).

Each error prints as `<json.path>: <message> [<code>]`. Warnings get a `warning:`
prefix. `--json` emits `{ok, path, confidence, violations[]}`. Each violation carries
`severity`. `ok` reflects errors only (`dummyindex/cli/scan.py:69-95`).
Exit `0` means clean or warnings only, noting an uncurated seed. Exit `1` means
error-severity violations. Exit `2` means no scan to check.

`context check --budget`, `--style`, and `--refs` return before drift detection
(`dummyindex/cli/check.py:75-90`).

`--budget` compares word counts against two ratchets: `.context/doc-budget.txt` and
`tests/data/skill-budget.txt` (`dummyindex/context/domains/docbudget/constants.py:24-25`).
Growth or new over-ceiling docs exit `1`. A malformed ratchet exits `2`.

`--style` checks sentences over 20 words and filler words against
`.context/style-budget.txt` (`dummyindex/context/domains/docbudget/constants.py:29`).
Unrecorded files allow zero violations. With no style ratchet, `--style` prints
violations and a seed hint, then exits `0`. Violations print as
`path:line: rule: excerpt`.

`--update-ratchet` requires `--budget` or `--style` (`dummyindex/cli/check.py:70-72`).
It updates only named groups. Run alone, it exits `2`. Both flags share
`_run_ratchet_check` (`dummyindex/cli/check.py:196-260`). Updates only lower entries.
Growth is refused, exit `1` (`check.py:245-247`).

`--refs` lists durable docs citing `proposals/` or `audits/` paths. It exits `1` on
any hit (`dummyindex/cli/check.py:263-273`).

`graph` (`ContextSubcommand.GRAPH` → `graph.run`, `dummyindex/cli/__init__.py:119`,
`dummyindex/cli/graph.py:23-184`) is the read-only query half.
It has seven bounded verbs: `callers-of|callees-of|impact|path|neighbors|dead-code|community`.
They read `features/symbol-graph.json`. Dispatch is wire-only into
`context.domains.graph_query`. Per-verb arity and flag scope are checked before any
filesystem read. `--depth` applies only to `impact`. `--hops` applies only to
`neighbors`. Integer flags must be >= 1.

Exit `0` means the query was answered. A valid empty answer counts, since zero callers
is what `dead-code` hunts. Exit `1` means an unknown or ambiguous symbol, no path
between endpoints, or an empty community. Exit `2` means a usage error or a missing
or invalid graph artifact. The error points to `dummyindex ingest`.
`--json` switches the renderer from markdown. The help block sits in the canonical
usage template (`dummyindex/cli/help.py:267-293`).

The seam grew with the maintenance, fleet, and evolve family. Four new members joined
the closed alphabet. `MAINTAIN = "maintain"` and `FLEET = "fleet"` are at
`dummyindex/context/enums.py:155-156`. `DRIFT_ACK = "drift-ack"` and `EVOLVE = "evolve"`
are at `dummyindex/context/enums.py:163-164`.

Each is registered in `_HANDLERS` like every other verb
(`ContextSubcommand.MAINTAIN: maintain.run` through `EVOLVE: evolve.run`,
`dummyindex/cli/__init__.py:135-144`; handler imports at `:33-44`). The wire modules
(`dummyindex/cli/maintain.py`, `fleet.py`, `drift_ack.py`, `evolve.py`) parse argv,
lazy-import their domain inside `run`, print, and return a code.

Usage blocks: maintain at `dummyindex/cli/help.py:559-587`, fleet at `:588-630`,
evolve at `:631-692`, drift-ack at `:720-733`. No dispatcher logic changed. Enum membership, one table row,
and a help block are the whole integration. This keeps the
`test_every_enum_member_has_a_handler` guard total.

`reconcile-stamp` has an explicit opt-in, `--heal-orphaned`
(`dummyindex/cli/reconcile.py:85-90`). An orphaned anchor (history rewritten) refuses
by default. The flag re-baselines at HEAD with a loud warning
(`dummyindex/cli/reconcile.py:115-130`). Canonical usage documents it at
`dummyindex/cli/help.py:198-209`.

`memory session-start` prints a local probation block after the memory block.
`_print_probation` reads the hook's `session_id`, calls `session_block`, and prints any
result. It is silent on any error (`dummyindex/cli/memory.py:59-70`; call at `:169`).
It renders via `dummyindex/context/domains/probation/render.py:48`. Semantics belong to
the `probation` feature. A SessionStart hook never fails the session
(`dummyindex/cli/memory.py:170`).

Help is a read-only contract. Top-level help lists the canonical flag before the alias
and labels it (`dummyindex/__main__.py:104-175`). `usage_for` extracts the exact subcommand
block, falling back to full usage only defensively (`dummyindex/cli/help.py:789-797`). The `check` usage lists `--budget`,
`--style`, `--refs`, and `--update-ratchet` (`dummyindex/cli/help.py:59-72`).
Tests require `-h` and `--help` to return 0 without mutating the filesystem, for every
context subcommand (`tests/cli/test_subcommand_help.py:27-53`).

`context hooks status` reports all five managed Claude events, including the per-turn
`UserPromptSubmit` output/skill contract. It exits successfully only when all five are
present (`dummyindex/cli/hooks.py`, `dummyindex/context/hooks.py`).

### Legacy root CLAUDE.md folding (`rebuild`)

Every successful `dummyindex context rebuild` exit folds a dangling legacy root
`CLAUDE.md` into `.claude/CLAUDE.md`. Exits include `--changed` rebuilt,
enriched-preserved, no-change skipped, bare, and full.

The shared `_fold_legacy_claude_md` helper calls `migrate_claude_md_location`
(`dummyindex/cli/rebuild.py:21-37`). The `has_foldable_legacy_claude_md` guard means
rebuild never *creates* guidance or touches an active Codex instruction candidate.
Failures warn on stderr. The exit code stays unchanged (`tests/cli/test_rebuild_migration.py`).

### Rule-copy canary (`tests/cli/test_cli_doc_sync_policy_canary.py`)

A second doc-sync guard sits beside `test_cli_doc_sync.py`. It reuses that module's
`_DEFAULT_PLUGIN_DOCS` and `_DOC_IDS`. The existing guard asserts token *presence*.
This one asserts that three docs restating `ALWAYS_ON_OUTPUT_POLICY` keep each
rule's *statement*: `docs/COMMANDS.md`, `docs/guide/07-cli.md`, and
`dummyindex/skills/skill.md`.

Ported from ponytail's `scripts/check-rule-copies.js` (MIT), using its
`INVARIANTS` fallback. This is not byte equality, because prose differs per doc. Rows now also cover "at most 5 items per
group", Chinese subagent prompts, and English caveman style. The
`command-or-path-before-prose` row was dropped.

Two marker-delimited regions bound the scan: `test-anchor:policy-restatement` and
`test-anchor:policy-selfapply`, which wraps the `i-have-adhd` bullet. `render_skill`
strips them. The strip regex is line-anchored and would miss an inline marker
(`test_render_skill_strips_test_anchor_markers`).

Scope: it catches a **dropped** rule statement and a **named set** of inversions. It
does not catch free-prose contradiction.

## Contracts

- `init.run(args: list[str]) -> int` parses the shared plugin opt-out, host, root,
  depth, docs, and force flags. It builds the index and writes host guidance.
  It installs Claude hooks when applicable. Then it runs the default-plugin
  boundary for Claude-enabled hosts (`dummyindex/cli/init.py:87-231`). Usage and validation
  failures return `2`. A completed build stays `0` on recoverable guidance, hook,
  or plugin failures.
- `_wire_default_plugins_step(project_root: Path, *, platform: str,
  no_default_plugins: bool) -> None` owns the default action order. The order is
  one-run gate, disclosure, strict validation, migration/reconciliation,
  selected-set declaration, materialization, then rendering (`dummyindex/cli/init.py:17-84`).
- `wire.run(args: list[str]) -> int` validates root and arguments, then dispatches the
  interactive reconciler. An absent `.context/` is exit `2`. An absent config is a
  graceful exit `0` (`dummyindex/cli/wire.py:46-63`, `dummyindex/cli/wire.py:96-107`).
- `_wire(out_root: Path, context_dir: Path, *, auto_yes: bool,
  prompt: Callable[[str], str]) -> int` classifies the ledger, prompts or reports,
  then prints a count summary (`dummyindex/cli/wire.py:66-173`).
- `_wire_plugin(out_root: Path, entry: WiredEntry) -> bool` passes the same one-entry
  tuple to declaration and materialization. Declaration errors, needs-user results,
  or install errors return `False` (`dummyindex/cli/wire.py:221-244`).
- `graph.run(args: list[str]) -> int` parses verb, operands, and flags, then loads the
  symbol graph. Operands resolve by node id, bare name, or `path.py:name` suffix.
  Exits: answered `0`; unknown, ambiguous, no-path, or empty-community `1`; usage or
  artifact errors `2` (`dummyindex/cli/graph.py:23-184`).
- `usage_for(sub: ContextSubcommand) -> str` returns every canonical help block whose
  opening line begins with the exact subcommand token, including nested verb lines
  (`dummyindex/cli/help.py:789-797`).
- `_print_help() -> None` renders canonical and legacy flag wording. `main() -> None`
  dispatches install/uninstall directly and maps top-level `ingest` to context `init` (`dummyindex/__main__.py:104-175`,
  `dummyindex/__main__.py:298-348`).

## Examples

`dummyindex context init . --platform both --no-hooks` builds `.context/` and both
guidance surfaces. It prints two pinned disclosures. It reconciles config, declares
selected targets, probes Claude once, and attempts each target once.
Coverage asserts the disclosure precedes every runner call
(`tests/cli/test_init_cli.py:155-216`).

`dummyindex ingest . --no-default-plugins` dispatches to context `init`, builds the
index, and returns before any default-specific action. `--no-superpowers` takes the
same path. Both leave config and settings byte-for-byte unchanged
(`tests/cli/test_init_cli.py:292-321`).

`dummyindex context wire --root REPO --yes` over a config holding only
`caveman@caveman` declares its pinned marketplace and enables it. It invokes only that
target's runner sequence. Superpowers and `i-have-adhd` are not installed as a side
effect (`tests/cli/test_wire.py:227-282`).
