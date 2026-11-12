---
name: dummyindex-equip
description: "Route project work through a host-appropriate toolkit grounded in the repo's `.context/` spine. Prepare and evolve shared, hash-baselined project capabilities under `.context/equipment/` for every host. Claude can add thin native discovery adapters, hooks, and approved marketplace plugins without clobbering user edits. Use for `/dummyindex-equip`, `$dummyindex-equip`, equip this repo, map project tooling, add a Claude specialist, or find a Claude plugin or portable skill."
---

# /dummyindex-equip / $dummyindex-equip — equip the project with a tuned, evolving toolkit

> **Installed from dummyindex `__VERSION__`.** Run `dummyindex --version` to confirm the CLI matches. If they diverge, diagnose with `dummyindex context check --versions` (it reports which layer is stale). Then run `/dummyindex-update` on Claude or `$dummyindex-update` on Codex to bring the CLI, skills, and repo wiring back into sync. The update skill is non-destructive on a curated `.context/`. Do not use a blunt `dummyindex install` to "fix" a version skew.

## Shared preparation and use

Every host prepares, uses, verifies, and learns from the same capabilities in
`.context/equipment.json`. Generated bodies live at
`.context/equipment/<name>.md`. Each generated body is the editable,
hash-baselined source. A preserved legacy entry can still name another path.
Read that exact manifest path as data, without a need for its native agent to
be installed.

1. Read `.context/HOW_TO_USE.md`, relevant features and conventions, then
   preview `dummyindex context equip --dry-run`.
2. Prepare the project capabilities:
   ```bash
   dummyindex context equip apply [--for-proposal <slug>] [--root <repo>]
   ```
   The same command works on the portable host path (Codex and similar hosts).
   Claude Code adds `--platform claude` to prepare optional native discovery
   references and formatter hooks. `--platform both` also requests these native
   extras. Ordinary preparation creates no new Claude setup. An existing
   pristine legacy helper can become a reference, and edited/evolved files stay put.
3. Read the selected capability's `path` from the manifest and include its
   full mandate in the native subagent prompt. Use a callable exact-fit agent
   when one is available. Otherwise use a native implementation, exploration or
   general-purpose subagent. A missing native adapter never blocks the work.
4. Pass the task, bounded scope, relevant grounding, verification expectations,
   and any policies selected in this session to every delegate.
   Ponytail applies by default when exposed. When its Claude plugin hooks are
   active in this session, its `SubagentStart` hook already injects it into
   each subagent. Do not paste it again.

   Otherwise pass its loaded mandate unless the user turned it off this
   session. Never silently install it. Native names and tool syntax are
   adapters, not a second implementation of the capability.
5. Verify actual work with the project's checks. Persist a durable lesson
   through `equip patch`, which updates the canonical body's hash and version.
   Rule: never teach by editing a native pointer or bypassing the ownership
   lifecycle.

The toolkit retains implementer, tester, reviewer, verify and every grounded
template-backed specialist, plus adopted capabilities. Its existing refresh,
reset, patch, remove, uninstall and plugin operations remain available.

## Generated vs adopted

- **GENERATED specialist** — `.context/equipment/<proj>-<cap>-specialist.md` with the `<!-- dummyindex:generated -->` marker and a `version` + `origin_hash` + `grounded_in` manifest record. Editable, refreshable, lifecycle-managed. Produced where a template backs: **db / security / performance / docs / search / frontend / api / migration / ci**. Only frontend/api/migration/ci yield `<proj>-<cap>-procedure` and `-domain` specialists. The db/security/performance/docs/search capabilities yield one `<proj>-<cap>-specialist`. `dimension`-less manifests stay valid.
- **ADOPTED specialist** — manifest-only pointer (`"path": ""`, `"source": "installed"`, no `origin_hash`) to a project or registry agent. No file is written. Produced for a capability no template backs.

A capability a project agent already covers is **adopted, not regenerated**. An explicit `add-specialist` always **generates**.

## Safety framing (state this to the user)

