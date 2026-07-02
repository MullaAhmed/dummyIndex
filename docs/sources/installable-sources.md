# Installable sources catalog

Curated, verified catalog of sources from which dummyindex can discover and install
Claude Code skills, plugins, and agents. This document is the single source of truth
for candidate sources; promotion into `SEED_MARKETPLACES`
(`dummyindex/context/domains/equip/plugins/marketplace.py`) happens from here.

**How this feeds `equip discover`:**

- **Channel A — native marketplaces.** Repos with `.claude-plugin/marketplace.json`.
  Plugins install natively into `.claude/settings.json` via Claude Code's plugin
  manager, gated by tiered trust + blast-radius disclosure.
- **Channel B — skills.sh ecosystem.** Vercel's `skills.sh` installer and its
  official collection (`vercel-labs/agent-skills`). Skills install via the skills
  CLI rather than the native plugin manager.
- **Vendored collections.** Loose repos of `SKILL.md` / agent `.md` files with no
  `marketplace.json` (seed flag `is_collection=True`). Their contents are copied
  (vendored) into the target repo, never natively enabled.
- **Reference only.** Registries and awesome-lists used for discovery; never
  install targets.

**Trust policy:** `trusted=True` is reserved for Anthropic and Vercel official
repos. Everything else — regardless of stars — is `untrusted` and goes through
blast-radius disclosure before install.

**Verified:** 2026-06-13, via `gh repo view` (existence, stars, last push, archive
status) and `gh api repos/<owner>/<repo>/contents/.claude-plugin/marketplace.json`
(native-marketplace check). Entries that could not be verified are marked
**UNVERIFIED**. The stars/last-push/existence facts below carry this date; they
have not been re-verified since.

**SEED_MARKETPLACES column reconciled against `marketplace.py` on 2026-07-01** —
the "In SEED_MARKETPLACES" column and the seed-flag notes reflect the current
`SEED_MARKETPLACES` tuple, which was expanded after the 2026-06-13 gh pass. The
two previously-flagged seed-flag drifts are now resolved in code.

---

## a) Native Claude plugin marketplaces

Repos with a verified `.claude-plugin/marketplace.json`. Mechanism: **native marketplace**.

| Repo | What it offers | Stars | Last push | Trust | In SEED_MARKETPLACES |
|---|---|---|---|---|---|
| `anthropics/claude-plugins-official` | Anthropic-managed directory of high-quality Claude Code plugins | 30,003 | 2026-06-12 | trusted | yes |
| `anthropics/skills` | Anthropic's public Agent Skills repo (document skills, artifacts, etc.) | 149,936 | 2026-06-09 | trusted | yes (native; seeded `is_collection=False`) |
| `anthropics/claude-code` | Claude Code main repo; ships first-party plugins (plugin-dev, hookify, code-review, ...) | 132,068 | 2026-06-12 | trusted | yes |
| `anthropics/knowledge-work-plugins` | Plugins for knowledge workers (Claude Cowork-oriented) | 20,427 | 2026-06-12 | trusted | yes |
| `anthropics/claude-plugins-community` | Community plugin marketplace (read-only mirror of community submissions) | 179 | 2026-06-12 | untrusted (community-submitted content despite Anthropic hosting) | yes |
| `obra/superpowers` | Agentic skills framework + development methodology (TDD, debugging, planning skills) | 225,964 | 2026-06-12 | untrusted | yes |
| `affaan-m/ECC` | Agent harness optimization system: skills, instincts, memory, security | 214,285 | 2026-06-11 | untrusted | yes |
| `addyosmani/agent-skills` | Production-grade engineering skills for AI coding agents | 56,729 | 2026-06-11 | untrusted | yes |
| `sickn33/antigravity-awesome-skills` | 1,500+ agentic skills library with installer CLI, bundles, workflows | 40,497 | 2026-06-12 | untrusted | no |
| `wshobson/agents` | Multi-harness plugin marketplace (Claude Code, Codex, Cursor, OpenCode, ...) | 36,668 | 2026-06-12 | untrusted | yes |
| `kepano/obsidian-skills` | Obsidian skills: CLI, Markdown, Bases, JSON Canvas | 35,438 | 2026-06-08 | untrusted | yes |
| `VoltAgent/awesome-claude-code-subagents` | 100+ specialized subagents, packaged as a native marketplace | 21,677 | 2026-05-27 | untrusted | no |
| `alirezarezvani/claude-skills` | 337 skills/agents/commands across engineering, marketing, product, compliance | 17,929 | 2026-06-12 | untrusted | no |
| `trailofbits/skills` | Security research, vulnerability detection, and audit-workflow skills | 5,680 | 2026-06-11 | untrusted | yes |
| `obra/superpowers-marketplace` | Curated companion marketplace to superpowers | 1,067 | 2026-06-12 | untrusted | yes |
| `Piebald-AI/claude-code-lsps` | LSP-server plugins (code-running surface — high blast radius) | 475 | 2026-06-01 | untrusted | no |
| `trailofbits/skills-curated` | Curated, community-vetted plugin marketplace | 437 | 2026-06-12 | untrusted | no |
| `LerianStudio/ring` | 89 skills + 38 agents enforcing engineering practices (TDD, review gates) | 196 | 2026-06-12 | untrusted | no |

