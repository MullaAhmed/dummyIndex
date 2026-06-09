# equip as a Claude plugin manager — design

**Date:** 2026-06-10
**Status:** Approved (brainstorming) → ready for implementation plan
**Target version:** 0.18.0
**Branch:** `feat/equip-plugin-manager`

## 1. Problem

dummyindex is meant to act as a Claude Code **plugin manager** — it should
discover relevant agents, skills, and plugins from the available marketplaces
and from GitHub, then wire them into the project. Today it does neither.

The `equip` domain (`dummyindex/context/domains/equip/`) is **templates-first +
adopt**: it detects the repo's stack and proposal capabilities, renders a tuned
`.claude/` toolkit from shipped `*.md.tmpl` templates, and "adopts" specialists.
But its entire notion of *adoptable things* is a **hardcoded constant** —
`_REGISTRY_CAPABILITIES` in `adopt.py`, six built-in global agent names sourced
from `SubagentType` (`dummyindex/context/domains/dev_pick.py`). Nothing in the
codebase fetches, clones, searches, or installs from a marketplace or from
GitHub. `EquipmentSource` has only `GENERATED` and `INSTALLED`, and "INSTALLED"
means "a manifest-only pointer at a name I already knew about."

That hardcoded registry is the exact seam this feature widens: from *six names I
know* to *live marketplace catalogs I discover*.

## 2. Goals / non-goals

**Goals**

- `equip discover` — auto-match: reuse the existing capability model
  (`detect_stack` + proposal capabilities) to surface plugins/agents/skills that
  fill the toolkit's gaps.
- `equip discover "<query>"` — query: search the seed marketplaces **and**
  GitHub for matches to a free-text term.
- Both produce **one ranked dry-run `InstallPlan`** the user approves before
  anything is written (mirrors `equip apply --dry-run`).
- **Hybrid wiring:** packaged marketplace plugins are enabled via Claude Code's
  **native** mechanism; loose agents/skills are **vendored** (copied) into
  `.claude/`. One manifest tracks both, each tagged with mechanism + upstream
  origin.
- **Tiered trust + blast-radius disclosure:** Anthropic-official marketplaces
  are trusted by default; everything else needs explicit approval. The plan
  always discloses each candidate's blast radius (hooks / MCP / LSP / bin vs
  inert agents/skills/commands). Nothing that runs code is enabled silently.
- `status` / `refresh` / `uninstall` extend to cover the new item kinds.

**Non-goals**

- Reimplementing Claude Code's installer. dummyindex *proposes and analyzes*;
  the actual install mechanics are delegated to the native surface
  (`claude plugin …` and the `extraKnownMarketplaces` / `enabledPlugins` keys in
  `.claude/settings.json`).
- Authoring/publishing a marketplace of our own.
- Live network calls in the test suite.
- Auto-installing anything without an approved plan.

## 3. The native wiring target (authoritative)

Claude Code's plugin system is the wiring target. Confirmed surface:

- **Marketplace** = a git repo with `.claude-plugin/marketplace.json` listing
  plugins (`name`, `source`, `description`, `version`, `keywords`, `category`,
  and optional `hooks` / `mcpServers` / `lspServers` declarations).
- **Project-committed state** lives in `.claude/settings.json`:
  - `extraKnownMarketplaces` — `{ "<name>": { "source": { "source": "github",
    "repo": "owner/repo", "ref"?: "<sha|tag>" } } }`
  - `enabledPlugins` — `{ "<plugin>@<marketplace>": true }`
- **User-level marketplace registry:** `~/.claude/plugins/known_marketplaces.json`.
- **Installed plugin cache:** `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/`.
- **Scriptable CLI:** `claude plugin marketplace add|list|remove|update`,
  `claude plugin install|uninstall|enable|disable|list|details`,
  `claude plugin validate <path>`. `--scope user|project|local`. `list --json`.
