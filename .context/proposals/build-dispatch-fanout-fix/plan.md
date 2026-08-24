# Plan — build-dispatch-fanout-fix

> Ordered, file-path-naming tasks; reuse over net-new. All paths verified.

## Tasks

1. **Classifier.** `dummyindex/context/domains/buildloop/models.py`: extend
   `dispatch_mode(item, agent_names: frozenset[str] | None = None)` — `via` starting
   `agent:` → `SUBAGENT`; bare `via` matching `agent_names` → `SUBAGENT` (caller adds
   the upgrade note); otherwise current behaviour. Keep default-arg purity so existing
   callers/tests stay valid.
2. **Mapper wiring + payload keys.** `dummyindex/cli/build_loop/waves.py`: in
   `_entry_for` (and `_dispatchable` pool construction), pass the pool's agent-name
   frozenset into `dispatch_mode`; when the bare-name upgrade fires AND the pinned
   entry carries a non-null `subagent_type`, pin the Choice to that entry (skip
   capability scoring) — untyped legacy entries stay MAIN_SESSION with an
   `upgrade_note` explaining why. `agent:<name>` not matching a kind-agent entry also
   stays MAIN_SESSION with a warning `upgrade_note`. Set additive keys on the
   do_next/do_next_wave payloads (`routing`, `upgrade_note`) here in waves.py where
   those payloads are built.
3. **Routing plumbing.** New module
   `dummyindex/context/domains/buildloop/routing.py` (NEW):
   `resolve_routing(proposal_json, cli_override) -> dict` with alias validation via
   `ModelChoice` from `domains/config.py` (domain stays wire-free per coding-practices).
   Token parsing lives CLI-side: add `--route k=v` to
   `dummyindex/cli/build_loop/dispatch.py::run` arg handling and to
   `dummyindex/cli/propose.py::_parse_propose_args` (both NEW flag surfaces). Template
   note: optional `routing` object documented where `domains/proposals/store.py`
   writes `proposal.json` (`_TEMPLATE_FILES` writers).
4. **Payload disclosure.** `cli/build_loop/dispatch.py::_do_status` renders resolved
   routing; `waves.py::do_next/do_next_wave` payloads gain `"routing"` +
   `"upgrade_note"` keys; build skill opening step prints the `models:` line (T5).
5. **Skill docs.** Packaged skills: `plan/SKILL.md` step 6 gains the two-class rule
   (`agent:<name>` for generated agents; binding `— via` reserved for plugin commands,
   skills, MCP-bound tools) and its step 8 assertion ("GATE and `— via` items are
   main-session") is updated to the two-class wording. `build/SKILL.md` via-rules
   sections document the carve-out, `--route`, proposal `routing`, the printed
   disclosure line, and that substitution-failure applies only to genuine tool tags.
6. **Tests** (disjoint files):
   - extend `tests/context/domains/buildloop/test_models.py` (or nearest existing home)
     — classifier matrix.
   - new `tests/cli/test_waves_upgrade.py` — pool-upgrade pinning + upgrade_note.
   - new `tests/context/domains/test_model_routing.py` — precedence + validation.
   - grep-level doc test added to the waves test file or docs test home.

## Wave disjointness

| Wave | Items | Files |
|---|---|---|
| 1 | T1 | `domains/buildloop/models.py` |
| 1 | T3 | `domains/buildloop/routing.py` (NEW), `cli/build_loop/dispatch.py` (--route parse), `cli/propose.py` (--route parse), `domains/proposals/store.py` (template note) |
| 2 | T2 | `cli/build_loop/waves.py` (after T1; includes payload keys) |
| 2 | T5 | packaged skills md + `cli/help.py` USAGE (disjoint of waves.py) |
| 3 | T4 | `cli/build_loop/dispatch.py` (_do_status rendering; disjoint of waves.py) |
| 4 | T6a–T6d | one distinct test file each |
