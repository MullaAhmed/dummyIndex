# Equip Plugin Usage Interview — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `equip install` require a usage playbook for every plugin (capturing how it's used in this repo), with a non-interactive escape, and surface plugins missing one in `equip status`.

**Architecture:** The CLI (`equip install`) gains `--usage-doc PATH` / `--skip-usage-doc` and records the playbook path in the manifest item's existing `grounded_in`. The gate runs *after* the `--yes` approval check so approval errors keep priority. `equip status` reports a marketplace/vendored item with empty `grounded_in` as `incomplete`. The council (`skills/equip/SKILL.md`) gains a documented interview step that writes the playbook then installs with `--usage-doc`. No manifest schema change.

**Tech Stack:** Python 3.13, pytest, the existing equip fake-runner test harness (`tests/context/domains/equip/test_equip_discover_cli.py`).

**Environment note:** the project `.venv` is currently a broken symlink. Run tests with `PYTHONPATH=. python3 -m pytest …` (system Python 3.12) until the venv is recreated. All commands below use that form.

---

## File Structure

- **Modify** `dummyindex/cli/equip/discover.py` — add `_validate_usage_doc` helper; parse `--usage-doc`/`--skip-usage-doc` in `run_install`; gate after approval; thread the recorded path into `_record_native` → `grounded_in`.
- **Modify** `dummyindex/context/domains/equip/lifecycle/status.py` — add `missing_playbook` to `StatusReport`; populate it in `status()`.
- **Modify** `dummyindex/cli/equip/verbs.py` — render the `missing_playbook` section in `run_status` (text + JSON).
- **Modify** `tests/context/domains/equip/test_equip_discover_cli.py` — update 4 existing success-path install tests to pass `--skip-usage-doc`; add new gate/capture tests.
- **Modify** `tests/context/domains/equip/test_equip_lifecycle_plugins.py` — add status `incomplete` tests.
- **Modify** `dummyindex/skills/equip/SKILL.md` — document the interview step, the playbook template, the `--usage-doc`/`--repo` flags, and add a checklist line.

---

## Task 1: Keep existing install tests green under the new gate

The gate (Task 2) makes a bare `equip install` fail. Four existing tests reach a *successful* install and must opt out explicitly first, so the suite is green before and after the gate lands.

**Files:**
- Test: `tests/context/domains/equip/test_equip_discover_cli.py`

- [ ] **Step 1: Add `--skip-usage-doc` to the four success-path install tests**

In each of these tests, add `"--skip-usage-doc"` to the `run_equip([...])` arg list (anywhere after `"install"`):
- `test_install_trusted_native_writes_settings_and_manifest`
- `test_install_untrusted_codeplugin_allowed_with_yes`
- `test_install_local_scope_writes_local_settings_and_records_path`
- `test_install_explicit_repo_installs_undiscoverable_plugin`

Example (first one):

```python
def test_install_trusted_native_writes_settings_and_manifest(monkeypatch, tmp_path):
    _install_fake_runner(monkeypatch)
    rc = run_equip(
        ["install", "pg-tuner@claude-plugins-official", "--skip-usage-doc", "--root", str(tmp_path)]
    )
    assert rc == 0
    ...
```

Leave the other install tests unchanged — they exit before the gate (approval refusal → rc 1, not-found → rc 1, bad scope/repo → rc 2).

- [ ] **Step 2: Run the suite — still green (gate not added yet, flag is currently ignored as unknown)**

Run: `PYTHONPATH=. python3 -m pytest tests/context/domains/equip/test_equip_discover_cli.py -q`
Expected: PASS. (`--skip-usage-doc` is silently dropped by `pull_*` helpers today; the assertions are unchanged.)

- [ ] **Step 3: Commit**

```bash
git add tests/context/domains/equip/test_equip_discover_cli.py
git commit -m "test(equip): opt existing install tests out of the upcoming usage-doc gate"
```

---

## Task 2: CLI gate + capture in `run_install`

