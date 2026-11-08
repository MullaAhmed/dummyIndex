## Data integrity

- `dummyindex/context/domains/equip/lifecycle/evolve.py:61-70` — a learning patch writes the body before persisting its manifest hash/version. Manifest-write failure leaves the patched body against the old baseline; inspect both files before retrying, because exact-once patch text may no longer match.
- `dummyindex/context/domains/equip/lifecycle/library.py:191-216` — `reuse_capability` writes the body before rewriting the manifest `origin_hash`. A manifest-write failure leaves a changed body against the old hash, so `status` treats it as user-owned.
- `dummyindex/cli/equip/library_verbs.py:46-54` — `store_items` skips agents whose body file is missing, silently. An error mid-store returns 1 and keeps earlier entries.
- `dummyindex/context/domains/equip/generate/adapters.py:73-84` — pointer ownership uses decoded, newline-normalized text. Capability attribution hashes raw bytes (`dummyindex/context/domains/equip/identity.py:36-49`); compare like-for-like identities across checkouts.

## Security

- `dummyindex/cli/equip/dispatch.py:480-539`, `dummyindex/context/domains/equip/generate/adapters.py:54-88` — Regeneration and migration must not turn a sentinel or old path baseline into ownership of a foreign destination. The merge checks canonical destination content independently, rejects linked targets and leaves edited pointers untouched.
- `dummyindex/context/domains/equip/lifecycle/library.py:219-233` — `reverify` hashes every `grounding` path in `library.json` without containment, so a forged index can test any readable file against a hash. Owner-controlled index review is the mitigation.
- `dummyindex/context/domains/equip/models.py:155-169`, `dummyindex/context/domains/equip/lifecycle/status.py:77-91`, `dummyindex/context/domains/equip/lifecycle/status.py:327-346` — Lifecycle still trusts registry paths: a forged generated record can carry an absolute or parent-traversing path into explicit reset. Apply and adapter guards are not a sandbox for every lifecycle operation.

## Product surface

- **Deleting a generated specialist to decline it** — refresh reports missing bodies without recreating them, but apply regenerates every undimensioned specialist and each signalled dimensioned one. Deletion is not a durable opt-out (`dummyindex/context/domains/equip/generate/catalog.py:81-144`, `dummyindex/context/domains/equip/lifecycle/status.py:226-266`).
- **Reapplying after a project/stack rename** — apply carries old manifest names forward; refresh reports a pristine item with no current render as unchanged. Old identities and files can remain beside new ones (`dummyindex/cli/equip/dispatch.py:641-663`, `dummyindex/context/domains/equip/lifecycle/status.py:275-279`).
- **A later preparation write fails** — legacy migrations restore on specified failures, but canonical files, settings and the registry may already exist. Inspect the registry and warnings before retrying; no whole-operation rollback (`dummyindex/cli/equip/dispatch.py:467-478`, `dummyindex/cli/equip/dispatch.py:617-673`).
- **Reading status, identity or reuse as runtime proof** — records, body hashes and `reverify` `ok` show what was prepared, loaded or stored. They do not prove native plugin loading, delegate compliance or model-quality gains (`dummyindex/context/domains/equip/identity.py:26-56`, `dummyindex/context/domains/equip/generate/adapters.py:33-42`).
- **Lesson validation is shape-only** — `validate_lesson` checks fields, not truth; a stored lesson does not show it helped (`dummyindex/context/domains/equip/lifecycle/library.py:37-46`).
