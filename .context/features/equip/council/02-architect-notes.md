# Architect notes — equip (stage 2)

## What I changed

- Added a **Bounded context** section stating equip's single responsibility
  (`.context/` spine → on-disk toolkit + lifecycle) and explicit out-of-scope
  (ingest, build skill, proposal authoring) so the seam is unambiguous.
- Promoted the loose "Where it lives" prose into wire-layer vs policy-layer with
  the I/O invariant stated up front (all reads/writes in `cli/equip/`; domain is
  pure, `sources.py` the lone exception).
- Replaced the flat "Key decisions" bullets with a **Patterns (named at
  path:range)** section — every pattern now carries a concrete `path:range`,
  including the manifest/hash-baselining oracle, generate-vs-adopt ladder,
  trust-tier gate, impersonation guard, patch seam, native-vs-vendor mechanism,
  and the safe-write guard.
- Added a **Dependencies** section (Upstream / Downstream / Cross-cutting /
  Cycles) — previously dependencies were implicit.
- Rewrote "Key decisions" as **decided X because Y** statements.
- Fixed two stale ranges: `SEED_MARKETPLACES` is `marketplace.py:49-64` (was
  `:43-64`, which is the dataclass not the seed list); `build_catalog` cited as
  `catalog.py:60-91` (was the file header `:1-21`).
- Cut filler ("Architecture in three sentences" kept — load-bearing; no
  astronautics added).

## Patterns named

| Pattern | Location |
|---|---|
| Hash-baselining (ownership oracle) | `lifecycle/hashing.py:16-18` + `lifecycle/status.py:137-165` |
| Manifest MERGE-never-rebuild | `dispatch.py:381-400`, `:498-517` |
| Generate-vs-adopt precedence ladder | `adopt.py:81-144` (loop `:120-141`) |
| Stack-consistency gate | `adopt.py:134-138` + `catalog.py:49-57` |
| Trust-tier + blast-radius approval gate | `install_plan.py:35-48` (gate `:42`) + `marketplace.py:49-64` |
| Reserved-name impersonation guard | `discover.py:57-59` + `:104-123` |
| Patch seam | `evolve.py:25-70` |
| Native-vs-vendor mechanism | `install_plan.py:37-39` + `plugins/vendor.py` |
| Safe-write guard | `wiring/safety.py:1-33` |

All ranges verified against source this session.

## Dependencies surfaced

- **Upstream:** ingest artefacts (`map/files.json`, convention docs) read-only via
  `detect_stack`; `PreflightReport` (`preflight/models.py`); proposal text (via
  `proposal.py`, only under `--for-proposal`); `atomic_io.write_text_atomic`.
- **Downstream:** the build skill (reads `.context/equipment.json`);
  `.claude/settings.json` format-hook consumers; generated `.md` agents/skills.
- **Cycles:** none. CLI → domain only (never reverse); `evolve.py` imports
  `status._bump` / `is_lifecycle_managed` downward within the package.

## Decisions promoted

- Origin-hash baselining over a forgeable sentinel.
- Manifest write is a MERGE so `apply` never drops a prior record.
- Forced caps generate before project-agent preference; template still beats
  registry adoption.
- Trust is sourced from seed list / discovery path, never candidate JSON →
  untrusted always gates on `--yes` regardless of `runs_code`.
- Reserved seed names from a foreign repo rejected as impersonation.
- Backend-only stack never adopts Frontend Developer off plan-text keywords; skip
  surfaced not silent.
- Patch seam is the only sanctioned evolution path (re-baselines + patch-bumps to
  stay PRISTINE).