**Files:**
- Modify: `dummyindex/cli/equip/discover.py` (`run_install`, new `_validate_usage_doc`, `_record_native`)
- Test: `tests/context/domains/equip/test_equip_discover_cli.py`

- [ ] **Step 1: Write the failing tests**

Add to `test_equip_discover_cli.py`. The fixture catalog already has trusted `pg-tuner@claude-plugins-official` (no approval needed — exercises the gate cleanly):

```python
def test_install_requires_usage_doc_or_skip(monkeypatch, tmp_path):
    _install_fake_runner(monkeypatch)
    rc = run_equip(["install", "pg-tuner@claude-plugins-official", "--root", str(tmp_path)])
    assert rc == 2
    assert not (tmp_path / ".claude" / "settings.json").exists()


def test_install_usage_doc_and_skip_conflict(monkeypatch, tmp_path):
    _install_fake_runner(monkeypatch)
    doc = tmp_path / "play.md"
    doc.write_text("# how to use\n")
    rc = run_equip(
        [
            "install", "pg-tuner@claude-plugins-official",
            "--usage-doc", str(doc), "--skip-usage-doc", "--root", str(tmp_path),
        ]
    )
    assert rc == 2


def test_install_usage_doc_missing_file_errors(monkeypatch, tmp_path):
    _install_fake_runner(monkeypatch)
    rc = run_equip(
        [
            "install", "pg-tuner@claude-plugins-official",
            "--usage-doc", str(tmp_path / "nope.md"), "--root", str(tmp_path),
        ]
    )
    assert rc == 1
    assert not (tmp_path / ".claude" / "settings.json").exists()


def test_install_usage_doc_recorded_in_grounded_in(monkeypatch, tmp_path):
    _install_fake_runner(monkeypatch)
    doc = tmp_path / ".context" / "equipment" / "pg-tuner.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("# pg-tuner — usage in this repo\n")
    rc = run_equip(
        [
            "install", "pg-tuner@claude-plugins-official",
            "--usage-doc", str(doc), "--root", str(tmp_path),
        ]
    )
    assert rc == 0
    manifest = json.loads((tmp_path / ".context" / "equipment.json").read_text())
    item = next(i for i in manifest["items"] if i["name"] == "pg-tuner@claude-plugins-official")
    assert item["grounded_in"] == [".context/equipment/pg-tuner.md"]


def test_install_skip_usage_doc_leaves_grounded_in_empty(monkeypatch, tmp_path):
    _install_fake_runner(monkeypatch)
    rc = run_equip(
        ["install", "pg-tuner@claude-plugins-official", "--skip-usage-doc", "--root", str(tmp_path)]
    )
    assert rc == 0
    manifest = json.loads((tmp_path / ".context" / "equipment.json").read_text())
    item = next(i for i in manifest["items"] if i["name"] == "pg-tuner@claude-plugins-official")
    assert item["grounded_in"] == []


def test_install_approval_error_precedes_usage_gate(monkeypatch, tmp_path):
    # An untrusted plugin without --yes fails on approval (rc 1) before the usage
    # gate is evaluated — approval keeps priority.
    _install_fake_runner(monkeypatch)
    rc = run_equip(["install", "pg-tuner@claude-plugins-community", "--root", str(tmp_path)])
    assert rc == 1


def test_install_usage_doc_outside_repo_recorded_absolute(monkeypatch, tmp_path, capsys):
    # A playbook outside the repo root is recorded as an absolute path, with a
    # warning that it won't travel with the committed manifest.
    _install_fake_runner(monkeypatch)
    root = tmp_path / "proj"
    root.mkdir()
    outside = tmp_path / "external.md"  # sibling of proj, outside the repo root
    outside.write_text("# external playbook\n")
    rc = run_equip(
        ["install", "pg-tuner@claude-plugins-official", "--usage-doc", str(outside), "--root", str(root)]
    )
    assert rc == 0
    assert "outside the repo" in capsys.readouterr().err
    manifest = json.loads((root / ".context" / "equipment.json").read_text())
    item = next(i for i in manifest["items"] if i["name"] == "pg-tuner@claude-plugins-official")
    assert item["grounded_in"] == [str(outside.resolve())]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=. python3 -m pytest tests/context/domains/equip/test_equip_discover_cli.py -k "usage_doc or skip or approval_error" -q`
