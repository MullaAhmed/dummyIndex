# Supporting

<!-- dummyindex:merged:begin -->
### Merged from `community-7`

**Files involved:**

- `dummyindex/cli/build_loop/__init__.py`
- `dummyindex/cli/build_loop/dispatch.py`
- `dummyindex/cli/equip/__init__.py`
- `dummyindex/cli/equip/common.py`
- `dummyindex/cli/equip/discover.py`
- `dummyindex/cli/equip/dispatch.py`
- `dummyindex/cli/equip/plugin_state.py`
- `dummyindex/cli/equip/verbs.py`
- `dummyindex/context/domains/equip/generate/adopt.py`
- `dummyindex/context/domains/equip/generate/catalog.py`
- `dummyindex/context/domains/equip/generate/proposal.py`
- `dummyindex/context/domains/equip/generate/render.py`
- `dummyindex/context/domains/equip/generate/specialists.py`
- `dummyindex/context/domains/equip/lifecycle/manifest.py`
- `dummyindex/context/domains/equip/plugins/install_plan.py`
- `tests/context/domains/equip/test_equip_catalog.py`
- `tests/context/domains/equip/test_equip_e2e.py`
- `tests/context/domains/equip/test_equip_install_plan.py`
- `tests/context/domains/equip/test_equip_specialist_invariants.py`
- `tests/context/domains/equip/test_equip_specialists.py`

**Original notes:**

# community-7 — spec

confidence: INFERRED

## Intent

Define the **generated specialist family** — the on-demand, capability-keyed agents (`db` / `security` / `performance` / `docs` / `search`) that sit beside the always-generated core four (implement / test / review / verify). Each capability maps to one shipped `*.md.tmpl` plus the `.context/` docs it grounds in, and now to a small set of **load-bearing convention substrings** (`invariants`) the template emits verbatim. This module is pure data + three functions (`specialists.py:1-23` documents the "pure data + one constructor; imports no sibling policy module" boundary); `adopt`/`catalog` consume it without importing back.

The recent change makes the Wave-2 **invariant canary real**: a generated specialist's `EquipmentItem` now carries `invariants` as **manifest metadata** so `classify_item` can tell a benign user edit (`CUSTOMIZED`) from one that drops a convention (`INVARIANT_BROKEN`). Without these substrings the canary is a no-op (`test_equip_specialist_invariants.py:1-16`).

## User-visible behavior

- A capability with a template here is **generated** as a project-scoped agent (`{proj}-{name_suffix}`, e.g. `backend-db-specialist`); one with no template falls through to manifest-only adoption — `FRONTEND` is deliberately omitted so the registry's *Frontend Developer* covers it (`specialists.py:79-88`).
- Every rendered specialist's manifest entry (`EquipmentItem`) carries 2–3 `invariants` — slot-free literals guaranteed present verbatim in its rendered body (`test_equip_specialist_invariants.py:57-78`). The core four carry **none**, so their entries stay byte-identical and the canary stays dormant for them (`specialists.py:198-212`, `plan.py:52-58`).
- `invariants` are metadata only: they are **never** written into the rendered bytes, so they do not perturb the `origin_hash` (sha256 of the body alone; `plan.py:83-92`, proven at `test_equip_specialist_invariants.py:95-103`).
- On `equip status`, a user-edited specialist that still contains every invariant reports `CUSTOMIZED`; one missing ≥1 invariant reports `INVARIANT_BROKEN`. Both are user-owned — never auto-rewritten, re-baselined, or deleted (`status.py:137-165`, `enums.py:88-92`).

## Contracts

- `SpecialistTemplate` — frozen dataclass; one capability's template + grounding + canary substrings. `specialists.py:52-76`
  - fields: `capability: str`, `template: str`, `name_suffix: str`, `grounding_docs: tuple[str, ...]`, `invariants: tuple[str, ...] = ()` (`specialists.py:72-76`).
  - `name_suffix` is appended to the project slug to form the agent name and keeps file / frontmatter `name:` / manifest `subagent_type` in agreement (`specialists.py:53-69`).