**Resolved — `anthropics/skills`:** previously seeded `is_collection=True` while
the repo shipped `.claude-plugin/marketplace.json`. The seed now carries
`is_collection=False` (plain native marketplace), matching the repo.

**Promotion status:** the prior top picks (`obra/superpowers`,
`addyosmani/agent-skills`, `wshobson/agents`, `anthropics/claude-code`,
`trailofbits/skills`, `kepano/obsidian-skills`) are all now in
SEED_MARKETPLACES. Fresh candidates from the `no` rows above should be selected
at the next re-verification pass.

## b) Skill collections (loose SKILL.md repos / skills.sh)

No `marketplace.json`. Mechanism: **skills.sh** (Channel B) or **vendored collection**.

| Repo | What it offers | Stars | Last push | Trust | Mechanism | In SEED_MARKETPLACES |
|---|---|---|---|---|---|---|
| `vercel-labs/agent-skills` | Vercel's official agent skills collection; canonical skills.sh source | 27,853 | 2026-06-10 | trusted (Vercel official) | skills.sh | yes (seeded `is_collection=True` — CLI would vendor it; the equip skill prefers `npx skills`) |
| `K-Dense-AI/scientific-agent-skills` | 140 science skills + 100+ scientific database integrations | 28,077 | 2026-06-12 | untrusted | vendored collection | no |
| `davila7/claude-code-templates` | aitmpl.com — templates, agents, commands; ships its own installer CLI | 28,014 | 2026-06-12 | untrusted | vendored collection (own CLI; do not use its installer — vendor files directly) | no |

## c) Agent collections (subagent .md repos)

Loose repos of agent definition files. Mechanism: **vendored collection**
(`is_collection=True` if promoted).

| Repo | What it offers | Stars | Last push | Trust | In SEED_MARKETPLACES |
|---|---|---|---|---|---|
| `msitarzewski/agency-agents` | Full "AI agency" of persona agents across 20+ domains (engineering, design, finance, ...) | 112,376 | 2026-06-07 | untrusted | yes (seeded `is_collection=True` — vendored) |
| `contains-studio/agents` | Studio-style department agents (engineering, design, marketing, ops) | 12,384 | 2025-07-28 (stale ~11 mo) | untrusted | no |
| `vijaythecoder/awesome-claude-agents` | Orchestrated subagent dev team | 4,309 | 2025-10-30 (stale ~7 mo) | untrusted | no |
| `iannuttall/claude-agents` | Custom subagents — **ARCHIVED 2025-07; do not promote** | 2,056 | 2025-07-25 | untrusted | no |
| `0xfurai/claude-code-subagents` | 100+ production-ready development subagents | 927 | 2025-10-15 (stale) | untrusted | no |
| `dl-ezo/claude-code-sub-agents` | 35 subagents for end-to-end development automation | 186 | 2025-07-30 (stale, small) | untrusted | no |

**Resolved — `msitarzewski/agency-agents`:** the repo has no `.claude-plugin/`
directory — it is category folders of agent `.md` files. The seed now carries
`is_collection=True`, so its contents are vendored (copied) rather than natively
enabled.

