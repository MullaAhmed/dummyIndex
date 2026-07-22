# CLI command dispatch — spec

`confidence: INFERRED`

## Intent

The CLI dispatch layer turns command-line arguments into one bounded operation,
keeps help and compatibility aliases consistent across entry points, and owns
the user-facing ordering of validation, mutation, reporting, and exit codes. It
keeps domain policy downstream while making one-run safety gates impossible to
bypass accidentally.

## User-visible behavior

`dummyindex ingest` aliases `dummyindex context init`; both accept
`--no-default-plugins` as the canonical one-run opt-out and
`--no-superpowers` as its compatibility alias
(`dummyindex/__main__.py:152-173`, `dummyindex/__main__.py:304-307`,
`dummyindex/cli/help.py:21-42`). Either spelling resolves to one boolean and is
removed before path/flag parsing, so it never persists to config
(`dummyindex/cli/init.py:87-107`). The gate returns before default-specific
config migration, trust disclosure, Claude settings writes, runner probes, or
backfill; project indexing and selected-host guidance still run because the flag
only suppresses default plugins (`dummyindex/cli/init.py:17-27`,
`dummyindex/cli/init.py:180-229`).

Claude and `both` init runs print the pinned third-party trust disclosure before
reading or reconciling plugin config, then migrate config, fold equipment intent,
backfill missing reviewed defaults when enabled, and read the resulting selected
`wired` set. That same set drives declaration and one materialization pass, so a
new default is available in the same run without installing unrelated targets
(`dummyindex/cli/init.py:29-84`). Codex-only init returns before the plugin step
and never invokes the Claude default runner (`dummyindex/cli/init.py:121-129`,
`dummyindex/cli/init.py:197-229`; regression coverage at
`tests/cli/test_init_cli.py:219-255`).

Default-plugin reporting is best-effort. Successful migration/reconciliation
and per-target enable/install/defer output go to stdout; malformed config and
per-target declaration/install failures go to stderr without failing an already
completed index build (`dummyindex/cli/init.py:46-84`). A malformed config is
validated before tolerant migration, so default mutation fails closed rather
than falling back to the built-in set (`dummyindex/cli/init.py:51-68`;
`tests/cli/test_init_cli.py:324-347`). A durable
`default_plugins_enabled=false` config remains byte-identical and makes no
settings or runner calls (`tests/cli/test_init_cli.py:350-374`).

`dummyindex context wire` is the interactive escalation surface for declared
entries. It reads config, classifies each entry, leaves satisfied targets alone,
surfaces skill/bad-target entries as manual, and prompts only for valid absent
plugins; non-TTY input without `--yes` prints a would-prompt list and never
blocks (`dummyindex/cli/wire.py:46-173`). An affirmative answer routes exactly
one selected entry through declaration and target-filtered materialization, so a
custom plugin cannot pull reviewed defaults and a reviewed default materializes
only itself (`dummyindex/cli/wire.py:221-244`;
`tests/cli/test_wire.py:197-282`). Per-entry failure is reported as
`could not wire ... (left needs-user)` and the command still returns 0 after its
summary (`dummyindex/cli/wire.py:137-173`).

Help is a read-only contract. Top-level help lists the canonical flag before the
alias and labels the alias explicitly (`dummyindex/__main__.py:103-173`), while
`usage_for` extracts the exact context-subcommand block and falls back to full
usage only defensively (`dummyindex/cli/help.py:504-557`). Tests require both
`-h` and `--help` to return 0 without filesystem mutation for every context
subcommand (`tests/cli/test_subcommand_help.py:27-53`).

## Contracts

- `init.run(args: list[str]) -> int` parses the shared plugin opt-out, host,
  root, depth, docs, and force flags; builds the index; writes selected-host
  guidance; installs Claude hooks when applicable; and only then runs the
  default-plugin boundary for Claude-enabled hosts
  (`dummyindex/cli/init.py:87-231`). Usage/validation failures return `2`; a
  completed build remains `0` when best-effort guidance, hook, or plugin work
  reports a recoverable failure.
- `_wire_default_plugins_step(project_root: Path, *, platform: str,
  no_default_plugins: bool) -> None` owns the default action order: one-run gate,
  disclosure, strict validation, migration/reconciliation, selected-set
  declaration, selected-set materialization, then result rendering
  (`dummyindex/cli/init.py:17-84`).
- `wire.run(args: list[str]) -> int` validates root/arguments and dispatches the
  interactive reconciler; absent `.context/` is exit `2`, while absent config is
  a graceful exit `0` (`dummyindex/cli/wire.py:46-63`,
  `dummyindex/cli/wire.py:96-107`).
- `_wire(out_root: Path, context_dir: Path, *, auto_yes: bool,
  prompt: Callable[[str], str]) -> int` classifies the full ledger, prompts or
  reports, and prints a deterministic count summary
  (`dummyindex/cli/wire.py:66-173`).
- `_wire_plugin(out_root: Path, entry: WiredEntry) -> bool` passes the same
  one-entry tuple to declaration and materialization. Declaration errors,
  needs-user results, or install errors return `False`
  (`dummyindex/cli/wire.py:221-244`).
- `usage_for(sub: ContextSubcommand) -> str` returns every canonical help block
  beginning with the exact subcommand token, including nested verb lines
  (`dummyindex/cli/help.py:515-557`).
- `_print_help() -> None` renders top-level commands and canonical/legacy flag
  wording; `main() -> None` dispatches install/uninstall directly and maps
  top-level `ingest` to context `init`
  (`dummyindex/__main__.py:103-173`, `dummyindex/__main__.py:259-324`).

## Examples

`dummyindex context init . --platform both --no-hooks` builds `.context/` and
both managed guidance surfaces, prints the two pinned third-party disclosures,
reconciles an opted-in config, declares all selected targets, probes Claude once,
and attempts each selected target once. Integration coverage asserts each
marketplace-add precedes its matching install and the disclosure exists before
the first runner call (`tests/cli/test_init_cli.py:155-216`).

`dummyindex ingest . --no-default-plugins` dispatches to context `init`, builds
the index, and returns before any default-specific config/settings/runner action.
The compatibility spelling `--no-superpowers` follows the identical path; both
leave an existing config and settings file byte-for-byte unchanged
(`tests/cli/test_init_cli.py:292-321`).

`dummyindex context wire --root REPO --yes` over a config containing only
`caveman@caveman` declares its pinned marketplace, enables it, and invokes only
that target's runner sequence. The selected tuple prevents superpowers or
i-have-adhd from being installed as a side effect
(`tests/cli/test_wire.py:227-282`).