- `SPECIALIST_TEMPLATES: Mapping[str, SpecialistTemplate]` — the registry, a read-only `MappingProxyType` (reads/iteration/`in` work, assignment is refused — global immutability). Keys: `DATABASE`, `SECURITY`, `PERFORMANCE`, `DOCS`, `SEARCH`; each carries 2–3 `invariants`. `specialists.py:88-186`
- `templated_capabilities() -> frozenset[str]` — the capability set a template exists for; handed to `adopt.resolve_coverage` for the generate-vs-adopt decision. `specialists.py:189-195`
- `invariants_for(capabilities: tuple[str, ...]) -> tuple[str, ...]` — returns the `invariants` of the **first** templated capability in `capabilities`, else `()`. The renderer calls it with a spec's `capabilities`; the core four (no template) yield `()`. `specialists.py:198-212`
- `specialist_spec(capability: str, *, label: str, proj: str) -> GenerateSpec` — builds the project-scoped `GenerateSpec` (`{proj}-{suffix}`, `kind=AGENT`, `rel_path=.claude/agents/{name}.md`, `grounding_docs` from the template). Raises `KeyError` when no template backs `capability`. `specialists.py:215-232`
- `EquipmentItem.invariants: tuple[str, ...] = ()` — the manifest field the substrings land in; `to_dict` **omits** it when empty so a v3 manifest stays byte-identical (no `SCHEMA_VERSION` bump). `models.py:98-101`, `models.py:130-131`, `models.py:150`
- `render_generated_set(...)` — stamps `invariants=invariants_for(spec.capabilities)` onto each item, assembled like `grounded_in`, never injected into `content`; `origin_hash = content_hash(content)`. `plan.py:25-94` (stamp at `plan.py:88`).
- `classify_item(root, item) -> ItemState` — hash is the authority (`PRISTINE`/`MISSING`); on a hash mismatch the canary refines: no invariants ⇒ `USER_MODIFIED`, all present ⇒ `CUSTOMIZED`, ≥1 gone ⇒ `INVARIANT_BROKEN`. `status.py:137-165`
- `ItemState.CUSTOMIZED` / `ItemState.INVARIANT_BROKEN` — the two canary refinements of `USER_MODIFIED`, reachable only when an item carries `invariants`. `enums.py:88-92`

## Examples

Happy path — render a specialist and read its invariants off the resulting `EquipmentItem` (mirrors `test_equip_specialist_invariants.py:40-51, 59-78`):

```python
spec = specialist_spec("database", label="python", proj="backend")
# spec.name == "backend-db-specialist", spec.capabilities == ("database",)

(item, rel_path, content), = render_generated_set(
    profile=StackProfile(label="python", frameworks=("FastAPI",)),
    specs=(spec,),
    conventions=(".context/conventions/naming.md",),
    grounding=(".context/HOW_TO_USE.md", ".context/conventions/naming.md"),
    proj="backend",
)

assert item.invariants == (
    "## Ground yourself first (mandatory, before any edit)",
    "Additive/expand-then-contract by default",
    "Stay inside the planned scope.",
)                                      # the db template's slot-free literals
assert all(inv in content for inv in item.invariants)   # verbatim in the body
assert item.origin_hash == content_hash(content)        # invariants never hashed
```

The substrings live only in the manifest entry, not the rendered bytes — so writing `content` to disk and deleting `item.invariants[0]` flips `classify_item` from `PRISTINE` to `INVARIANT_BROKEN`, while appending a harmless note (every invariant intact) yields `CUSTOMIZED` (`test_equip_specialist_invariants.py:119-154`).

<!-- dummyindex:merged:end -->

<!-- dummyindex:merged:begin -->
### Merged from `community-14`

**Files involved:**

- `dummyindex/cli/equip/plugin_state.py`
- `dummyindex/context/claude_plugins.py`
- `dummyindex/context/claude_settings.py`
- `dummyindex/context/domains/equip/lifecycle/status.py`
- `dummyindex/context/domains/equip/wiring/hooks.py`
- `dummyindex/context/hooks.py`
- `tests/context/domains/equip/test_equip_canary.py`
- `tests/context/domains/equip/test_equip_lifecycle.py`
- `tests/context/test_claude_plugins.py`
- `tests/context/test_claude_settings.py`

**Original notes:**

# community-14 — spec

`confidence: INFERRED`

## Intent

