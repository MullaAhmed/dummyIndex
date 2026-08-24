# Build-loop checklist & waves — plan

confidence: INFERRED

## Bounded context

This feature owns exactly one thing: turning a proposal's `checklist.md` into a deterministic, wave-grouped dispatch frontier. The domain (`dummyindex/context/domains/buildloop/`) is **pure state over one file it owns** — no I/O beyond reading/rewriting that checklist. The CLI (`dummyindex/cli/build_loop/`) is **wire-only**: parse args, call the domain, print. The actual agent dispatch and verify-before-tick discipline are deliberately *outside* this code — they live in the `dummyindex-build` skill (markdown) (`__init__.py:18-22`). That split is the load-bearing boundary: this feature decides *what* the next independent unit of work is and *who* should do it; the skill decides *whether and how* to dispatch.

- **Domain modules:** `checklist.py` (parse / flip / skip / wave / counts), `models.py` (`ChecklistItem`, `Choice`, `DispatchMode`, `dispatch_mode`, `AGENT_VIA_PREFIX`), `routing.py` (model-routing resolution: `parse_route_flags`, `read_proposal_routing`, `resolve_routing`, `ROUTING_KEYS`), `mapping.py` (`map_task_to_equipment`), `errors.py` (`BuildLoopError`), `__init__.py` (public surface, `:34-51`).
- **CLI modules:** `dispatch.py` (`run` + `--check` / `--skip` / `--status`, plus the repeatable `--route K=V` collector), `waves.py` (`--next` / `--next-wave`, the auto-recouncil resolver).
- **Tests:** `tests/context/domains/test_build_loop.py` (parse/flip/skip/counts/wave + CLI), `test_build_loop_routing.py` (mapping + gate/via dispatch classification + routing).

## Dependencies (upstream / downstream / cycles)

- **Upstream — consumes proposals:** the checklist path is `.context/proposals/<slug>/checklist.md` (`dispatch.py:131-137`), an artifact produced by the plan step (`dummyindex-plan`). This feature trusts the plan step's contract that a `## Wave N` group contains only disjoint-file tasks — see Decision *"Independence is delegated, not enforced."* It shares `BuildLoopError` semantics with the proposals domain's `ProposalError` (`proposals/errors.py:5`) but does not import it; the error hierarchies are siblings.
- **Upstream — consumes equipment.json:** `_load_manifest` reads `.context/equipment.json` → its `items` list (`waves.py:136-156`), produced by `dummyindex-equip`. Absent / empty / unparseable all collapse to `[]` — see the *"Warn, don't halt"* decision.
- **Upstream — consumes proposal routing + config policy:** the optional `"routing"` block in `proposal.json` (written by `propose --route`) and config schema v5's `build.auto_recouncil` (`config.py:30-33`, default true) are read at verb time — routing via `resolve_routing`, the closing-phase policy via `resolved_auto_recouncil` (`waves.py:86-101`, fail-open to true on a bad/absent config).
- **Downstream — feeds the build skill:** `--next` / `--next-wave` emit the frontier (item, mapped agent, dispatch mode, `equipped` flag, grounding, per-item `upgrade_note`, resolved model `routing`) that the `dummyindex-build` skill reads to dispatch and gate (`waves.py:406-463`, `466-535`).
- **Internal deferred imports (intentional, cycle-avoidance):** `map_task_to_equipment` is imported *inside* `_entry_for` (`waves.py:254`) and `next_wave` *inside* `do_next_wave` (`waves.py:478`), not at module top. This keeps the CLI module importable without eagerly pulling the domain mapping graph; it is a deliberate seam, not an accident.

## How it works (three invariants)

