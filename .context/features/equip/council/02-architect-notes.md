# Architect notes — Project equipment toolkit

## What I changed

- Sections — remapped the draft's headings (Bounded context / Preparation pipeline / Lifecycle / Dependencies / Verification seam) onto the dev template set (Where it lives / Architecture in three sentences / Data model / Key decisions / Open questions) — as briefed, matching `dummyindex/skills/agents/dev.md:91-118`.
- Paths — one legend line (`dummyindex/` dropped, `equip/` = `context/domains/equip/`) — removes repeated prefixes; all 60 `path:range` citations re-checked against current source line counts and content.
- Bounded context — plugin discover/install/verify and installer skill linking collapsed into one "Not this boundary" bullet; dropped the optimizer/model-engine disclaimer (not load-bearing).
- Lifecycle prose → six "Decided X because Y" bullets in Key decisions.
- Verification seam dropped — test files are enumerated in `feature.json`; `spec.md:116-118` already says deterministic tests do not establish model obedience.
- `is_link`/junction gap moved from Lifecycle into Open questions — it is an unresolved guard weakness, not a decision.
- Ranges — `lifecycle/status.py:217-357` widened to `77-433` (includes `is_lifecycle_managed` and `uninstall`); no-rollback evidence narrowed from `dispatch.py:617-687` to `dispatch.py:613` + `467-478,551-553,662-667`.
- Conflicts flagged (code wins; source not edited): `dummyindex/cli/equip/dispatch.py:21-25` docstring says "Wire-only … this module never decides what to build", but write/preserve/migrate/merge policy is at `dispatch.py:436-711`; `.context/conventions/folder-organization.md:30-36` and `.context/conventions/coding-practices.md:92-93` (CLI dispatchers stay <~300 lines) vs an 815-line `dispatch.py` → Open question "Layering".
- Stale comments (code wins): `dummyindex/context/domains/equip/models.py:95` "path under .claude/" vs canonical `.context/equipment` (`generate/catalog.py:40`); `lifecycle/manifest.py:3-4` "what equip put into .claude/"; `lifecycle/manifest.py:18-20` describes the retired eval trio.
- New open question — `_matches_content` compares raw bytes (`dispatch.py:723-727`), while ownership compares decoded universal-newline text (`lifecycle/status.py:156-161`, `generate/adapters.py:75`).
- Doc evidence — no catalogued prose doc quoted. `dummyindex/skills/equip/SKILL.md` (low, 8 broken refs) and `docs/reference/01-conventions.md` (low, 38) used only as history, via the curated `.context/conventions/` cross-checks.
- Map gaps — `_run_apply` (`dispatch.py:257`) and the nested restore in `_apply_write` are absent from `map/symbols.json`; constants `PACKAGE_FIELDS` (`identity.py:10`), `SCHEMA_VERSION` (`constants.py:14`), `_CAPABILITIES_DIR` (`catalog.py:40`) are absent because the map indexes only functions and classes. All are source-verified; the plan does not name the nested restore.
- Reasoning — single-shot (no Sequential Thinking MCP); advisor rate-limited.
- Size — 104 → 102 lines, 573 → 543 words, 6031 → 6014 bytes.

## Patterns named

