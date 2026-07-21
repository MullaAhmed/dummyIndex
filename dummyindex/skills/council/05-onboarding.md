# Onboarding (first run only)

Capture the user's council preferences once, persist them to
`.context/config.json`, and reuse them on every later run. Runs when the
repo has **no `.context/config.json`** — a fresh repo, or a v0.13.x
`.context/` upgrading to v0.14 — and on an explicit `/dummyindex --reconfigure`.

The config stores **choices only — never API keys**. Credentials remain in the
active host's environment or connector configuration; this file is committed
and shared by the team.

## When to run

1. After Phase 1 backbone (so the feature count is known for the mode cost
   estimate), check for config:
   ```bash
   dummyindex context config show
   ```
2. If it prints a config → onboarding already happened. Skip to Phase 1.5.
3. If it reports "no config.json" (exit 1) → run the questions below.
4. On `/dummyindex --reconfigure` → always run them, regardless of an
   existing config.

## Host-aware questions

Use the active host's normal user-input mechanism. Claude Code may use
`AskUserQuestion`; Codex asks directly. Collect the portable preferences first:

1. **Scope** — what should the dummyindex skill index by default on later runs?
   - `repo` (recommended) — the whole repository.
   - `subdir` — one subdirectory (ask a follow-up for the path).
   - `explicit` — pass paths on each run; persist no default.
2. **Mode** — how much council effort per feature? Show the feature count from
   `features/INDEX.json` and the relative dispatch shape. Do not quote a dollar
   estimate on Codex because the active model and entitlement determine usage.

   | Mode | Per-feature dispatches | When |
   |---|---|---|
   | `light` | dev only | quick pass |
   | `standard` (recommended) | dev + architect + 1 critic | default |
   | `deep` | dev + architect + all critics + cross-review | max rigor |

3. **External docs** _(skippable, default: none)_ — any prose-doc roots outside
   the repo to catalogue? `none` / collect one or more paths.

Then apply the resolved-platform branch:

### Claude Code

Ask two additional questions (five total):

4. **Model** — which Claude model should the council run on? This is required;
   do not choose silently: `opus-4.8`, `sonnet-4.6` (recommended), or
   `haiku-4.5`.
5. **Managed hooks** _(skippable, default: install)_ — install dummyindex's
   Claude hooks: SessionStart drift/memory/GC, Stop memory/reconcile gate,
   PreCompact breadcrumb, and PreToolUse document guard? `install` / `skip`.

### Codex

Do **not** offer Claude model labels or a managed-hook install question.

- Persist `model=current`, which explicitly means the model running this Codex
  session and its spawned subagents.
- Persist `--no-hook`. Codex has a native hook system, but dummyindex currently
  installs only its Claude hook definitions; Codex uses its active project
  instruction file (`AGENTS.override.md`, `AGENTS.md`, or a configured fallback)
  and explicit `$dummyindex*` workflows instead.

### Both hosts

Do not collapse an explicit `--platform both` request into the Codex-only
branch merely because the current session is running in Codex.

- Persist `model=current`, the portable active-session selector understood by
  either installed workflow.
- Ask the **Managed hooks** question because Claude integration is selected;
  default to `install`. Persist `--hook` for install or `--no-hook` only when
  the user explicitly chooses skip. This value records Claude's hook state;
  Codex itself still relies on guidance and explicit skills.

## Persist the answers

Write the config via one CLI call.

Claude Code:

```bash
dummyindex context onboard \
  --platform claude \
  --scope <repo|subdir|explicit> [--scope-path <PATH>] \
  --mode <light|standard|deep> \
  --model <opus-4.8|sonnet-4.6|haiku-4.5> \
  [--hook | --no-hook] \
  [--doc <PATH>]...
```

Codex:

```bash
dummyindex context onboard \
  --platform codex \
  --scope <repo|subdir|explicit> [--scope-path <PATH>] \
  --mode <light|standard|deep> \
  --model current --no-hook \
  [--doc <PATH>]...
```

Both hosts:

```bash
dummyindex context onboard \
  --platform both \
  --scope <repo|subdir|explicit> [--scope-path <PATH>] \
  --mode <light|standard|deep> \
  --model current \
  [--hook | --no-hook] \
  [--doc <PATH>]...
```

- `--scope-path` is required when `--scope subdir`; the CLI rejects the pair
  otherwise (exit 2).
- `--platform` pins the host branch even when both managed guidance files are
  present. When omitted, the CLI infers dummyindex's exact managed markers and
  falls back to Claude only when neither marker exists.
- `--model` is mandatory. `current` is the explicit Codex value, not an omitted
  or inferred default.
- Omit `--doc` for "none"; repeat it once per external doc root.

The command writes `.context/config.json` and prints the resolved JSON. Confirm
it back to the user in one line.

## After onboarding

- Use the chosen **mode** for this run's council (an explicit `/dummyindex
  --mode ...` on the invocation still overrides the stored default).
- On Claude-only or both-host onboarding, make the live managed-hook state
  match the persisted choice. Run `dummyindex context hooks install` after an
  **install** choice and `dummyindex context hooks uninstall` after a **skip**
  choice. This also makes `--reconfigure` apply a changed preference instead
  of merely recording it. Report the command's result.
- On Codex-only, do not inspect or uninstall `.claude/settings.json`;
  `--no-hook` records the Codex integration's supported state.
- With both hosts selected, the hook choice applies to Claude even when
  onboarding is being conducted from Codex.
- Proceed to Phase 1.5 (Conventions).

## Non-interactive / CI

When there is no interactive host session (CI, scripted installs), select the
platform explicitly:

```bash
dummyindex install --platform claude --no-onboarding --defaults
dummyindex install --platform codex --no-onboarding --defaults
dummyindex install --platform both --no-onboarding --defaults
```

Claude defaults to `scope=repo, mode=standard, model=sonnet-4.6, hook on`; Codex
defaults to `scope=repo, mode=standard, model=current, hook off`. `both` uses the
portable `model=current` and keeps the Claude managed hooks on. All three
default to no external docs. `config show` then reports the resolved values.
