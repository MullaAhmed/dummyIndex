# Codex Guidance Architecture Plan

confidence: INFERRED

## Bounded context

Codex Guidance owns the policy and lifecycle for dummyindex-managed Codex instruction files. It decides which Codex configuration layers are observable, which project-relative instruction candidates are safe, which target is active, whether the complete managed block fits Codex's byte budget, how project-block ownership survives refresh, and how managed blocks are removed. It does not own Codex configuration authoring, generic managed-block mutation, project installation orchestration, indexing, reconcile policy, or source-document discovery; those systems consume this feature's policy or provide its lower-level write primitive (`dummyindex/codex_guidance.py:1-7`, `dummyindex/context/output/agents_md.py:1-22`).

## Where it lives

- `dummyindex/codex_guidance.py` is the policy kernel. It is stdlib-only and centralizes Codex-home resolution, persistent configuration overlays, trust checks, fallback normalization, byte-budget resolution, and instruction-path classification (`dummyindex/codex_guidance.py:9-18`, `dummyindex/codex_guidance.py:21-253`).
- `dummyindex/context/output/agents_md.py` is the lifecycle adapter. It renders Codex-specific managed bodies and ownership metadata, resolves project/global targets, validates scope and budget, delegates managed-block mutation, discovers stale managed fallbacks, and aggregates cleanup results (`dummyindex/context/output/agents_md.py:10-31`, `dummyindex/context/output/agents_md.py:94-204`, `dummyindex/context/output/agents_md.py:207-446`).
- `dummyindex/context/output/bootstrap.py` is upstream infrastructure, not part of this bounded context. Codex Guidance reuses its marker parser and atomic, byte-preserving block insertion/removal primitives with Codex markers and place-first semantics (`dummyindex/context/output/bootstrap.py:82-180`, `dummyindex/context/output/agents_md.py:17-22`, `dummyindex/context/output/agents_md.py:110-129`).
- `tests/context/output/test_agents_md.py` is the behavioral contract for precedence, trust, scope containment, byte budgets, ownership, byte preservation, idempotency, and best-effort cleanup (`tests/context/output/test_agents_md.py:65-823`).

## Architecture in three sentences

The policy kernel overlays observable system, user, and explicitly trusted project configuration, then emits normalized candidates and limits without importing CLI, installer, pipeline, build, or output modules (`dummyindex/codex_guidance.py:37-181`). The lifecycle adapter uses a plan/apply split: `_project_guidance_plan` makes target, ownership, scope, and budget decisions; preflight returns that plan without writing; bootstrap delegates the approved mutation to the shared managed-block writer (`dummyindex/context/output/agents_md.py:110-161`). Cleanup expands beyond current configuration through a bounded marker scan, then removes each owned block independently and returns both successes and failures (`dummyindex/context/output/agents_md.py:273-346`, `dummyindex/context/output/agents_md.py:407-441`).

## Patterns named

- **Policy kernel:** one stdlib-only module defines instruction discovery semantics shared by file detection, doc collection, reconciliation, source-doc discovery, onboarding, and guidance output (`dummyindex/codex_guidance.py:1-18`, `dummyindex/pipeline/io/detect.py:10-13`, `dummyindex/context/build/common.py:15-20`, `dummyindex/context/build/reconcile.py:39-42`, `dummyindex/context/domains/source_docs/discovery.py:7-10`).
- **Trust-gated configuration overlay:** system config is lowest precedence, user config overlays it, and repository config participates only when the resolved root has an exact trusted entry in user-owned config (`dummyindex/codex_guidance.py:146-181`, `dummyindex/codex_guidance.py:208-230`).
- **Plan/apply split:** `_project_guidance_plan` is the single deterministic decision seam used by both preflight and write paths, preventing bootstrap from re-deciding target or ownership (`dummyindex/context/output/agents_md.py:110-161`).
- **Marker-bounded ownership:** dummyindex owns only content between exact managed markers; project metadata distinguishes explicit install, user auto-init, and legacy unowned blocks (`dummyindex/context/output/agents_md.py:24-31`, `dummyindex/context/output/agents_md.py:349-380`).
- **Fail-closed filesystem boundary:** normalized relative fallbacks and resolved containment checks prevent configured paths or symlinks from escaping project or Codex-home scope; byte-budget validation runs before mutation (`dummyindex/codex_guidance.py:233-253`, `dummyindex/context/output/agents_md.py:255-270`, `dummyindex/context/output/agents_md.py:383-404`).
- **Bounded stale-resource discovery:** uninstall scans for old managed fallbacks with explicit depth, file-count, byte, directory, and symlink limits (`dummyindex/context/output/agents_md.py:68-91`, `dummyindex/context/output/agents_md.py:273-346`).
- **Best-effort batch cleanup:** malformed or unsafe files become `AgentsMdCleanupIssue` records while safe targets continue through removal (`dummyindex/context/output/agents_md.py:94-107`, `dummyindex/context/output/agents_md.py:407-441`).

## Dependencies surfaced

### Upstream

- Python path, environment, and TOML facilities supply all policy-kernel dependencies; Python 3.10 uses the `tomli` compatibility import (`dummyindex/codex_guidance.py:9-18`).
- Shared bootstrap infrastructure supplies `ALWAYS_ON_OUTPUT_POLICY`, marker-span validation, idempotent place-first insertion, byte-preserving removal, and atomic file writes (`dummyindex/context/output/agents_md.py:17-22`, `dummyindex/context/output/bootstrap.py:26-31`, `dummyindex/context/output/bootstrap.py:82-180`).

