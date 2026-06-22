# Build-loop checklist & waves — spec

confidence: INFERRED

## Intent

Drive a proposal's `checklist.md` to completion as a deterministic state machine, exposing a wave-grouped dispatch frontier so the `dummyindex-build` skill can run mutually-independent items in parallel. The `buildloop` domain owns pure, testable state — parse the markdown checklist, classify each item (subagent vs main-session), map each item to the best-fit equipment agent, and atomically tick or skip exactly one box. The CLI (`cli/build_loop/`) is wire-only: parse args, call the domain, print. Agent dispatch and verify-before-tick discipline live in the skill, not in code (`dummyindex/context/domains/buildloop/__init__.py:18-22`).

## User-visible behavior

`dummyindex context build --proposal <slug> <verb>` takes exactly one verb (`dispatch.py:110-128`). The proposal's checklist is read from `.context/proposals/<slug>/checklist.md` (`dispatch.py:131-137`).

**`--next [--json]`** — print the first unchecked item, its mapped equipment agent (or `general-purpose` fallback), the dispatch mode, and the grounding paths (`waves.py:232-276`). The serial-fallback verb.

**`--next-wave [--json]`** — print EVERY unchecked item sharing the earliest incomplete group, each with its own equipment mapping; the parallel-dispatch frontier (`waves.py:279-337`). A `## Wave N` / `## Group N` heading opens one shared group; on a flat checklist this degrades to exactly the single `--next` item (`checklist.py:25-32`, `waves.py:18-20`). The JSON `group` key is the opaque 0-based group id from `parse_checklist`, not the `N` in the heading text (`waves.py:13-15`, `305`).

**Equipped gate** — the repo is "equipped" iff `.context/equipment.json` exists and parses to >=1 item; absent/empty/corrupt JSON all collapse to `[]` → not equipped (`waves.py:248-250`, `81-101`). In human mode `--next`/`--next-wave` print a `_NOT_EQUIPPED_WARNING` to **stderr** then fall back to general-purpose (`waves.py:57-61`, `271-272`, `313-314`); JSON mode emits `equipped: false` and never warns. This boundary "not-equipped" signal is distinct from a per-item `fallback` on an equipped repo (where general-purpose is the correct silent outcome) (`waves.py:54-56`).

**Per-item dispatch classification** — a `**GATE**`/`GATE`-led item is a human decision; a `— via <tool>`-tagged item is a binding tool invocation. Both are `main-session` items carrying a conductor `instruction` and never reach the agent matcher or get a `subagent_type` (`models.py:61-70`, `waves.py:169-179`, `63-78`). Everything else is a `subagent` dispatch unit. Only `kind == "agent"` (non-marketplace/non-vendored) equipment entries join the mapping pool; skills/hooks/command plugins are excluded so an incidental token never launches one as a bogus `subagent_type` (`waves.py:104-129`).

**`--check "<item>"`** — atomically flip one item to `- [x]` by 0-based index, digit string, or unique case-insensitive substring; idempotent on an already-ticked box; ambiguous/no match is an error (`checklist.py:135-160`, `197-212`, `dispatch.py:152-161`).

**`--skip "<item>" --reason "<why>"`** — close one box as `- [~] … — skipped: <why>`; `~` parses as done so the wave frontier advances, but the file records why no work happened instead of a bare misreporting tick. `--reason` is mandatory; refuses an already-closed box and an empty reason (`checklist.py:215-237`, `dispatch.py:99-108`, `164-173`).

**`--status [--json]`** — print done/total; when complete, print the reconcile next step `dummyindex context reconcile` (`dispatch.py:176-197`, `waves.py:50`).

Boundary failures (missing checklist, ambiguous key) raise `BuildLoopError`; the CLI catches it, prints `error: …` to stderr, returns exit code 2 (`errors.py:5-7`, `dispatch.py:136-139`).

## Contracts

Public surface re-exported from the domain package (`__init__.py:34-51`):

- `parse_checklist(path: Path) -> tuple[ChecklistItem, ...]` — `checklist.py:68`
- `next_wave(items: tuple[ChecklistItem, ...]) -> tuple[ChecklistItem, ...]` — `checklist.py:115`
- `counts(items: tuple[ChecklistItem, ...]) -> tuple[int, int]` — `checklist.py:129`
- `flip_item(path: Path, key: Union[int, str]) -> ChecklistItem` — `checklist.py:197`
- `skip_item(path: Path, key: Union[int, str], reason: str) -> ChecklistItem` — `checklist.py:215`
- `map_task_to_equipment(item_text: str, manifest: Sequence[Mapping[str, Any]], *, grounding: tuple[str, ...] = ()) -> Choice` — `mapping.py:203`
- `dispatch_mode(item: ChecklistItem) -> DispatchMode` — `models.py:61`
- `ChecklistItem(index, text, done, group=0, gate=False, via=None)` frozen — `models.py:42-49`
- `Choice(item_text, equipment_name, fallback, grounding, subagent_type=None)` frozen — `models.py:52-58`
- `DispatchMode(SUBAGENT="subagent", MAIN_SESSION="main-session")` — `models.py:35-39`
- `BuildLoopError(Exception)` — `errors.py:5`

CLI entry: `run(args: list[str]) -> int` — `dispatch.py:69`. Wave handlers `do_next` / `do_next_wave` — `waves.py:232`, `279`.

## Examples

Wave checklist:
```
## Wave 1 — scaffolding
- [ ] Add the parser module
- [ ] Write the models dataclass
## Wave 2 — wiring
- [ ] **GATE** confirm the public API shape
- [ ] Run the test suite — via dummyindex-verify
```
`--next-wave` returns both Wave-1 items (group id 0), each mapped to an agent. After both tick, `--next-wave` returns Wave 2: the GATE item (`main-session`, gate instruction) and the via-tagged item (`main-session`, via instruction) — neither dispatched.

Skip:
```
dummyindex context build --proposal s --skip "parser module" --reason "covered by existing CLI"
# → - [~] Add the parser module — skipped: covered by existing CLI
```

A flat (heading-less) checklist gives each item its own singleton group, so `--next-wave` yields exactly one item — the old strictly-serial behavior (`checklist.py:28-32`).
