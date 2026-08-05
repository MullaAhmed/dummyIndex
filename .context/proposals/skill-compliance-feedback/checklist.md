# Checklist — Make always-on skill policies self-enforcing through Headroom correction feedback

> Work top-to-bottom. Tick `- [x]` only after the item is independently
> verified. Implementation waves are serialized because each consumes the
> preceding public contract.

## Wave 1 — correction grammar

- [x] Add deterministic skill correction/revocation models, parsing,
  normalization, event deduplication, ordering, aggregation, and focused tests
  (`miner/corrections.py`, `miner/models.py`, `miner/enums.py`,
  `miner/__init__.py`, `test_corrections.py`).

## Wave 2 — profile scan and safe cache

- [x] Add main-thread-only multi-profile discovery, row-level repo scoping,
  strict bounded cache projection, unique-temp atomic writes, and privacy /
  concurrency / empty-transition tests (`miner/feedback.py`, `miner/resolve.py`,
  `miner/scan.py`, `miner/pipeline.py`, `miner/__init__.py`, `atomic_io.py`, and
  their named tests).

## Wave 3 — memory CLI

- [x] Add `memory mine` and `memory prompt-context`, current-prompt handling,
  fail-open exact JSON, help synchronization, and CLI tests
  (`memory/enums.py`, `memory/__init__.py`, `cli/memory.py`, `cli/help.py`,
  `test_memory_cli.py`, `test_cli_doc_sync.py`).

## Wave 4 — Claude hook wiring

- [x] Add the SessionStart miner and independent UserPromptSubmit feedback
  command without changing Stop or the five-event status contract; verify
  local/global guards, static fallback, user-hook preservation, shell
  fail-open behavior, and reinstall idempotence (`context/hooks.py`,
  `test_hooks.py`).

## Wave 5 — public contract

- [x] Update `CHANGELOG.md`, `docs/COMMANDS.md`,
  `docs/guide/03-architecture.md`, `docs/guide/07-cli.md`,
  `docs/guide/09-lifecycle.md`, `dummyindex/skills/skill.md`, and
  `dummyindex/skills/council/05-onboarding.md`; verify the unchanged shared
  policy canary.

## Wave 6 — focused acceptance

- [x] **GATE** Acceptance: run
  `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest
  tests/context/domains/memory/miner -q --tb=short -p no:cacheprovider`.
- [x] **GATE** Acceptance: run
  `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest
  tests/context/domains/memory/test_memory_cli.py -q --tb=short
  -p no:cacheprovider`.
- [x] **GATE** Acceptance: run
  `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest
  tests/cli/test_cli_doc_sync.py -q --tb=short -p no:cacheprovider`.
- [x] **GATE** Acceptance: run
  `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest
  tests/context/test_hooks.py -q --tb=short -p no:cacheprovider`.
- [x] **GATE** Acceptance: verify the BOS-shaped ADHD fixture and a generic
  skill fixture in `test_corrections.py` both produce their exact safe slugs.

## Wave 7 — repository acceptance

- [x] **GATE** Acceptance: run
  `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/ -q
  --tb=short -p no:cacheprovider`, `ruff check --no-cache .`, and
  `ruff format --check .`.