1. **Wave grouping = independence by construction.** A `## Wave N` / `## Group N` heading opens one shared `group` id; every checkbox under it shares that id, and group ids are assigned monotonically in document order (`checklist.py:25-32`, `80-97`). Because the plan step only groups disjoint-file tasks, same-group items are mutually independent and parallel-safe.
2. **Frontier = earliest incomplete group.** `next_wave` finds the first unchecked item and returns every unchecked item sharing its group (`checklist.py:115-126`). Monotonic group ids guarantee that first item is in the earliest incomplete group, so that group must fully close before any later one starts.
3. **Legacy flat checklists stay serial.** A non-wave heading closes an open group; items outside any wave heading get singleton groups (`checklist.py:28-32`, `83-97`). So a heading-less checklist degrades to exactly one `--next` item — the old strictly-serial behaviour.

## Parse model

`parse_checklist` reads line by line (`checklist.py:68`):

- `_ITEM_RE` matches `- [<mark>] <text>`: a space mark is unchecked, **any** non-space closes the box, so both `x` and `~` parse as done (`checklist.py:50`, `98-99`).
- `_WAVE_HEADING_RE` (heading text starting `wave`/`group`, case-insensitive) opens a wave; `_HEADING_RE` (any other heading) closes it (`checklist.py:55-56`, `85-88`). The group id is assigned **lazily at the first item** under a heading, so an empty wave heading never burns an id and groups stay contiguous (`checklist.py:80-94`).
- Two structural markers are parsed off the item but the text is **retained verbatim** so substring `--check` keys keep working (`checklist.py:20-23`): `_GATE_RE` — a leading `**GATE**`/`GATE`, case-sensitive + word-bound so "gate the rollout" / "GATEWAY" never match (`checklist.py:60-61`, `108`); `_VIA_RE` — a trailing `— via <tool>` em-dash tag (`checklist.py:63-65`, `109`). Both feed `ChecklistItem.gate` / `.via`, which `dispatch_mode` reads to classify main-session vs subagent (`models.py:61-70`).
- Items are frozen dataclasses; flips/skips return new copies via `dataclasses.replace` (`checklist.py:212`, `237`) — immutability convention honoured.

## Decisions

**Warn, don't halt, when unequipped (warn-and-halt gate lives in the skill).** Code does NOT hard-stop when `.context/equipment.json` is missing. Human mode emits `_NOT_EQUIPPED_WARNING` to **stderr** and falls back to general-purpose; JSON mode emits `equipped: false` and never warns (`waves.py:71-76`, `424-429`, `458-459`, `511-512`). The actual STOP belongs to the `dummyindex-build` skill, which reads that boundary signal. The warning is worded not to assert *absence*, because a present-but-corrupt file lands in the same `[]` branch (`waves.py:53-56`, `136-156`). This boundary "not-equipped" signal is distinct from a per-item `fallback` on an equipped repo, where general-purpose is the correct *silent* outcome (`waves.py:53-56`).

**Skip is a first-class state, not a tick.** `skip_item` writes `- [~]` plus a `— skipped: <reason>` annotation, so the frontier advances (`~` parses as done) while the file honestly records that no work happened — never a bare `- [x]` that would misreport the item as built (`checklist.py:14-17`, `215-237`). Reason is mandatory; an already-closed box is refused.

**Atomic, idempotent, mtime-preserving flips.** `_rewrite_item_line` rewrites only the n-th checkbox line (prose and other items preserved verbatim) via tmp-write + `replace` (`checklist.py:163-194`). `flip_item` is a no-op on an already-ticked box, preserving mtime so the drift hook does not false-fire (`checklist.py:207-211`).

**Pool hygiene — only real agents are dispatchable.** Only `kind == "agent"` entries that are not marketplace/vendored plugins join the mapping pool, mirroring the audit-roster guard so both manifest consumers agree and no plugin name leaks in as a bogus `subagent_type` (`waves.py:159-185`). Within the agent set, entries that actually name a `subagent_type` are preferred (`typed or agents`, `waves.py:184-185`) so an untyped legacy record can't shadow a typed one; when none is typed, the legacy agent pool is kept and each entry reports its downgrade honestly via `fallback`/general-purpose render (`_pinned_subagent_entry`, `waves.py:218-236`). GATE items bypass the matcher entirely (`waves.py:265-266`).