### Downstream

- Installer and init/bootstrap commands create global or project guidance; the dual-host bootstrap preflights both Claude and Codex targets before either write (`dummyindex/installer/install.py:325-334`, `dummyindex/installer/install.py:404-455`, `dummyindex/cli/init.py:197-208`, `dummyindex/cli/bootstrap.py:33-69`).
- Uninstall consumes ownership-filtered cleanup results and reports per-file failures without failing unrelated removal (`dummyindex/installer/uninstall.py:170-214`).
- Onboarding uses active instruction candidates to infer Codex host coverage from exact managed markers (`dummyindex/cli/onboard.py:209-247`).
- File detection, document collection, reconcile filtering, and source-doc discovery use the same instruction-path policy so managed guidance is not treated as project content (`dummyindex/pipeline/io/detect.py:10-13`, `dummyindex/context/build/common.py:56-77`, `dummyindex/context/build/reconcile.py:39-42`, `dummyindex/context/domains/source_docs/discovery.py:58-78`).

### Cycle check

Dependency direction is acyclic in the inspected source: `codex_guidance.py` imports only stdlib/TOML compatibility; `agents_md.py` imports the policy kernel and sibling bootstrap infrastructure; CLI, installer, pipeline, build, and source-doc modules import downward into those APIs, with no reverse import from the kernel or adapter (`dummyindex/codex_guidance.py:9-18`, `dummyindex/context/output/agents_md.py:10-22`).

## Data model

- `CODEX_INSTRUCTION_PRECEDENCE` is the ordered standard candidate pair `AGENTS.override.md`, `AGENTS.md`; validated project fallbacks append after it without duplicates (`dummyindex/codex_guidance.py:21-25`, `dummyindex/codex_guidance.py:37-67`, `dummyindex/codex_guidance.py:90-101`).
- Effective Codex configuration remains transient ordered dictionaries. Invalid or unreadable layers are absent, and a valid empty higher-precedence fallback list deliberately clears a lower layer (`dummyindex/codex_guidance.py:37-67`, `dummyindex/codex_guidance.py:146-205`).
- Project ownership is a closed string set: `project` and `user-auto-init`; a managed block with no single valid owner is legacy-unowned (`dummyindex/context/output/agents_md.py:29-31`, `dummyindex/context/output/agents_md.py:355-380`).
- `AgentsMdCleanupIssue(path, message)` and `AgentsMdCleanupResult(removed, errors)` are frozen result records for independent cleanup outcomes (`dummyindex/context/output/agents_md.py:94-107`).

## Key decisions

- Keep project and global selection semantics distinct. Project selection follows Codex discovery by first existing regular candidate, including an empty override; global registration uses the first nonwhitespace standard candidate and otherwise creates `AGENTS.md` (`dummyindex/context/output/agents_md.py:164-180`, `dummyindex/context/output/agents_md.py:207-252`).
- Place the Codex managed block first. This keeps dummyindex guidance inside Codex's configured instruction-byte window while the shared writer preserves BOM and all user bytes outside the block (`dummyindex/context/output/bootstrap.py:90-132`, `dummyindex/context/output/agents_md.py:110-129`, `dummyindex/context/output/agents_md.py:383-404`).
- Require explicit user trust before repository configuration can redirect guidance or change its budget. Trust keys do not resolve configured aliases, preventing stale trusted symlinks from transferring trust (`dummyindex/codex_guidance.py:146-181`, `dummyindex/codex_guidance.py:208-230`).
- Preserve ownership on refresh. User auto-init may refresh an explicit or legacy block but does not claim it, and owner-filtered uninstall removes only an exact owner match (`dummyindex/context/output/agents_md.py:142-161`, `dummyindex/context/output/agents_md.py:355-380`, `dummyindex/context/output/agents_md.py:423-440`).
- Treat malformed current state conservatively. Unreadable active candidates remain selected so bootstrap surfaces the real error, out-of-scope targets are rejected, and malformed cleanup targets remain unchanged while other targets proceed (`dummyindex/context/output/agents_md.py:243-270`, `dummyindex/context/output/agents_md.py:407-441`).

## Open questions

- Runtime `-c` overrides, selected profiles, and launch-directory nested project layers remain outside the standalone CLI's observation boundary (`dummyindex/codex_guidance.py:146-155`). Any future parity work must obtain those values from Codex rather than infer them from persistent files.
- Outside-project absolute paths collapse to a basename for conservative instruction classification. This protects explicitly supplied external standard guidance but can classify more files than a live Codex launch-directory search would (`dummyindex/codex_guidance.py:111-143`, `dummyindex/codex_guidance.py:246-253`).
- Global selection is content-based while project selection is existence-based. The difference is source-evidenced and tested, but callers must not factor the selectors into one helper without preserving both contracts (`dummyindex/context/output/agents_md.py:207-252`).

## Audit trail

No catalogued prose document is quoted or used as authority. The generated architecture overview marks its linked prose advisory, and the previously identified general convention source is low-confidence with broken references; source imports, implementations, and tests govern this plan. No conflict was found between the developer draft and current source; this revision narrows ownership, names only demonstrated patterns, and makes dependency direction explicit.
