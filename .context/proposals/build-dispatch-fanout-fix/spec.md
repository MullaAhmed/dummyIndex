# Spec — Stop generated via-tags forcing main-session dispatch; add first-class model routing to builds

> Scaffolded by `dummyindex context propose`. Flesh out the intent
> and contracts below, then keep the **Acceptance** checklist honest.

## Intent

Every wave of a real build (e.g. `enriched-refresh-manifest-stamp`) carries acceptance
items tagged `— via dummyindex-verify`, and planners routinely tag implementation items
`— via python-implementer`. Both are **generated agents** defined in
`.context/equipment.json` (`python-implementer.suite.json`,
`dummyindex-verify.suite.json` exist under `equipment-evals/`). But
`dispatch_mode()` (`dummyindex/context/domains/buildloop/models.py`) classifies *any*
`via` tag as `MAIN_SESSION`, so the conductor runs those items itself instead of
fanning them out — killing the parallelism the wave system exists for. Observed live:
"are you launching 3 subagents at once? … just get it done asap" vs serial execution.

Second, unmet need: model routing. The user hand-pastes *"use sonnet for writing actual
files, opus for auditing, fable for any decisions"* into nearly every build invocation
(6+ occurrences across Aug), and asks twice "what models would be used?" — because
routing is prose convention, not data.

## Contracts

- **Agent-prefixed via tags dispatch as subagents.** New tag syntax
  `— via agent:<name>`. In `dispatch_mode`, a `via` beginning `agent:` is classified
  `SUBAGENT` (the `<name>` becomes the Task target). Bare `— via <tool>` keeps today's
  binding main-session semantics (plugin commands, `/skills`, MCP-bound tools).
- **Defensive bare-name upgrade.** When a checklist item carries a bare `— via <name>`
  and `<name>` exactly matches a `kind: agent` entry in the dispatchable equipment pool
  (`_dispatchable` in `cli/build_loop/waves.py`), the mapper pins the unit to that named
  entry (capability scoring bypassed) and records the reclassification as a new additive
  payload key `upgrade_note`. Skill-kind names (e.g. `dummyindex-verify`, kind: skill)
  stay MAIN_SESSION by design — skills execute in the main session. Non-matching names
  stay MAIN_SESSION.
- **Routing is proposal data, not config.** `proposal.json` gains an optional
  `"routing": {"implementer": "<model>", "auditor": "<model>", "decisions":
  "<model>"}` block (written by `/dummyindex-plan --route k=v`; absent = no routing).
  Values are family aliases validated against the existing `ModelChoice` alphabet in
  `domains/config.py` (reuse; no new enum). `build --route k=v[k=v…]` overrides at
  run time; precedence invocation > proposal > unset.
- **Unknown names fail safe.** An `agent:<name>` with no kind-agent pool match stays
  MAIN_SESSION carrying a warning `upgrade_note` — never a late Task-tool failure.
  Residual by design: skill-kind tags (acceptance items) remain serialized main-session
  work; this proposal removes only the false serialization of agent-kind tags.
- **Routing validation.** Closed key set `{implementer, auditor, decisions}`; unknown
  keys rejected; every `ModelChoice` alias (incl. `current`) legal; unresolvable
  aliases in a hand-edited proposal.json fail loudly at build start.
- **Effective-model disclosure.** `build --status/--check` payloads include the
  resolved routing map; the build SKILL's opening step prints
  `models: implementer=<x> auditor=<y> decisions=<z>` before the first wave — the
  answer to "what models would be used?", printed without being asked.
- **Skill guidance fix.** Packaged `plan/SKILL.md` stops teaching bare-name agent
  tagging: generated agents are either left untagged (mapper auto-selects) or tagged
  `agent:<name>`; only plugin-commands/skills/MCP tools take binding `— via`.
  `build/SKILL.md` documents the two tag classes and the substitution-failure rule
  unchanged for genuine tools.
- **Invariants.** `DispatchMode` alphabet unchanged; `--json` payloads gain keys, never
  lose them; GATE semantics untouched; no config schema bump (deliberately avoids
  colliding with `reconcile-guardrails-maintain`'s v5 work in the same file).

## Acceptance

- [ ] pytest `-k dispatch` green: `agent:` tag → SUBAGENT; unknown bare name →
      MAIN_SESSION; bare name matching pool entry → upgraded with note; GATE always
      MAIN_SESSION.
- [ ] pytest `-k route` green: precedence invocation > proposal > unset; invalid alias
      rejected using the ModelChoice validator.
- [ ] Fixture checklist item tagged `— via python-implementer` maps as a subagent unit
      pinned to that agent; a `— via /dummyindex-verify` skill tag stays main-session.
- [ ] `--status` output (dispatch.py `_do_status`) shows resolved routing; next-wave
      payloads carry `routing`; SKILL grep shows the disclosure step.
- [ ] Full suite green: `python -m pytest tests/ -q --tb=short`.

<!-- dummyindex:consistency:begin -->
## Consistency

**Related features:**

- `install-surface`
- `equip`
- `session-memory`
- `usage-report`
- `tree-enrich`

**Conventions to honor:**

- `conventions/coding-practices.md`
- `conventions/data-access.md`
- `conventions/folder-organization.md`
- `conventions/naming.md`
- `conventions/testing.md`

<!-- dummyindex:consistency:end -->
