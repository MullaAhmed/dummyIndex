<p align="center">
  <a href="https://github.com/MullaAhmed/dummyindex"><img src="https://raw.githubusercontent.com/MullaAhmed/dummyIndex/refs/heads/main/docs/logo-text.svg" width="260" alt="dummyIndex"/></a>
</p>

# dummyindex

The persistent context engine for a repo. A Claude Code and OpenAI Codex skill
family that turns any codebase into a `.context/` folder agents can navigate
without broad grepping — deterministic AST extraction plus a multi-agent
council (dev, architect, critics) that fills in the judgment.

```bash
pip install --user dummyindex          # or: uv tool install dummyindex

# Pick one host (or use --platform both):
dummyindex install --platform claude
dummyindex install --platform codex

cd /path/to/your/repo
# Claude Code: /dummyindex .
# Codex:       $dummyindex .
```

The bootstrap is the only time you need the terminal. After that, use slash
commands in Claude Code or `$skill-name` mentions in Codex; the Python CLI is
the deterministic backbone those skills invoke.

After the first run, both hosts receive durable instructions to consult
`.context/` before searching source broadly. Claude uses dummyindex-managed
hooks and `.claude/CLAUDE.md`; Codex uses the active project instruction file
(`AGENTS.override.md`, `AGENTS.md`, or a configured fallback) and native skill
discovery. Codex has its own hook surface, but dummyindex does not install into
it today. For fallback names and the byte limit, dummyindex reads Codex's
platform system config, then user config, then the root `.codex/config.toml`
only when the persistent user config explicitly trusts that project via
`[projects."<absolute-root>"].trust_level`. It cannot observe a session's
selected profile, `-c` overrides, or nested launch-directory config layers.

---

## What it is

dummyindex runs in two modes per repo. **Setup mode** (one-time) builds
`.context/` and writes host guidance. **Ongoing mode** plans, builds, remembers,
audits, and cleans generated context through the installed skill family.

The workflow bodies are shared. Installed Codex copies include a compatibility
header that maps Claude's Task/Agent vocabulary to Codex `explorer`, `worker`,
and `default` subagents; maps skill calls to `$name`; and uses the active Codex
model through `--model current`. The core index, plan, build, memory, audit, and
GC workflows work without Claude state. On Claude, plan auto-equips the rendered
`.claude/` toolkit and build requires its manifest. On Codex, plan never runs
equip discovery/installation/rendering, build needs no equipment manifest, and
`$dummyindex-equip` is a read-only routing report over available native skills,
custom agents, and built-in `explorer`, `worker`, and `default` subagents.

On Claude, managed hooks add a PreToolUse document guard, SessionStart
drift/memory/GC signals, and a Stop reconcile nudge. On Codex, durable
active-instruction-file guidance and explicit `$dummyindex*` workflows provide
the same core context lifecycle without claiming that Claude hook definitions
are active.

Core principle: dummyindex stays the spine — deterministic commands manage
context and state, while the active host's dispatched agents do judgment and
production-code work.

---

## Install

User-global (one-time):

```bash
pip install --user dummyindex        # or: uv tool install dummyindex
dummyindex install --platform claude # ~/.claude/skills/dummyindex*/
dummyindex install --platform codex  # ~/.agents/skills/dummyindex*/
dummyindex install --platform both   # both skill trees
```

Per-repo (no global state):

```bash
cd /path/to/your/repo
dummyindex install --platform codex --scope project
# writes .agents/skills/dummyindex*/ and the active project instruction file
```

To remove:

```bash
dummyindex uninstall --platform codex
# add --scope project [--dir PATH], or use --platform both
```

---

## Quickstart

The same workflows have host-native spellings:

| Workflow | Claude Code | Codex |
|---|---|---|
| Index / reconcile | `/dummyindex` | `$dummyindex` |
| Plan | `/dummyindex-plan` | `$dummyindex-plan` |
| Build | `/dummyindex-build` | `$dummyindex-build` |
| Equip | `/dummyindex-equip` (render/manage `.claude/`) | `$dummyindex-equip` (read-only native routing) |
| Remember | `/dummyindex-remember` | `$dummyindex-remember` |
| Audit | `/dummyindex-audit` | `$dummyindex-audit` |
| Context GC | `/dummyindex-gc` | `$dummyindex-gc` |
| Update | `/dummyindex-update` | `$dummyindex-update` |

In Codex you can also open `/skills` and select any installed dummyindex skill.
dummyindex installs Agent Skills rather than custom prompts, so
`$dummyindex-plan` is the supported equivalent of the Claude slash invocation.

CLI — the **agent's** deterministic backbone (no LLM cost). The skill and council run these; you don't type them by hand. The only terminal commands a human runs are the `install` bootstrap above. Shown here for transparency:

```bash
dummyindex ingest . --platform codex # build .context/ + active Codex project guidance
dummyindex context query "how does auth work"   # ranked feature shortlist
dummyindex context rebuild --changed .          # quick deterministic backbone refresh
dummyindex context reconcile .                  # what drifted since the last reconcile (commit-anchored)
dummyindex context hooks status .              # Claude integration hook health
dummyindex context --help            # full command list
```

---

Token usage reads Claude Code transcripts and is therefore Claude-only. The
Claude install includes `/tokens`; a Codex-only install does not create it.
Codex already provides `/status` for current context/session tokens and
`/usage` for account usage.

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
