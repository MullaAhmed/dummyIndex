<p align="center">
  <a href="https://github.com/MullaAhmed/dummyindex"><img src="https://raw.githubusercontent.com/MullaAhmed/dummyIndex/refs/heads/main/docs/logo-text.svg" width="260" alt="dummyIndex"/></a>
</p>

# dummyindex

The persistent context engine for a repo. A Claude Code skill that turns any codebase into a `.context/` folder Claude can navigate without grepping — deterministic AST extraction plus a multi-agent council (dev, architect, critics) that fills in the judgment.

```
pip install --user dummyindex          # or: uv tool install dummyindex
dummyindex install                     # one-time, user-global
cd /path/to/your/repo
claude                                 # open Claude Code in your repo
> /dummyindex <path>                   # e.g. /dummyindex ./src
```

The bootstrap above (`pip install` + `dummyindex install`) is the only time you touch the terminal — after that your interface is the **slash commands** inside Claude Code, and the rest of the CLI is the agent's deterministic backbone (the skill and council invoke it; you don't run it by hand).

After the first run, every future Claude Code session in this repo consults `.context/` before reading source at random. Managed hooks surface drift, memory, GC nudges, and doc-write guardrails; the session reconciles the index in place.

---

## What it is

dummyindex runs in two modes per repo. **Setup mode** (one-time): `/dummyindex` builds `.context/`, installs hooks, and writes the CLAUDE.md managed block. **Ongoing mode** (every session): the spine plans, builds, and evolves — `/dummyindex-plan` turns a feature request into a consistency-checked proposal and auto-equips the project-tuned toolkit in `.claude/` for it, `/dummyindex-build` drives the proposal through those equipped agents wave-by-wave (and warns if the repo isn't equipped instead of silently falling back), and `/dummyindex-remember` saves cross-session memory to `.context/session-memory/`. `/dummyindex-equip` is the standalone way to (re)equip or evolve the toolkit — it also acts as a **plugin manager** (`discover` searches the marketplaces + GitHub for plugins that fill detected gaps, `install` wires them natively into `.claude/settings.json`) and can **score its own generated tools** (`eval` grades a tool's trigger-description against observed firing decisions; `benchmark` aggregates repeated runs). `/dummyindex-audit` runs an adversarial argue-and-audit panel over the real source, and `/dummyindex-gc` sweeps and **deletes** stale / superseded / dead generated docs (user-confirmed).

The index keeps itself honest with guardrails: a PreToolUse Write-guard keeps internal planning docs in their managed `.context/` homes (proposals / audits), and a SessionStart hook reports drift and nudges a GC sweep once enough commits pile up.

Core principle: dummyindex stays the spine — it never writes production code itself. It plans, equips `.context/`-grounded tooling into `.claude/`, and orchestrates; the generated tooling + dispatched agents do the writing.

---

## Install

User-global (one-time):

```bash
pip install --user dummyindex        # or: uv tool install dummyindex
dummyindex install                   # copies skill into ~/.claude/skills/dummyindex/
```

Per-repo (no global state):

```bash
cd /path/to/your/repo
dummyindex install --scope project   # writes .claude/skills/dummyindex/SKILL.md in this repo
```

To remove:

```bash
dummyindex uninstall                 # or: --scope project [--dir PATH]
```

---

## Quickstart

Inside a Claude Code session opened in your repo:

```
/dummyindex                          # ingest + council, install hooks (setup mode)
/dummyindex ./src                    # scope to a subdirectory
/dummyindex-plan "add rate limiting" # NL → proposal, then auto-equips the toolkit for it
/dummyindex-build                    # drive the proposal's checklist through the equipped agents
/dummyindex-equip                    # standalone: (re)equip or evolve the toolkit (plan auto-equips)
/dummyindex-remember                 # save cross-session memory
/dummyindex-audit "is the cache correct?"  # adversarial argue-and-audit panel → report.md
/dummyindex-gc                       # sweep stale generated proposals/audits, with confirmation
/dummyindex-update                   # update dummyindex to the latest GitHub version
```

CLI — the **agent's** deterministic backbone (no LLM cost). The skill and council run these; you don't type them by hand. The only terminal commands a human runs are the `install` bootstrap above. Shown here for transparency:

```bash
dummyindex ingest .                  # build .context/ backbone + CLAUDE.md block
dummyindex context query "how does auth work"   # ranked feature shortlist
dummyindex context rebuild --changed .          # quick deterministic backbone refresh
dummyindex context reconcile .                  # what drifted since the last reconcile (commit-anchored)
dummyindex context hooks status .              # check hook health
dummyindex context --help            # full command list
```

---

Token usage (reads Claude Code transcripts, no LLM cost) — a human checks this via the **`/tokens`** slash command, which wraps `dummyindex usage`:

```bash
dummyindex usage                     # current chat: context window + dedup session totals
dummyindex usage daily               # per-day totals across every project (also: session|monthly|blocks)
```

**Full command reference: [docs/COMMANDS.md](docs/COMMANDS.md)** — every slash command and CLI command in one place.

---

## Docs

- **[docs/COMMANDS.md](docs/COMMANDS.md)** — every command (slash + CLI) in one page
- **[docs/README.md](docs/README.md)** — docs index (guide + reference + internal)
- **[docs/guide/](docs/guide/)** — twelve conceptual docs: architecture, data model, CLI surface, lifecycle, retrieval model, and more

---

## License

MIT — see `LICENSE`.
