# Feature: Evolution probation lifecycle

`confidence: INFERRED`

Local lifecycle for rules derived from human chat corrections. A rule enters probation after a gate pass. Counted evidence then promotes, suspends, demotes or expires it. Probation items stay local to the checkout and are not committed. Exposure is not applicability.

## Behavior

- States: `observed`, `proposed`, `probation`, `promoted`, `suspended`, `demoted`, `expired`, `quarantined` (`dummyindex/evolve/probation/enums.py:8-18`).
- `LIVE` is `probation` and `suspended` (`enums.py:38`). Only live items feed the session block.
- `proposed` is transient. `enter` sets it, then saves `probation` in the same call (`actions.py:115-118`).
- `observed` is declared but never assigned in this package.
- Entry: `enter` runs after a chat-event gate pass (`dummyindex/evolve/evolve_learning.py:358-370`).
- `enter` blocks high-impact text (`actions.py:75-76`).
- `enter` blocks when a live item already holds the target, or 10 or more live items exist (`actions.py:80-85`).
- `enter` blocks a non-terminal id collision (`actions.py:89-91`).
- High-impact text: scanner hits, URLs, code fences or `$ ` command lines (`rules.py:22`, `rules.py:127-136`).
- Probe: one key, `require` or `forbid`, with a regex of at most 200 characters (`rules.py:139-155`).
- Probe check: tool-call signatures from the first exposure turn to the attribution turn (`rules.py:56-74`).
- Harm: two distinct non-origin sessions and two distinct days (`rules.py:77-82`).
- Promote eligibility: at least 10 non-origin sessions and 3 days, with no harm or contest (`rules.py:92-117`). Probed items also need one YES verdict and no NO (`rules.py:109-117`).
- Transitions, applied by `sync`:
  - Retraction: live to `demoted` (`sync.py:173-178`).
  - Harm: live to `demoted`. A promoted item gets `demote_pending` (`sync.py:264-269`).
  - Source hash change: `probation` to `suspended`. A match restores it (`sync.py:280-287`).
  - No exposure inside retention: live to `expired` (`sync.py:290-300`).
  - Two ignored counts set `needs_enforcement` (`sync.py:186-191`, `constants.py:4`).
- Routing (`rules.py:42-53`): known item ids count. `.context/conventions/<name>.md`, except `naming`, seeds a learning event (`sync.py:141-142`). Seeding needs `durable` and no live item for the target in that session (`sync.py:136-140`). A failed seed leaves the row unconsumed (`sync.py:240-241`). `.context/features/` and other paths are digested (`sync.py:143`).
- Promote: `promote` syncs first, then gates each eligible item (`actions.py:123-142`). A content-scan hit quarantines it (`actions.py:148-152`).
- Demote: a promoted item loses its managed block through the gate. Other states become `demoted` (`actions.py:278-299`).
- Storage: one JSON per item plus `_state.json` under `.context/cache/evolution/probation/` (`store.py:19-20`, `store.py:51-90`).
- Lock: `store.locked` raises when another writer holds the observe lock (`store.py:93-98`).
- Sync: runs when evolution is enabled and the lock is free (`sync.py:68-77`). Probe rows wait unless `probes=True` (`sync.py:164-165`).
- Session block: lists probation items within 1600 characters and records exposure (`render.py:48-104`, `render.py:107-117`).
- Session block: one `Next:` line per session, by priority (`render.py:131-154`).
- Report: counts, rates and resident bytes. Rates are `None` when undefined (`render.py:157-223`).
- Hook: `_print_probation` prints the block on SessionStart (`dummyindex/context/cli/memory.py:59-70`, `memory.py:169`).
- CLI: `attribute` and `probation report|promote|demote` (`dummyindex/evolve/cli/evolve_probation.py:16-153`). Dispatch at `dummyindex/evolve/cli/evolve.py:68`.
- `probation` verbs run `sync(probes=True)` first (`dummyindex/evolve/cli/evolve_probation.py:136`). `attribute` syncs after recording (`:73`).
- `attribute --retracts` needs `--verdict attributed` and `--item` (`:60`).
- Kill switch: `DUMMYINDEX_EVOLUTION=0` prints a disabled line and exits 0 (`dummyindex/evolve/observe/keys.py:56-64`).
- Retention: 30 days, lowered by `cleanupPeriodDays` (`keys.py:14`, `keys.py:67-75`).

## Boundaries

- `evolution`: `actions.py` imports the gate, promotion and learning-record helpers (`actions.py:17-21`). Curated writes happen only through `run_gate` and `promote_files` (`actions.py:189-216`).
- `observe`: supplies corrections, attributions, exposures, the lock, the kill switch, retention and `scan_text` (`sync.py:16-25`, `rules.py:11`, `render.py:13-23`).
- `session-memory`: no import. The probation package does not import the memory domain. Only the hook in `cli/memory.py:59-70` calls `session_block`.

## Tests

- `tests/evolve/test_probation.py`: state, routing, probes, harm, eligibility, sync, render.
- `tests/evolve/test_probation_actions.py`: enter, promote, demote, gate failure.
- `tests/evolve/cli/test_evolve_probation_cli.py`: verbs, exit codes, disabled line.
