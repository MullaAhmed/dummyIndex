# Plan — config-depth-wired-ux

> Ordered, file-path-naming tasks. Reused symbols cited from
> `.context/map/symbols.json`. Prefer reuse over net-new. No task is tagged
> `— via <tool>`: `.context/equipment.json` declares only generated specialists
> (python-implementer/tester/reviewer, dummyindex-security/docs, verify skill)
> and no marketplace plugins, so build routes these tasks to those specialists
> by keyword — a tag would be redundant. No external-capability gaps → no
> `equip discover`.

## Tasks

### Schema + model (shared scaffolding — everything depends on this)

1. **Add the depth + wired model to `Config`.** `dummyindex/context/domains/config.py`
   + `dummyindex/context/default_plugins.py`.
   - Define `WiredEntry` (frozen) and its `WiredKind(str, Enum)` (`plugin`/`skill`)
     in **base-layer `default_plugins.py`** (so `config.py` imports it *upward* —
     never the reverse — preserving the "imports nothing from `domains/`" rule).
     Give it `to_dict`/`from_dict` mirroring `equip/models.py:EquipmentItem`
     (emit enum `.value`s, tolerate absent optionals). Seed it from
     `DefaultPlugin` via one adapter so `target` formatting has one source.
   - In `config.py`: add `DepthCommand(str, Enum)` (members: `ingest`, `reconcile`,
     `audit`, `build` — **not** `rebuild`); add
     `command_depths: tuple[tuple[DepthCommand, CouncilMode], ...]` (immutable;
     serialize as a JSON object) and `wired: tuple[WiredEntry, ...]` to `Config`;
     drop `wire_superpowers`. Reuse `CouncilMode`, `_require_enum`, `_is_iterable`.
     Reject unknown `command_depths` keys via the `DepthCommand` `ValueError` path
     (mirror `_require_enum`), not a hand-rolled frozenset check.
   - Add `resolve_depth(context_dir, command, depth_flag) -> CouncilMode` to
     `config.py` (precedence flag → `command_depths[command]` → `mode` →
     `STANDARD`; invalid → `ConfigError` with the allowed set). See task 3.
   - Bump `CONFIG_SCHEMA_VERSION` → 2; `from_dict` migrates a v1 payload **in
     memory** (`wire_superpowers: true` → seeded `wired`; `false` → empty) instead
     of rejecting it; accept 2, reject 3+. Update `to_dict`, `default_config`,
     module docstring (regenerate the schema example to the full v2 shape).
   - Seed `default_config().wired` from `default_plugins.DEFAULT_PLUGINS` (import
     the data only — base-layer direction holds: `config` → `default_plugins`).
   - Add `dummyindex_version: str` to `Config`; `write_config` stamps the current
     version (`importlib.metadata.version("dummyindex")`, as `init.py:48-52` does)
     on every write; `read_config`/`from_dict` tolerate any value (never gate);
     v1→v2 migration populates it. Keep the version-read in one helper so callers
     don't duplicate the `importlib.metadata` dance. `status` labels this the
     *config*-writer version distinctly from `meta.dummyindex_version` (build).

2. **Tests for the schema/model first (TDD).** `tests/context/domains/test_config.py`.
   - Extend the existing `wire_superpowers` tests into: `wired` round-trip,
     `command_depths` round-trip + unknown-key rejection, v1→v2 migration both
     boolean values, schema-version-2 acceptance / v3 rejection, `WiredEntry`
     validation. Reuse `default_config_with` helper.

### Depth resolution (depends on 1)

3. **Point `audit` at the shared resolver.** `dummyindex/context/domains/audit/workspace.py`.
   - `resolve_depth` itself lives in `config.py` (task 1). Reduce
     `resolve_mode(context_dir, mode_flag)` to a thin wrapper that delegates to
     `resolve_depth(context_dir, DepthCommand.audit, mode_flag)`, so audit's
     existing callers/tests are undisturbed. Reuse `read_config`, `ConfigError`.
   - Unit tests in `tests/context/domains/test_config.py` (resolver lives there
     now) covering all four precedence rungs + invalid value; keep the existing
     `audit` workspace tests green.

4. **Thread `--depth` into each depth-bearing command's arg layer.**
   - Add `depth` to the **shared `cli/common.py:parse_kv_flags`** value-taking
     alphabet — do **not** import `onboard._pull_value_flag` into other `cli/`
     modules (avoids widening the cross-`cli`-import exception).
   - `dummyindex/cli/audit.py`: `--mode` stays audit-local in its `value_keys`;
     route `values.get("depth") or values.get("mode")` through
     `resolve_depth(.., DepthCommand.audit, ..)`; **error if both are supplied**.
   - `dummyindex/cli/init.py` (ingest/init), `dummyindex/cli/reconcile.py`, and
     the build-loop CLI: pull `--depth` via `parse_kv_flags` and pass the resolved
     `CouncilMode` into `council_batch.active_stages(mode, …)` (the named
     consumer). **`rebuild` is not touched** — it has no council stage.
   - CLI tests per touched command asserting the flag overrides config for one
     run and that `config.json` bytes are unchanged after the run.

