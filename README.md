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

After the first run, every future Claude Code session in this repo consults `.context/` before reading source at random. A SessionStart hook surfaces what drifted since the last update, and the session reconciles the index in place.

---

## What it is

dummyindex runs in two modes per repo. **Setup mode** (one-time): `/dummyindex` builds `.context/`, installs hooks, and writes the CLAUDE.md managed block. **Ongoing mode** (every session): the spine plans, builds, and evolves — `/dummyindex-plan` turns a feature request into a consistency-checked proposal and auto-equips the project-tuned toolkit in `.claude/` for it, `/dummyindex-build` drives the proposal through those equipped agents (and warns if the repo isn't equipped instead of silently falling back), and `/dummyindex-remember` saves cross-session memory to `.context/session-memory/`. `/dummyindex-equip` is the standalone way to (re)equip or evolve the toolkit.

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
```

CLI (no LLM cost, deterministic backbone only):

```bash
dummyindex ingest .                  # build .context/ backbone + CLAUDE.md block
dummyindex context query "how does auth work"   # ranked feature shortlist
dummyindex context rebuild --changed .          # incremental re-index
dummyindex context hooks status .              # check hook health
dummyindex context --help            # full command list
```

---

## Docs

- **[docs/README.md](docs/README.md)** — docs index (guide + reference + internal)
- **[docs/guide/](docs/guide/)** — twelve conceptual docs: architecture, data model, CLI surface, lifecycle, retrieval model, and more

---

## License

MIT — see `LICENSE`.
