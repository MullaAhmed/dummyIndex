## Data integrity

- `dummyindex/context/domains/equip/lifecycle/evolve.py:61-70`, `dummyindex/context/domains/equip/lifecycle/library.py:191-216`, `dummyindex/cli/equip/dispatch.py:607`, `dummyindex/cli/equip/dispatch.py:719` — body written before manifest persist. Manifest-write failure leaves body against old baseline; `status` reads it as user-owned. Inspect both files before retry; exact-once patch text may be stale.
- `dummyindex/cli/equip/library_verbs.py:46-54` — `store_items` skips agents whose body file is missing, silently. Mid-store error returns 1, keeps earlier entries.
- `dummyindex/context/domains/equip/generate/adapters.py:73-84` — pointer ownership uses decoded, newline-normalized text. Capability attribution hashes raw bytes (`dummyindex/context/domains/equip/identity.py:36-49`); compare like-for-like identities across checkouts.

## Sourcing

- Upstream text enters agent prompt verbatim; overlay only frames it. `warn:url` makes auto-adoption rare (`dummyindex/cli/equip/source.py:331-333`, `dummyindex/context/domains/equip/plugins/sourcing.py:156`).
- skills.sh output format is assumed; parsing is lenient (`dummyindex/context/domains/equip/plugins/sources.py:337-361`).
- `--dry-run --source` still calls GitHub and skills.sh. Read-only means no writes, not offline (`dummyindex/cli/equip/source.py:274-357`).
- Sourced items carry only two overlay invariants; template invariants dropped, so alarm covers less (`dummyindex/context/domains/equip/generate/sourced.py:18-21`, `:101`).
- Upstream change report-only; pin holds until `equip reset` (`dummyindex/cli/equip/source.py:253-271`).

## Security

- `dummyindex/cli/equip/dispatch.py:615-638`, `dummyindex/cli/equip/dispatch.py:727-738`, `dummyindex/context/domains/equip/generate/adapters.py:54-88` — regeneration and migration must not turn sentinel or old path baseline into foreign-destination ownership. Merge checks canonical destination independently, rejects linked targets, keeps edited pointers.
- `dummyindex/context/domains/equip/lifecycle/library.py:219-233` — `reverify` hashes every `grounding` path in `library.json` without containment, so forged index can test any readable file against hash. Mitigation: owner reviews index.
- `dummyindex/context/domains/equip/models.py:155-169`, `dummyindex/context/domains/equip/lifecycle/status.py:77-91`, `dummyindex/context/domains/equip/lifecycle/status.py:333-362` — lifecycle trusts registry paths: forged generated record can carry absolute or parent-traversing path into explicit reset. Apply and adapter guards are no lifecycle sandbox.

## Product surface

- **Deleting a generated specialist to decline it** — refresh reports missing bodies without recreating them. Apply regenerates every undimensioned and signalled dimensioned specialist. Deletion is no durable opt-out (`dummyindex/context/domains/equip/generate/catalog.py:81-144`, `dummyindex/context/domains/equip/lifecycle/status.py:226-266`).
- **Reapplying after a project/stack rename** — apply carries old manifest names forward. Refresh reports pristine items with no current render as unchanged (`dummyindex/cli/equip/dispatch.py:706-714`, `dummyindex/context/domains/equip/lifecycle/status.py:275-279`).
- **A later preparation write fails** — legacy migrations restore only on later required-write failures. Canonical files, settings and registry may already exist. Inspect registry and warnings before retry; no whole-operation rollback (`dummyindex/cli/equip/dispatch.py:519-530`, `dispatch.py:607-608`, `dispatch.py:719-721`).
- **Status is not runtime proof** — records, body hashes and `reverify` `ok` show what was prepared, loaded or stored. They prove neither native plugin loading, delegate compliance nor model-quality gains (`dummyindex/context/domains/equip/identity.py:31-56`, `dummyindex/context/domains/equip/generate/adapters.py:33-42`).
- **Lesson validation is shape-only** — `validate_lesson` checks fields, not truth; stored lesson shows no help (`dummyindex/context/domains/equip/lifecycle/library.py:37-46`).