A user equips a repo with a generated toolkit (implementer / tester / reviewer agents, capability specialists, a format hook), then edits some of those files by hand. The lifecycle's job is to keep equip's own files current without ever destroying that hand-work, and — new in this build — to tell the user *which kind* of edit they made. A byte-for-byte content hash recorded at generation time is the sole authority for "is this still ours": matches means equip may re-render it, differs means the user owns it now. The recent change adds a canary on top of that authority: when an owned file also carries declared load-bearing convention substrings (its "invariants"), the lifecycle reports whether the user's edit kept the contract (a benign customization) or quietly dropped it (an alarm), so a silently weakened specialist surfaces instead of hiding inside the generic "modified" bucket. The promise the caller relies on is the never-clobber contract: an owned file — in any of its three flavors — is never re-rendered, never re-baselined, and never deleted by `refresh`, `uninstall`, or a re-`apply`.

## User-visible behavior

Four `equip` surfaces expose the verdicts, all routed in `dummyindex/cli/equip/dispatch.py:96-134`:

- **`equip status`** (`cli/equip/verbs.py:70-103`) — classifies every tracked item and prints one line per item, `<state> <name> (v<version>)`. The state value is the `ItemState` enum value (`pristine` / `user-modified` / `missing` / `adopted` / `customized` / `invariant-broken`). `--json` emits `{items:[{name,state,version}], missing_playbook:[...]}`. Marketplace plugins with no usage playbook get an extra `incomplete … (no usage playbook)` line.
- **`equip refresh`** (`cli/equip/verbs.py:109-124`) — re-renders only PRISTINE-and-stale generated items, re-baselines + minor-bumps them; reports counts of refreshed / unchanged / skipped(user-modified) / skipped(evolved) / skipped(missing). User-owned files (USER_MODIFIED, CUSTOMIZED, INVARIANT_BROKEN) are all reported under skipped(user-modified) and never touched. Items classified INVARIANT_BROKEN additionally surface as a distinct `⚠ … dropped a load-bearing invariant (review — INVARIANT_BROKEN)` alarm section, rendered by `_print_refresh_report` (`cli/equip/verbs.py:35-64`). A cosmetic CUSTOMIZED edit is *not* in the alarm. With no invariants in play, the alarm section never prints (back-compat).
- **`equip uninstall`** (`cli/equip/verbs.py:211-232`) — deletes PRISTINE generated/vendored files, the settings hook entries (by sentinel), and the manifest; reports kept user-modified files and removed hook events. User-owned files (all three states) are kept and listed as `kept … (user-modified)`.
- **`equip apply`** (re-apply, `cli/equip/dispatch.py:381-547`) — on a known generated target whose state is user-owned, the apply write path keeps the file byte-untouched, carries the prior record forward verbatim (no re-baseline), and prints `keep <name> -> <path> (<state>, preserved)`. This is what prevents a second `apply` from laundering an INVARIANT_BROKEN file back to PRISTINE.

The three verdicts a user newly sees on an owned file: `customized` (edited, every declared invariant intact), `invariant-broken` (edited, ≥1 declared invariant gone), and the unchanged `user-modified` (edited, no invariants declared for this item — the byte-identical pre-canary outcome). Only the five generated specialists (database / security / performance / docs / search) declare invariants today, so the two new states are reachable only for those; the core four agents, skills, and hooks carry no invariants and classify exactly as before.

## Contracts

Public functions and dataclasses (all in `dummyindex/context/domains/equip/lifecycle/status.py` unless noted; re-exported from `dummyindex/context/domains/equip/__init__.py`):

