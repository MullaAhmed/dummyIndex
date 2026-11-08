# Spec — dummyindex internally uses ponytail: reviewed default plugin plus default-on subagent mandate

## Intent

User report: "dummyindex cant internally use pony tail".

Today no dummyindex path ever applies ponytail. Three skills pass its mandate
only "if Ponytail is selected and exposed" (`dummyindex/skills/build/SKILL.md:83`,
`dummyindex/skills/plan/SKILL.md:73`, `dummyindex/skills/equip/SKILL.md:35`).
Nothing selects it. Nothing installs it. No code references it.

Goal: every subagent a dummyindex skill dispatches works under ponytail's
ruleset by default. On Claude the plugin hook covers every skill, including
audit, evolve and gc. The skill-text change covers plan, build and equip on
other hosts.

Ponytail (`DietrichGebert/ponytail`, MIT) is a rule plugin. It makes an agent
write only the code a task needs. It keeps validation, error handling,
security and accessibility.

## Chosen meaning

Two parts. Both are needed. Each is small.

1. **Claude: 4th reviewed default plugin.** Add `ponytail@ponytail` to
   `DEFAULT_PLUGINS`. Its `SubagentStart` hook injects the ruleset into every
   subagent while its mode is not `off`. Default mode is `full`. So every
   dummyindex delegate gets it with no skill logic.
2. **Every host: default-on skill text.** Replace "selected and exposed" with
   "applies by default when exposed" in the three skills. When the plugin
   hooks are active, the conductor does not paste it. Otherwise the conductor
   pastes the loaded mandate.

Rejected: a behavior gate for policy text. The `behavior-gate` feature already
ships it (`tests/eval/test_behavior_gate.py`). YAGNI.

## Upstream grounding

Reviewed 2026-11-08 against upstream `main` at
`96608e078b2d5ea607c5c3b8b5a54d1c1fba6846` (committer date 2026-10-29),
plugin v5.3.3.

- Install: marketplace `ponytail` from repo `DietrichGebert/ponytail`, plugin
  `ponytail`. Target `ponytail@ponytail`.
- `hooks/claude-codex-hooks.json`: `SessionStart`
  (`startup|resume|clear|compact`), `SubagentStart`, `UserPromptSubmit`. Each
  runs a Node script with a 15 s timeout.
- `hooks/ponytail-subagent.js`: injects the ruleset into each subagent. Absent
  or `off` mode injects nothing. Optional `PONYTAIL_SUBAGENT_MATCHER` narrows
  it. No file writes. No network.
- `hooks/ponytail-config.js`: `DEFAULT_MODE = 'full'`. Reads
  `PONYTAIL_DEFAULT_MODE` and `<config dir>/ponytail/config.json`.
- `.claude-plugin/plugin.json`: also loads `hooks/claude-band.json` (empty
  `hooks`) and a band UI module. The band keeps a local task ledger CSV under
  `~/.config/ponytail/band/`. An optional webhook URL is empty by default.
  Once a user sets it, each task row leaves the machine.

## Contracts

### Default plugin record

Append one record to `DEFAULT_PLUGINS` in
`dummyindex/context/default_plugins.py`, after `i-have-adhd`:

```python
DefaultPlugin(
    plugin="ponytail",
    marketplace="ponytail",
    repo="DietrichGebert/ponytail",
    surfaces=(
        "skills",
        "commands",
        "SessionStart Node command hook",
        "SubagentStart Node command hook",
        "UserPromptSubmit Node command hook",
        "band UI module with local task ledger",
    ),
    runs_code=True,
)
```

No new function. No new module. Every existing seam consumes the tuple:
`default_wired`, `describe_default_plugin_trust`, `wire_default_plugins`,
`install_default_plugins`, `reconcile_default_plugins`
(`dummyindex/context/domains/config.py`).

Invariants kept (existing generic tests already cover the last four):

- The trust line prints before any settings write or runner probe.
- Codex-only installs write no `.claude/**` state and wire no plugin.
- `--no-default-plugins` / `--no-superpowers` skip all four defaults for one run.
- `default_plugins_enabled: false` blocks backfill of ponytail.
- A `"ponytail@ponytail": false` tombstone is never flipped or materialized.

Existing repos gain ponytail through `reconcile_default_plugins` backfill on
the next Claude/both `install` or `init`. It appends after custom entries.
`wire_default_plugins` then writes `enabledPlugins` into the committed project
`.claude/settings.json`. So one upgrade enables it for the whole team. This
matches how every earlier default landed.

Expected trust line (exact):

```
default plugin trust -> ponytail@ponytail from DietrichGebert/ponytail (tracks latest); reviewed surfaces: skills, commands, SessionStart Node command hook, SubagentStart Node command hook, UserPromptSubmit Node command hook, band UI module with local task ledger; runs code: yes; opt out this run with --no-default-plugins
```

### Skill text

Replace the Ponytail sentence in build, plan and equip skills with this text.
Keep the same position. Do not touch other paragraphs.

> Ponytail applies by default when exposed. When its Claude plugin hooks are
> active in this session, its `SubagentStart` hook already injects it into
> each subagent; do not paste it again. Otherwise pass its loaded mandate
> unless the user turned it off this session. Never silently install it.

The build skill's `"policies"` persistence sentence stays as is.

### Docs

