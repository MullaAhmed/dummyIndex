## Data integrity

- `dummyindex/context/domains/equip/lifecycle/evolve.py:61-70` — a learning patch writes the body before persisting its new manifest hash/version. Manifest-write failure can leave the patched body against the previous baseline; inspect both files before retrying, because exact-once patch text may no longer match. Apply likewise has only bounded multi-file recovery (`dummyindex/cli/equip/dispatch.py:617-687`).
- `dummyindex/context/domains/equip/generate/adapters.py:73-84` — native-pointer ownership compares decoded text with universal-newline normalization, including the prior-content hash; LF/CRLF conversion alone does not make a pointer foreign. This ownership comparison is distinct from the actual-byte SHA256 returned by capability attribution (`dummyindex/context/domains/equip/identity.py:36-49`); compare like-for-like identities when interpreting checkout changes.

## Security

- `dummyindex/cli/equip/dispatch.py:480-539`, `dummyindex/context/domains/equip/generate/adapters.py:54-88` — Regeneration/migration must not turn a sentinel or an old path baseline into ownership of a foreign destination. The merge independently checks canonical destination content, preserves changed prior bodies, rejects linked apply/adapter targets and leaves edited native pointers untouched. Pointer equality compares decoded text with newline normalization; it is not literal raw-byte identity.
- `dummyindex/context/domains/equip/models.py:155-169`, `dummyindex/context/domains/equip/lifecycle/status.py:77-91`, `dummyindex/context/domains/equip/lifecycle/status.py:327-346` — The broader lifecycle still trusts paths from the local equipment registry: a forged generated record can carry an absolute or parent-traversing path into explicit reset. The generated/hash-present test does not confine that path. Owner-controlled manifest review remains the mitigation; canonical apply/adaptor guards must not be described as a sandbox for every lifecycle operation.

## Product surface

- **Deleting a generated specialist to decline it** — refresh reports missing
  bodies without recreating them, but a later apply generates every
  template-backed specialist again — deletion is not a durable opt-out
  (`dummyindex/context/domains/equip/generate/catalog.py:85-110`,
  `dummyindex/context/domains/equip/lifecycle/status.py:226-266`).
- **Reapplying after a project/stack rename** — apply carries old manifest
  names forward and refresh reports a pristine item with no current render as
  unchanged — preservation can leave old capability identities/files alongside
  the new ones; it is not automatic lifecycle cleanup
  (`dummyindex/cli/equip/dispatch.py:641-663`,
  `dummyindex/context/domains/equip/lifecycle/status.py:275-279`).
- **A later preparation write fails** — required-write paths restore specified
  legacy migrations, but canonical files/settings may already exist — error
  status does not mean no project changes. Inspect the reported registry and
  warnings before retrying; whole-operation rollback is not delivered
  (`dummyindex/cli/equip/dispatch.py:467-478`,
  `dummyindex/cli/equip/dispatch.py:551-553`,
  `dummyindex/cli/equip/dispatch.py:617-673`).
- **Reading equipment status/identity as runtime proof** — records and actual
  body hashes establish what was prepared/loaded; adapters only point to the
  shared body — they do not prove native plugin loading, delegate compliance
  or model-quality gains. Plugin installation/verification remains a separate
  surface (`dummyindex/context/domains/equip/identity.py:26-56`,
  `dummyindex/context/domains/equip/generate/adapters.py:33-42`,
  `dummyindex/context/domains/equip/lifecycle/status.py:186-207`).
- **An unchanged pointer is checked out with CRLF** — adapter ownership compares
  decoded universal-newline-normalized text, so it remains recognized — pointer
  compatibility does not imply that the actual-loaded-byte SHA256 is unchanged;
  the attribution path hashes raw bytes and separately accepts normalized
  lifecycle baselines (`dummyindex/context/domains/equip/generate/adapters.py:73-89`,
  `dummyindex/context/domains/equip/identity.py:36-44`).
