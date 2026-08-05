# Plan — Make always-on skill policies self-enforcing through Headroom correction feedback

> Ordered, file-path-naming tasks. Cite reused symbols from
> `.context/map/symbols.json` where you can reuse instead of writing new.

## Tasks

1. Add the deterministic correction/revocation model, parser, and aggregator in
   `dummyindex/context/domains/memory/miner/corrections.py` **(NEW)**,
   `dummyindex/context/domains/memory/miner/models.py`,
   `dummyindex/context/domains/memory/miner/enums.py`, and
   `dummyindex/context/domains/memory/miner/__init__.py`. Reuse the existing
   frozen-dataclass/closed-enum pattern and cover human-event filtering,
   direct/complaint/revocation grammar, quote/code false positives,
   normalization and aliases, UUID/fingerprint deduplication,
   timestamp/fallback ordering, and two-post-revocation-event qualification in
   `tests/context/domains/memory/miner/test_corrections.py` **(NEW)**.
   Conventions:
   `.context/conventions/coding-practices.md`,
   `.context/conventions/folder-organization.md`,
   `.context/conventions/naming.md`, and
   `.context/conventions/testing.md`.

2. Build the multi-profile, main-thread-only scan and local cache projection in
   `dummyindex/context/domains/memory/miner/feedback.py` **(NEW)**,
   `dummyindex/context/domains/memory/miner/resolve.py`,
   `dummyindex/context/domains/memory/miner/scan.py`,
   `dummyindex/context/domains/memory/miner/pipeline.py`,
   `dummyindex/context/domains/memory/miner/__init__.py`,
   `dummyindex/context/domains/atomic_io.py`, and
   `tests/context/domains/test_atomic_io.py`. Verify with
   `tests/context/domains/memory/miner/test_feedback.py` **(NEW)**,
   `tests/context/domains/memory/miner/test_resolve.py`,
   `tests/context/domains/memory/miner/test_scan.py`,
   `tests/context/domains/memory/miner/test_pipeline.py`, and
   `tests/context/domains/memory/miner/test_scope.py`. Reuse and strengthen
   `write_text_atomic` (`atomic_io_write_text_atomic` in
   `.context/map/symbols.json`; source confirmed at
   `dummyindex/context/domains/atomic_io.py:12`) with unique temporary siblings.
   Enforce exact row `cwd`, non-recursive root JSONLs,
   active/default/home-profile union, schema/bounds/symlink validation,
   unchanged-write elision, and no raw prompt/event metadata in
   `.context/cache/skill-feedback.json` **(NEW)**. Leave the tool-signature
   `failure-patterns.md` pipeline explicit and unchanged. Conventions:
   `.context/conventions/coding-practices.md`,
   `.context/conventions/data-access.md`,
   `.context/conventions/folder-organization.md`, and
   `.context/conventions/testing.md`.

3. Add the wire-only runtime commands `mine` **(NEW)** and `prompt-context`
   **(NEW)** through `MemoryVerb.MINE` **(NEW)** and
   `MemoryVerb.PROMPT_CONTEXT` **(NEW)**. Reuse `MemoryVerb`
   (`enums_memoryverb` in `.context/map/symbols.json`; source confirmed at
   `dummyindex/context/domains/memory/enums.py:17`) and `read_hook_stdin`
   (`memory_read_hook_stdin`; source confirmed at
   `dummyindex/cli/memory.py:23`). Edit
   `dummyindex/context/domains/memory/enums.py`,
   `dummyindex/context/domains/memory/__init__.py`,
   `dummyindex/cli/memory.py`, `dummyindex/cli/help.py`,
   `tests/context/domains/memory/test_memory_cli.py`, and
   `tests/cli/test_cli_doc_sync.py`. The CLI must keep hook paths fail-open,
   consume current `prompt` stdin for same-turn directives/revocations, emit
   exact compact JSON only when safe feedback exists, and remain silent
   otherwise. Conventions:
   `.context/conventions/coding-practices.md`,
   `.context/conventions/data-access.md`, and
   `.context/conventions/testing.md`.