`dummyindex/skills/skill.md`, `docs/COMMANDS.md`, `docs/guide/07-cli.md` each
gain a 4th default bullet after the `policy-selfapply` end anchor. Anchored
regions stay byte-identical. The bullet names:

- the target `ponytail@ponytail` and repo `DietrichGebert/ponytail`;
- "tracks the latest upstream default branch";
- every reviewed surface and `runs_code=true`;
- the webhook: empty by default, sends task rows off the machine once set;
- the `SubagentStart` injection into every subagent, including dummyindex's.

Default counts change from three to four. Third-party counts change from two
to three. Opt-out layer counts stay three. `skill.md` adds one sentence:
Codex-only runs never install ponytail; a user-installed Codex plugin gets the
default-on skill text.

### Dogfood

This repo's `.context/config.json` `wired` gains `ponytail@ponytail` last. Write
it with `reconcile_default_plugins(Path(".context"), platform="both")`. Do not
hand-edit the file.

## Decisions

- D1. Meaning = candidates 1 + 2. Candidate 1 alone leaves non-Claude hosts on
  the "selected" gate. Candidate 2 alone changes nothing while ponytail is
  absent, which is the common case.
- D2. Candidate 3 dropped. `behavior-gate` already proves policy text produces
  behavior.
- D3. Claude delivery = upstream `SubagentStart` hook. No dummyindex hook, no
  prompt splicing, no change to `envelopes.py`.
- D4. Codex: no plugin install. dummyindex has no Codex plugin installer.
  Building one is out of scope. Skill text covers a user-installed Codex plugin.
- D5. Append ponytail last. Keeps existing order and backfill order stable.
- D6. Surfaces recorded from the pinned upstream review above. Build does not
  re-fetch upstream. No drift-check task; tracking latest is the existing
  reviewed-exception model.
- D7. Existing repos opt in on upgrade through existing backfill. No new
  consent flag. The trust line discloses it before any write. Opt-out stays
  the tombstone or the durable config flag.
- D8. Audit, evolve and gc skills get no new sentence. On Claude the hook
  covers them. Non-Claude coverage for them waits for a request (YAGNI).
- D9. "Turned it off" means the user said so this session. dummyindex reads no
  ponytail mode state.
- D10. Old adoption proposal `repo-adoptions-ponytail-headroom` is not
  superseded. Its open items are host-gap notes and a headroom miner.
- D11. New code carries no long comments.

## Risks

- Every subagent pays the ruleset's tokens. Accepted; `/ponytail off` ends it.
- Ponytail and the caveman/ADHD policy both shape output. Ponytail targets code
  size, not prose. Explicit user formatting still wins.
- Upstream tracks latest; surfaces can drift. Same exposure as caveman today.
- Ponytail's hooks need Node. Caveman already needs Node.
- A foreign `ponytail` marketplace declaration blocks wiring as `needs_user`.
  Existing conflict handling covers it.

## Acceptance

- [ ] `DEFAULT_PLUGINS[-1]` equals the record above; the exact-records test in
      `tests/context/test_default_plugins.py` pins all four records in order.
- [ ] `describe_default_plugin_trust()` returns 3 lines (caveman, i-have-adhd,
      ponytail); `lines[2]` equals the expected trust line above.
- [ ] `wire_default_plugins(default_wired(), tmp)` writes
      `extraKnownMarketplaces.ponytail.source == {"source": "github", "repo": "DietrichGebert/ponytail"}`
      and `enabledPlugins["ponytail@ponytail"] is True`; it makes zero runner calls.
- [ ] With a fake runner, `install_default_plugins` records
      `marketplace add DietrichGebert/ponytail --scope project` at a lower
      `calls` index than `plugin install ponytail@ponytail --scope project`.
- [ ] `reconcile_default_plugins` on a config holding the old three defaults
      plus one custom entry appends `ponytail@ponytail` last.
- [ ] A project `enabledPlugins` value `"ponytail@ponytail": false` survives
      `wire_default_plugins`; `install_default_plugins` makes no install call
      for ponytail.
- [ ] `default_config()` wired targets end with `ponytail@ponytail`.
- [ ] `tests/test_install.py` expects the ponytail trust line before the first
      runner call.
- [ ] `tests/cli/test_cli_doc_sync.py` requires `ponytail@ponytail`,
      `DietrichGebert/ponytail` and `SubagentStart` in all three default-plugin
      docs, and passes.
- [ ] `tests/test_skills_doc_hygiene.py` asserts, for build, plan and equip
      skills after whitespace flattening: "Ponytail applies by default when
      exposed", "`SubagentStart` hook already injects it" and "Never silently
      install it" present; "Ponytail is selected and exposed" absent.
- [ ] `.context/config.json` `wired` ends with `ponytail@ponytail`.
- [ ] `.context/features/equip/spec.md` contains "applies by default when
      exposed" and no longer contains "not installed or assumed automatically".
- [ ] No "Ponytail is selected and exposed" remains under `dummyindex/`,
      `tests/`, `docs/` or `.context/features/`.
- [ ] `pytest -q` exits 0.

<!-- dummyindex:consistency:begin -->
## Consistency

**Related features:**

- `equip`
- `install-surface`
- `cli-dispatch`

**Conventions to honor:**

- `conventions/coding-practices.md`
- `conventions/data-access.md`
- `conventions/folder-organization.md`
- `conventions/naming.md`
- `conventions/testing.md`

<!-- dummyindex:consistency:end -->
