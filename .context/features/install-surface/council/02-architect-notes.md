# Architect notes — install-surface (stage 2)

## What I changed

- Added a **Bounded context** section up top: one responsibility (idempotent,
  non-destructive install/uninstall + auto-init), with an explicit in-scope /
  out-of-scope line — the `.context/` builders, the `claude` plugin CLI, and
  equip are *called*, not owned.
- Replaced the prose-only layering aside with a dedicated **Dependencies**
  section that names upstream callers, downstream callees, and the shared leaf,
  and explicitly debunks the apparent install→hooks→default_plugins cycle (it's
  a fan-out; the two side-effect modules never call each other).
- Lifted the patterns out of the decisions list into a **Patterns** section,
  each at `path:range`: additive settings merge, managed-block, Runner seam.
- Rewrote **Key decisions** with a one-paragraph framing of *why* additive /
  non-destructive (the surface is re-run on every upgrade over possibly-curated,
  team-configured repos → second run must never lose user state), then tied each
  decision back to that invariant instead of just restating behaviour.
- Cut filler: dropped the redundant layering sentence from "Where it lives",
  trimmed restated rationale, corrected a few line ranges against source
  (`default_runner` 207-223, `_install_one` 255-274, scrub 348-369,
  CLAUDE.md 344-345, refresh fork 246-277, DefaultPlugin 36-52).

## Patterns named

- **Additive settings merge** — read-merge-write touching only this feature's
  keys; `wire_default_plugins` (`default_plugins.py:136-172`) on `enabledPlugins`,
  `hooks.install` (`hooks.py:329-412`) on `hooks.<Event>`; both refuse non-object
  settings, both via one `load_settings`.
- **Managed-block** — `SENTINEL = "DUMMYINDEX_AUTO_REFRESH"` (`hooks.py:48`) +
  managed comment select this feature's own hook entries; user hooks without the
  sentinel are left alone (`hooks.py:339-340`). CLAUDE.md block is the markdown
  analogue (`install.py:171-172`).
- **Runner seam** — injectable `Runner`; `default_runner`
  (`default_plugins.py:207-223`) fixed argv, no shell, 127 on missing exe, never
  raises (`conventions/coding-practices.md` §Runner seam).

## Dependencies surfaced

- Upstream: `__main__.main` (`__main__.py:245-267`) sole entry; `/dummyindex-update`
  re-runs `install`.
- Downstream of `_auto_init_project`: `.context/` builders (fresh vs.
  deterministic-refresh fork, `install.py:248-277`), `hooks.install`
  (`hooks.py:329-412`), `wire_default_plugins` + `install_default_plugins`
  (`default_plugins.py:136-172,287-329`) — independent siblings.
- No cycle: hooks and default_plugins never call each other. Shared leaf is
  `.claude/settings.json` via `load_settings`, disjoint keys, no write contention.
- Layering `__main__ → installer → context` (`conventions/coding-practices.md`
  §Layering) holds.

## Decisions promoted

- Promoted the **why** of additive/non-destructive: every-upgrade re-run over
  curated, team-configured repos ⇒ no run may lose user state. Each seam-level
  decision (no re-cluster of enriched index; best-effort secondaries; declaration
  vs materialisation split; already-decided sacrosanct; legacy scrub) reframed as
  that one invariant applied locally, rather than as standalone behaviour notes.