- `classify_item(root: Path, item: EquipmentItem) -> ItemState` — `status.py:137-165`. Hash is authority: file absent ⇒ `MISSING`; `content_hash(text) == item.origin_hash` ⇒ `PRISTINE`. On a hash mismatch the canary refines: `not item.invariants` ⇒ `USER_MODIFIED`; `all(inv in text for inv in item.invariants)` ⇒ `CUSTOMIZED`; otherwise ⇒ `INVARIANT_BROKEN`. Invariants are consulted *only* on mismatch, so a PRISTINE item that happens to carry invariants stays PRISTINE.
- `is_user_owned(state: ItemState) -> bool` — `status.py:168-181`. Returns `True` for exactly `{USER_MODIFIED, CUSTOMIZED, INVARIANT_BROKEN}`; `False` for `PRISTINE`/`MISSING`/`ADOPTED`. This predicate is the never-clobber key — `refresh`, `uninstall`, and the apply write path branch on it, never on the individual enum members, so all three owned states are handled identically.
- `status(root: Path, manifest: EquipmentManifest) -> StatusReport` — `status.py:184-205`. Classifies generated + vendored items by origin-hash, marketplace items by their `enabledPlugins` key, adopted (INSTALLED) items by presence; also collects marketplace items missing a `grounded_in` playbook.
- `refresh(root: Path, *, fresh_renders: dict[str, str], dry_run: bool = False) -> RefreshReport` — `status.py:215-301`. Reads the manifest from `root/.context`. For each lifecycle-managed item: user-owned ⇒ skip forever (append to `skipped_user_modified`; if INVARIANT_BROKEN also append to `alarm_invariant_broken`) and carry the record forward unchanged; MISSING ⇒ report, don't recreate; PRISTINE-but-evolved ⇒ keep; otherwise re-render only if the version-normalized fresh render's hash differs from `origin_hash`, then minor-bump + re-baseline. `dry_run` reports the same decisions, writing nothing.
- `uninstall(root: Path, manifest: EquipmentManifest, *, dry_run: bool = False) -> UninstallReport` — `status.py:333-399`. Removes PRISTINE generated/vendored files; keeps + reports user-owned ones (all three states via `is_user_owned`, `status.py:353`); disables marketplace plugins and drops their marketplaces; removes hook entries by `EQUIP_SENTINEL`; deletes the manifest. `dry_run` decides everything but writes nothing.
- `reset(root, manifest, name, *, fresh_render) -> EquipmentItem` — `status.py:304-330`. The explicit escape hatch: overwrites even a user-owned file, re-baselines + minor-bumps, persists the manifest. Raises `ResetError` for a non-resettable name.
- `is_lifecycle_managed(item) -> bool` (`status.py:76-88`) / `is_vendored_file(item) -> bool` (`status.py:91-103`) / `is_evolved(item) -> bool` (`status.py:120-135`) — membership predicates gating which items the disk-touching verbs act on.

`ItemState` members — `enums.py:76-92`: `PRISTINE="pristine"`, `USER_MODIFIED="user-modified"`, `MISSING="missing"`, `ADOPTED="adopted"`, `CUSTOMIZED="customized"`, `INVARIANT_BROKEN="invariant-broken"`. `(str, Enum)` so values round-trip through `--json`.

`RefreshReport` — `status.py:56-66`, frozen dataclass: `refreshed`, `skipped_user_modified`, `skipped_missing`, `skipped_evolved`, `unchanged`, `alarm_invariant_broken` — all `tuple[str, ...]`, default `()`. `alarm_invariant_broken` is empty whenever no item carries invariants.

`StatusReport` — `status.py:50-53`: `items: tuple[tuple[str, ItemState, str | None], ...]`, `missing_playbook: tuple[str, ...]`. `UninstallReport` — `status.py:69-73`: `removed`, `skipped_user_modified`, `removed_hook_events`.

`EquipmentItem.invariants: tuple[str, ...] = ()` — `models.py:101`. Stamped by `invariants_for(spec.capabilities)` at render time (`generate/plan.py:88`), drawn from the per-specialist literals in `generate/specialists.py:104-184`. It is item metadata only, never part of the rendered `content`, so `origin_hash` (sha256 of the bytes alone) is identical with or without it; `to_dict` omits it when empty (`models.py:130-132`), keeping v3 manifests byte-identical.

## Examples

**Happy path — a user customizes a generated specialist, then refreshes (never-clobber + canary):**

1. `equip apply` renders the security specialist to `.claude/agents/<proj>-security-specialist.md`. `plan.render_generated_set` stamps `version="1.0.0"`, `origin_hash=content_hash(rendered_bytes)`, and `invariants=("## Ground yourself first (mandatory, before judging or editing)", "**Tenant isolation.**", 'Never assert "secure" without the evidence to back it.')` (`specialists.py:124-128`).
2. The user edits the file — appends a project-specific note but keeps all three invariant lines. The on-disk hash now differs from `origin_hash`.
3. `equip status` → `classify_item` (`status.py:137-165`): not MISSING, hash ≠ `origin_hash`, `item.invariants` non-empty, every invariant still `in text` ⇒ `ItemState.CUSTOMIZED`. The user sees `customized <name> (v1.0.0)`.
4. `equip refresh` offers a genuinely newer template render. `is_user_owned(CUSTOMIZED)` is `True` (`status.py:168-181`), so `refresh` appends the name to `skipped_user_modified`, does **not** add it to `alarm_invariant_broken` (it is benign), carries the record forward unchanged, and writes nothing for it — the file survives byte-for-byte and `origin_hash` is unchanged (`test_equip_canary.py:192-211`, `:224-231`).

