# Architect notes — install-surface (stage 2)

Verification basis: every citation in the dev draft was machine-checked against
`.context/map/symbols.json` **and** re-derived from live source. All 70 ranges
are in-bounds. Where the index and the code disagreed, the code won.

## What I changed

- **Added a citation law and disambiguated every bare filename.** Four names are
  ambiguous inside this feature: `orchestrate.py` (`installer/install/` vs
  `installer/link/`), `models.py` / `classify.py` (`installer/link/` vs
  `context/domains/*/`), `hooks.py` (`context/` vs `cli/`), `config.py`
  (`context/domains/` vs `cli/`). This is not pedantry — my automated resolver
  landed on `context/domains/audit/models.py`, `context/domains/docguard/
  classify.py`, `cli/hooks.py`, and `cli/config.py` for the draft's bare names,
  three of which are real files with plausible-looking content. Every path in
  the revision is now rooted at `dummyindex/`.
- **Named a bounded context up front.** Install owns *placement and wiring*;
  index building, hook behavior, equipment rendering, plugin contents, and the
  `claude` CLI are downstream services behind narrow seams. The draft implied
  this; it now states it before the file list.
- **Added a pattern table** (12 rows, each with a `path:range`) after the
  three-sentence architecture, so the patterns are enumerable rather than buried
  in prose.
- **Added a `## Dependencies` section**, replacing the draft's implicit
  dependency story.
- **Documented the 10-value install tuple** in *Data model* — the brief's
  named artefact was absent from the draft entirely.
- **Trimmed no citations.** The draft's ranges were correct; three were
  tightened (`_SIBLING_SKILLS` 87-97 → 87-95; `install_statusline` 310-376 →
  306-376 to start at the write-if-absent comment; `claude_link_allowlist`
  gained its second use site at `:463`).
- **Replaced the draft's hedged closing bullet** ("treat any range that does not
  land on the named symbol as drift") with a concrete `## Index conflict`
  section naming the exact drift and the fix command.

## Patterns named

All twelve are in the plan's table with ranges. The five that were previously
unnamed:

- **Deferred import to break a cycle** — `installer/install/orchestrate.py:251`,
  `:445`.
- **Package-attribute indirection as test seam** —
  `installer/install/orchestrate.py:5-13`, `:21`.
- **Deferred-write / exactly-one-of invariant** —
  `installer/install/orchestrate.py:326-330`, `384-441`.
- **Write-if-absent (idempotence without a sentinel)** —
  `context/hooks.py:306-376`.
- **Fail-closed classification over a closed enum** —
  `installer/link/models.py:17-49`, `installer/link/classify.py:199-336`.

## Dependencies surfaced

- **Upstream:** `__main__.main` → `parse_install_args`
  (`installer/args.py:84-217`) → `installer/install/orchestrate.install`. The
  sole inbound contract is a positional 10-tuple.
- **Downstream:** every `context.*` dependency is a function-level import inside
  a `try` (`installer/install/project_init.py:49-59`, `172-173`, `235`, `262`,
  `280`, `305-318`). The installer stays runnable when a downstream module is
  broken — import failure degrades to a printed skip.
- **One real cycle, deliberately broken.** `installer/repair.py:65` imports
  `.install` at module level; `installer/install/orchestrate.py` therefore
  imports `..repair` *inside functions* at `:251` and `:445`. Hoisting those two
  imports reintroduces the cycle. `installer/uninstall.py` is the acyclic leaf
  both depend on (`repair.py:67`).
- **`installer/link/` is strictly layered with no back-edges:** `common` →
  `families`/`models` → `classify` → `create` → `orchestrate`/`sweep`, with the
  import law stated at `installer/link/families.py:1-6`. Verified against every
  import statement in the package. This is what lets `link/` be safely imported
  by `install/`, `repair.py`, and `uninstall.py` alike.