- A plugin bundles `commands/`, `agents/`, `skills/`, `hooks/`, optional
  `.mcp.json` / `.lsp.json` / `bin/`.

**Seed marketplaces (extensible, not exhaustive):**
`anthropics/claude-plugins-official` (trusted, auto-available),
`anthropics/claude-plugins-community`, `anthropics/knowledge-work-plugins`,
`anthropics/skills` (likely a loose skills collection → vendor path),
`affaan-m/ECC`, `msitarzewski/agency-agents`. The seed list is data in
`_constants.py`; GitHub search extends discovery beyond it.

## 4. Architecture & data flow

Six stages, layered to match `docs/reference/01-conventions.md` §2 (pure policy
core; I/O isolated — the same shape `git_delta.py` and `preflight/inventory.py`
already use for subprocess work):

```
discover ─▶ parse/validate ─▶ match+rank ─▶ blast-radius ─▶ PLAN(dry-run) ─▶ approve ─▶ wire ─▶ record
 (I/O)        (pure)            (pure)         (pure)          (pure)                    (I/O)   (I/O)
```

- **Auto:** `equip discover` → `detect_stack` + proposal caps → needed-capability
  set (gaps vs current manifest) → `match_candidates` over fetched catalogs.
- **Query:** `equip discover "<q>"` → same pipeline seeded by the query against
  catalogs + GitHub search.
- Both yield an `InstallPlan`, printed as a dry-run with blast radius.
  `equip install <plugin>@<marketplace>` (or `discover --yes`) applies it.

## 5. New modules (inside the `equip` domain)

| Module | Layer | Responsibility | Key surface |
|---|---|---|---|
| `equip/sources.py` | **I/O** (subprocess) | Fetch catalogs + GitHub search. Prefer native `claude plugin marketplace list/add --json`; fall back to `gh api`/`git` for raw `.claude-plugin/marketplace.json` and `gh search code/repos`. Returns raw JSON/text only. A thin `Runner` seam (callable) makes it testable without live network. | `fetch_catalog(source) -> RawCatalog`, `search_github(query) -> tuple[RawCatalogRef, ...]`, `available_tools() -> ToolAvailability` |
| `equip/marketplace.py` | **pure** | Parse + validate marketplace JSON into frozen dataclasses; schema-validate at the boundary; raise `CatalogError` on malformed input. | `MarketplaceCatalog`, `PluginEntry`, `parse_catalog(raw) -> MarketplaceCatalog`, `validate_catalog(data)` |
| `equip/discover.py` | **pure** | Map plugin metadata (keywords/category/description) → the existing `Capability` vocab; rank candidates against needed caps and/or a query. | `Candidate`, `match_candidates(catalogs, *, needed_caps, query) -> tuple[Candidate, ...]` |
| `equip/blast_radius.py` | **pure** | Inspect a plugin entry's declared surface → which surfaces it touches + a "runs code" flag; assign the trust tier from the source. | `BlastRadius`, `TrustTier`, `analyze(entry, *, marketplace) -> BlastRadius` |
| `equip/install_plan.py` | **pure** | Combine candidates + trust policy → per-candidate decision: NATIVE-enable vs VENDOR-copy, and whether explicit approval is required. | `InstallPlan`, `PlannedInstall`, `build_install_plan(candidates, *, policy) -> InstallPlan` |

**Extensions to existing modules**

- `equip/enums.py`:
  - `EquipmentSource` += `MARKETPLACE` (native-enabled), `VENDORED` (copied).
  - `EquipVerb` += `DISCOVER`, `INSTALL`.
  - New: `TrustTier` (`TRUSTED` / `UNTRUSTED`), `InstallMechanism`
    (`NATIVE` / `VENDOR`), `PluginSurface` (`AGENT`/`SKILL`/`COMMAND`/`HOOK`/
    `MCP`/`LSP`/`BIN`).