**Alarm path — a user deletes a load-bearing invariant:**

1. Same generated specialist, but the user's edit removes the `**Tenant isolation.**` line.
2. `equip status` → hash ≠ `origin_hash`, `item.invariants` non-empty, `all(inv in text ...)` is `False` (one is gone) ⇒ `ItemState.INVARIANT_BROKEN`; the user sees `invariant-broken <name>`.
3. `equip refresh` → `is_user_owned(INVARIANT_BROKEN)` is `True` so the file is still never touched, **and** the name lands in `alarm_invariant_broken`; `_print_refresh_report` renders the `⚠ … (review — INVARIANT_BROKEN)` section (`verbs.py:58-64`, `test_equip_canary.py:215-220`, `:249-264`).
4. A second `equip apply` does not launder the verdict: the apply write path sees `is_user_owned(state)` is `True`, keeps the file byte-untouched, and carries the prior record forward without re-baselining, so the next `classify_item` still returns `INVARIANT_BROKEN` (`dispatch.py:412-426`, `test_equip_canary.py:362-385`).

**Back-compat path — an item with no invariants:** a hand-edited core agent (no templated capability, `invariants=()`) classifies as `USER_MODIFIED` exactly as before, and the refresh alarm tuple stays empty (`test_equip_canary.py:129-141`, `:235-242`).

<!-- dummyindex:merged:end -->

<!-- dummyindex:merged:begin -->
### Merged from `community-17`

**Files involved:**

- `dummyindex/context/domains/equip/errors.py`
- `dummyindex/context/domains/equip/generate/detect.py`
- `dummyindex/context/domains/equip/generate/render.py`
- `dummyindex/context/domains/equip/wiring/safety.py`
- `dummyindex/context/domains/memory/detect.py`
- `dummyindex/context/domains/proposals/errors.py`
- `tests/context/domains/equip/test_equip.py`

**Original notes:**

# Feature: community-17

_Deterministic stub (`confidence: ConfidenceLevel.EXTRACTED`). The `/dummyindex` skill will rewrite this `spec.md` — the feature's entry point — with a real summary based on the source code._

## At a glance

- **Members:** 88 symbol(s)
- **Files:** 7
- **Entry points:** 2
- **Flows:** 2

## Files involved

- `dummyindex/context/domains/equip/errors.py`
- `dummyindex/context/domains/equip/generate/detect.py`
- `dummyindex/context/domains/equip/generate/render.py`
- `dummyindex/context/domains/equip/wiring/safety.py`
- `dummyindex/context/domains/memory/detect.py`
- `dummyindex/context/domains/proposals/errors.py`
- `tests/context/domains/equip/test_equip.py`

## Flows

- [`flow-185`](./flows/flow-185.md) — entry: `_frontmatter_name()` (4 steps, 1 files)
- [`flow-186`](./flows/flow-186.md) — entry: `_write_files_map()` (38 steps, 1 files)

## Entry points

- `test_equip_frontmatter_name`
- `test_equip_write_files_map`

<!-- dummyindex:merged:end -->

<!-- dummyindex:merged:begin -->
### Merged from `community-29`

**Files involved:**

- `dummyindex/context/domains/equip/errors.py`
- `dummyindex/context/domains/equip/plugins/sources.py`
- `tests/context/domains/equip/test_equip_sources.py`

**Original notes:**

# Feature: community-29

_Deterministic stub (`confidence: ConfidenceLevel.EXTRACTED`). The `/dummyindex` skill will rewrite this `spec.md` — the feature's entry point — with a real summary based on the source code._

## At a glance

- **Members:** 30 symbol(s)
- **Files:** 3
- **Entry points:** 1
- **Flows:** 1

## Files involved

- `dummyindex/context/domains/equip/errors.py`
- `dummyindex/context/domains/equip/plugins/sources.py`
- `tests/context/domains/equip/test_equip_sources.py`

## Flows

- [`flow-264`](./flows/flow-264.md) — entry: `_fake_runner()` (8 steps, 1 files)

## Entry points

- `test_equip_sources_fake_runner`

<!-- dummyindex:merged:end -->