- **State ownership by lifetime:** `.context/config.json` (durable, git) /
  `.claude/settings.json` (team, git) / `.claude/settings.local.json` (local,
  not git) / `~/.claude/plugins/` (per-machine, never git).

## Decisions promoted

- **The 10-value positional tuple is a live hazard, decided as acceptable.**
  Four adjacent interchangeable `bool` slots (`skill_only`, `no_onboarding`,
  `defaults`, `no_default_plugins`) mean a reorder on either side of
  `installer/args.py:203-214` ↔ `__main__.py:293-304` is a silent semantic swap
  no type checker catches. Keyword re-binding at `__main__.py:305-316` makes it
  readable, not safe. Promoted to an open question with the trade-off stated.
- **`--no-superpowers` collapses three times, and why.** Parse
  (`installer/args.py:141-143`, which is why the tuple has no `no_superpowers`
  slot), public API (`installer/install/orchestrate.py:118`), and
  `_auto_init_project` (`installer/install/project_init.py:47`). The latter two
  are independent public call seams predating the rename; each must accept the
  old spelling on its own. Cost: three edits when the alias is dropped.
- **`--defaults` / `--no-onboarding` are ORed at the call site, not at parse**
  (`installer/install/orchestrate.py:489`) — preserving the option to diverge,
  at the price of two of the four interchangeable bool slots.
- **stdout redirection is chosen per command by protocol, not by taste.**
  `2>/dev/null` where stdout carries protocol meaning (UserPromptSubmit JSON,
  Stop `decision: block`, PreToolUse `permissionDecision: deny` —
  `context/hooks.py:132-143`, `213-225`, `250-264`); full `>/dev/null 2>&1` only
  where output is pure side effect (`:185-196`, `:229-243`). Inverting it either
  leaks noise into every turn or silently disables a gate.
- **Write-if-absent buys statusLine idempotence at a stated price**
  (`context/hooks.py:306-376`): a user who edits our value keeps it forever and
  we can never migrate the badge command. The draft named the mechanism; the
  trade-off was unstated.
- **The "exactly one of {8 links, 8 real dirs}" invariant is scoped to the blank
  slate.** A hand-deleted partial layout that also hits an unexpected link
  failure can end with siblings absent — non-destructive, self-heals on rerun
  (`installer/install/orchestrate.py:407-428`). The draft stated the invariant
  without its scope.
- **Package-attribute indirection is load-bearing, not accidental.** Calls route
  through `_install_pkg` / `_link_pkg` so `monkeypatch.setattr` on the package is
  observed (`installer/install/orchestrate.py:5-13`, `:399`;
  `project_init.py:111`, `:149`; `link/sweep.py:10`). "Simplifying" to direct
  calls silently breaks `tests/test_install_link.py`.
- **No commit pin: the accepted cost is named.** We consume whatever bytes the
  upstream branch serves at clone time
  (`context/default_plugins.py:353-370`).

## Conflicts flagged

**`.context/map/symbols.json` is stale for `dummyindex/context/hooks.py`.** It
places `HookStatus` at 322 (real 429), `install` at 376 (real 486), `uninstall`
at 503 (real 617), `status` at 580 (real 694) — +64 to +114 drift — and still
carries a `statusline_nudge` symbol the code no longer defines (the current
function is `install_statusline` at `context/hooks.py:346`). The dev's ranges
match the code, not the index; the index is the wrong artefact. Recorded in the
plan's `## Index conflict` section. Fix: `dummyindex context rebuild --changed`.

Verified independently and **not** a conflict: the 5-event / 10-command hook set
is exactly as the draft claims (UserPromptSubmit 2, SessionStart 4, Stop 2,
PreCompact 1, PreToolUse 1 — `context/hooks.py:120-276`), and the 8 link
families are main + 7 `_SIBLING_SKILLS` labels
(`installer/common.py:87-95` → `installer/link/families.py:16-24`).

Doc evidence: no `.context/` prose doc was quoted as authority in this revision.
Every claim is anchored to source read at HEAD.
