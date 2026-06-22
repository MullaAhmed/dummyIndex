# Build-loop checklist & waves — plan

confidence: INFERRED

## Where it lives

Domain (pure state, no I/O beyond the checklist file it owns): `dummyindex/context/domains/buildloop/` — `checklist.py` (parse/flip/skip/wave/counts), `models.py` (`ChecklistItem`, `Choice`, `DispatchMode`, `dispatch_mode`), `mapping.py` (`map_task_to_equipment`), `errors.py` (`BuildLoopError`), `__init__.py` (public surface, `:34-51`). CLI (wire-only): `dummyindex/cli/build_loop/` — `dispatch.py` (`run` + `--check`/`--skip`/`--status`), `waves.py` (`--next`/`--next-wave`). Tests: `tests/context/domains/test_build_loop.py`, `test_build_loop_routing.py`. The dispatch/verify-before-tick loop itself is the `dummyindex-build` skill (markdown), not code (`__init__.py:18-22`).

## Architecture in three sentences

A `## Wave N` / `## Group N` heading opens one shared `group` id under which every checkbox item is grouped, and the plan step only groups tasks that touch disjoint files — so items sharing a group are mutually independent by construction and safe to dispatch in parallel (`checklist.py:25-32`, `90-97`). `next_wave` finds the first unchecked item and returns every unchecked item sharing its group; because group ids are monotonic in document order, the first unchecked item is always in the earliest incomplete group, and that group must finish before any later one starts (`checklist.py:115-126`). Any non-wave heading closes an open group and items outside any wave heading each get their own singleton group, so a legacy flat checklist stays strictly serial (`checklist.py:28-32`, `83-97`).

## Data model

`parse_checklist` reads the file line by line: `_ITEM_RE` matches `- [<mark>] <text>` (mark = space → unchecked, any non-space → done, so both `x` and `~` close the box) (`checklist.py:50`, `98-99`). `_WAVE_HEADING_RE` (heading text starting `wave`/`group`, case-insensitive) opens a wave; `_HEADING_RE` (any other heading) closes it (`checklist.py:55-56`, `85-88`). The wave's group id is assigned lazily at the first item under it, so an empty wave heading never burns an id and groups stay contiguous (`checklist.py:80-94`). Two structural markers are parsed off the item text but the text is retained verbatim so substring `--check` keys keep working (`checklist.py:20-23`): `_GATE_RE` — a leading `**GATE**`/`GATE`, case-sensitive + word-bound so "gate the rollout"/"GATEWAY" never match (`checklist.py:60-61`, `108`); `_VIA_RE` — a trailing `— via <tool>` em-dash tag (`checklist.py:63-65`, `109`). Both feed `ChecklistItem.gate`/`.via`, which `dispatch_mode` reads to classify main-session vs subagent (`models.py:61-70`). Items are immutable frozen dataclasses; flips/skips return new copies via `dataclasses.replace` (`checklist.py:212`, `237`).

## Key decisions

**Warn + (don't) halt when unequipped.** The build loop does NOT hard-stop in code when `.context/equipment.json` is missing — it emits `_NOT_EQUIPPED_WARNING` to stderr (human mode) or `equipped: false` (JSON) and falls back to general-purpose, leaving the STOP decision to the `dummyindex-build` skill which reads that signal (`waves.py:57-61`, `248-250`, `271-272`). The warning is worded not to assert absence, since a present-but-corrupt file also lands in the `[]` branch (`waves.py:54-56`, `91-101`).

**Skip is a first-class state, not a tick.** `skip_item` writes `- [~]` plus a `— skipped: <reason>` annotation so the frontier advances (`~` parses as done) while the file honestly records that no work happened — never a bare `- [x]` that misreports the item as built (`checklist.py:14-17`, `215-237`). Reason is mandatory and an already-closed box is refused.

**Atomic, idempotent flips.** `_rewrite_item_line` rewrites only the n-th checkbox line (prose/other items preserved verbatim) via tmp-write + `replace` (`checklist.py:163-194`). `flip_item` is a no-op on an already-ticked box, preserving mtime (`checklist.py:207-211`).

**Pool hygiene.** Only `kind == "agent"` entries that are not marketplace/vendored plugins join the mapping pool, mirroring the audit roster guard so both manifest consumers agree and no plugin name leaks in as a bogus `subagent_type` (`waves.py:104-129`). GATE/via items bypass the matcher entirely (`waves.py:169-179`). Mapping is item-kind aware: the implement-capable entry is the default owner; a specialist only wins at `_SPECIALIST_MIN_SCORE` (2) AND strictly outscoring the implementer, so an incidental token never re-routes implementation work (`mapping.py:48-49`, `241-248`).

## Open questions

- `map_task_to_equipment` is imported inside `_entry_for` (`waves.py:159`) and `next_wave` inside `do_next_wave` (`waves.py:290`) — deferred imports; intentional cycle-avoidance or incidental? Not load-bearing for behavior.
- The `group` id exposed in `--next-wave --json` is opaque and 0-based, deliberately NOT the `## Wave N` heading number (`waves.py:13-15`); consumers that want the human label must read `checklist.md` directly — no contract surfaces the label.
- `next_wave` is re-exported and used by `do_next_wave`, but `parse_checklist`'s grouping is the only independence guarantee; the domain trusts the plan step to have grouped only disjoint-file tasks (`checklist.py:28-30`) — there is no code-level independence check.
