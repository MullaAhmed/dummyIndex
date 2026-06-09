"""Tests for `dummyindex context equip` — templates-first toolkit rendering."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from dummyindex.cli.equip import _cmd_equip, _project_slug
from dummyindex.context.domains.equip import (
    GENERATED_SENTINEL,
    IMPLEMENTER_TEMPLATE,
    REVIEWER_TEMPLATE,
    SCHEMA_VERSION,
    TESTER_TEMPLATE,
    VERIFY_TEMPLATE,
    EquipmentItem,
    EquipmentKind,
    EquipmentManifest,
    StackProfile,
    build_catalog,
    content_hash,
    detect_stack,
    is_safe_to_write,
    render_generated_set,
    render_template,
)
from dummyindex.context.domains.preflight import PreflightReport, SettingsState


def _write_files_map(context_dir: Path, languages: list[str | None]) -> None:
    files = [
        {"path": f"src/f{i}.x", "language": lang, "size_bytes": 10}
        for i, lang in enumerate(languages)
    ]
    (context_dir / "map").mkdir(parents=True, exist_ok=True)
    (context_dir / "map" / "files.json").write_text(
        json.dumps({"schema_version": 1, "files": files}) + "\n", encoding="utf-8"
    )


# ----- stack detection ------------------------------------------------------


@pytest.mark.unit
def test_detect_stack_picks_dominant_language(tmp_path: Path) -> None:
    context_dir = tmp_path / ".context"
    _write_files_map(context_dir, ["python", "python", "python", "javascript"])
    profile = detect_stack(context_dir)
    assert profile.label == "python"


@pytest.mark.unit
def test_detect_stack_ties_break_alphabetically(tmp_path: Path) -> None:
    context_dir = tmp_path / ".context"
    _write_files_map(context_dir, ["python", "go"])
    profile = detect_stack(context_dir)
    assert profile.label == "go"  # tie -> alphabetical


@pytest.mark.unit
def test_detect_stack_missing_map_is_generic(tmp_path: Path) -> None:
    profile = detect_stack(tmp_path / ".context")
    assert profile.label == "generic"
    assert profile.frameworks == ()


@pytest.mark.unit
def test_detect_stack_ignores_null_languages(tmp_path: Path) -> None:
    context_dir = tmp_path / ".context"
    _write_files_map(context_dir, [None, None, "rust"])
    assert detect_stack(context_dir).label == "rust"


@pytest.mark.unit
def test_detect_stack_surfaces_frameworks_from_manifest(tmp_path: Path) -> None:
    context_dir = tmp_path / ".context"
    _write_files_map(context_dir, ["python"])
    (tmp_path / "pyproject.toml").write_text(
        'dependencies = ["fastapi", "uvicorn"]\n', encoding="utf-8"
    )
    profile = detect_stack(context_dir)
    assert "FastAPI" in profile.frameworks


# ----- toolchain detection --------------------------------------------------


@pytest.mark.unit
def test_detect_stack_python_toolchain_with_uv(tmp_path: Path) -> None:
    context_dir = tmp_path / ".context"
    _write_files_map(context_dir, ["python", "python"])
    (tmp_path / "pyproject.toml").write_text(
        "[tool.ruff]\n[tool.mypy]\n"
        'dependencies = ["pytest"]\n',
        encoding="utf-8",
    )
    (tmp_path / "uv.lock").write_text("# lock\n", encoding="utf-8")
    profile = detect_stack(context_dir)
    assert profile.test_runner == "pytest"
    assert profile.test_command == "uv run pytest -q"
    assert profile.linter == "ruff"
    # spec §2: uv-managed python commands run via the venv. Format is the
    # exception (spec §5, hook-shell, bare + binary-guarded).
    assert profile.lint_command == "uv run ruff check ."
    assert profile.type_checker == "mypy"
    assert profile.typecheck_command == "uv run mypy ."
    assert profile.formatter == "ruff"
    assert profile.format_command == 'ruff format "$CLAUDE_FILE_PATHS"'


@pytest.mark.unit
def test_detect_stack_python_without_uv_has_no_prefix(tmp_path: Path) -> None:
    context_dir = tmp_path / ".context"
    _write_files_map(context_dir, ["python"])
    (tmp_path / "pyproject.toml").write_text(
        '[tool.mypy]\ndependencies = ["pytest"]\n', encoding="utf-8"
    )
    profile = detect_stack(context_dir)
    assert profile.test_command == "pytest -q"
    assert profile.typecheck_command == "mypy ."


@pytest.mark.unit
def test_detect_stack_node_toolchain(tmp_path: Path) -> None:
    context_dir = tmp_path / ".context"
    _write_files_map(context_dir, ["javascript"])
    (tmp_path / "package.json").write_text(
        '{"devDependencies": {"jest": "^29", "prettier": "^3", "eslint": "^9"}}',
        encoding="utf-8",
    )
    profile = detect_stack(context_dir)
    assert profile.test_runner == "jest"
    assert profile.test_command == "npx jest"
    assert profile.linter == "eslint"
    assert profile.lint_command == "npx eslint ."
    assert profile.formatter == "prettier"
    assert profile.format_command == 'npx prettier --write "$CLAUDE_FILE_PATHS"'


@pytest.mark.unit
def test_detect_stack_empty_repo_toolchain_all_none(tmp_path: Path) -> None:
    profile = detect_stack(tmp_path / ".context")
    assert profile.label == "generic"
    assert profile.test_runner is None
    assert profile.test_command is None
    assert profile.linter is None
    assert profile.lint_command is None
    assert profile.type_checker is None
    assert profile.typecheck_command is None
    assert profile.formatter is None
    assert profile.format_command is None


# ----- render ----------------------------------------------------------------


@pytest.mark.unit
def test_render_fills_slots_and_grounds(tmp_path: Path) -> None:
    body = render_template(
        IMPLEMENTER_TEMPLATE,
        stack="python",
        proj="python",
        conventions=(".context/conventions/naming.md",),
    )
    assert "{{stack}}" not in body
    assert "{{conventions}}" not in body
    assert "{{context_root}}" not in body
    assert "python" in body
    assert ".context/conventions/naming.md" in body
    assert ".context" in body  # grounding present
    assert GENERATED_SENTINEL in body  # sentinel stamped for never-clobber
    # frontmatter MUST lead the file (byte 0) or Claude Code won't discover the
    # agent/skill — the sentinel lives in the body, not before `---`.
    assert body.startswith("---")
    assert body.index("name:") < body.index(GENERATED_SENTINEL)


@pytest.mark.unit
def test_render_empty_conventions_still_grounds(tmp_path: Path) -> None:
    body = render_template(
        IMPLEMENTER_TEMPLATE, stack="generic", proj="generic", conventions=()
    )
    assert "{{conventions}}" not in body
    assert ".context" in body


# ----- render v2: toolchain slots + version frontmatter ---------------------

_ALL_TEMPLATES = (
    IMPLEMENTER_TEMPLATE,
    TESTER_TEMPLATE,
    REVIEWER_TEMPLATE,
    VERIFY_TEMPLATE,
)


@pytest.mark.unit
@pytest.mark.parametrize("template", _ALL_TEMPLATES)
def test_every_template_frontmatter_first_with_version(template: str) -> None:
    body = render_template(
        template,
        stack="python",
        proj="backend",
        conventions=(".context/conventions/naming.md",),
        test_command="uv run pytest -q",
        lint_command="uv run ruff check .",
        typecheck_command="uv run mypy .",
        framework="FastAPI",
    )
    assert body.startswith("---")               # frontmatter at byte 0
    fm_end = body.index("\n---", 3)
    frontmatter = body[:fm_end]
    assert "version: 1.0.0" in frontmatter       # versioned artifact
    assert GENERATED_SENTINEL in body            # in-body generated marker
    assert body.index("name:") < body.index(GENERATED_SENTINEL)
    assert "{{" not in body                      # every slot filled


@pytest.mark.unit
def test_tester_embeds_test_command() -> None:
    body = render_template(
        TESTER_TEMPLATE,
        stack="python",
        proj="python",
        conventions=(),
        test_command="uv run pytest -q",
    )
    assert "uv run pytest -q" in body


@pytest.mark.unit
def test_reviewer_references_conventions_and_concerns() -> None:
    body = render_template(
        REVIEWER_TEMPLATE,
        stack="python",
        proj="python",
        conventions=(".context/conventions/naming.md",),
    )
    assert ".context/conventions/" in body
    assert "concerns.md" in body


# ----- render v3: {proj}- identifier vs {stack} prose -----------------------


def _frontmatter_name(body: str) -> str:
    """The ``name:`` value from a leading YAML frontmatter block."""
    assert body.startswith("---")
    for line in body.splitlines():
        if line.startswith("name:"):
            return line.split(":", 1)[1].strip()
    raise AssertionError("no name: line in frontmatter")


@pytest.mark.unit
@pytest.mark.parametrize("template", (REVIEWER_TEMPLATE, VERIFY_TEMPLATE))
def test_reviewer_and_verify_carry_proj_identifier(template: str) -> None:
    # proj != stack so a stale {{stack}}-based name would surface as the bug.
    body = render_template(template, stack="python", proj="backend", conventions=())
    suffix = "reviewer" if template is REVIEWER_TEMPLATE else "verify"
    # The *identifier* surfaces (frontmatter name + H1) carry the {proj} prefix.
    assert _frontmatter_name(body) == f"backend-{suffix}"
    assert f"# backend-{suffix}" in body
    # The prose body still describes the repo's real stack, not the proj slug.
    assert "**python**" in body
    assert "{{" not in body  # no dangling slot


@pytest.mark.unit
def test_implementer_verify_crossref_uses_proj() -> None:
    body = render_template(
        IMPLEMENTER_TEMPLATE, stack="python", proj="backend", conventions=()
    )
    # The hand-off points at the {proj}-verify skill that equip actually ships.
    assert "backend-verify" in body
    assert "python-verify" not in body
    # Implementer's own identifier stays {stack}-based by design.
    assert _frontmatter_name(body) == "python-implementer"


@pytest.mark.unit
def test_implementer_bakes_format_command() -> None:
    body = render_template(
        IMPLEMENTER_TEMPLATE,
        stack="python",
        proj="python",
        conventions=(),
        format_command="uv run ruff format .",
    )
    assert "uv run ruff format ." in body
    assert "{{format_command}}" not in body


@pytest.mark.unit
def test_implementer_format_command_falls_back() -> None:
    body = render_template(
        IMPLEMENTER_TEMPLATE, stack="python", proj="python", conventions=()
    )
    assert "{{format_command}}" not in body
    assert "no command detected" in body  # the _NO_COMMAND placeholder


def _preflight_report() -> PreflightReport:
    return PreflightReport(
        project_root="/tmp/x",
        is_git_repo=True,
        git_clean=True,
        settings=SettingsState(
            exists=False,
            parseable=True,
            user_hook_events=(),
            dummyindex_hook_present=False,
        ),
        rule_files=(),
        project_agents=(),
        claude_md_exists=False,
        claude_md_has_managed_block=False,
    )


@pytest.mark.unit
def test_three_way_identity_for_standard_generated_set() -> None:
    """manifest subagent_type == rendered frontmatter name == filename stem.

    proj != stack so the reviewer/verify carry {proj}- and the
    implementer/tester carry {stack}-; this is what makes the build loop's
    emitted ``subagent_type`` resolve to a real agent/skill by frontmatter name.
    """
    profile = StackProfile(label="python")
    decision = build_catalog(
        profile=profile,
        conventions=(),
        preflight=_preflight_report(),
        proj="backend",
    )
    rendered = render_generated_set(
        profile=profile,
        specs=decision.generate,
        conventions=(),
        grounding=(),
        proj="backend",
    )
    # name -> expected identifier prefix ({proj} for reviewer/verify, {stack} else)
    expected_prefix = {
        "python-implementer": "python",
        "python-tester": "python",
        "backend-reviewer": "backend",
        "backend-verify": "backend",
    }
    seen: set[str] = set()
    for item, rel_path, content in rendered:
        seen.add(item.name)
        assert item.name.rsplit("-", 1)[0] == expected_prefix[item.name]
        # name <-> rendered frontmatter
        assert _frontmatter_name(content) == item.name
        if item.kind is EquipmentKind.AGENT:
            # agents: subagent_type == name == filename stem.
            assert item.subagent_type == item.name
            assert Path(rel_path).stem == item.name
        else:
            # the verify skill lives at <name>/SKILL.md (stem is "SKILL").
            assert item.subagent_type is None
            assert Path(rel_path).parent.name == item.name
    assert seen == set(expected_prefix)


# ----- manifest schema ------------------------------------------------------


@pytest.mark.unit
def test_manifest_roundtrip_matches_schema() -> None:
    item = EquipmentItem(
        kind="agent",
        name="python-implementer",
        path=".claude/agents/python-implementer.md",
        source="generated",
        capabilities=("implement",),
        grounded_in=(".context/HOW_TO_USE.md",),
    )
    manifest = EquipmentManifest(schema_version=1, items=(item,))
    data = manifest.to_dict()
    assert data["schema_version"] == 1
    assert data["items"][0]["capabilities"] == ["implement"]
    assert data["items"][0]["grounded_in"] == [".context/HOW_TO_USE.md"]
    # round-trips back into frozen tuples
    back = EquipmentManifest.from_dict(data)
    assert back == manifest
    assert isinstance(back.items[0].capabilities, tuple)


# ----- manifest schema v2 ---------------------------------------------------


@pytest.mark.unit
def test_schema_version_is_2() -> None:
    assert SCHEMA_VERSION == 2


@pytest.mark.unit
def test_item_roundtrips_v2_fields() -> None:
    item = EquipmentItem(
        kind="agent",
        name="python-implementer",
        path=".claude/agents/python-implementer.md",
        source="generated",
        capabilities=("implement",),
        grounded_in=(".context/HOW_TO_USE.md",),
        subagent_type="python-implementer",
        version="1.0.0",
        origin_hash="sha256:deadbeef",
    )
    data = item.to_dict()
    assert data["subagent_type"] == "python-implementer"
    assert data["version"] == "1.0.0"
    assert data["origin_hash"] == "sha256:deadbeef"
    assert EquipmentItem.from_dict(data) == item


@pytest.mark.unit
def test_v1_item_loads_with_none_defaults() -> None:
    """A v1 manifest entry (no new keys) loads with the new fields as None."""
    v1 = {
        "kind": "agent",
        "name": "python-implementer",
        "path": ".claude/agents/python-implementer.md",
        "source": "generated",
        "capabilities": ["implement"],
        "grounded_in": [".context/HOW_TO_USE.md"],
    }
    item = EquipmentItem.from_dict(v1)
    assert item.subagent_type is None
    assert item.version is None
    assert item.origin_hash is None


@pytest.mark.unit
def test_v1_manifest_loads_tolerantly() -> None:
    v1 = {
        "schema_version": 1,
        "items": [
            {
                "kind": "skill",
                "name": "proj-verify",
                "path": ".claude/skills/proj-verify/SKILL.md",
                "source": "generated",
                "capabilities": ["test", "verify"],
                "grounded_in": [".context/HOW_TO_USE.md"],
            }
        ],
    }
    manifest = EquipmentManifest.from_dict(v1)
    assert manifest.schema_version == 1  # preserved as-read
    assert manifest.items[0].version is None


# ----- content hashing ------------------------------------------------------


@pytest.mark.unit
def test_content_hash_stable_and_prefixed() -> None:
    h1 = content_hash("x")
    h2 = content_hash("x")
    assert h1 == h2
    assert h1.startswith("sha256:")
    assert content_hash("y") != h1


# ----- safety: never clobber ------------------------------------------------


@pytest.mark.unit
def test_is_safe_to_write_absent(tmp_path: Path) -> None:
    assert is_safe_to_write(tmp_path / "nope.md") is True


@pytest.mark.unit
def test_is_safe_to_write_ours(tmp_path: Path) -> None:
    p = tmp_path / "ours.md"
    p.write_text(f"{GENERATED_SENTINEL}\nbody\n", encoding="utf-8")
    assert is_safe_to_write(p) is True


@pytest.mark.unit
def test_is_safe_to_write_user_file(tmp_path: Path) -> None:
    p = tmp_path / "theirs.md"
    p.write_text("# my hand-written agent\n", encoding="utf-8")
    assert is_safe_to_write(p) is False


# ----- CLI: equip end to end ------------------------------------------------


def _project(tmp_path: Path, languages: list[str | None]) -> Path:
    context_dir = tmp_path / ".context"
    _write_files_map(context_dir, languages)
    (context_dir / "conventions").mkdir(parents=True, exist_ok=True)
    (context_dir / "conventions" / "naming.md").write_text("# naming\n", encoding="utf-8")
    return tmp_path


@pytest.mark.integration
def test_equip_writes_agent_and_skill(tmp_path: Path) -> None:
    root = _project(tmp_path, ["python", "python"])
    rc = _cmd_equip([str(root)])
    assert rc == 0

    agent = root / ".claude" / "agents" / "python-implementer.md"
    skill = root / ".claude" / "skills" / f"{_project_slug(root)}-verify" / "SKILL.md"
    assert agent.is_file()
    assert skill.is_file()
    # generated files carry the sentinel + reference .context/
    agent_text = agent.read_text(encoding="utf-8")
    assert GENERATED_SENTINEL in agent_text
    assert ".context/conventions/naming.md" in agent_text
    # frontmatter-first: written files must be discoverable by Claude Code.
    assert agent_text.startswith("---")
    assert skill.read_text(encoding="utf-8").startswith("---")


@pytest.mark.integration
def test_equip_writes_manifest_with_schema(tmp_path: Path) -> None:
    root = _project(tmp_path, ["python"])
    rc = _cmd_equip([str(root)])
    assert rc == 0

    manifest_path = root / ".context" / "equipment.json"
    assert manifest_path.is_file()
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["schema_version"] == 2  # equip writes the current SCHEMA_VERSION
    assert len(data["items"]) >= 2
    for item in data["items"]:
        assert item["capabilities"]  # non-empty
        assert item["grounded_in"]   # grounded
        assert ".context/HOW_TO_USE.md" in item["grounded_in"]


@pytest.mark.integration
def test_equip_wires_format_hook_when_formatter_present(tmp_path: Path) -> None:
    # v2 (spec §5): apply now WRITES the PostToolUse format hook into
    # settings.json (the MVP's record-only behaviour is gone). Spec wins.
    root = _project(tmp_path, ["python"])
    (root / "pyproject.toml").write_text("[tool.ruff]\n", encoding="utf-8")
    rc = _cmd_equip([str(root)])
    assert rc == 0

    data = json.loads((root / ".context" / "equipment.json").read_text(encoding="utf-8"))
    hooks = [i for i in data["items"] if i["kind"] == "hook"]
    assert hooks and hooks[0]["name"] == "ruff-format"
    assert hooks[0]["capabilities"] == ["format"]
    # the hook IS written to settings.json now, with our sentinel.
    settings = root / ".claude" / "settings.json"
    assert settings.exists()
    blob = settings.read_text(encoding="utf-8")
    assert "DUMMYINDEX_EQUIP" in blob
    assert "PostToolUse" in blob


@pytest.mark.integration
def test_equip_never_clobbers_user_file(tmp_path: Path) -> None:
    root = _project(tmp_path, ["python"])
    agent = root / ".claude" / "agents" / "python-implementer.md"
    agent.parent.mkdir(parents=True, exist_ok=True)
    original = "# MY hand-written agent — do not touch\n"
    agent.write_text(original, encoding="utf-8")

    rc = _cmd_equip([str(root)])
    assert rc == 0
    # untouched
    assert agent.read_text(encoding="utf-8") == original
    # and not recorded as written in the manifest
    data = json.loads((root / ".context" / "equipment.json").read_text(encoding="utf-8"))
    names = {i["name"] for i in data["items"]}
    assert "python-implementer" not in names


@pytest.mark.integration
def test_equip_dry_run_writes_nothing(tmp_path: Path) -> None:
    root = _project(tmp_path, ["python"])
    rc = _cmd_equip([str(root), "--dry-run"])
    assert rc == 0
    assert not (root / ".claude").exists()
    assert not (root / ".context" / "equipment.json").exists()


@pytest.mark.integration
def test_equip_rejects_unknown_args(tmp_path: Path) -> None:
    root = _project(tmp_path, ["python"])
    rc = _cmd_equip([str(root), "--bogus"])
    assert rc == 2


# ----- Task 9: v2 apply pipeline (catalog set, hooks, baselines) ------------


def _equipped(tmp_path: Path, *, formatter: bool = True) -> Path:
    """Apply a full python toolkit (with a ruff formatter) and return the root."""
    root = _project(tmp_path, ["python", "python"])
    if formatter:
        (root / "pyproject.toml").write_text(
            "[tool.ruff]\n[tool.mypy]\ndependencies = [\"pytest\"]\n", encoding="utf-8"
        )
    rc = _cmd_equip([str(root)])
    assert rc == 0
    return root


@pytest.mark.integration
def test_apply_writes_full_catalog_set(tmp_path: Path) -> None:
    root = _equipped(tmp_path)
    proj = _project_slug(root)
    assert (root / ".claude" / "agents" / "python-implementer.md").is_file()
    assert (root / ".claude" / "agents" / "python-tester.md").is_file()
    assert (root / ".claude" / "agents" / f"{proj}-reviewer.md").is_file()
    assert (root / ".claude" / "skills" / f"{proj}-verify" / "SKILL.md").is_file()
    data = json.loads((root / ".context" / "equipment.json").read_text(encoding="utf-8"))
    by_name = {i["name"]: i for i in data["items"]}
    # generated agents carry subagent_type + version + origin_hash
    impl = by_name["python-implementer"]
    assert impl["subagent_type"] == "python-implementer"
    assert impl["version"] == "1.0.0"
    assert impl["origin_hash"].startswith("sha256:")


@pytest.mark.integration
def test_apply_writes_equip_hook_into_settings(tmp_path: Path) -> None:
    root = _equipped(tmp_path)
    settings = json.loads((root / ".claude" / "settings.json").read_text(encoding="utf-8"))
    posttooluse = settings["hooks"]["PostToolUse"]
    cmds = [h["command"] for e in posttooluse for h in e.get("hooks", [])]
    assert any("DUMMYINDEX_EQUIP" in c for c in cmds)
    assert any("ruff format" in c for c in cmds)


@pytest.mark.integration
def test_apply_preserves_user_posttooluse_and_autorefresh(tmp_path: Path) -> None:
    root = _project(tmp_path, ["python"])
    (root / "pyproject.toml").write_text("[tool.ruff]\n", encoding="utf-8")
    settings_path = root / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps(
            {
                "hooks": {
                    "PostToolUse": [
                        {"hooks": [{"type": "command", "command": "echo my-own-hook"}]}
                    ],
                    "SessionStart": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "# DUMMYINDEX_AUTO_REFRESH\necho drift\n",
                                }
                            ]
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    rc = _cmd_equip([str(root)])
    assert rc == 0
    after = json.loads(settings_path.read_text(encoding="utf-8"))
    post_cmds = [h["command"] for e in after["hooks"]["PostToolUse"] for h in e["hooks"]]
    assert any("my-own-hook" in c for c in post_cmds)  # user entry preserved
    assert any("DUMMYINDEX_EQUIP" in c for c in post_cmds)  # ours added
    sess_cmds = [h["command"] for e in after["hooks"]["SessionStart"] for h in e["hooks"]]
    assert any("DUMMYINDEX_AUTO_REFRESH" in c for c in sess_cmds)  # untouched


@pytest.mark.integration
def test_apply_malformed_settings_skips_hook_but_writes_files(tmp_path: Path) -> None:
    root = _project(tmp_path, ["python"])
    (root / "pyproject.toml").write_text("[tool.ruff]\n", encoding="utf-8")
    settings_path = root / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text("{ this is not json", encoding="utf-8")
    rc = _cmd_equip([str(root)])
    assert rc == 0
    # files still written
    assert (root / ".claude" / "agents" / "python-implementer.md").is_file()
    # malformed settings left untouched
    assert settings_path.read_text(encoding="utf-8") == "{ this is not json"
    # the hook is NOT recorded in the manifest (it was skipped)
    data = json.loads((root / ".context" / "equipment.json").read_text(encoding="utf-8"))
    assert not [i for i in data["items"] if i["kind"] == "hook"]


@pytest.mark.integration
def test_apply_dry_run_writes_no_files_no_settings(tmp_path: Path) -> None:
    root = _project(tmp_path, ["python"])
    (root / "pyproject.toml").write_text("[tool.ruff]\n", encoding="utf-8")
    rc = _cmd_equip([str(root), "--dry-run"])
    assert rc == 0
    assert not (root / ".claude").exists()
    assert not (root / ".context" / "equipment.json").exists()


@pytest.mark.integration
def test_apply_json_stdout_is_pure_json(tmp_path: Path, capsys) -> None:
    # --json must emit ONLY the payload on stdout (repo convention); no preamble
    # or per-item write lines may pollute it.
    root = _project(tmp_path, ["python"])
    (root / "pyproject.toml").write_text("[tool.ruff]\n", encoding="utf-8")
    capsys.readouterr()
    rc = _cmd_equip(["--json", str(root)])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)  # would raise if polluted
    assert "python-implementer" in payload["written"]
    assert "PostToolUse" in payload["hook_events"]


@pytest.mark.integration
def test_apply_dry_run_json_stdout_is_pure_json(tmp_path: Path, capsys) -> None:
    root = _project(tmp_path, ["python"])
    (root / "pyproject.toml").write_text("[tool.ruff]\n", encoding="utf-8")
    capsys.readouterr()
    rc = _cmd_equip([str(root), "--dry-run", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["dry_run"] is True
    assert any(g["name"] == "python-implementer" for g in payload["generate"])
    # nothing was written
    assert not (root / ".context" / "equipment.json").exists()


@pytest.mark.integration
def test_reapply_preserves_user_modified_generated_file(tmp_path: Path) -> None:
    """REGRESSION (handoff §critical): a hand-edited generated file (sentinel
    still present) must NOT be clobbered on re-apply. The gate is classify_item
    against the recorded baseline, not is_safe_to_write (which sees the sentinel
    and would say 'safe to overwrite').
    """
    root = _equipped(tmp_path)
    agent = root / ".claude" / "agents" / "python-implementer.md"
    # Hand-edit: APPEND (keep the sentinel) so we exercise the real bug.
    edited = agent.read_text(encoding="utf-8") + "\n<!-- USER TWEAK: keep me -->\n"
    agent.write_text(edited, encoding="utf-8")

    rc = _cmd_equip([str(root)])  # re-apply
    assert rc == 0
    # user content survives
    assert "USER TWEAK: keep me" in agent.read_text(encoding="utf-8")
    # and it is still recorded (carried forward verbatim, not dropped)
    data = json.loads((root / ".context" / "equipment.json").read_text(encoding="utf-8"))
    assert "python-implementer" in {i["name"] for i in data["items"]}


# ----- Task 9/10: per-proposal scoping --------------------------------------


def test_for_proposal_missing_slug_exits_2(tmp_path: Path) -> None:
    root = _project(tmp_path, ["python"])
    rc = _cmd_equip([str(root), "--for-proposal", "no-such-proposal"])
    assert rc == 2


@pytest.mark.integration
def test_for_proposal_generates_db_specialist_file(tmp_path: Path) -> None:
    # database has a template → a real, file-backed specialist is GENERATED
    # (no longer a manifest-only Data Engineer pointer).
    root = _project(tmp_path, ["python"])
    prop = root / ".context" / "proposals" / "add-db"
    prop.mkdir(parents=True)
    (prop / "plan.md").write_text(
        "# Plan\n\nAdd a database migration and SQL schema.\n", encoding="utf-8"
    )
    (prop / "checklist.md").write_text("- [ ] write the migration\n", encoding="utf-8")
    rc = _cmd_equip([str(root), "--for-proposal", "add-db"])
    assert rc == 0
    proj = _project_slug(root)
    agent_file = root / ".claude" / "agents" / f"{proj}-db-specialist.md"
    assert agent_file.is_file()
    assert GENERATED_SENTINEL in agent_file.read_text(encoding="utf-8")
    data = json.loads((root / ".context" / "equipment.json").read_text(encoding="utf-8"))
    spec = next(i for i in data["items"] if i["name"] == f"{proj}-db-specialist")
    assert spec["source"] == "generated"
    assert spec["version"] == "1.0.0"
    assert spec["origin_hash"].startswith("sha256:")
    assert ".context/HOW_TO_USE.md" in spec["grounded_in"]


@pytest.mark.integration
def test_for_proposal_adopts_frontend_when_no_template(tmp_path: Path) -> None:
    # frontend has NO template → the registry's Frontend Developer is adopted
    # manifest-only (the unchanged "no template → adopt" fallback), no file.
    root = _project(tmp_path, ["python"])
    prop = root / ".context" / "proposals" / "add-ui"
    prop.mkdir(parents=True)
    (prop / "plan.md").write_text(
        "# Plan\n\nAdd a React frontend dashboard with CSS.\n", encoding="utf-8"
    )
    (prop / "checklist.md").write_text("- [ ] build the UI\n", encoding="utf-8")
    rc = _cmd_equip([str(root), "--for-proposal", "add-ui"])
    assert rc == 0
    data = json.loads((root / ".context" / "equipment.json").read_text(encoding="utf-8"))
    installed = [i for i in data["items"] if i["source"] == "installed"]
    assert any("frontend" in (i.get("capabilities") or []) for i in installed)
    # adopted, never written as a file
    assert not list((root / ".claude" / "agents").glob("*frontend*"))


# ----- Task 10: verb surface ------------------------------------------------


def test_bare_equip_is_apply(tmp_path: Path) -> None:
    root = _project(tmp_path, ["python"])
    rc = _cmd_equip([str(root)])
    assert rc == 0
    assert (root / ".context" / "equipment.json").is_file()


def test_unknown_verb_then_path_is_apply_on_path(tmp_path: Path) -> None:
    # The leading token is only a verb if it matches EquipVerb; a path stays apply.
    root = _project(tmp_path, ["python"])
    rc = _cmd_equip([str(root), "--dry-run"])
    assert rc == 0


@pytest.mark.integration
def test_verb_status_json(tmp_path: Path) -> None:
    root = _equipped(tmp_path)
    rc = _cmd_equip(["status", "--root", str(root), "--json"])
    assert rc == 0


@pytest.mark.integration
def test_verb_status_reports_pristine(tmp_path: Path, capsys) -> None:
    root = _equipped(tmp_path)
    capsys.readouterr()
    rc = _cmd_equip(["status", "--root", str(root), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    states = {i["name"]: i["state"] for i in payload["items"]}
    assert states["python-implementer"] == "pristine"


@pytest.mark.integration
def test_verb_refresh_dry_run(tmp_path: Path) -> None:
    root = _equipped(tmp_path)
    rc = _cmd_equip(["refresh", "--root", str(root), "--dry-run"])
    assert rc == 0


@pytest.mark.integration
def test_verb_reset_restores(tmp_path: Path) -> None:
    root = _equipped(tmp_path)
    agent = root / ".claude" / "agents" / "python-implementer.md"
    agent.write_text("clobbered\n", encoding="utf-8")
    rc = _cmd_equip(["reset", "python-implementer", "--root", str(root)])
    assert rc == 0
    # restored to a real rendered agent (frontmatter-first)
    assert agent.read_text(encoding="utf-8").startswith("---")


@pytest.mark.integration
def test_verb_uninstall_leaves_user_modified(tmp_path: Path) -> None:
    root = _equipped(tmp_path)
    agent = root / ".claude" / "agents" / "python-implementer.md"
    agent.write_text(agent.read_text(encoding="utf-8") + "\nuser edit\n", encoding="utf-8")
    rc = _cmd_equip(["uninstall", "--root", str(root)])
    assert rc == 0
    # user-modified file kept; a pristine one gone
    assert agent.is_file()
    assert "user edit" in agent.read_text(encoding="utf-8")
    assert not (root / ".claude" / "agents" / "python-tester.md").exists()


@pytest.mark.integration
def test_verb_patch_applies_and_bumps_version(tmp_path: Path) -> None:
    root = _equipped(tmp_path)
    agent = root / ".claude" / "agents" / "python-implementer.md"
    # pick a unique substring present in the rendered agent
    old = "## How you work"
    assert old in agent.read_text(encoding="utf-8")
    patch_file = tmp_path / "p.json"
    patch_file.write_text(
        json.dumps({"old": old, "new": old + "\n\n<!-- patched -->"}), encoding="utf-8"
    )
    rc = _cmd_equip(["patch", "--item", "python-implementer", "--from-file", str(patch_file), "--root", str(root)])
    assert rc == 0
    assert "<!-- patched -->" in agent.read_text(encoding="utf-8")
    data = json.loads((root / ".context" / "equipment.json").read_text(encoding="utf-8"))
    by_name = {i["name"]: i for i in data["items"]}
    assert by_name["python-implementer"]["version"] == "1.0.1"


@pytest.mark.integration
def test_verb_patch_bad_file_exits_2(tmp_path: Path) -> None:
    root = _equipped(tmp_path)
    patch_file = tmp_path / "bad.json"
    patch_file.write_text(json.dumps({"new": "x"}), encoding="utf-8")  # missing 'old'
    rc = _cmd_equip(["patch", "--item", "python-implementer", "--from-file", str(patch_file), "--root", str(root)])
    assert rc == 2


def test_verb_patch_requires_item_and_file(tmp_path: Path) -> None:
    root = _project(tmp_path, ["python"])
    assert _cmd_equip(["patch", "--root", str(root)]) == 2


# ----- frontmatter version sync helper ---------------------------------------


def test_set_frontmatter_version_replaces_only_frontmatter_line() -> None:
    from dummyindex.context.domains.equip import set_frontmatter_version

    text = "---\nname: x\nversion: 1.0.0\n---\nbody mentions version: 1.0.0 here\n"
    out = set_frontmatter_version(text, "2.3.4")
    assert "version: 2.3.4" in out
    assert "body mentions version: 1.0.0 here" in out    # body untouched


def test_set_frontmatter_version_without_frontmatter_is_noop() -> None:
    from dummyindex.context.domains.equip import set_frontmatter_version

    assert set_frontmatter_version("plain text\n", "9.9.9") == "plain text\n"