Expected: FAIL — gate not implemented (bare install currently returns rc 0, `grounded_in` stays `[]`).

- [ ] **Step 3: Add the `_validate_usage_doc` helper**

In `dummyindex/cli/equip/discover.py`, add after `_parse_repo_flag`:

```python
def _validate_usage_doc(
    project_root: Path, usage_doc: str | None, skip: bool
) -> tuple[str | None, int | None]:
    """Resolve the mandatory usage-playbook flags for a plugin install.

    Returns ``(recorded_path_or_None, error_rc_or_None)``: a repo-relative POSIX
    path to record in ``grounded_in`` (or ``None`` when skipped), and an exit
    code to return immediately on error (or ``None`` to proceed). An absolute
    path outside the repo is recorded as-is with a warning — it won't travel
    with the committed manifest.
    """
    if usage_doc is not None and skip:
        print(
            "error: pass either --usage-doc <path> or --skip-usage-doc, not both",
            file=sys.stderr,
        )
        return None, 2
    if usage_doc is None and not skip:
        print(
            "error: a plugin install needs a usage playbook — the /dummyindex-equip "
            "council writes one, or pass --usage-doc <path> (or --skip-usage-doc to "
            "opt out).",
            file=sys.stderr,
        )
        return None, 2
    if skip:
        return None, None
    doc = Path(usage_doc)  # usage_doc is not None here
    if not doc.is_file():
        print(f"error: --usage-doc {usage_doc}: file not found", file=sys.stderr)
        return None, 1
    resolved = doc.resolve()
    try:
        return resolved.relative_to(project_root.resolve()).as_posix(), None
    except ValueError:
        print(
            f"warning: --usage-doc {doc} is outside the repo; recording an "
            "absolute path",
            file=sys.stderr,
        )
        return str(resolved), None
```

- [ ] **Step 4: Parse the flags + run the gate in `run_install`**

In `run_install`, add flag parsing alongside the existing `--repo` parsing (after the `--repo` block, before `project_root, rest = _parse_root(rest)`):

```python
    usage_doc, rest = pull_flag_value(rest, "usage-doc")
    skip_usage_doc, rest = pull_bool_flag(rest, "skip-usage-doc")
```

Then place the gate **after** the approval check and **before** the settings write. Locate this existing block:

```python
    if pi.requires_approval and not yes:
        print(
            f"error: {target} requires approval (untrusted source"
            f"{'; surfaces: ' + ', '.join(pi.blast.surfaces) if pi.blast.surfaces else ''}). "
            "Re-run with --yes to approve.",
            file=sys.stderr,
        )
        return 1

    settings = _settings_path_for_scope(project_root, scope)
```

Insert the gate between them:

```python
    if pi.requires_approval and not yes:
        print(
            f"error: {target} requires approval (untrusted source"
            f"{'; surfaces: ' + ', '.join(pi.blast.surfaces) if pi.blast.surfaces else ''}). "
            "Re-run with --yes to approve.",
            file=sys.stderr,
        )
        return 1

    usage_rel, usage_rc = _validate_usage_doc(project_root, usage_doc, skip_usage_doc)
    if usage_rc is not None:
        return usage_rc

    settings = _settings_path_for_scope(project_root, scope)
```

- [ ] **Step 5: Thread the recorded path into `_record_native`**

Update the `_record_native` call site (inside the `if scope in (None, "project", "local"):` block):

```python
            _record_native(project_root, chosen, settings_rel=settings_rel, usage_doc_rel=usage_rel)
```

Update the `_record_native` signature + the `EquipmentItem(...)` it builds:

```python
def _record_native(
    project_root: Path, chosen: Candidate, *, settings_rel: str, usage_doc_rel: str | None = None
) -> None:
    context_dir = project_root / ".context"
    prior = read_manifest(context_dir)
    name = f"{chosen.plugin.name}@{chosen.marketplace}"
    item = EquipmentItem(
        kind=EquipmentKind.AGENT,
        name=name,
        path=settings_rel,
        source=EquipmentSource.MARKETPLACE,
        capabilities=chosen.capabilities,
        grounded_in=(usage_doc_rel,) if usage_doc_rel else (),
        marketplace=chosen.marketplace,
        origin_repo=chosen.repo,
        origin_ref=chosen.plugin.version,
        mechanism=InstallMechanism.NATIVE.value,
    )
    items = tuple(i for i in prior.items if i.name != name) + (item,)
    write_manifest(context_dir, EquipmentManifest(schema_version=SCHEMA_VERSION, items=items))
```

- [ ] **Step 6: Run the new tests + the full discover suite**

Run: `PYTHONPATH=. python3 -m pytest tests/context/domains/equip/test_equip_discover_cli.py -q`
Expected: PASS (all, including the Task-1-updated tests).

- [ ] **Step 7: Commit**

```bash
git add dummyindex/cli/equip/discover.py tests/context/domains/equip/test_equip_discover_cli.py
git commit -m "feat(equip): require a usage playbook on plugin install (--usage-doc/--skip-usage-doc)"
```

---

## Task 3: `equip status` reports plugins missing a usage playbook

**Files:**
- Modify: `dummyindex/context/domains/equip/lifecycle/status.py` (`StatusReport`, `status`)
- Test: `tests/context/domains/equip/test_equip_lifecycle_plugins.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/context/domains/equip/test_equip_lifecycle_plugins.py` (it already imports the lifecycle `status` and builds manifests — match its existing import style and `EquipmentItem`/`EquipmentManifest` construction):

```python
def test_status_flags_marketplace_item_without_playbook(tmp_path):
    from dummyindex.context.domains.equip.lifecycle.status import status
    from dummyindex.context.domains.equip.models import EquipmentItem, EquipmentManifest
    from dummyindex.context.domains.equip.enums import EquipmentKind, EquipmentSource

    grounded = EquipmentItem(
        kind=EquipmentKind.AGENT, name="has-doc@mkt", path=".claude/settings.json",
        source=EquipmentSource.MARKETPLACE, grounded_in=(".context/equipment/has-doc.md",),
        mechanism="native",
    )
    ungrounded = EquipmentItem(
        kind=EquipmentKind.AGENT, name="no-doc@mkt", path=".claude/settings.json",
        source=EquipmentSource.MARKETPLACE, grounded_in=(), mechanism="native",
    )
    report = status(tmp_path, EquipmentManifest(schema_version=3, items=(grounded, ungrounded)))
    assert report.missing_playbook == ("no-doc@mkt",)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `PYTHONPATH=. python3 -m pytest tests/context/domains/equip/test_equip_lifecycle_plugins.py::test_status_flags_marketplace_item_without_playbook -v`
Expected: FAIL — `StatusReport` has no `missing_playbook` attribute.

- [ ] **Step 3: Add the field + populate it**

In `dummyindex/context/domains/equip/lifecycle/status.py`, extend `StatusReport`:

```python
@dataclass(frozen=True)
class StatusReport:
    items: tuple[tuple[str, ItemState, str | None], ...] = ()
    missing_playbook: tuple[str, ...] = ()
```

Update `status()` to compute it (a marketplace/vendored item with empty `grounded_in`):

```python
def status(root: Path, manifest: EquipmentManifest) -> StatusReport:
    """Classify every tracked item: generated + vendored by origin-hash, and
    marketplace items by whether their ``enabledPlugins`` key is still set.
    Also flag plugin items (marketplace/vendored) that carry no usage playbook
    in ``grounded_in`` — they are wired but undocumented."""
    rows: list[tuple[str, ItemState, str | None]] = []
    missing_playbook: list[str] = []
    for item in manifest.items:
        if is_lifecycle_managed(item) or is_vendored_file(item):
            rows.append((item.name, classify_item(root, item), item.version))
        elif item.source == EquipmentSource.MARKETPLACE:
            rows.append((item.name, _classify_marketplace(root, item), item.version))
        if (
            item.source in (EquipmentSource.MARKETPLACE, EquipmentSource.VENDORED)
            and not item.grounded_in
        ):
            missing_playbook.append(item.name)
    return StatusReport(items=tuple(rows), missing_playbook=tuple(missing_playbook))
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `PYTHONPATH=. python3 -m pytest tests/context/domains/equip/test_equip_lifecycle_plugins.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dummyindex/context/domains/equip/lifecycle/status.py tests/context/domains/equip/test_equip_lifecycle_plugins.py
git commit -m "feat(equip): status flags plugins wired without a usage playbook"
```