- **Never clobber.** A pre-existing **user** file at a target path is **skipped,
  not overwritten** (and the skip is reported). Generated files carry a
  `<!-- dummyindex:generated -->` marker, but the **origin-hash is the
  authority**. Once you hand-edit a generated file, it becomes **USER_MODIFIED**
  and is **preserved forever**. `refresh` skips it, re-apply preserves it,
  and `uninstall` keeps it.
- **Settings are preserve-or-refuse.** Equip adds the format hook additively
  under our `DUMMYINDEX_EQUIP` sentinel. Your other hooks (including
  dummyindex's own `DUMMYINDEX_AUTO_REFRESH` SessionStart entry) stay
  untouched. An unparseable `settings.json` is **left alone**. Equip skips and
  reports the hook, and the files still land.
- **Status / dry-run FIRST.** Never run `refresh`, `patch`, or `uninstall`
  before you first show the user what it will touch. Show it with
  `equip status`, then with the `--dry-run` of the verb. Show the patch intent
  (the old→new diff) before you apply it.
- **No-arg is help, never apply.** A bare `dummyindex context equip` prints
  usage and exits 2. It never mutates. `apply` is the explicit write verb.
  `equip --dry-run` is the only read-only verbless form. So a probe of equip to
  see what it does is always safe.

## The lifecycle (verbs)

**Always start read-only**, then act:

1. **Preview & apply.** `apply` is an **explicit verb**. Equip treats a bare
   `dummyindex context equip` (no verb, no flags) as a help probe. It prints
   usage, exits 2, and **writes nothing**. Always pass the verb (or run
   `--dry-run` to preview):
   ```bash
   dummyindex context equip --dry-run     # prints the plan; writes nothing (verbless OK — read-only)
   dummyindex context equip apply         # shared bodies + manifest
   ```
   `apply` refuses (exit 1) on a repo with no `.context/`. Equip renders FROM
   the index, so run `dummyindex ingest` first.

   Scope to a planned change with `--for-proposal <slug>`. Equip reads the
   `plan.md` and `checklist.md` of that proposal and covers each demanded
   capability. It **generates** a specialist file when a template backs the
   capability. Templates exist for db / security / performance / docs / search /
   frontend / api / migration / ci, including RLS / tenant-isolation signals
   that map to security. It **adopts** a specialist (manifest-only) when no
   template exists. Add `--json` to parse the result.

2. **Force a specialist explicitly** (equip generates all of them by default).
   This pins the order and identity of one specialist. It is also how equip
   carries a pre-existing specialist forward.
   ```bash
   dummyindex context equip add-specialist <capability>     # db|security|performance|docs|search|frontend|api|migration|ci
   dummyindex context equip apply --specialist <capability>  # same, as a flag on apply
   ```
   The command writes a grounded, editable `<proj>-<capability>-specialist`
   agent and tracks it like the core four. It is idempotent and additive. A plain
   `equip apply` re-run afterward **preserves** it (it never silently drops a
   specialist you added). Equip rejects an unknown capability (no template) and
   lists the valid ones. Adoption covers it on a `--for-proposal` run instead.

3. **Inspect what you own.**
   ```bash
   dummyindex context equip status [--json]
   ```
   The command classifies every generated item, the core four **and** any
   generated specialist. The classes are **pristine** (ours, safe to evolve),
   **user-modified** (yours now, skipped forever), and **missing**. Run this
   before any mutating verb.

4. **Refresh — pull template improvements into PRISTINE items only.**
   ```bash
   dummyindex context equip refresh --dry-run   # show what would change
   dummyindex context equip refresh             # re-render PRISTINE-and-stale, minor-bump
   ```
   Equip never touches USER_MODIFIED items. Show the dry-run before you apply it.

5. **Reset — the escape hatch for one item.**
   ```bash
   dummyindex context equip reset <NAME>        # restore its pristine render, re-baseline
   ```
   Use when the user explicitly wants a hand-edited tool returned to the
   generated baseline. Confirm intent first — this overwrites their edit.

6. **Patch — sanctioned evolution (stays PRISTINE).**
   ```bash
   dummyindex context equip patch --item <NAME> --from-file patch.json
   ```
   `patch.json` is `{"old": "...", "new": "..."}`. `old` must match **exactly
   once**. When you apply it, the patch re-baselines the origin-hash and
   patch-bumps the version. So the tool stays ours (unlike a hand edit). **Show
   the user the old→new intent before you apply it.**

7. **Uninstall — remove only what is ours.**
   ```bash
   dummyindex context equip uninstall --dry-run
   dummyindex context equip uninstall
   ```
   The command deletes PRISTINE generated files, our `DUMMYINDEX_EQUIP` hook,
   and the manifest. It keeps USER_MODIFIED files and user hooks and reports
   them. It also **disables any plugins** that equip enabled (and drops their
   marketplaces) from `settings.json`. It removes **PRISTINE vendored** files.
   It keeps a hand-edited vendored copy, like any USER_MODIFIED item.

8. **Reuse from the library.** Specialists and `EXPERIENCE.md` lessons live in `.context/equipment/library/<capability_id>/`. `library.json` tracks them (outside `equipment.json`). Status is `ok|needs-reverify`. A changed `origin_hash` or grounding hash, a deleted grounding path, or a missing entry means `needs-reverify`.
   ```bash
   dummyindex context equip reuse <capability_id> [--force]
   ```
   The command copies the body. It refuses to overwrite a locally edited target unless `--force`.

## Plugin manager (discover + install; Claude Code only)

Equip is also a native Claude **plugin manager**. It finds
agents/skills/plugins from
the known marketplaces (`anthropics/claude-plugins-official`,
`…-community`, `knowledge-work-plugins`, plus community sources) and from a
GitHub search. Then it wires the ones you approve.

This marketplace wiring is Claude-only. Codex-native plugin or skill
installation is outside `$dummyindex-equip` and is not tracked by this
equipment lifecycle.

```bash
dummyindex context equip discover                 # auto: match detected stack capabilities
dummyindex context equip discover "postgres perf" # query: search seeds + GitHub
dummyindex context equip install <plugin>@<marketplace> [--yes] [--scope project|local|user]
```

Before `equip apply --source`, follow [sourcing.md](sourcing.md).

### Two discovery channels (know which you're reaching for)

Two ecosystems. Use both, keep them straight:

- **Channel A — Claude plugin marketplaces** (`equip discover` / `equip
  install`, above). Plugins are wired **natively** into `.claude/settings.json`
  (or vendored), recorded in `.context/equipment.json`, and lifecycle-managed by
  equip (`status` / `refresh` / `uninstall`). This is the channel for
  hooks / MCP / commands and anything you want tracked in the repo.
- **Channel B — the open agent-skills ecosystem** (`npx skills`, backed by
  **https://skills.sh/**). This is the package manager for portable *agent
  skills* — the same kind of skill file as `dummyindex/skills/*/SKILL.md`. Skills
  are **inert** (instructions, not code). Verify the result under Claude's
  `.claude/skills` directory. Reach for this channel when the
  need is a **skill** rather than a packaged plugin. A skill is a reusable
  workflow / knowledge pack (design, testing, changelogs, PR review).

The flow below applies to **both**. The only differences are the search/install
commands and the quality signal (marketplace trust tier vs. skills.sh install
count). Prefer Channel A when you want repo-committed, lifecycle-tracked wiring.
Prefer Channel B when a popular, battle-tested skill already covers the task.

### The skills.sh ecosystem (`npx skills`)

`npx skills` is the CLI for the open agent-skills ecosystem. Browse the catalog
and its **install-ranked leaderboard** at **https://skills.sh/**.

```bash
npx skills find [query]              # search interactively or by keyword
npx skills add <owner/repo@skill>    # install a skill (add -g for user-level, -y to skip prompts)
npx skills check                     # check installed skills for updates
npx skills update                    # update all installed skills
npx skills init <name>               # scaffold a brand-new skill
```

- **Leaderboard first.** Before a keyword search, check https://skills.sh/ — it
  ranks skills by total installs, surfacing the battle-tested ones. Popular,
  high-trust sources include `vercel-labs/agent-skills` (React / Next.js / web
  design) and `anthropics/skills` (frontend design, document processing).
- **Search by keyword:** `npx skills find react performance`,
  `npx skills find pr review`, `npx skills find changelog`. Specific beats vague
  — `"react testing"` over `"testing"`.
- **Install for the user (only after they approve and you have vetted it):**
  ```bash
  npx skills add <owner/repo@skill> -g -y    # -g = user-level, -y = no prompt
  ```

### How to help the user find a plugin or skill (the flow)

Do not jump straight to a raw `discover` dump. Work the request front-to-back.
Each step narrows what you search for and what you will recommend. It
applies to both channels. Pick the channel in Step 3.

**Step 1 — Understand what they need.** Before searching, pin down three things:

1. the **domain** (e.g. database, testing, deployment, docs, search),
2. the **specific task** (e.g. "write Postgres migrations", "review PRs",
   "generate a changelog"),
3. whether it is **common enough that a plugin likely exists**. A niche,
   repo-specific need usually suits a generated specialist (see
   *When nothing matches* below) better than a marketplace hunt.

If the ask is vague ("help me with the database"), ask one clarifying question
before you spend a search.

**Step 2 — Check the popular/trusted sources first.** Both channels have a
"leaderboard" — start there before a broad search:

- *Channel A:* the Anthropic-official seed marketplaces are battle-tested,
  **trusted**-tier, and install without the extra approval gate. Start with an
  auto `discover` (stack-matched) or a focused query. A trusted candidate that
  covers the need is almost always the right answer.
- *Channel B:* check the **https://skills.sh/ leaderboard**, which ranks skills
  by total installs. A skill with 100K+ installs from `vercel-labs/agent-skills`
  or `anthropics/skills` is a safer bet than a novel GitHub result.

Prefer a popular/trusted hit over a higher-novelty match before you widen the net.

**Step 3 — Search the right channel.** For a **plugin** (Channel A), run the
verb. Auto mode (no query) matches the capabilities of the detected stack. A query
searches the seed catalogs **and** GitHub. For a **skill** (Channel B), use
`npx skills find`:

```bash
dummyindex context equip discover                  # A: stack-matched
dummyindex context equip discover "postgres migrations"
dummyindex context equip discover "pr review" --json   # A: parse the ranked plan
npx skills find "pr review"                         # B: skills.sh + leaderboard
```

Query tips that change the results:

- **Be specific** — `"react testing"` beats `"testing"`. The score is
  `2·(capability overlap) + (query-token hits)`, so concrete tokens rank better.
- **Try alternative terms** — if `"deploy"` is thin, try `"deployment"` or
  `"ci"`. Capability inference is token-based.
- **Name a low-profile repo directly.** Use this when you know the plugin lives
  somewhere that `gh search` does not surface. Add `--repo <owner>/<name>`
  instead of guessing queries.

**Step 4 — Verify quality BEFORE you recommend.** A high rank is *not* a
recommendation. `discover` ranks by keyword/capability overlap, not by quality —
vet every candidate against these before you present it:

1. **Trust tier** — `trusted` (Anthropic-official seed) vs `untrusted`
   (everything else, including all GitHub-discovered repos). Prefer trusted.
2. **Blast radius** — does it **run code** (`hook` / `mcp` / `lsp` / `bin`) or is
   it **inert** (`agent` / `skill` / `command`)? A code-running plugin from an
   untrusted source is `⚠ requires --yes` and demands real scrutiny.
3. **Source reputation** — for any **untrusted** GitHub-discovered candidate,
   inspect the repo before you recommend it:
   `gh repo view <owner>/<name>`. Treat low stars / no recent activity / no
   README with skepticism.
4. **Install count (Channel B / skills.sh)** — prefer skills with **1K+
   installs**. Be cautious with anything under 100. Official sources
   (`vercel-labs`, `anthropics`, `microsoft`) outrank unknown authors. This is
   the skills.sh analog of the marketplace trust tier.
5. **Capability fit** — does its `covers:` line (or skill description)
   match the task from Step 1? Or did it match only on an incidental keyword?

If a candidate fails these, **do not surface it**. Say you found matches but
none you would trust, and fall through to *When nothing matches*.

**Step 5 — Present the options clearly.** For each plugin you would recommend,
give the user a consistent picture. Include its name, what it does, its source
and trust, its blast radius, and the exact install command. For example:

```
Found a strong match:

• postgres-toolkit@claude-plugins-official  (trusted)
  Postgres migration + query-review skills from Anthropic.
  Blast radius: skill, command (inert — no code runs).
  Install:  dummyindex context equip install postgres-toolkit@claude-plugins-official

One untrusted alternative (db-helpers@some-community, ⚠ runs an mcp server,
repo has 30 stars) — I'd skip it unless you specifically want its features.
```

**Step 6 — Offer to install.** If the user wants one:

- *Channel A (plugin):* **do not wire it on assumptions**. Run the usage
  interview below first, then `equip install`. This turns a discovery into a
  committed, lifecycle-tracked tool.
- *Channel B (skill):* once they approve, install it with
  `npx skills add <owner/repo@skill> -g -y` (`-g` user-level, `-y` no prompt).

### The mechanics (how discover + install behave)

- **`discover` is always a dry-run.** It prints a **ranked plan** and, for each
  candidate, its **blast radius** and its trust tier. The blast radius is the
  surfaces it declares. The surfaces `hook` / `mcp` / `lsp` / `bin` run code.
  The surfaces `agent` / `skill` / `command` are inert. It writes nothing.
- **Tiered trust.** Anthropic-official marketplaces are **trusted**. Everything
  else is **untrusted**. A candidate that **runs code** from an **untrusted**
  source is flagged `⚠ requires --yes` and `install` refuses it without `--yes`.
  Inert or trusted candidates install without the extra gate. **Never enable a
  code-running plugin before you first show the user its blast radius.**
- **Hybrid wiring.** Equip enables a packaged marketplace plugin **natively**.
  It adds the plugin to `extraKnownMarketplaces` + `enabledPlugins` in
  `.claude/settings.json` (scope `project` by default, committed for the team).
  A loose skill from a **collection** (such as `anthropics/skills`,
  `vercel-labs/agent-skills`) is **vendored**. `discover` now enumerates each
  collection's skills as candidates. `install <skill>@<collection>` fetches
  the `SKILL.md` of the skill **at a pinned commit sha**.

  Equip resolves the sha from HEAD at install time, never from a moving ref.
  It stamps the skill with `<!-- dummyindex:installed -->`. It writes the skill
  to `.claude/skills/<name>/SKILL.md` under the never-clobber guard. The guard
  refuses a user's own file at that path. Equip re-vendors only our own
  **unedited** vendored copy. The same origin-hash oracle also refuses a
  hand-edited copy, so a re-`install` never silently discards your edit.

  The skill is then lifecycle-managed by origin-hash exactly like a generated
  file. `status` / `uninstall` cover it. Equip freezes a hand-edited vendored
  copy as USER_MODIFIED and never re-fetches it. Run `uninstall` first to
  re-vendor at a fresh pin. The trust gate is identical to native. An
  **untrusted** collection still needs `--yes` and a usage doc.
- Equip records every install in `.context/equipment.json`. The record has its
  upstream origin (marketplace + repo + ref) and its mechanism. So `status` /
  `uninstall` cover marketplace and vendored items alongside the generated ones.

### When nothing matches (fall back gracefully)

A `discover` run can return nothing, or return only candidates that failed the
Step 4 quality gate. This is a normal outcome, not a dead end:

1. **Say so plainly** — "I searched the marketplaces + GitHub for X and found no
   plugin I would trust for it."
2. **Offer to cover it yourself.** If a template backs the capability
   (db / security / performance / docs / search), generate a project-tuned
   specialist instead. It is grounded in *this* repo's `.context/` and is the
   better answer for a repo-specific need:
   ```bash
   dummyindex context equip add-specialist <capability>
   ```
3. **Otherwise** the generic implementer/reviewer handles it, or you do the task
   directly. Do not invent a plugin that does not exist. Do not lower the
   Step 4 bar to force a match.
4. **If it is a recurring need with no existing skill**, offer to scaffold a new
   one for the user. Do it with `npx skills init <name>` (Channel B). The result
   is a portable skill that they can refine and, later, publish.

### Usage interview (required before an install is "done")

A plugin equip is **not complete** until you have captured *how it is used in
this repo*. Never wire one on assumptions. After `discover` shows the blast
radius and before `install`, interview the user **one question at a time**:

1. **Purpose here** — what is this plugin for in *this* repo specifically?
2. **When to use** — which tasks or signals should activate its skills/agents/commands?
3. **When NOT to use** — where should it stay out of the way?
4. **Constraints / guardrails** — scopes, side effects, data it touches.
5. **Scope** — `project` (default, committed) / `local` / `user`?

Write the answers to `.context/equipment/<plugin>.md` with this template:

```markdown
# <plugin> — usage in this repo

**Source:** <plugin>@<marketplace> (<owner/repo>)
**Scope:** project | local | user

## Purpose here
…

## When to use
…

## When NOT to use
…

## Constraints & guardrails
…
```

Then install and pass the playbook:

```bash
dummyindex context equip install <plugin>@<marketplace> [--repo <owner>/<name>] \
  [--yes] --scope <scope> --usage-doc .context/equipment/<plugin>.md
```

`--usage-doc` records the playbook in the manifest's `grounded_in`. For automation
only, `--skip-usage-doc` opts out — a plugin with no playbook shows **incomplete**
in `equip status`. Use `--repo <owner>/<name>` when the marketplace lives in a
low-profile repo that `discover` (seed list + GitHub search) does not surface.

## Discipline (spec-led)

- **Read `.context/HOW_TO_USE.md` first** — the generated tools are grounded in
  it and in `.context/conventions/`. If `.context/` is absent, tell the user to
  run `/dummyindex` first. Equip has nothing to ground against without it.
- When `.context/` disagrees with the code, **the code wins** — flag the drift.
- Do not gold-plate. The catalog decides the set. A bigger toolkit is a separate
  ask. A generated specialist backed by a real, grounded `.context/` capability
  template is **not** speculative. It is the right answer for db / security /
  performance / docs / search.

  What stays forbidden is **un-grounded, no-evidence generation**. Equip never
  invents a template for a capability with no template and no `.context/`
  grounding. That gap falls to a manifest-only adoption or the generic
  implementer.

## Checklist (verify before claiming done)

- [ ] `dummyindex context equip --dry-run` (or `status`) was shown first.
- [ ] The implementer + tester + reviewer agents and the verify skill were
      prepared under `.context/equipment/` additively. Or a target was skipped because a
      user / USER_MODIFIED file sat there, and this was reported.
- [ ] If native Claude extras were requested, the format hook was wired
      under `DUMMYINDEX_EQUIP` when a formatter was detected. This left user hooks and the managed
      session-hook entries (`DUMMYINDEX_AUTO_REFRESH` sentinel) undisturbed.
- [ ] Any requested specialist was **generated** (a file with the marker +
      `version`/`origin_hash`/`grounded_in`) when a template backs it. Or it was
      **adopted** (manifest-only, `"path": ""`) when none does. You told the
      user which.
- [ ] `.context/equipment.json` (schema v4) lists each tool with `capabilities`,
      `grounded_in`, and — for generated agents (core four **and** specialists) —
      `subagent_type` / `version` / `origin_hash`.
- [ ] Before any `refresh` / `patch` / `reset` / `uninstall`, the intent
      (dry-run output or the patch's old→new) was shown to the user.
- [ ] Each plugin install captured a usage playbook at `.context/equipment/<plugin>.md`
      recorded in `grounded_in` (or was explicitly `--skip-usage-doc`). `equip status`
      shows no unintended `incomplete` plugins.