Most agent collections here went stale in mid-to-late 2025 (likely superseded by
the native plugin/marketplace mechanism). Only `msitarzewski/agency-agents`
remains actively pushed.

## d) MCP server registries (reference only)

Never install targets for dummyindex. Useful for resolving MCP servers a plugin
declares, or for manual research.

| Source | What it offers | Stars | Last push | Mechanism |
|---|---|---|---|---|
| `modelcontextprotocol/servers` (GitHub) | Canonical reference MCP servers + registry of community servers | 87,129 | 2026-06-07 | reference |
| smithery.ai | Web MCP registry with hosted servers | n/a (not GitHub) | UNVERIFIED | reference |
| mcp.so | Web MCP server directory | n/a (not GitHub) | UNVERIFIED | reference |
| glama.ai | Web MCP registry / gateway | n/a (not GitHub) | UNVERIFIED | reference |
| pulsemcp.com | Web MCP server directory with usage stats | n/a (not GitHub) | UNVERIFIED | reference |

## e) Aggregators / awesome-lists (discovery only)

Lists that point at sources. Use to find NEW catalog candidates; never install
from them directly.

| Repo | What it offers | Stars | Last push | Mechanism |
|---|---|---|---|---|
| `hesreallyhim/awesome-claude-code` | Curated list of skills, hooks, commands, orchestrators, plugins | 46,302 | 2026-04-27 | reference |
| `github/awesome-copilot` | Community instructions/agents/skills for GitHub Copilot (cross-pollination only — Copilot formats differ) | 34,919 | 2026-06-12 | reference |

---

## Maintaining this catalog

### Verifying a new source before adding

1. **Existence + health:**
   `gh repo view <owner>/<repo> --json nameWithOwner,description,stargazerCount,pushedAt,isArchived`
   — drop if 404 or `isArchived: true`; mark UNVERIFIED (do not silently drop) if
   `gh` is rate-limited.
2. **Activity:** prefer a push within the last 6 months. Older repos may be
   listed but must carry a "(stale)" annotation and should not be promoted.
3. **Marketplace check:**
   `gh api repos/<owner>/<repo>/contents/.claude-plugin/marketplace.json --jq .name`
   — success means native marketplace (Channel A); 404 means loose collection
   (vendored, `is_collection=True`).
4. **Blast-radius scan:** inspect the marketplace.json plugin entries for
   code-running surfaces (`hooks`, `mcpServers`, `lspServers`, `bin` — the
   `_CODE_SURFACE_KEYS` map in `marketplace.py`). Anything with those surfaces
   from an untrusted source requires explicit user disclosure at install time.
5. **Trust:** `trusted=True` only for Anthropic/Vercel official org repos. Stars
   are a popularity signal, not a trust signal.
6. **Identity check:** confirm the marketplace.json `name` does not collide with
   a reserved/seed name from a different repo (the discovery orchestration drops
   impostors, but don't seed one).

### Promotion path: catalog entry -> SEED_MARKETPLACES

1. Source passes all six checks above and has been in this catalog through at
   least one re-verification cycle.
2. Add a `SeedMarketplace(name, "owner/repo", trusted=..., is_collection=...)`
   row to `SEED_MARKETPLACES` in
   `dummyindex/context/domains/equip/plugins/marketplace.py`, with tests.
3. Update this document's "In SEED_MARKETPLACES" column in the same commit.
4. Re-verify the whole catalog (steps 1-4 per entry) at least quarterly, or
   whenever `equip discover` reports a seed fetch failure. Update the
   "Verified" date in the header after each pass.

### Known seed drift

None outstanding. The two items previously listed here are resolved in
`marketplace.py` (as of the 2026-07-01 reconcile):

- `anthropics/skills`: now seeded `is_collection=False` (plain native
  marketplace), matching the repo's `marketplace.json`.
- `msitarzewski/agency-agents`: now seeded `is_collection=True` (vendored),
  matching a repo with no `marketplace.json`.

This document does not change code; record any newly-found drift here and open a
deliberate code change + tests when picking it up.
