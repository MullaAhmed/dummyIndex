# Build-loop checklist & waves — spec

confidence: INFERRED

## Intent

Drive a proposal's `checklist.md` to completion as a deterministic state machine, exposing a wave-grouped dispatch frontier so the `dummyindex-build` skill can run mutually-independent items in parallel. The `buildloop` domain owns pure, testable state — parse the markdown checklist, classify each item (subagent vs main-session), map each item to the best-fit equipment agent, resolve the proposal's model routing (`routing.py`), and atomically tick or skip exactly one box. The CLI (`cli/build_loop/`) is wire-only: parse args, call the domain, print. Agent dispatch and verify-before-tick discipline live in the skill, not in code (`dummyindex/context/domains/buildloop/__init__.py:18-22`).

## User-visible behavior

`dummyindex context build --proposal <slug> <verb>` takes exactly one verb (`dispatch.py:155-175`). The proposal's checklist is read from `.context/proposals/<slug>/checklist.md` (`dispatch.py:189-193`).

**`--route K=V` (repeatable)** — per-build model routing override; applies to `--next`, `--next-wave`, and `--status` only (a `--route` on `--check`/`--skip` is a usage error, `dispatch.py:178-182`). Keys are the closed role set `implementer|auditor|decisions`; values are `ModelChoice` aliases (`current|opus|sonnet|haiku|fable`). Precedence: **invocation > proposal > unset** — `resolve_routing` merges the validated override over the optional `"routing"` block in `proposal.json` (`routing.py:119-131`). An invalid key/alias fails with exit 2 before anything runs (`routing.py:48-74`, `dispatch.py:184-187`); `propose --route` records the block via the same parser (`cli/propose.py:62`, `92-99`).

**`--next [--json]`** — print the first unchecked item, its mapped equipment agent (or `general-purpose` fallback), the dispatch mode, any `upgrade_note`, and the grounding paths; the JSON payload also carries the resolved model `routing` map (`waves.py:406-463`). The serial-fallback verb.

**`--next-wave [--json]`** — print EVERY unchecked item sharing the earliest incomplete group, each with its own equipment mapping; the parallel-dispatch frontier (`waves.py:466-535`). A `## Wave N` / `## Group N` heading opens one shared group; on a flat checklist this degrades to exactly the single `--next` item (`checklist.py:25-32`, `waves.py:18-20`). The JSON `group` key is the opaque 0-based group id from `parse_checklist`, not the `N` in the heading text (`waves.py:13-15`, `499`).

**Equipped gate** — the repo is "equipped" iff `.context/equipment.json` exists and parses to >=1 item; absent/empty/corrupt JSON all collapse to `[]` → not equipped (`waves.py:424-429`, `136-156`). In human mode `--next`/`--next-wave` print a `_NOT_EQUIPPED_WARNING` to **stderr** then fall back to general-purpose (`waves.py:71-76`, `458-459`, `511-512`); JSON mode emits `equipped: false` and never warns. This boundary "not-equipped" signal is distinct from a per-item `fallback` on an equipped repo (where general-purpose is the correct silent outcome) (`waves.py:53-56`).

**Per-item dispatch classification** — a `**GATE**`/`GATE`-led item is a human decision and always main-session, even when it also carries a via tag (`models.py:88-89`). A `— via <tool>`-tagged item is a binding main-session tool invocation **except** in two agent-naming shapes that upgrade it to a pinned subagent unit (`models.py:73-96`, `AGENT_VIA_PREFIX` at `models.py:70`): an explicit `— via agent:<name>`, or a bare `— via <name>` exactly matching a kind-agent pool name. The upgrade pins the entry when it carries a `subagent_type` (capability scoring bypassed); unknown agent names and untyped legacy matches fail safe as main-session items carrying a warning `upgrade_note`, never a late Task-tool failure on an unequipped name (`waves.py:239-317`). Everything else is a `subagent` dispatch unit. Only Task-dispatchable entries join the mapping pool — among `kind == "agent"` non-marketplace/vendored entries, ones naming a `subagent_type` are preferred so an untyped legacy record can't shadow a typed one; skills/hooks/command plugins are excluded so an incidental token never launches one as a bogus `subagent_type` (`waves.py:159-185`).

