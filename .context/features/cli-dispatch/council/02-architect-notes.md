# Architect notes — cli-dispatch (stage 2)

## What I changed

- Added a **Bounded context** section that states the cluster's exact boundary
  (alphabet + help + exit-code contract + parse seam) and names it a
  one-directional sink: `cli/` depends on the world, the world never depends on
  `cli/` (verified against `folder-organization.md:27-28`).
- Split the old single "Architecture in three sentences" prose into two
  named-and-located sections: **Patterns named** and **Dependencies**.
- Promoted the old "Open questions"-adjacent rationale into **Decisions** with a
  fourth promoted decision (closed alphabet over bare strings, with its
  enforcing test).
- **Corrected verified ranges** that the prior draft had slightly off:
  `_HANDLERS` is `cli/__init__.py:83-126` (not `:83-124`), `_wants_help` is
  `:57-82` (not `:57-80`), `dispatch` is `:127-145`, `usage_error` is
  `cli/common.py:47-61`, `ContextSubcommand` is `context/enums.py:40-86` and is
  exactly 39 members (`INIT`@47 → `STATUSLINE`@86). Verified the four
  sibling-import sites line-by-line.
  <!-- reconcile 2026-06-22: the enum has since grown to 41 members
  (`INIT`@47 → `STATUSLINE`@87), now including `HOOKS = "hooks"`@51 and
  `WIRE = "wire"`@85. The "39 members / @86" figures above are the stage-2
  historical snapshot; the live counts are in spec.md / plan.md. -->
- Cut filler: removed the redundant "Architecture in three sentences" framing
  and the duplicated data-model restatement; no astronautics added.

## Patterns named

- **Thin adapter (wire-only handler)** — `cli/query.py:7-15`, `cli/debt.py:34-68`,
  `cli/features.py:243-297`.
- **Enum-driven dispatch (closed-alphabet table)** — `cli/__init__.py:127-145`,
  table `:83-126`, alphabet `context/enums.py:40-86`, reject path `:131-137`.
- **Shared-helper seam** — `cli/common.py:13-45,47-61,77-100,103-148,182-203`.

## Dependencies surfaced

- Routes to every domain it dispatches (the only outward arrows), each taken
  lazily inside the `run` body.
- The documented narrow sibling-import exception, all four sites located:
  `cli/check.py:19`, `cli/refresh.py:5`, `cli/reconcile_gate.py:12`,
  `cli/statusline.py:28` — literal invariant broken, shared-helper spirit intact
  (`folder-organization.md:77-83`).
- Eager top-imports kept light: only `cli/common.py`, enums, and `cli/help.py`
  (`cli/__init__.py:18,52`).

## Decisions promoted

- **Lazy import for cheap startup** — `cli/query.py:7-15`, `cli/debt.py:36`,
  `cli/features.py:34`.
- **I/O confined to the boundary** — `print` only in `cli/*`; exit codes 0/1/2,
  specific-before-base (`coding-practices.md:55-62`).
- **Help is read-only, runs before side effects** — `cli/__init__.py:57-82,142-144`,
  `usage_for` slice `cli/help.py:427-447`.
- **Closed alphabet over bare strings** — enforced by
  `test_every_enum_member_has_a_handler` (feature.json:120).