- Functional core / imperative shell at `dummyindex/context/domains/equip/generate/catalog.py:74-110` ("Pure; no I/O", :83) with shell `dummyindex/cli/equip/dispatch.py:436-711` — `render_generated_set` (`generate/plan.py:29-146`) reads templates (`generate/render.py:167-174`) but writes nothing, so it is labelled "write-free", not pure.
- Hash-baselined ownership at `dummyindex/context/domains/equip/lifecycle/status.py:138-183` — `classify_item` + `is_user_owned` gate every disk mutation.
- Merge-forward registry write at `dummyindex/cli/equip/dispatch.py:638-660` (contract in docstring `:451-455`) — this run's records win name collisions; the rest carry forward.
- Adapter (discovery pointer) at `dummyindex/context/domains/equip/generate/adapters.py:33-42` — the native file delegates to the canonical body; guarded write at `:54-89`.
- Single render path at `dummyindex/context/domains/equip/generate/plan.py:3-5` — reused by refresh/reset through `fresh_rendered` (`dummyindex/cli/equip/common.py:199-245`).
- Bounded compensation at `dummyindex/cli/equip/dispatch.py:467-478` (called `:551-553`, `:662-667`) — reverts only converted legacy pointers; deliberately not called a saga or a transaction.
- Not named: repository/port. No Protocol or port abstraction exists (`.context/conventions/coding-practices.md:64-67`), and the Runner seam in `equip/plugins/sources.py` sits outside this boundary.

## Dependencies surfaced

- Upstream: `.context/` spine, preflight, proposal capabilities (`dummyindex/cli/equip/dispatch.py:289-322`); `write_text_atomic` (`dummyindex/context/domains/atomic_io.py:71-81`); `wire_hooks` (`dispatch.py:613-636`); `normalize_platform_arg` from `dummyindex/installer/common.py:161` (`dispatch.py:69`).
- Downstream, new versus the draft: `task_binding` → `capability_identity` (`dummyindex/context/domains/buildloop/envelopes.py:76-107`); evolve promotion `_managed_overlay` (`dummyindex/context/domains/evolve_gate.py:254-325`) is a second re-baselining writer and imports equip's private `_bump` (`:260`); `_refresh_equipment_step` → `cli.equip.common.fresh_rendered` + `refresh` (`dummyindex/installer/install/project_init.py:183-214`).
- Downstream, kept: build routing `role_path` (`dummyindex/cli/build_loop/waves.py:232,320-336`). Read-only manifest readers (`dummyindex/cli/status.py:236`, `dummyindex/context/domains/audit/catalog.py:122`, `dummyindex/context/domains/config.py:670-672`) are left out of the plan because they carry no write contract.
- Cycle: `cli ↔ installer` at package level only (`dispatch.py:69`; `project_init.py:196` lazy, plus `project_init.py:56` → `cli.migrate`). It is acyclic per module because `installer/common.py:11` imports only `..versioning`.
- Cycle: `generate ↔ lifecycle` at package level only. `generate` → `lifecycle/hashing.py` (`generate/plan.py:21`, `generate/adapters.py:11`); `lifecycle` → `generate/render.py` (`lifecycle/status.py:42`, `lifecycle/evolve.py:19`) and `generate/adapters.py` (lazy, `lifecycle/status.py:385,392`). `hashing.py` imports only `hashlib`, so there is no module cycle.

## Decisions promoted

- decided a recorded hash owns only its recorded path, because a sentinel or old baseline must not claim a foreign destination (was implicit at `dummyindex/cli/equip/dispatch.py:526-540`).
- decided invariants are manifest metadata only, because in-body they would shift `origin_hash` (was implicit at `dummyindex/context/domains/equip/generate/plan.py:56-62`).
- decided evolution = exact-once patch + patch-level bump, because a patched body must stay PRISTINE yet never be re-rendered (was implicit at `lifecycle/status.py:121-135`, `dispatch.py:505-515`). Evolve promotion follows the same rule (`evolve_gate.py:306-322`).
- decided native files are pointers, because workflow and policy text live only in the canonical body (was implicit at `generate/adapters.py:33-42`).
- decided the manifest write merges and never rebuilds, because no prior record may silently drop (was implicit at `dispatch.py:451-455`).
- decided the order files → hooks → manifest → pointers, because "malformed settings never blocks" file writes (was implicit at `dispatch.py:613`); recovery is limited to converted legacy pointers.
- decided byte-faithful atomic writes, because the hash baselines fingerprint the in-memory string (was implicit at `dummyindex/context/domains/atomic_io.py:71-81`).
