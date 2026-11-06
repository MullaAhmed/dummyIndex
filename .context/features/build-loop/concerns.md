# Build-loop checklist & waves — concerns

`confidence: INFERRED`

## Data integrity

- `dummyindex/context/domains/buildloop/checklist.py:72-80` — fallback task IDs hash task wording, so editing the text changes the reference; positional selectors also change meaning after reordering. Use explicit task markers for durable references and resolve the current checklist before completing a dispatched task.
- `dummyindex/context/domains/buildloop/receipts.py:38-49` — `checks.json` is written before the checkbox rewrite. A later rewrite failure can leave a valid stored receipt beside an unfinished task; receipt presence alone is not completion, and recovery must inspect both artifacts.

## Security

- `dummyindex/context/domains/buildloop/receipts.py:54-96` — A forged, stale or out-of-project completion receipt must not authorize checking another task. Enforced mitigations bind task ID/text, current source commit and artifact bytes, reject conflicting identity aliases, resolve evidence paths inside the repository and reject disposable evidence locations. These are content checks, not authentication of the executor or proof that its reported tests ran.
- `dummyindex/context/domains/buildloop/envelopes.py:49-105` — Proposal policies and legacy role paths are owner-trusted guidance inputs. Policy paths may be absolute and their bytes are read before the 8,192-byte envelope limit; a substituted proposal can select an unintended local file or cause an oversized read. The sixteen-policy/envelope limits bound references and output, not file sizes or trust. Mitigation: review owner-selected proposal/manifest guidance; hashes record loaded identity but do not approve instructions.

## Product surface

- **Editing a task without an explicit marker** — the fallback ID hashes its
  text, so rewording changes identity even though reordering/checking/skipping
  does not — use the existing `<!-- task:ID -->` contract when wording must
  evolve; a stale receipt is refused rather than silently applied
  (`dummyindex/context/domains/buildloop/checklist.py:72-81`,
  `dummyindex/context/domains/buildloop/receipts.py:63-69`).
- **Retrying an ambiguous substring** — the error now shows five matching
  `index: text` candidates and an omitted count — candidate discovery is
  delivered; a bare numeric retry can still hit the numeric-label ambiguity
  guard, while the existing `index:N` selector is unambiguous
  (`dummyindex/context/domains/buildloop/checklist.py:166-202`).
- **Dispatching a large wave** — output contains at most eight items and is
  reduced further to fit 65,536 bytes, with `group_total`/`truncated` — callers
  must finish the returned batch and request the frontier again; receiving a
  wave is not evidence that every group item was launched
  (`dummyindex/cli/build_loop/waves.py:484-549`).
- **Reading a checked box or capability hash as verified execution** — plain
  checks remain available, and receipt validation proves matching task/artifact
  bytes rather than real tool execution — the host still judges outcomes and
  follows preservation/budget guidance; no model-quality guarantee is delivered
  (`dummyindex/context/domains/buildloop/checklist.py:245-266`,
  `dummyindex/context/domains/buildloop/receipts.py:54-96`).
