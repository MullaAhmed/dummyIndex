# Codex Guidance Implementation Plan

confidence: INFERRED

## Where it lives

- `dummyindex/codex_guidance.py` owns business policy: instruction-name precedence, Codex-home discovery, layered TOML loading, project trust, safe fallback normalization, byte-budget resolution, and instruction-path classification (`dummyindex/codex_guidance.py:21-253`).
- `dummyindex/context/output/agents_md.py` owns filesystem plumbing: managed block bodies and markers, target selection, preflight, scope and budget validation, ownership metadata, installation, stale-file discovery, and cleanup result aggregation (`dummyindex/context/output/agents_md.py:24-446`).
- `tests/context/output/test_agents_md.py` specifies precedence, layered configuration, trust, symlink containment, byte preservation, byte budgets, ownership, idempotency, and independent cleanup failure behavior (`tests/context/output/test_agents_md.py:65-823`).

## Architecture in three sentences

The policy module resolves observable Codex configuration from system, user, and explicitly trusted project layers, then exposes normalized instruction candidates and limits (`dummyindex/codex_guidance.py:29-181`). The output module turns those values into a deterministic target plan, validates scope and byte capacity, and delegates managed-block mutation to shared byte-preserving helpers (`dummyindex/context/output/agents_md.py:110-180`, `dummyindex/context/output/agents_md.py:255-270`, `dummyindex/context/output/agents_md.py:383-441`). Removal widens discovery only through bounded, non-symlink-following scans and records per-path failures so one bad guidance file does not prevent cleanup elsewhere (`dummyindex/context/output/agents_md.py:273-346`, `dummyindex/context/output/agents_md.py:407-441`).

## Data model

- `CODEX_INSTRUCTION_PRECEDENCE` is the ordered pair `AGENTS.override.md`, `AGENTS.md`; validated configured fallbacks append after it (`dummyindex/codex_guidance.py:21-24`, `dummyindex/codex_guidance.py:90-101`).
- `AgentsMdCleanupIssue(path: Path, message: str)` describes one unsafe or malformed cleanup target; `AgentsMdCleanupResult(removed: tuple[Path, ...], errors: tuple[AgentsMdCleanupIssue, ...])` aggregates immutable independent outcomes (`dummyindex/context/output/agents_md.py:94-107`).
- Project block ownership is a closed string set: `project` for explicit project installation and `user-auto-init` for user-level automatic initialization. Legacy blocks without one valid owner remain unowned (`dummyindex/context/output/agents_md.py:29-31`, `dummyindex/context/output/agents_md.py:349-380`).
- Effective configuration is represented internally as ordered dictionaries loaded from TOML, with invalid layers treated as absent and only a trusted project root allowed to contribute a project layer (`dummyindex/codex_guidance.py:146-205`).

## Key decisions

- Preserve Codex's project selection semantics by choosing the first existing regular candidate, even if empty; global selection retains the older nonwhitespace behavior (`dummyindex/context/output/agents_md.py:207-240`).
- Fail closed at filesystem boundaries: normalize fallback paths before use, resolve selected targets before access, refuse scope escapes, and validate that the full managed block fits the Codex byte budget before mutation (`dummyindex/codex_guidance.py:233-243`, `dummyindex/context/output/agents_md.py:255-270`, `dummyindex/context/output/agents_md.py:383-404`).
- Keep persistent project configuration below an explicit user trust gate. A trusted symlink alias does not transfer trust to a different resolved repository key (`dummyindex/codex_guidance.py:146-181`, `dummyindex/codex_guidance.py:208-230`).
- Preserve user content and ownership across refreshes. User auto-init may update an existing explicit block but cannot relabel it, and owner-filtered uninstall leaves explicit or legacy-unowned blocks alone (`dummyindex/context/output/agents_md.py:142-161`, `dummyindex/context/output/agents_md.py:355-380`, `dummyindex/context/output/agents_md.py:423-440`).
- Bound stale-guidance discovery by file count, depth, bytes per file, skipped directories, and no directory-symlink traversal (`dummyindex/context/output/agents_md.py:68-91`, `dummyindex/context/output/agents_md.py:273-346`).
- Treat source as authoritative. No catalogued prose document is quoted here; the relevant general convention source is catalogued low-confidence, so it serves only as historical context and does not override the implementation.

## Open questions

- Runtime `-c` overrides, selected profiles, and nested launch-directory project layers are not observable to this standalone CLI; the implementation intentionally limits itself to persistent system, user, and repository-root configuration (`dummyindex/codex_guidance.py:146-155`).
- Outside-project absolute paths use basename matching for standard or single-component candidates because the CLI cannot know Codex's launch directory. This is conservative and may classify more external `AGENTS.md` files as guidance than a live Codex process would (`dummyindex/codex_guidance.py:111-143`).
- The global target selector uses nonwhitespace content while project target selection uses file existence. This is deliberate in current source but remains an asymmetry worth preserving explicitly in future changes (`dummyindex/context/output/agents_md.py:207-252`).
