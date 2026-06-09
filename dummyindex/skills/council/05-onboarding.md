# Onboarding (first run only)

Capture the user's council preferences once, persist them to
`.context/config.json`, and reuse them on every later run. Runs when the
repo has **no `.context/config.json`** — a fresh repo, or a v0.13.x
`.context/` upgrading to v0.14 — and on an explicit `/dummyindex --reconfigure`.

The config stores **choices only — never API keys**. Keys live in the
Claude session's environment; this file is committed and shared by the team.

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

## The five questions (use the `AskUserQuestion` tool)

Ask all five in one `AskUserQuestion` call where possible. Questions 1–3 are
**required**; 4–5 have safe defaults and may be skipped.

1. **Scope** — what should `/dummyindex` index by default on later runs?
   - `repo` (recommended) — the whole repository.
   - `subdir` — one subdirectory (ask a follow-up for the path).
   - `explicit` — pass paths on each run; persist no default.
2. **Mode** — how much council effort per feature? Show the estimate from the
   feature count in `features/INDEX.json` (N = feature count):
   | Mode | Per-feature dispatches | Rough cost (N≈14) | When |
   |---|---|---|---|
   | `light` | dev only | ~$2–4 | quick pass |
   | `standard` (recommended) | dev + architect + 1 critic | ~$6–10 | default |
   | `deep` | dev + architect + all critics + cross-review | ~$15–25 | max rigor |
3. **Model** — which model should the council run on? **Required — never pick
   one silently.**
   - `opus-4.7` — deepest reasoning.
   - `sonnet-4.6` (recommended) — best balance.
   - `haiku-4.5` — fastest / cheapest.
4. **Session hooks** _(skippable, default: install)_ — install the three
   managed hooks (SessionStart drift report, Stop handoff nudge, PreCompact
   breadcrumb) so each new session sees a staleness report and handoffs are
   captured? `install` (recommended) / `skip`.
5. **External docs** _(skippable, default: none)_ — any prose-doc roots outside
   the repo to catalogue? `none` / collect one or more paths.

## Persist the answers

Write the config via the CLI — one call, mapping each answer to a flag:

```bash
dummyindex context onboard \
  --scope <repo|subdir|explicit> [--scope-path <PATH>] \
  --mode <light|standard|deep> \
  --model <opus-4.7|sonnet-4.6|haiku-4.5> \
  [--hook | --no-hook] \
  [--doc <PATH>]...
```

- `--scope-path` is required when `--scope subdir`; the CLI rejects the pair
  otherwise (exit 2).
- `--model` is mandatory — there is no silent default on this path.
- Omit `--doc` for "none"; repeat it once per external doc root.

The command writes `.context/config.json` and prints the resolved JSON. Confirm
it back to the user in one line.

## After onboarding

- Use the chosen **mode** for this run's council (an explicit `/dummyindex
  --mode ...` on the invocation still overrides the stored default).
- If the user picked **skip** for the hook and Phase 1 already installed it,
  leave it — `--no-hook` only records the preference; removing a live hook is a
  separate `dummyindex context hooks uninstall`.
- Proceed to Phase 1.5 (Conventions).

## Non-interactive / CI

When there's no Claude session to answer questions (CI, scripted installs):

```bash
dummyindex install --no-onboarding --defaults   # writes default config.json
```

writes `scope=repo, mode=standard, model=sonnet-4.6, hook on, no external docs`
so the pipeline runs unattended. `config show` then reports the resolved values.
