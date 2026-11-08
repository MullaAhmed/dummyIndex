# Feature: Evolution probation lifecycle

`confidence: INFERRED`

Local lifecycle for rules derived from human chat corrections. A rule enters probation after a gate pass. Counted evidence then promotes, suspends, demotes or expires it. Probation items stay local to the checkout and are not committed. Exposure is not applicability.

## Behavior

- States: `observed`, `proposed`, `probation`, `promoted`, `suspended`, `demoted`, `expired`, `quarantined` (`dummyindex/context/domains/probation/enums.py:8-18`).
- `LIVE` is `probation` and `suspended` (`enums.py:38`). Only live items feed the session block.
- `proposed` is transient. `enter` sets it, then saves `probation` in the same call (`actions.py:111-114`).
- `observed` is declared but never assigned in this package.
- Entry: `enter` runs after a chat-event gate pass (`dummyindex/context/domains/evolve_learning.py:351-363`).
- `enter` blocks high-impact text (`actions.py:71-72`).
- `enter` blocks when a live item already holds the target, or 10 or more live items exist (`actions.py:76-81`).
- `enter` blocks a non-terminal id collision (`actions.py:85-87`).
- High-impact text: scanner hits, URLs, code fences or `$ ` command lines (`rules.py:21`, `rules.py:126-135`).
- Probe: one key, `require` or `forbid`, with a regex of at most 200 characters (`rules.py:138-154`).
- Probe check: tool-call signatures from the first exposure turn to the attribution turn (`rules.py:55-73`).
- Harm: two distinct non-origin sessions and two distinct days (`rules.py:76-81`).
- Promote eligibility: at least 10 non-origin sessions and 3 days, with no harm or contest (`rules.py:91-116`). Probed items also need one YES verdict and no NO (`rules.py:108-116`).
- Transitions, applied by `sync`:
  - Retraction: live to `demoted` (`sync.py:171-176`).
  - Harm: live to `demoted`. A promoted item gets `demote_pending` (`sync.py:262-267`).
  - Source hash change: `probation` to `suspended`. A match restores it (`sync.py:278-285`).
  - No exposure inside retention: live to `expired` (`sync.py:288-298`).
  - Two ignored counts set `needs_enforcement` (`sync.py:184-189`, `constants.py:4`).
- Routing (`rules.py:41-52`): known item ids count. `.context/conventions/<name>.md`, except `naming`, seeds a learning event (`sync.py:139-140`). Seeding needs `durable` and no live item for the target in that session (`sync.py:134-138`). A failed seed leaves the row unconsumed (`sync.py:238-239`). `.context/features/` and other paths are digested (`sync.py:141`).
- Promote: `promote` syncs first, then gates each eligible item (`actions.py:119-138`). A content-scan hit quarantines it (`actions.py:144-148`).
- Demote: a promoted item loses its managed block through the gate. Other states become `demoted` (`actions.py:274-295`).
- Storage: one JSON per item plus `_state.json` under `.context/cache/evolution/probation/` (`store.py:17-18`, `store.py:49-88`).
- Lock: `store.locked` raises when another writer holds the observe lock (`store.py:91-96`).
- Sync: runs when evolution is enabled and the lock is free (`sync.py:66-75`). Probe rows wait unless `probes=True` (`sync.py:162-163`).
- Session block: lists probation items within 1600 characters and records exposure (`render.py:48-104`, `render.py:107-117`).
- Session block: one `Next:` line per session, by priority (`render.py:131-154`).
- Report: counts, rates and resident bytes. Rates are `None` when undefined (`render.py:157-223`).
- Hook: `_print_probation` prints the block on SessionStart (`dummyindex/cli/memory.py:59-70`, `memory.py:169`).
- CLI: `attribute` and `probation report|promote|demote` (`dummyindex/cli/evolve_probation.py:16-153`). Dispatch at `dummyindex/cli/evolve.py:67`.
- `probation` verbs run `sync(probes=True)` first (`dummyindex/cli/evolve_probation.py:136`). `attribute` syncs after recording (`:73`).
- `attribute --retracts` needs `--verdict attributed` and `--item` (`:60`).
- Kill switch: `DUMMYINDEX_EVOLUTION=0` prints a disabled line and exits 0 (`dummyindex/context/domains/observe/keys.py:56-64`).
- Retention: 30 days, lowered by `cleanupPeriodDays` (`keys.py:14`, `keys.py:67-75`).

## Boundaries

- `evolution`: `actions.py` imports the gate, promotion and learning-record helpers (`actions.py:13-17`). Curated writes happen only through `run_gate` and `promote_files` (`actions.py:185-212`).
- `observe`: supplies corrections, attributions, exposures, the lock, the kill switch, retention and `scan_text` (`sync.py:14-23`, `rules.py:10`, `render.py:13-23`).
- `session-memory`: no import. The probation package does not import the memory domain. Only the hook in `cli/memory.py:59-70` calls `session_block`.

## Tests

- `tests/context/domains/test_probation.py`: state, routing, probes, harm, eligibility, sync, render.
- `tests/context/domains/test_probation_actions.py`: enter, promote, demote, gate failure.
- `tests/cli/test_evolve_probation_cli.py`: verbs, exit codes, disabled line.