**Via tags naming agents fan out instead of serializing — and fail safe.** `dispatch_mode(item, agent_names)` upgrades a via tag to a subagent unit on an explicit `agent:<name>` prefix or a bare name exactly matching a pool entry (`models.py:70`, `88-95`). `_entry_for` pins such an item to that named pool entry with capability scoring bypassed; unknown agent names and untyped legacy matches degrade to main-session carrying a warning `upgrade_note` + report/escalate instruction, never a late Task-tool failure on an unequipped name (`waves.py:239-317`, `_AGENT_TAG_WARNING_INSTRUCTION` at `:116-120`).

**Routing is proposal data, not config — invocation > proposal > unset.** The optional `"routing"` object in `proposal.json` (closed role keys `implementer|auditor|decisions`; values validated against the shared `ModelChoice` alias alphabet) is merged under the per-invocation `--route K=V` override by `resolve_routing` (`routing.py:119-131`). One validator serves both `propose --route` and `build --route` so they reject exactly the same inputs; a hand-edited invalid block fails loudly at build start (exit 2 before any wave dispatches), never misroutes mid-build (`routing.py:48-94`, `waves.py:391-403`).

**Implementer is the default owner; specialists must earn the override.** Mapping is item-kind aware: the implement-capable entry owns checklist work by default, and a specialist wins only at `_SPECIALIST_MIN_SCORE` (2) AND strictly outscoring the implementer — so an incidental token (e.g. a stray "review" in prose) never re-routes implementation work (`mapping.py:51`, `372-376`).

**Independence is delegated, not enforced.** `next_wave`'s grouping is the *only* independence guarantee; there is no code-level disjoint-file check. The domain trusts the plan step to have grouped only disjoint-file tasks (`checklist.py:28-30`). This is a deliberate contract boundary, not an oversight — enforcing file-disjointness here would require the domain to read source it intentionally does not touch.

**Opaque group id, not the heading label.** The `group` in `--next-wave --json` is opaque and 0-based, deliberately NOT the `## Wave N` heading number (`waves.py:13-15`, `499`). No contract surfaces the human label; a consumer that wants it must read `checklist.md` directly.

## Contracts

Public surface, re-exported from `__init__.py:34-51`:

- `parse_checklist(path) -> tuple[ChecklistItem, ...]` — `checklist.py:68`
- `next_wave(items) -> tuple[ChecklistItem, ...]` — `checklist.py:115`
- `counts(items) -> tuple[int, int]` — `checklist.py:129`
- `flip_item(path, key) -> ChecklistItem` — `checklist.py:197`
- `skip_item(path, key, reason) -> ChecklistItem` — `checklist.py:215`
- `map_task_to_equipment(item_text, manifest, *, grounding=()) -> Choice` — `mapping.py:335`
- `dispatch_mode(item, agent_names=None) -> DispatchMode` — `models.py:73`
- `ChecklistItem(index, text, done, group=0, gate=False, via=None)` frozen — `models.py:48-55`
- `Choice(item_text, equipment_name, fallback, grounding, subagent_type=None)` frozen — `models.py:58-64`
- `DispatchMode(SUBAGENT, MAIN_SESSION)` — `models.py:41-45`; `AGENT_VIA_PREFIX = "agent:"` — `models.py:70`
- `ROUTING_KEYS`, `parse_route_flags(tokens)`, `read_proposal_routing(path)`, `resolve_routing(path, cli_override=None)` — `routing.py:38`, `77`, `97`, `119`
- `BuildLoopError(Exception)` — `errors.py:6`

CLI: `run(args) -> int` (`dispatch.py:109`); wave handlers `do_next` / `do_next_wave` (`waves.py:406`, `466`); status `_do_status` (`dispatch.py:249`). Boundary failures raise `BuildLoopError`; the CLI prints `error: …` to stderr and returns exit code 2 (`errors.py:6-8`, `dispatch.py:196-199`).