**`--check "<item>"`** — atomically flip one item to `- [x]` by 0-based index, digit string, or unique case-insensitive substring; idempotent on an already-ticked box; ambiguous/no match is an error (`checklist.py:135-160`, `197-212`, `dispatch.py:152-161`).

**`--skip "<item>" --reason "<why>"`** — close one box as `- [~] … — skipped: <why>`; `~` parses as done so the wave frontier advances, but the file records why no work happened instead of a bare misreporting tick. `--reason` is mandatory; refuses an already-closed box and an empty reason (`checklist.py:215-237`, `dispatch.py:146-153`, `237-246`).

**`--status [--json]`** — print done/total plus the resolved model routing: a `models: role=alias …` disclosure in text mode (silent when the proposal is unrouted) and a `routing` map via `--json`; also the resolved closing-phase policy as `auto_recouncil: on|off` (`config` schema v5 `build.auto_recouncil`, default on; `waves.py:86-101`, `dispatch.py:281-286`). When complete, print the reconcile next step `dummyindex context reconcile`, or — with auto_recouncil off — report that the maintain loop is skipped and the pending count it leaves behind (`dispatch.py:287-298`).

Boundary failures (missing checklist, ambiguous key, invalid routing) raise `BuildLoopError`; the CLI catches it, prints `error: …` to stderr, returns exit code 2 (`errors.py:6-8`, `dispatch.py:196-199`).

## Contracts

Public surface re-exported from the domain package (`__init__.py:34-51` plus `AGENT_VIA_PREFIX` and the routing pair at `__init__.py:41-42`):

- `parse_checklist(path: Path) -> tuple[ChecklistItem, ...]` — `checklist.py:68`
- `next_wave(items: tuple[ChecklistItem, ...]) -> tuple[ChecklistItem, ...]` — `checklist.py:115`
- `counts(items: tuple[ChecklistItem, ...]) -> tuple[int, int]` — `checklist.py:129`
- `flip_item(path: Path, key: Union[int, str]) -> ChecklistItem` — `checklist.py:197`
- `skip_item(path: Path, key: Union[int, str], reason: str) -> ChecklistItem` — `checklist.py:215`
- `map_task_to_equipment(item_text: str, manifest: Sequence[Mapping[str, Any]], *, grounding: tuple[str, ...] = ()) -> Choice` — `mapping.py:335`
- `dispatch_mode(item: ChecklistItem, agent_names: frozenset[str] | None = None) -> DispatchMode` — `models.py:73`
- `ChecklistItem(index, text, done, group=0, gate=False, via=None)` frozen — `models.py:48-55`
- `Choice(item_text, equipment_name, fallback, grounding, subagent_type=None)` frozen — `models.py:58-64`
- `DispatchMode(SUBAGENT="subagent", MAIN_SESSION="main-session")` — `models.py:41-45`
- `AGENT_VIA_PREFIX = "agent:"` — `models.py:70`
- Routing (`routing.py`, re-exported): `ROUTING_KEYS = ("implementer", "auditor", "decisions")` — `routing.py:38`; `parse_route_flags(tokens) -> dict[str, str]` — `routing.py:77`; `read_proposal_routing(proposal_json) -> dict[str, str]` — `routing.py:97`; `resolve_routing(proposal_json, cli_override=None) -> dict[str, str]` — `routing.py:119`
- `BuildLoopError(Exception)` — `errors.py:6`

CLI entry: `run(args: list[str]) -> int` — `dispatch.py:109`. Wave handlers `do_next` / `do_next_wave` — `waves.py:406`, `466`; both take `route_override` and emit `routing` + per-item `upgrade_note`. Status handler `_do_status` — `dispatch.py:249`; auto-recouncil resolution `resolved_auto_recouncil` — `waves.py:86`.

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

Routing:
```
dummyindex context propose --slug s --title "…" --route implementer=sonnet
dummyindex context build --proposal s --route auditor=opus --status
# → build status [s]: 0/5 done
#   models: implementer=sonnet auditor=opus
#   auto_recouncil: on
```

A flat (heading-less) checklist gives each item its own singleton group, so `--next-wave` yields exactly one item — the old strictly-serial behavior (`checklist.py:28-32`).