- `equip/models.py`: `EquipmentItem` gains optional origin fields — `marketplace:
  str | None`, `origin_repo: str | None`, `origin_ref: str | None` (commit sha),
  `mechanism: str | None`. `schema_version` → **3**; `from_dict` stays tolerant
  (v2 entries load; missing fields → `None`).
- `equip/_constants.py`: `SEED_MARKETPLACES` tuple + a capability-keyword table
  for inferring `Capability` from plugin metadata (sibling to the existing
  `_CAPABILITY_TOKENS` / `_PROPOSAL_CAPABILITY_TOKENS`). `SCHEMA_VERSION` → 3.
- `equip/errors.py`: `SourceError`, `CatalogError`, `WireError` (all under
  `EquipError`).
- `context/claude_plugins.py` (new, sibling of `claude_settings.py`, same
  layer): merge `extraKnownMarketplaces` + `enabledPlugins` into settings.json
  with the same preserve-or-refuse + atomic-write discipline (`load_settings` /
  `write_settings` are reused; new `merge_marketplace_entry` /
  `set_enabled_plugin`). Reuses `MalformedSettingsError`.

## 6. CLI surface (two new verbs, one ledger)

```
equip discover [QUERY] [--root DIR] [--json]
    # auto-match when QUERY omitted; query-search otherwise.
    # Always a dry-run: prints the ranked InstallPlan + blast radius. Writes nothing.

equip install <plugin>@<marketplace> [--yes] [--scope project|local|user] [--root DIR] [--json]
    # Applies the install for one candidate.
    # --yes is REQUIRED to enable an UNTRUSTED, code-running plugin.
    # Default --scope project (.claude/settings.json, committed).

equip status | refresh | uninstall
    # Now also classify/report/remove MARKETPLACE + VENDORED items.
```

- New handler module `cli/_equip_discover.py` (mirrors `_equip_verbs.py`),
  wired into `equip.py`'s `_cmd_equip` dispatch and `_split_verb`; flag helpers
  added to `_equip_common.py`.
- Wire-only per CONVENTIONS §8: each handler parses flags, calls domain +
  `sources`/`claude_plugins`, prints, returns an exit code (0 / 2 usage / 1
  runtime). The fetch (subprocess) and the settings/vendored-file writes happen
  at this boundary; matching/ranking/planning stays in the pure domain modules.

## 7. Trust & blast-radius (the safety spine)

- **TrustTier:** `TRUSTED` = Anthropic-official seed marketplaces; `UNTRUSTED` =
  community / GitHub-discovered.
- **Surfaces:** inert (`agent`/`skill`/`command`) vs code-running (`hook`/`mcp`/
  `lsp`/`bin`). `BlastRadius.runs_code` is true iff any code-running surface is
  declared.
- **Policy (`build_install_plan`):**
  - inert candidate, any tier → included, no extra gate.
  - code-running + `TRUSTED` → included; blast radius shown; auto-approvable.
  - code-running + `UNTRUSTED` → flagged ⚠; `requires_approval = True`;
    `equip install` refuses without `--yes`.
- The dry-run **always** prints each candidate's blast radius. No hook/MCP/bin is
  ever enabled without it appearing in the plan.
- **Supply-chain:** pin a commit **sha** (`origin_ref`) when vendoring and when
  adding a marketplace; optionally run `claude plugin validate <path>` before
  enabling a native plugin. All fetched catalog JSON is schema-validated before
  use (input-validation at the boundary; CONVENTIONS §13).

## 8. Hybrid wiring & manifest (schema v3)

- **NATIVE** (packaged plugin): add the marketplace to `extraKnownMarketplaces`
  and the plugin to `enabledPlugins` in `.claude/settings.json` (scope-aware),
  and/or drive `claude plugin marketplace add` + `claude plugin install --scope
  <scope>`. Manifest item: `kind=AGENT|SKILL|…` as declared, `source=MARKETPLACE`,
  `path=".claude/settings.json"`, `marketplace`/`origin_repo`/`origin_ref` set,
  `mechanism="native"`, no `origin_hash` (upstream owns the bytes).