---

## Task 4: Render the `incomplete` state in `equip status` CLI

**Files:**
- Modify: `dummyindex/cli/equip/verbs.py` (`run_status`)
- Test: `tests/context/domains/equip/test_equip_lifecycle_plugins.py`

- [ ] **Step 1: Write the failing test**

This test drives the CLI end-to-end. It installs a plugin with `--skip-usage-doc` (empty grounding) then asserts `status` text names it as incomplete. Add to `test_equip_lifecycle_plugins.py`, reusing the discover-CLI fake runner:

```python
def test_status_cli_reports_incomplete_playbook(monkeypatch, tmp_path, capsys):
    from tests.context.domains.equip.test_equip_discover_cli import _install_fake_runner
    from dummyindex.cli.equip import run as run_equip

    _install_fake_runner(monkeypatch)
    assert run_equip(
        ["install", "pg-tuner@claude-plugins-official", "--skip-usage-doc", "--root", str(tmp_path)]
    ) == 0
    capsys.readouterr()  # drop install output
    rc = run_equip(["status", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "incomplete" in out
    assert "pg-tuner@claude-plugins-official" in out
    assert "usage playbook" in out
```

(If `tests/` is not importable as a package in this repo, replace the cross-module import by pasting the fake-runner setup inline — check whether `tests/context/domains/equip/__init__.py` exists; the repo mirrors the source tree, so sibling test imports work.)

- [ ] **Step 2: Run the test to verify it fails**

Run: `PYTHONPATH=. python3 -m pytest tests/context/domains/equip/test_equip_lifecycle_plugins.py::test_status_cli_reports_incomplete_playbook -v`
Expected: FAIL — `status` output has no "incomplete" line.

- [ ] **Step 3: Render the section**

In `dummyindex/cli/equip/verbs.py`, update `run_status`. Add to the JSON payload and the text output.

JSON branch — extend the payload dict:

```python
    if as_json:
        payload = {
            "items": [
                {"name": name, "state": state.value, "version": version}
                for name, state, version in report.items
            ],
            "missing_playbook": list(report.missing_playbook),
        }
        print(json.dumps(payload, indent=2))
        return 0
```

Text branch — after the items loop, before `return 0`:

```python
    print("equip status:")
    for name, state, version in report.items:
        ver = version or "-"
        print(f"  {state.value:13} {name}  (v{ver})")
    for name in report.missing_playbook:
        print(f"  {'incomplete':13} {name}  (no usage playbook)")
    return 0
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `PYTHONPATH=. python3 -m pytest tests/context/domains/equip/test_equip_lifecycle_plugins.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dummyindex/cli/equip/verbs.py tests/context/domains/equip/test_equip_lifecycle_plugins.py
git commit -m "feat(equip): render incomplete-playbook plugins in equip status output"
```

---

## Task 5: Council interview + playbook template in the skill doc

**Files:**
- Modify: `dummyindex/skills/equip/SKILL.md`

- [ ] **Step 1: Add an interview subsection to the Plugin manager section**

In `dummyindex/skills/equip/SKILL.md`, in the "Plugin manager (discover + install)" section, after the `discover`/`install` bullets, add:

````markdown
### Usage interview (required before an install is "done")

A plugin equip is **not complete** until you've captured *how it's used in this
repo* — never wire one on assumptions. After `discover` shows the blast radius
and before `install`, interview the user **one question at a time**:

1. **Purpose here** — what is this plugin for in *this* repo specifically?
2. **When to use** — which tasks or signals should activate its skills/agents/commands?
3. **When NOT to use** — where should it stay out of the way?
4. **Constraints / guardrails** — scopes, side effects, data it touches.
5. **Scope** — `project` (default, committed) / `local` / `user`?

Write the answers to `.context/equipment/<plugin>.md` using this template:

```markdown
# <plugin> — usage in this repo

