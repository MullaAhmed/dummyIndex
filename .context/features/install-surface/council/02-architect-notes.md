# Architect notes — install-surface (stage 2)

## What I changed

- Set a hard bounded context: install owns skill placement and orchestration;
  build algorithms, hook behavior, equip rendering, plugin contents, and the
  Claude CLI remain downstream services.
- Recast `_wire_default_plugins_step` as the ordered application-service seam:
  opt-out → trust disclosure → strict config read → migration → equipment intent
  recovery → reviewed-default reconciliation → declaration → materialisation →
  reporting (`dummyindex/installer/install.py:597-665`).
- Added explicit state ownership for `.context/config.json`, project/local Claude
  settings, the reviewed source registry, and per-machine Claude plugin storage.
- Separated primary build/install success from best-effort satellite readiness.
  This is the architectural reason the command can succeed while integration
  warnings remain.
- Removed repeated behavioral prose and consolidated it into one orchestration
  flow, one pattern catalog, one dependency map, and promoted decisions.

## Patterns named

- **Application-service transaction script** — installer sequencing with explicit
  early/fail-closed boundaries (`dummyindex/installer/install.py:597-665`).
- **Reviewed registry as policy data** — validated frozen defaults and immutable
  third-party refs (`dummyindex/context/default_plugins.py:118-202`).
- **Append-only intent reconciliation** — equipment and reviewed defaults append
  without reordering or replacing custom entries
  (`dummyindex/context/domains/config.py:567-659`).
- **Tombstone precedence** — any effective project/local false wins
  (`dummyindex/context/default_plugins.py:337-349`).
- **Declaration/materialisation split** — repository intent is distinct from
  per-machine bits (`dummyindex/context/default_plugins.py:448-481`,
  `dummyindex/context/default_plugins.py:533-558`).
- **External anti-corruption adapter** — injected `Runner` and normalized
  `RunResult` isolate Claude CLI behavior
  (`dummyindex/context/default_plugins.py:550-581`).
- **Conflict-preserving merge** — a mismatched same-name marketplace is never
  overwritten (`dummyindex/context/default_plugins.py:357-406`).
- **Best-effort satellite fan-out** — guidance, hooks, plugins, and equipment are
  sibling integrations after the primary context decision
  (`dummyindex/installer/install.py:374-465`).

## Dependencies surfaced

- Upstream process flow is `__main__.main` → `parse_install_args` → `install`
  (`dummyindex/__main__.py:259-289`,
  `dummyindex/installer/args.py:63-147`).
- `_auto_init_project` fans out to context build/refresh, Claude/Codex guidance,
  hooks, default plugins, and optional equipment refresh
  (`dummyindex/installer/install.py:357-509`).
- `config.py` imports the base `WiredEntry`/`default_wired` policy types; the
  default-plugin module does not import config, so persistence does not create a
  cycle (`dummyindex/context/domains/config.py:68-75`).
- `default_plugins.py` delegates settings mutation to `claude_settings` and
  `claude_plugins`, then crosses the process boundary only through `Runner`.
- `.context/config.json` is durable intent; `.claude/settings.json` is shared
  project declaration; `.claude/settings.local.json` contributes local
  tombstones; `~/.claude/plugins/` is per-machine materialisation.

## Decisions promoted

- One-run opt-out is a side-effect-free gate, not a temporary config rewrite.
- Trust changes require reviewed source changes; runtime config cannot enlarge
  the trusted materialisation set.
- Reconciliation is monotonic: automation fills absence and preserves explicit
  custom entries, false states, and marketplace conflicts.
- Malformed config is distinct from missing config and stops defaults fail-closed.
- Codex shares the installer but remains free of Claude-native plugin/hook state.
- Curated indexes deterministically refresh on reinstall and never re-cluster as
  an incidental upgrade side effect.
- External materialisation is deliberately best-effort after project declaration;
  missing Claude CLI/network defers without invalidating repository intent.
