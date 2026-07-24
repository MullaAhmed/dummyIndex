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

dummyindex install                     # flagless = universal + linked: one real
                                        # .agents/skills tree, .claude/skills
                                        # symlinked to it — discoverable by
                                        # Claude Code, Codex, Cursor, Gemini CLI

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
dummyindex install                   # flagless = universal + linked (default)
```

A flagless install is **universal by default**: one real `.agents/skills`
tree, plus one relative symlink per skill family on the Claude side — so a
single install works in Claude Code, Codex, Cursor, and Gemini CLI with no
further flags. `CLAUDE.md` and `AGENTS.md` are both written.

```
~/.agents/skills/dummyindex/          # real files — the portable rendering
~/.agents/skills/dummyindex-plan/     # ...and the other 6 sibling families
~/.claude/skills/dummyindex        -> ../../.agents/skills/dummyindex
~/.claude/skills/dummyindex-plan  -> ../../.agents/skills/dummyindex-plan
```

Links always point `.claude → .agents`, never the reverse: `.agents` is the
portable rendering, and Claude Code is the only host that reads *only*
`.claude`, so it's the one side that gets symlinked.

Narrow to one host with `--platform claude` or `--platform agents` (real
trees on both sides, no linking — there's nothing to link to):

```bash
dummyindex install --platform claude # ~/.claude/skills/dummyindex*/
dummyindex install --platform agents # ~/.agents/skills/dummyindex*/
```

`--platform agents` is the platform-agnostic selector — the same
`.agents/skills` family is discoverable by Codex, Cursor, Copilot CLI,
OpenCode, Amp, Gemini CLI, Goose, Pi, Cline, and other Agent-Skills/AGENTS.md
harnesses. `--platform codex` still works as a **deprecated alias**: it
prints one deprecation warning and renders byte-identical skill trees.

Linking is a tri-state. The default (no flag) is **AUTO**: link when
possible, otherwise fall back to writing real, duplicated trees with a
warning. `--copy` opts out for one run — always writes real, duplicated
trees under both `.claude/skills` and `.agents/skills`, exactly like every
release before this one. `--link` is the **strict** form: it errors instead
of silently falling back to copy when the Claude side can't be symlinked.

**Updating dummyindex migrates duplicated repos automatically.** A plain
`dummyindex install` — the same command `/dummyindex-update` runs — detects
an existing duplicated layout (real trees under both `.claude/skills` and
`.agents/skills`) or a claude-only layout, and converts every proven Claude
copy to a link in that same run, printing a `claude skill migrated -> ...`
line per family the first time. This happens even when both copies already
carry the same version stamp — repair alone would leave those alone, but
migration forces the conversion. After that first run, the layout is already
linked and reinstalls are quiet.

Windows: on a checkout with `core.symlinks=false`, or without Developer Mode
enabled, AUTO falls back to copy mode with a warning — the install still
succeeds and both hosts still work. A materialized-link placeholder (a plain
file standing in for the symlink, the shape that checkout produces) is
recovered by running `git config core.symlinks true` and re-checking out the
repo; the next `dummyindex install` then replaces it with a real link.

Per-repo (no global state):

```bash
cd /path/to/your/repo
dummyindex install --scope project
# universal + linked, rooted at this repo instead of $HOME

dummyindex install --platform agents --scope project
# narrowed: writes only .agents/skills/dummyindex*/ and the active project
# instruction file
```

To remove:

```bash
dummyindex uninstall
# flagless = removes both hosts, mirroring a flagless install

dummyindex uninstall --platform agents
# add --scope project [--dir PATH], or use --platform both
```

Uninstall removes the whole named family directories it installed — the main
skill plus its 7 siblings — under `.claude/skills/` and/or `.agents/skills/`
at the target scope, so don't store your own files inside
`.claude/skills/dummyindex*/` or `.agents/skills/dummyindex*/`; they won't
survive an uninstall. Narrowing removal with `--platform agents` on a linked
layout also sweeps the now-dangling Claude-side links and prints the exact
`dummyindex install --platform claude` command to restore that surface,
since the Claude side was only ever links into the tree that command just
removed.

Rerunning `install` also **repairs** stale copies an older dummyindex version
left behind (stale preambles, stale managed guidance blocks), scoped to the
platform(s) and scope you selected — everything else is reported with the
exact command to fix it. A duplicate copy at both user and project scope is
reported, never deleted, unless you pass `--dedupe user|project`; a copy
stamped newer than the running package is left alone unless you pass
`--force-downgrade`. A foreign symlinked family dir — one dummyindex didn't
create — is always refused; a dummyindex-owned link (the linked layout
itself) is recognized and left in place or healed, never mistaken for a
stray duplicate. See
[docs/COMMANDS.md](docs/COMMANDS.md#platform-selector-repair-on-reinstall-and-dedupe)
for the full contract.

Cursor already reads `.claude/agents/` natively, so a repo's
`context equip`-generated Claude agents work there with no extra rendering.

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
dummyindex ingest . --platform agents # build .context/ + active Codex/Cursor/etc. project guidance
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