**Source:** <plugin>@<marketplace> (<owner/repo>)
**Scope:** project | local | user

## Purpose here
…

## When to use
…

## When NOT to use
…

## Constraints & guardrails
…
```

Then install, passing the playbook:

```bash
dummyindex context equip install <plugin>@<marketplace> [--repo <owner>/<name>] \
  [--yes] --scope <scope> --usage-doc .context/equipment/<plugin>.md
```

`--usage-doc` records the playbook in the manifest's `grounded_in`. For automation
only, `--skip-usage-doc` opts out — a plugin with no playbook shows **incomplete**
in `equip status`. Use `--repo <owner>/<name>` when the marketplace lives in a
low-profile repo that `discover` (seed list + GitHub search) doesn't surface.
````

- [ ] **Step 2: Add a checklist line**

In the "Checklist (verify before claiming done)" section, add:

```markdown
- [ ] Each plugin install captured a usage playbook at `.context/equipment/<plugin>.md`
      recorded in `grounded_in` (or was explicitly `--skip-usage-doc`); `equip status`
      shows no unintended `incomplete` plugins.
```

- [ ] **Step 3: Commit**

```bash
git add dummyindex/skills/equip/SKILL.md
git commit -m "docs(equip): council interviews for plugin usage + documents --usage-doc/--repo"
```

---

## Task 6: Full-suite verification + review

**Files:** none (verification only)

- [ ] **Step 1: Run the whole suite**

Run: `PYTHONPATH=. python3 -m pytest -q`
Expected: PASS (1004 prior + the new tests; zero failures).

- [ ] **Step 2: Live smoke (read-only, real repo)**

Run:
```bash
cd /tmp && rm -rf usage-smoke && mkdir usage-smoke
printf '# canvas-to-code — usage\n' > /tmp/usage-smoke/play.md
PYTHONPATH=/mnt/windows-ssd/Projects/memory/dummyindex python3 -m dummyindex context equip \
  install canvas-to-code@canvas-to-code-marketplace --repo opensesh/canvas-to-code --yes \
  --scope project --usage-doc /tmp/usage-smoke/play.md --root /tmp/usage-smoke
```
Expected: succeeds; `/tmp/usage-smoke/.context/equipment.json` records `grounded_in` with the playbook path (absolute, since it's outside that root — warning shown). Then bare install without the flags → rc 2 with the council-pointing message.

- [ ] **Step 3: python-reviewer**

Dispatch the `python-reviewer` agent on the diff (`git diff main` for the branch). Address BLOCK/WARN findings; fix inline and re-run the suite.

- [ ] **Step 4: Final commit (if review fixes were made)**

```bash
git add -A
git commit -m "fix(equip): address python-reviewer findings on usage-doc gate"
```

---

## Notes for the implementer

- **Run order matters in `run_install`:** scope/repo validation (rc 2) → target parse (rc 2) → catalog fetch → match → approval (rc 1) → **usage gate (rc 2/1)** → write. The usage gate intentionally sits *after* approval so an untrusted-without-`--yes` install still reports the approval error first (a test asserts this).
- **`grounded_in` is repo-relative POSIX** for in-repo docs (matches how `path` is stored); an out-of-repo absolute path is recorded as-is with a warning.
- **Specialists are untouched:** they never go through `run_install` (they use `equip` / `add-specialist`), so the gate can't affect them. The `status` check keys on `source in {MARKETPLACE, VENDORED}`, which generated specialists (`GENERATED`) never match.
- **No schema bump:** `grounded_in` already exists on `EquipmentItem` and round-trips through `to_dict`/`from_dict`.