### Wired reconcile (depends on 1)

5. **Evolve plugin wiring into a non-interactive `wired`-list reconciler.**
   `dummyindex/context/default_plugins.py`.
   - `wire_default_plugins` takes `tuple[WiredEntry, ...]` **as a parameter** (no
     `config` import — base-layer direction holds); `DEFAULT_PLUGINS` stays only as
     the `default_config` seed. **Classify-and-report only — never call `input()`
     / never block** (it runs inside best-effort, never-raise, headless init).
     Per entry vs. `.claude/settings.json` *presence*: **satisfied** (present),
     **acted** (declared+absent → wire it via `enable_plugin`/`add_marketplace` +
     best-effort `install_default_plugins`), **needs-user** (untrusted-needs-`--yes`,
     install failure, or any `kind: skill` entry — no skill-enable primitive).
     Extend `PluginWireResult` with a returned `needs_user` field; keep `errors`.
     Reuse `_already_decided`, `enable_plugin`, `install_default_plugins`.
   - **No version-staleness verdict** — settings.json carries no installed version;
     `WiredEntry.version` is recorded/surfaced, not used to trigger an update.
   - `resolve_enabled` precedence preserved (empty `wired` == opted out;
     `--no-superpowers` forces empty).
   - Tests in `tests/context/test_default_plugins.py` (+ migrate the
     `tests/test_install.py` opt-out case from a `wire_superpowers=False` config to
     `wired=()`): each outcome class asserted on the **result** with an injected
     fake runner (no stdin), plus the seed-from-config path.

6. **equip `install` writes back to `config.wired`.**
   `dummyindex/cli/equip/discover.py:run_install` (+ helper near `_record_native`).
   - After enabling in settings + recording the `equipment.json` MARKETPLACE item,
     read `config.json`; **only if it exists**, upsert a matching `WiredEntry`
     (`kind=plugin`, `target=<plugin>@<marketplace>`, descriptive version) keyed on
     the target, then `write_config`. **Absent config (e.g. `--scope user`) →
     skip-with-warning** — never materialize a seeded config as a side effect.
     Project/in-repo scope only (mirror the manifest-record gate). Never raise —
     warn-and-continue like the current manifest write; single-writer-per-repo.
   - Tests in the existing equip install test: assert the `wired` upsert + the
     `equipment.json` record agree on the key and don't diverge; assert
     `--scope user`/no-config does not raise and writes no `config.json`; assert a
     `write_config` failure is warned and leaves the install rc/manifest intact.

### Wire-up + UX (depends on 1, 5)

7. **Init wiring + needs-user *reporting* (not in-process prompting).**
   `dummyindex/cli/init.py`, `dummyindex/installer/install.py` (both call the
   wiring path).
   - Replace `cfg.wire_superpowers` reads (`init.py:98`, `install.py:373`) with
     passing `cfg.wired` into the reconciler. Extend `describe_wire_result` to
     render per-class counts (satisfied/acted/needs-user) as summary lines —
     `capsys`-assertable. **needs-user entries are reported here, never prompted
     here** (these paths are best-effort/headless). The actual user prompt is a
     `**GATE**`/main-session item raised only by the interactive `/dummyindex`
     reconcile surface; `status` is the durable recoverable view. Reuse
     `resolve_enabled`, `describe_wire_result`, `describe_install_result`.

8. **Config-UX audit fixes.** `config.py` docstring (task 1 covers it),
   `dummyindex/cli/onboard.py` usage banner, `dummyindex/cli/help.py`,
   `dummyindex/cli/status.py`.
   - `onboard`/`help`: document `--depth` + `command_depths` + `wired`.
   - `status`: surface effective depth per command, `wired` classification counts
     (reuse the reconciler's classify-and-report path read-only — do not mutate),
     and a `config`-writer-version line **labelled distinctly** from
     `meta.dummyindex_version` (build version) so there aren't two contradictory
     drift lines.
   - Tests: `tests/cli/test_status.py` — `capsys` substrings for depth/wired/version
     **plus** a no-mutate assertion (`config.json` bytes unchanged after `status`);
     `onboard`/`help` usage tests asserting `--depth`/`command_depths`/`wired`
     substrings (mirror `test_parse_install_help_prints_usage_and_exits_zero`).

9. **Rename `ModelChoice.OPUS_4_7` → `OPUS_4_8`.** `dummyindex/context/domains/config.py`
   + the two test modules (`tests/context/domains/test_config.py`,
   `tests/context/domains/audit/test_audit_domain.py` — the latter asserts the
   member name directly): **8 occurrences across 3 files** (`grep -rn OPUS_4_7
   dummyindex/ tests/`). Value `"opus-4.8"` unchanged, so configs/serialization are
   unaffected — pure identifier fix; move all sites in lockstep, then confirm the
   grep is empty and the suite is green.

### Verification (depends on all)

10. **Full suite + docs reconcile.** `python -m pytest tests/ -q --tb=short`.
    Update affected `.context/features/<id>/` docs (config-bearing: `audit-panel`,
    `equip`, `install-surface`, `cli-dispatch`) if behavior drifted from their
    spec, or note for a follow-up `reconcile`.
