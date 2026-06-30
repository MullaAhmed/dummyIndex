# Auto-equip skills — spec

`status: planned`

## Problem

The harness is meant to *build itself* for each repo — adding skills/agents/commands
it can then use during plan/build/review/QA. Today it never adds an **external
skill** (from `anthropics/skills` or any seed), on any repo. Confirmed
code-grounded:

- `equip apply` (the only lifecycle-auto equip step, `skills/plan/SKILL.md:98`)
  only renders the repo's own templated agents + a `{proj}-verify` skill from
  packaged local templates (`generate/catalog.py:95-125`). It has no
  http/clone/fetch anywhere and never references `discover`/`install`
  (`cli/equip/dispatch.py:127-130`). By construction it cannot acquire an
  external skill.
- The only external path, `equip install`, is **manual** (no hook / council /
  build-loop caller) and **native-only**: `run_install` builds an `InstallPlan`
  but never branches on `pi.mechanism`, always calling `add_marketplace` +
  `enable_plugin` (`discover.py:471-540`). The VENDOR mechanism that would copy a
  loose `SKILL.md` onto disk is unreachable — `_collect_catalogs` `continue`-skips
  every `is_collection` seed (`discover.py:146-147`), `_fetch_one` always parses
  `is_collection=False` (`discover.py:80`), and `vendor.py`'s `stamp_vendored` /
  `vendored_item` have zero production callers. The module says it: *"The VENDOR
  install path is added in a later slice"* (`discover.py:7`).
- The auto-match signal `_needed_caps` is a self-described stub: it returns at
  most `("test","implement")` from the stack, never diffs against the existing
  `equipment.json`, and never sees a security/db/perf/docs/search gap
  (`discover.py:276-285`).

The proof on this very repo: every `.context/equipment.json` item is
`source:generated`, `marketplace:null`, `mechanism:null`. `plan.md:171-180`
already flags both gaps as open questions; this proposal retires them.

## Intent

Make the harness **detect skill gaps automatically** and **vendor relevant
skills from trusted collections** into `.claude/skills/`, behind the repo's
standing safety rule — **discovery is automatic; installation is never silent**.
Vendored skills become first-class, hash-baselined, never-clobber lifecycle
citizens, refreshable against a **pinned commit ref** (no moving-HEAD drift).

Non-goals (unchanged from equip-v2): a hub registry; silent auto-write of
external content; vendoring from untrusted sources without the `--yes` gate.

## User-visible behavior

1. **Gap-aware discovery.** `equip discover` (no query) computes the *real*
   capability gap — what the stack requires minus what `equipment.json` already
   covers — instead of the 2-tag stub, and ranks candidates against it (a corrupt
   manifest degrades to a stack-only gap with a stderr warning). Proposal-scoped
   *specialist* capabilities (security/db/…) are threaded in by the **plan-time
   caller** (Wave 4), not bare `discover`. Still dry-run; writes nothing.
2. **`equip install <plugin>@<collection>` can vendor a skill.** A collection
   seed (e.g. `vercel-labs/agent-skills`) now resolves: install fetches the
   skill's `SKILL.md` at a **pinned commit sha**, stamps it `VENDORED_SENTINEL`,
   writes it to `.claude/skills/<name>/SKILL.md` under the never-clobber guard,
   and records a `source=VENDORED, mechanism=vendor, origin_ref=<sha>` manifest
   item. The trust gate (`requires_approval = not trusted`) and the mandatory
   usage-doc are unchanged: an untrusted collection still needs `--yes`.
3. **Lifecycle parity.** `equip status/refresh/reset/uninstall` treat a vendored
   skill exactly like a generated file: PRISTINE re-fetches+re-stamps on refresh
   (an explicit, diffable ref bump), a user edit freezes it (clobber-protected),
   uninstall removes file + record together.
4. **Plan/build auto-equip (gated).** During planning, the LLM runs the gap
   analysis, surfaces the skill candidates that fill real gaps, and installs
   **one at a time on explicit user approval**. At build time, when a task falls
   back to `general-purpose`, the loop emits a structured *missing-capability*
   signal the build skill routes into the same discover→approve→vendor flow,
   instead of only printing the static "not equipped" warning.

## Contracts (new / changed)

Pure policy core (`context/domains/equip/generate/gaps.py`, new):
- `covered_capabilities(manifest: EquipmentManifest) -> frozenset[str]` — union
  of every item's `capabilities`.
- `required_capabilities(profile: StackProfile, *, proposal_capabilities=()) ->
  frozenset[str]` — canonical required set from the detected stack + proposal
  scoping.
- `capability_gaps(*, profile, manifest, proposal_capabilities=()) ->
  tuple[str, ...]` — `required − covered`, ordered by `Capability` declaration
  order (deterministic, no LLM).

I/O leaf (`context/domains/equip/plugins/sources.py`, extended — still the one
impure module, fake-runner tested):
- `resolve_ref(repo, *, runner=default_runner) -> str | None` — `gh api
  repos/{repo}/commits/HEAD` → pinned sha.
- `list_skills(repo, *, ref=None, runner=default_runner) -> tuple[SkillRef, ...]`
  — enumerate `<repo>` skill dirs (`*/SKILL.md`, and `skills/*/SKILL.md`) via the
  contents API at `ref`.
- `fetch_file(repo, path, *, ref=None, runner=default_runner)` — gains an
  optional `ref` (contents API `?ref=`); back-compat default `None` = HEAD.

CLI wire (`cli/equip/discover.py`):
- `_needed_caps` → delegates to `capability_gaps` (manifest-aware).
- `_collect_catalogs` admits collection seeds (enumerated as vendor candidates).
- `run_install` branches on `pi.mechanism is InstallMechanism.VENDOR`.
- `_record_vendored(...)` — mirror of `_record_native`, persisting the VENDORED
  item built by `vendored_item`.

Build loop (`cli/build_loop/waves.py`): a structured `missing-capability` signal
on `general-purpose` fallback (additive; existing dispatch contract unchanged).

## Acceptance

- [ ] `capability_gaps` returns `required − covered`, deterministic order; a repo
      whose manifest already covers a capability never re-lists it; pure (no I/O).
- [ ] `equip install <skill>@<trusted-collection>` (fake runner + tmp repo)
      writes `.claude/skills/<name>/SKILL.md` stamped with `VENDORED_SENTINEL`,
      records a `source=vendored, mechanism=vendor` item whose `origin_ref` is a
      40-hex sha (not `None`, not a semver).
- [ ] An untrusted collection still requires `--yes`; the usage-doc gate still
      fires; a user-edited vendored skill classifies USER_MODIFIED and is never
      re-fetched by `refresh`; `uninstall` removes file + record.
- [ ] `equip discover` (no query) prints the capabilities it is filling and ranks
      by the real gap, not the 2-tag stub.
- [ ] Build's `general-purpose` fallback emits the missing-capability signal;
      plan/build SKILL.md document the gated discover→approve→vendor loop.
- [ ] Full suite green (`conventions/testing.md`); `.context/features/equip/*`
      updated and its two open questions retired.