- **VENDORED** (loose agent/skill, e.g. from `anthropics/skills`): fetch the
  markdown, write into `.claude/agents|skills/<name>` carrying a
  `<!-- dummyindex:installed -->` sentinel; never-clobber guarded via the
  existing `is_safe_to_write`. Manifest item: `source=VENDORED`, `path` = the
  written file, `origin_hash` set (so `refresh`/`reset`/`uninstall` work exactly
  like generated items), `origin_repo`/`origin_ref` recorded.
- `lifecycle.classify_item` already keys off `origin_hash`; VENDORED items get it,
  MARKETPLACE items are skipped from hash-lifecycle (managed via settings keys).
  `uninstall` removes the settings keys for MARKETPLACE items and the file for
  VENDORED items.

## 9. Error handling

- `SourceError` — fetch/network failure, or a required tool (`claude`/`gh`/`git`)
  absent. Degrade gracefully: fall back to any seed cache, emit an actionable
  message, never crash.
- `CatalogError` — malformed/invalid `marketplace.json` (fails schema
  validation).
- `WireError` — settings/vendored write failed.
- Settings writes reuse `MalformedSettingsError` (preserve-or-refuse): never
  overwrite a settings.json we can't round-trip.

## 10. Testing (TDD, ≥80%)

- **Pure modules** (`marketplace`, `discover`, `blast_radius`, `install_plan`):
  unit-tested with **committed fixture catalogs** (sample `marketplace.json`
  payloads under `tests/`), fully deterministic and offline.
- **`sources.py`:** tested through its `Runner` seam with a fake subprocess /
  monkeypatched fetch — **no live network**. Cover the tool-absent and
  malformed-output degrade paths.
- **CLI:** `discover` dry-run tests assert the ranked plan + blast-radius lines;
  `install` tests use a temp repo and assert `extraKnownMarketplaces` /
  `enabledPlugins` keys, vendored files + sentinel, manifest v3 fields,
  never-clobber, `--yes` gating for untrusted code-running plugins, and
  idempotency. `status`/`uninstall` tests cover MARKETPLACE + VENDORED items.

## 11. Build sequence (phased; each phase shippable + green)

1. **Schema + enums:** extend `enums.py`, `models.py` (v3, tolerant `from_dict`),
   `_constants.py` seeds + keyword table, `errors.py`. Tests for round-trip +
   back-compat.
2. **Pure pipeline:** `marketplace.py` → `discover.py` → `blast_radius.py` →
   `install_plan.py`, each TDD with fixtures. No I/O.
3. **Sources I/O:** `sources.py` with the `Runner` seam; native-CLI-first with
   `gh`/`git` fallback; tool-availability + degrade paths.
4. **Wiring:** `context/claude_plugins.py` (settings merge) + the vendored-file
   writer; preserve-or-refuse, atomic, never-clobber.
5. **CLI verbs:** `cli/_equip_discover.py`, dispatch + flag wiring; dry-run and
   install integration tests.
6. **Lifecycle:** extend `status`/`refresh`/`uninstall` for MARKETPLACE +
   VENDORED; tests.
7. **Skill + docs:** update `skills/equip/SKILL.md` (discover/install flow +
   trust model), `docs/COMMANDS.md`, `docs/guide/07-cli.md`, `CHANGELOG.md`;
   bump to 0.18.0.

## 12. Open questions / deferred

- Whether to expose a friendly `dummyindex plugins …` alias to the same verbs
  (low cost, decide during implementation).
- Ranking heuristic refinement (capability overlap + keyword match + tier);
  start simple, iterate.
- GitHub search auth/rate-limit handling beyond `gh`'s own auth (start with `gh`
  authenticated; document the unauthenticated degrade).