4. Wire the commands into the canonical five-event hook bodies in
   `dummyindex/context/hooks.py` and verify them in
   `tests/context/test_hooks.py`: one silent miner command at SessionStart plus
   one CLI-backed `prompt-context` command in UserPromptSubmit; Stop remains
   byte-identical. Reuse `_hooks_for_scope`
   (`hooks_hooks_for_scope` in `.context/map/symbols.json`; source signature
   confirmed at `dummyindex/context/hooks.py:386`) and preserve local/global
   guards, order-independent valid payloads, the profile-independent static
   command, user-authored co-located hooks, exact five-event `HookStatus`,
   fail-open shell execution, and byte-idempotent reinstall. Conventions:
   `.context/conventions/coding-practices.md` and
   `.context/conventions/testing.md`.

5. Update the public contract in `CHANGELOG.md`, `docs/COMMANDS.md`,
   `docs/guide/03-architecture.md`, `docs/guide/07-cli.md`,
   `docs/guide/09-lifecycle.md`, `dummyindex/skills/skill.md`, and
   `dummyindex/skills/council/05-onboarding.md`. Describe the Headroom-derived
   correction branch honestly, the two new memory verbs, SessionStart-only
   historical scan, same-turn per-prompt injection, local cache bounds,
   revocation, fail-open behavior, and privacy boundary. Do not edit canary
   source; verify the unchanged shared-policy regions with
   `tests/cli/test_cli_doc_sync_policy_canary.py`.

6. Verify the complete contract with the commands named in
   `spec.md#Acceptance`, using `-p no:cacheprovider`,
   `PYTHONDONTWRITEBYTECODE=1`, and Ruff's `--no-cache` where shown so the
   verification wave is read-only. Post-build deterministic/curated context
   reconciliation remains the conductor's normal workflow step, not part of
   this no-write verification task.

## Reuse and drift

- Reused indexed symbols:
  `atomic_io_write_text_atomic`, `enums_memoryverb`,
  `memory_read_hook_stdin`, and `hooks_hooks_for_scope`.
- Reused source-only pilot seams:
  `mine_and_feed`, `scan_transcript_store`, `parse_transcript`, and
  `render_report`.
- Planning drift: the source-only pilot seams exist and were opened during
  planning, but the current symbol map does not yet list them.
  `hooks_hooks_for_scope` is present with a stale range; source wins. The stale
  `.context/PROJECT.md` and equip SHA-pin prose are unrelated grounding drift.

## Tooling map

All implementation, test, and documentation tasks are ordinary native Codex
work and carry no `— via` tag. Build should route them to native `worker`
subagents. No Claude equipment or plugin mutation is required or permitted.

## Wave disjointness

The implementation is intentionally serialized because Tasks 1–4 share the
miner public surface or consume the immediately preceding contract. Task 5
depends on the final runtime behavior, and Task 6 reads the completed tree.

| Wave | Item | Writes |
|---|---|---|
| 1 | Task 1 | `miner/corrections.py`, `miner/models.py`, `miner/enums.py`, `miner/__init__.py`, `test_corrections.py` |
| 2 | Task 2 | `miner/feedback.py`, `miner/resolve.py`, `miner/scan.py`, `miner/pipeline.py`, `miner/__init__.py`, `atomic_io.py`, `test_atomic_io.py`, `test_feedback.py`, `test_resolve.py`, `test_scan.py`, `test_pipeline.py`, `test_scope.py` |
| 3 | Task 3 | `memory/enums.py`, `memory/__init__.py`, `cli/memory.py`, `cli/help.py`, `test_memory_cli.py`, `test_cli_doc_sync.py` |
| 4 | Task 4 | `context/hooks.py`, `test_hooks.py` |
| 5 | Task 5 | `CHANGELOG.md`, `docs/COMMANDS.md`, `docs/guide/03-architecture.md`, `docs/guide/07-cli.md`, `docs/guide/09-lifecycle.md`, `skills/skill.md`, `skills/council/05-onboarding.md` |
| 6 | Task 6 | no project writes; bytecode, pytest cache, and Ruff cache disabled |

No file is written by two items in the same wave, and no wave contains a reader
of a file another item in that wave rewrites.

## Critique revision

The single panel round's BLOCK/HIGH findings were folded into the profile-union
model, row-level repo validation, main-only SessionStart scan, same-turn prompt
path, separate gitignored cache, revocation lifecycle, strict numeric bounds,
unique atomic temp files, CLI help coverage, and indexed `_hooks_for_scope`
reuse. Deliberately omitted: automatic legacy tool-signature mining (its raw
structured inputs are unsafe for a hook) and a wall-clock CI threshold (the
structural file-work assertion is deterministic; the live BOS benchmark is
informational).
