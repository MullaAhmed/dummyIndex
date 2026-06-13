---
name: dummyindex-equip
description: Render and EVOLVE a project-tuned Claude Code toolkit from this repo's `.context/` spine — stack implementer + tester + reviewer agents and a verify skill, grounded in the project's own conventions, plus generated capability SPECIALISTS (db / security / performance / docs / search), a PostToolUse formatter hook wired into settings.json, and registry/project specialists adopted to cover gaps a template doesn't. Also a Claude PLUGIN MANAGER — `discover` searches the marketplaces + GitHub for plugins that fill detected gaps (or match a query) and `install` wires them natively into `.claude/settings.json`, gated by tiered trust + blast-radius disclosure. Hash-baselined lifecycle (status / refresh / reset / uninstall) and a sanctioned patch seam mean generated tools improve over time without ever clobbering a user edit. Triggers — `/dummyindex-equip`, "equip the project", "equip this repo", "build tooling for this repo", "add a database/security specialist", "find a plugin", "find a plugin/skill for X", "is there a plugin for X", "how do I do X" (when a plugin might exist), "install a plugin", "search the marketplace".
allowed-tools: Read, Write, Bash
---

# /dummyindex-equip — equip the project with a tuned, evolving toolkit

> **Installed from dummyindex `__VERSION__`.** Run `dummyindex --version` to confirm the CLI matches. If they diverge, diagnose with `dummyindex context check --versions` (it reports which layer is stale), then run `/dummyindex-update` to bring the CLI, skills, and this repo's wiring back into sync — `/dummyindex-update` is non-destructive on a curated `.context/`. Don't reach for a blunt `dummyindex install` to "fix" a version skew.

You turn this repo's generated `.context/` spine into a small set of Claude Code
tools tuned to *this* project, each grounded in the repo's real conventions so
they consult the spine at runtime instead of inventing patterns:

- a **`<stack>-implementer`** agent and a **`<stack>-tester`** agent,
- a **`<proj>-reviewer`** agent (grounded in `.context/conventions/` + feature `concerns.md`),
- a **`<proj>-verify`** skill (embeds the project's test/lint/typecheck commands),
- a **PostToolUse format hook** wired into `.claude/settings.json` when a formatter is detected,
- on demand, a **generated capability specialist** — `<proj>-db-specialist`,
  `<proj>-security-specialist`, `<proj>-performance-specialist`,
  `<proj>-docs-specialist`, `<proj>-search-specialist` — a real, editable,
  hash-tracked file grounded in the matching `.context/` docs,
- plus any **adopted specialists** (project agents under `.claude/agents/`, or
  known-registry agents like *Frontend Developer*) that cover a capability **no
  template backs** — recorded in the manifest only, never written as files.

All of this is **codified policy**, not free-form generation: deterministic Python
decides what to detect, generate, adopt, and wire. You drive the CLI and present
the result; you do not hand-author agents here.

## Generated vs adopted (the distinction that matters)

Two ways equip can cover a capability — know which you're getting:

- **GENERATED specialist** — a `.claude/agents/<proj>-<cap>-specialist.md` file
  equip writes, carrying the `<!-- dummyindex:generated -->` marker and a
  `version` + `origin_hash` + `grounded_in` record in the manifest. It is
  **editable, refreshable, and fully lifecycle-managed** — exactly like the four
  core tools. Produced for capabilities a template backs: **db / security /
  performance / docs / search**.
- **ADOPTED specialist** — a manifest-only pointer (`"path": ""`,
  `"source": "installed"`, no `origin_hash`) at a project agent you already have
  or a built-in registry agent (e.g. *Frontend Developer*). **No file is
  written**; equip just records the dispatch target. Produced for a capability
  **no template backs** (frontend, or anything outside the template family).

A capability you already cover with a project agent is **adopted, not
regenerated** (it's not a gap). An explicit `add-specialist` request always
**generates** — that's how you turn a manifest pointer into a real, editable
file.

## Safety framing (state this to the user)

- **Never clobber.** A pre-existing **user** file at a target path is **skipped,
  not overwritten** (and the skip is reported). Generated files carry a
  `<!-- dummyindex:generated -->` marker, but the **origin-hash is the
  authority**: once you hand-edit a generated file it becomes **USER_MODIFIED**
  and is **preserved forever** — `refresh` skips it, re-apply preserves it,
  `uninstall` keeps it.
- **Settings are preserve-or-refuse.** The format hook is added additively under
  our `DUMMYINDEX_EQUIP` sentinel; your other hooks (including dummyindex's own
  `DUMMYINDEX_AUTO_REFRESH` SessionStart entry) are untouched. An unparseable
  `settings.json` is **left alone** — the hook is skipped and reported, files
  still land.
- **Status / dry-run FIRST.** Never run `refresh`, `patch`, or `uninstall`
  without first showing the user what it will touch (`equip status`, then the
  `--dry-run` of the verb). Show patch intent (the old→new diff) before applying.
- **No-arg is help, never apply.** A bare `dummyindex context equip` prints
  usage and exits 2 — it never mutates. `apply` is the explicit write verb;
  `equip --dry-run` is the only read-only verbless form. So probing equip to see
  what it does is always safe.

## The lifecycle (verbs)

**Always start read-only**, then act:

1. **Preview & apply.** `apply` is an **explicit verb** — a bare
   `dummyindex context equip` (no verb, no flags) is treated as a help probe:
   it prints usage and exits 2 **without writing anything**. Always pass the
   verb (or run `--dry-run` to preview):
   ```bash
   dummyindex context equip --dry-run     # prints the plan; writes nothing (verbless OK — read-only)
   dummyindex context equip apply         # apply: files + settings hook + manifest
   ```
   `apply` refuses (exit 1) on a repo with no `.context/` — equip renders FROM
   the index, so run `dummyindex ingest` first.
   Scope to a planned change with `--for-proposal <slug>` — equip reads that
   proposal's `plan.md`/`checklist.md` and covers each demanded capability: it
   **generates** a specialist file when a template backs the capability
   (db / security / performance / docs / search — including RLS / tenant-isolation
   signals that map to security), or **adopts** one (manifest-only) when no
   template exists (e.g. frontend → *Frontend Developer*). Add `--json` to parse
   the result.

2. **Add a specialist on demand.**
   ```bash
   dummyindex context equip add-specialist <capability>     # db|security|performance|docs|search
   dummyindex context equip apply --specialist <capability>  # same, as a flag on apply
   ```
   Writes a grounded, editable `<proj>-<capability>-specialist` agent and tracks
   it like the core four. Idempotent and additive — a plain `equip apply` re-run
   afterward **preserves** it (never silently drops a specialist you added). An
   unknown capability (no template, e.g. `frontend`) is rejected with the list of
   valid ones — that capability is covered by adoption on a `--for-proposal` run
   instead.

3. **Inspect what you own.**
   ```bash
   dummyindex context equip status [--json]
   ```
   Classifies every generated item — core four **and** any generated specialist:
   **pristine** (ours, safe to evolve), **user-modified** (yours now, skipped
   forever), **missing**. Run this before any mutating verb.

4. **Refresh — pull template improvements into PRISTINE items only.**
   ```bash
   dummyindex context equip refresh --dry-run   # show what would change
   dummyindex context equip refresh             # re-render PRISTINE-and-stale, minor-bump
   ```
   USER_MODIFIED items are never touched. Show the dry-run before applying.

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
   `patch.json` is `{"old": "...", "new": "..."}`; `old` must match **exactly
   once**. Applying it re-baselines the origin-hash and patch-bumps the version,
   so the tool stays ours (unlike a hand edit). **Show the user the old→new
   intent before you apply it.**

7. **Uninstall — remove only what is ours.**
   ```bash
   dummyindex context equip uninstall --dry-run
   dummyindex context equip uninstall
   ```
   Deletes PRISTINE generated files + our `DUMMYINDEX_EQUIP` hook + the manifest.
   USER_MODIFIED files and user hooks are kept and reported. It also **disables
   any plugins** equip enabled (and drops their marketplaces) from
   `settings.json`, and removes **PRISTINE vendored** files (a hand-edited
   vendored copy is kept, like any USER_MODIFIED item).

## Plugin manager (discover + install)

equip is also a Claude **plugin manager**: it finds agents/skills/plugins from
the known marketplaces (`anthropics/claude-plugins-official`,
`…-community`, `knowledge-work-plugins`, plus community sources) and from a
GitHub search, then wires the ones you approve.

```bash
dummyindex context equip discover                 # auto: match detected stack capabilities
dummyindex context equip discover "postgres perf" # query: search seeds + GitHub
dummyindex context equip install <plugin>@<marketplace> [--yes] [--scope project|local|user]
```

### Two discovery channels (know which you're reaching for)

There are **two** ecosystems to discover from — use both, but keep them straight:

- **Channel A — Claude plugin marketplaces** (`equip discover` / `equip
  install`, above). Plugins are wired **natively** into `.claude/settings.json`
  (or vendored), recorded in `.context/equipment.json`, and lifecycle-managed by
  equip (`status` / `refresh` / `uninstall`). This is the channel for
  hooks / MCP / commands and anything you want tracked in the repo.
- **Channel B — the open agent-skills ecosystem** (`npx skills`, backed by
  **https://skills.sh/**). This is the package manager for portable *agent
  skills* — the same kind of skill file as `dummyindex/skills/*/SKILL.md`. Skills
  are **inert** (instructions, not code) and install as `~/.claude/skills/<name>`
  entries. Reach for this channel when the need is a **skill** (a reusable
  workflow / knowledge pack: design, testing, changelogs, PR review) rather than
  a packaged plugin.

The flow below applies to **both** — the only differences are the search/install
commands and the quality signal (marketplace trust tier vs. skills.sh install
count). Prefer Channel A when you want repo-committed, lifecycle-tracked wiring;
prefer Channel B when a popular, battle-tested skill already covers the task.

### The skills.sh ecosystem (`npx skills`)

`npx skills` is the CLI for the open agent-skills ecosystem; browse the catalog
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
- **Install for the user (only after they approve and you've vetted it):**
  ```bash
  npx skills add <owner/repo@skill> -g -y    # -g = user-level, -y = no prompt
  ```

### How to help the user find a plugin or skill (the flow)

Don't jump straight to a raw `discover` dump. Work the request front-to-back —
each step narrows what you search for and what you'll actually recommend. It
applies to both channels; pick the channel in Step 3.

**Step 1 — Understand what they need.** Before searching, pin down three things:

1. the **domain** (e.g. database, testing, deployment, docs, search),
2. the **specific task** (e.g. "write Postgres migrations", "review PRs",
   "generate a changelog"),
3. whether it's **common enough that a plugin likely exists** — a niche,
   repo-specific need is usually better served by a generated specialist (see
   *When nothing matches* below) than by a marketplace hunt.

If the ask is vague ("help me with the database"), ask one clarifying question
before burning a search.

**Step 2 — Check the popular/trusted sources first.** Both channels have a
"leaderboard" — start there before a broad search:

- *Channel A:* the Anthropic-official seed marketplaces are battle-tested,
  **trusted**-tier, and install without the extra approval gate. Start with an
  auto `discover` (stack-matched) or a focused query — a trusted candidate that
  covers the need is almost always the right answer.
- *Channel B:* check the **https://skills.sh/ leaderboard**, which ranks skills
  by total installs. A skill with 100K+ installs from `vercel-labs/agent-skills`
  or `anthropics/skills` is a safer bet than a novel GitHub result.

Prefer a popular/trusted hit over a higher-novelty match before widening the net.

**Step 3 — Search the right channel.** For a **plugin** (Channel A), run the
verb — auto mode (no query) matches the detected stack's capabilities; a query
searches the seed catalogs **and** GitHub. For a **skill** (Channel B), use
`npx skills find`:

```bash
dummyindex context equip discover                  # A: stack-matched
dummyindex context equip discover "postgres migrations"
dummyindex context equip discover "pr review" --json   # A: parse the ranked plan
npx skills find "pr review"                         # B: skills.sh + leaderboard
```

Query tips that change the results:

- **Be specific** — `"react testing"` beats `"testing"`; the score is
  `2·(capability overlap) + (query-token hits)`, so concrete tokens rank better.
- **Try alternative terms** — if `"deploy"` is thin, try `"deployment"` or
  `"ci"`. Capability inference is token-based.
- **Name a low-profile repo directly** — if you know the plugin lives somewhere
  `gh search` won't surface, add `--repo <owner>/<name>` instead of guessing
  queries.

**Step 4 — Verify quality BEFORE you recommend.** A high rank is *not* a
recommendation. `discover` ranks by keyword/capability overlap, not by quality —
vet every candidate against these before you present it:

1. **Trust tier** — `trusted` (Anthropic-official seed) vs `untrusted`
   (everything else, including all GitHub-discovered repos). Prefer trusted.
2. **Blast radius** — does it **run code** (`hook` / `mcp` / `lsp` / `bin`) or is
   it **inert** (`agent` / `skill` / `command`)? A code-running plugin from an
   untrusted source is `⚠ requires --yes` and demands real scrutiny.
3. **Source reputation** — for any **untrusted** GitHub-discovered candidate,
   actually look at the repo before recommending it:
   `gh repo view <owner>/<name>` — treat low stars / no recent activity / no
   README with skepticism.
4. **Install count (Channel B / skills.sh)** — prefer skills with **1K+
   installs**; be cautious with anything under 100. Official sources
   (`vercel-labs`, `anthropics`, `microsoft`) outrank unknown authors. This is
   the skills.sh analog of the marketplace trust tier.
5. **Capability fit** — does its `covers:` line (or skill description) actually
   match the task from Step 1, or did it only match on an incidental keyword?

If a candidate fails these, **don't surface it** — say you found matches but
none you'd trust, and fall through to *When nothing matches*.

**Step 5 — Present the options clearly.** For each plugin you'd recommend, give
the user a consistent picture — name, what it does, where it's from + trust,
blast radius, and the exact install command. For example:

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

- *Channel A (plugin):* **don't wire it on assumptions** — run the usage
  interview below first, then `equip install`. This turns a discovery into a
  committed, lifecycle-tracked tool.
- *Channel B (skill):* once they approve, install it with
  `npx skills add <owner/repo@skill> -g -y` (`-g` user-level, `-y` no prompt).

### The mechanics (how discover + install behave)

- **`discover` is always a dry-run.** It prints a **ranked plan** and, for each
  candidate, its **blast radius** — the surfaces it declares (`hook` / `mcp` /
  `lsp` / `bin` run code; `agent` / `skill` / `command` are inert) and its trust
  tier. It writes nothing.
- **Tiered trust.** Anthropic-official marketplaces are **trusted**; everything
  else is **untrusted**. A candidate that **runs code** from an **untrusted**
  source is flagged `⚠ requires --yes` and `install` refuses it without `--yes`.
  Inert or trusted candidates install without the extra gate. **Never enable a
  code-running plugin without showing the user its blast radius first.**
- **Hybrid wiring.** A packaged marketplace plugin is enabled **natively** —
  equip adds it to `extraKnownMarketplaces` + `enabledPlugins` in
  `.claude/settings.json` (scope `project` by default, committed for the team).
  A loose agent/skill from a collection is **vendored** — copied into
  `.claude/` with the `<!-- dummyindex:installed -->` marker and an origin-hash,
  so it is lifecycle-managed like a generated file. *(Vendored-collection
  discovery — auto-surfacing loose agents/skills — is the next slice; the native
  path and the vendoring + lifecycle machinery ship now.)*
- Every install is recorded in `.context/equipment.json` with its upstream
  origin (marketplace + repo + ref) and mechanism, so `status` / `uninstall`
  cover marketplace and vendored items alongside the generated ones.

### When nothing matches (fall back gracefully)

A `discover` that returns nothing — or returns only candidates that failed the
Step 4 quality gate — is a normal outcome, not a dead end:

1. **Say so plainly** — "I searched the marketplaces + GitHub for X and found no
   plugin I'd trust for it."
2. **Offer to cover it yourself.** If a template backs the capability
   (db / security / performance / docs / search), generate a project-tuned
   specialist instead — it's grounded in *this* repo's `.context/` and is the
   better answer for a repo-specific need:
   ```bash
   dummyindex context equip add-specialist <capability>
   ```
3. **Otherwise** the generic implementer/reviewer handles it, or you do the task
   directly. Don't invent a plugin that doesn't exist, and don't lower the Step 4
   bar to force a match.
4. **If it's a recurring need with no existing skill**, offer to scaffold a new
   one for the user with `npx skills init <name>` (Channel B) — a portable skill
   they can refine and, later, publish.

### Usage interview (required before an install is "done")

A plugin equip is **not complete** until you've captured *how it's used in this
repo* — never wire one on assumptions. After `discover` shows the blast radius
and before `install`, interview the user **one question at a time**:

1. **Purpose here** — what is this plugin for in *this* repo specifically?
2. **When to use** — which tasks or signals should activate its skills/agents/commands?
3. **When NOT to use** — where should it stay out of the way?
4. **Constraints / guardrails** — scopes, side effects, data it touches.
5. **Scope** — `project` (default, committed) / `local` / `user`?

Write the answers to `.context/equipment/<plugin>.md` using this template:

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

Then install, passing the playbook:

```bash
dummyindex context equip install <plugin>@<marketplace> [--repo <owner>/<name>] \
  [--yes] --scope <scope> --usage-doc .context/equipment/<plugin>.md
```

`--usage-doc` records the playbook in the manifest's `grounded_in`. For automation
only, `--skip-usage-doc` opts out — a plugin with no playbook shows **incomplete**
in `equip status`. Use `--repo <owner>/<name>` when the marketplace lives in a
low-profile repo that `discover` (seed list + GitHub search) doesn't surface.

## Discipline (spec-led)

- **Read `.context/HOW_TO_USE.md` first** — the generated tools are grounded in
  it and in `.context/conventions/`. If `.context/` is absent, tell the user to
  run `/dummyindex` first; equip has nothing to ground against without it.
- When `.context/` disagrees with the code, **the code wins** — flag the drift.
- Don't gold-plate. The catalog decides the set; a bigger toolkit is a separate
  ask. A generated specialist backed by a real, grounded `.context/` capability
  template is **not** speculative — it is the right answer for db / security /
  performance / docs / search. What stays forbidden is **un-grounded, no-evidence
  generation**: equip never invents a template for a capability with no template
  and no `.context/` grounding — that gap falls to a manifest-only adoption or the
  generic implementer.

## Checklist (verify before claiming done)

- [ ] `dummyindex context equip --dry-run` (or `status`) was shown first.
- [ ] The implementer + tester + reviewer agents and the verify skill were
      written under `.claude/` additively (or a target was skipped because a
      user / USER_MODIFIED file sat there — reported).
- [ ] The format hook was wired under `DUMMYINDEX_EQUIP` (when a formatter was
      detected) without disturbing user hooks or the managed session-hook entries (`DUMMYINDEX_AUTO_REFRESH` sentinel).
- [ ] Any requested specialist was **generated** (a file with the marker +
      `version`/`origin_hash`/`grounded_in`) when a template backs it, or
      **adopted** (manifest-only, `"path": ""`) when none does — and you told the
      user which.
- [ ] `.context/equipment.json` (schema v3) lists each tool with `capabilities`,
      `grounded_in`, and — for generated agents (core four **and** specialists) —
      `subagent_type` / `version` / `origin_hash`.
- [ ] Before any `refresh` / `patch` / `reset` / `uninstall`, the intent
      (dry-run output or the patch's old→new) was shown to the user.
- [ ] Each plugin install captured a usage playbook at `.context/equipment/<plugin>.md`
      recorded in `grounded_in` (or was explicitly `--skip-usage-doc`); `equip status`
      shows no unintended `incomplete` plugins.
