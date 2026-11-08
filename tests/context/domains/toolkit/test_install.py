"""Two-step install: preview binds a plan hash; apply refuses a stale one."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from dummyindex.context.domains.equip.plugins.sources import RunResult
from dummyindex.context.domains.toolkit import (
    ToolkitError,
    toolkit_install,
    toolkit_list,
)
from tests.context.domains.toolkit.helpers import (
    MCP_TEXT,
    SHA_A,
    SHA_B,
    SKILL_TEXT,
    FakeGh,
    plugin_catalog,
    snapshot,
)
from tests.context.domains.toolkit.schema_check import (
    load_schema,
    schemas_dir,
    validate,
)

pytestmark = pytest.mark.unit

HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _skill_gh(sha: str | None = None) -> FakeGh:
    return FakeGh(
        contents={"owner/repo": {"skills/demo/SKILL.md": SKILL_TEXT}},
        commit_sha=sha or SHA_A,
    )


def _preview(
    gh: FakeGh, kind: str, source: str, root: Path, home: Path, scope: str = "project"
) -> dict:
    return toolkit_install(
        kind, source, root=root, home=home, scope=scope, preview=True, runner=gh
    )


def test_skill_preview_pins_sha_and_fixes_the_commands(root: Path, home: Path) -> None:
    gh = _skill_gh()
    prev = _preview(gh, "skill", "github:owner/repo/skills/demo@main", root, home)

    assert prev["kind"] == "skill"
    assert prev["name"] == "demo"
    assert prev["source"] == {
        "ref": "github:owner/repo/skills/demo@main",
        "scheme": "github",
    }
    assert prev["resolved"] == {"sha": SHA_A}
    assert prev["commands"] == [
        ["gh", "api", f"repos/owner/repo/contents/skills/demo/SKILL.md?ref={SHA_A}"]
    ]
    assert prev["blast_radius"]["scope"] == "project"
    assert prev["blast_radius"]["writes"] == [".context/toolkit/disabled.json"]
    assert prev["blast_radius"]["runs_code"] is False
    assert prev["trust"]["requires_confirmation"] is True
    assert prev["trust"]["scheme_allowed"] is True
    assert HEX64.match(prev["plan_hash"])


def test_preview_writes_nothing(root: Path, home: Path) -> None:
    before = snapshot(root)
    home_before = snapshot(home)
    _preview(_skill_gh(), "skill", "github:owner/repo/skills/demo", root, home)
    assert snapshot(root) == before
    assert snapshot(home) == home_before


def test_apply_with_matching_hash_installs_disabled_and_enable_is_separate(
    root: Path, home: Path
) -> None:
    gh = _skill_gh()
    prev = _preview(gh, "skill", "github:owner/repo/skills/demo", root, home)
    result = toolkit_install(
        "skill",
        "github:owner/repo/skills/demo",
        root=root,
        home=home,
        scope="project",
        yes=True,
        plan_hash=prev["plan_hash"],
        runner=gh,
    )

    assert result["installed"] is True
    assert result["enabled"] is False
    assert result["restart_required"] is False
    assert result["resolved_sha"] == SHA_A
    assert not (root / ".claude" / "skills" / "demo" / "SKILL.md").exists()

    listing = toolkit_list(root=root, home=home, kind="skill", scope="project")
    assert listing["items"] == [
        {
            "kind": "skill",
            "name": "demo",
            "scope": "project",
            "terminal_id": None,
            "enabled": False,
            "scope_warning": True,
            "warnings": [
                "Project scope: other sessions in this repo are affected.",
            ],
            "mechanism": None,
        }
    ]


def test_apply_refuses_a_stale_hash_when_the_ref_moved(root: Path, home: Path) -> None:
    src = "github:owner/repo/skills/demo@main"
    first = _skill_gh(SHA_A)
    prev = _preview(first, "skill", src, root, home)

    moved = _skill_gh(SHA_B)
    before = snapshot(root)
    with pytest.raises(ToolkitError) as exc:
        toolkit_install(
            "skill",
            src,
            root=root,
            home=home,
            scope="project",
            yes=True,
            plan_hash=prev["plan_hash"],
            runner=moved,
        )
    assert exc.value.code == "stale_plan_hash"
    assert snapshot(root) == before


@pytest.mark.parametrize("bogus", ["0" * 64, "not-a-hash", ""])
def test_apply_refuses_any_hash_that_does_not_match(
    root: Path, home: Path, bogus: str
) -> None:
    gh = _skill_gh()
    with pytest.raises(ToolkitError) as exc:
        toolkit_install(
            "skill",
            "github:owner/repo/skills/demo",
            root=root,
            home=home,
            scope="project",
            yes=True,
            plan_hash=bogus or None,
            runner=gh,
        )
    assert exc.value.code in ("stale_plan_hash", "invalid_argument")
    assert not (root / ".context" / "toolkit" / "disabled.json").exists()


def test_yes_without_preview_or_hash_is_refused(root: Path, home: Path) -> None:
    with pytest.raises(ToolkitError) as no_confirm:
        toolkit_install("skill", "github:owner/repo/demo", root=root, home=home)
    assert no_confirm.value.code == "confirmation_required"

    with pytest.raises(ToolkitError) as no_hash:
        toolkit_install(
            "skill", "github:owner/repo/demo", root=root, home=home, yes=True
        )
    assert no_hash.value.code == "invalid_argument"


def test_unresolvable_ref_is_source_unreachable(root: Path, home: Path) -> None:
    calls: list[list[str]] = []

    def refuse(argv: list[str]) -> RunResult:
        calls.append(list(argv))
        return RunResult(1, "", "HTTP 404")

    with pytest.raises(ToolkitError) as exc:
        toolkit_install(
            "skill",
            "github:owner/repo/demo@nope",
            root=root,
            home=home,
            preview=True,
            runner=refuse,
        )
    assert exc.value.code == "source_unreachable"
    assert calls == [["gh", "api", "repos/owner/repo/commits/nope"]]


def test_missing_skill_file_is_source_not_found(root: Path, home: Path) -> None:
    gh = FakeGh(contents={}, commit_sha=SHA_A)
    with pytest.raises(ToolkitError) as exc:
        _preview(gh, "skill", "github:owner/repo/skills/nope", root, home)
    assert exc.value.code == "source_not_found"


def test_mcp_preview_flags_a_command_server_as_running_code(
    root: Path, home: Path
) -> None:
    gh = FakeGh(
        contents={
            "owner/repo": {
                "mcp/tools.json": json.dumps({"command": "node", "args": ["x.js"]})
            }
        },
        commit_sha=SHA_A,
    )
    prev = _preview(gh, "mcp", "github:owner/repo/mcp/tools.json", root, home)
    assert prev["name"] == "tools"
    assert prev["blast_radius"]["runs_code"] is True
    assert prev["trust"]["trusted_repo"] is False


def test_mcp_remote_server_is_inert_and_applies_disabled(
    root: Path, home: Path
) -> None:
    gh = FakeGh(
        contents={"owner/repo": {"mcp/remote.json": MCP_TEXT}}, commit_sha=SHA_A
    )
    prev = _preview(gh, "mcp", "github:owner/repo/mcp/remote.json", root, home)
    assert prev["blast_radius"]["runs_code"] is False
    result = toolkit_install(
        "mcp",
        "github:owner/repo/mcp/remote.json",
        root=root,
        home=home,
        scope="project",
        yes=True,
        plan_hash=prev["plan_hash"],
        runner=gh,
    )
    assert result["enabled"] is False
    assert not (root / ".mcp.json").exists()


def test_plugin_preview_uses_the_equip_blast_radius_and_two_argv_commands(
    root: Path, home: Path
) -> None:
    gh = FakeGh(
        catalogs={"owner/repo": plugin_catalog("mkt", "lint", hooks=True)},
        commit_sha=SHA_A,
    )
    prev = toolkit_install(
        "plugin",
        "github:owner/repo/lint",
        root=root,
        home=home,
        scope="user",
        preview=True,
        runner=gh,
    )
    assert prev["name"] == "lint@mkt"
    assert prev["commands"] == [
        [
            "claude",
            "plugin",
            "install",
            "lint@mkt",
            "--marketplace",
            "owner/repo",
            "--scope",
            "user",
            "--json",
        ],
        ["claude", "plugin", "disable", "lint@mkt", "--scope", "user", "--json"],
    ]
    assert prev["blast_radius"]["runs_code"] is True
    assert "hook" in prev["blast_radius"]["surfaces"]
    assert prev["blast_radius"]["scope"] == "user"
    assert any("SHA" in w for w in prev["warnings"])


def test_plugin_apply_runs_install_then_disable_and_never_enables(
    root: Path, home: Path
) -> None:
    gh = FakeGh(
        catalogs={
            "anthropics/claude-plugins-official": plugin_catalog(
                "official", "lint", hooks=False
            )
        },
        commit_sha=SHA_A,
    )
    src = "github:anthropics/claude-plugins-official/lint"
    prev = toolkit_install(
        "plugin", src, root=root, home=home, scope="user", preview=True, runner=gh
    )
    assert prev["trust"]["trusted_repo"] is True
    result = toolkit_install(
        "plugin",
        src,
        root=root,
        home=home,
        scope="user",
        yes=True,
        plan_hash=prev["plan_hash"],
        runner=gh,
    )
    assert result["enabled"] is False
    assert result["name"] == "lint@official"
    claude_calls = [c for c in gh.calls if c[:2] == ["claude", "plugin"]]
    assert [c[2] for c in claude_calls] == ["install", "disable"]


def test_plugin_apply_reports_a_failing_claude_command(root: Path, home: Path) -> None:
    gh = FakeGh(
        catalogs={"owner/repo": plugin_catalog("mkt", "lint", hooks=False)},
        commit_sha=SHA_A,
        claude_returncode=3,
    )
    prev = toolkit_install(
        "plugin",
        "github:owner/repo/lint",
        root=root,
        home=home,
        scope="user",
        preview=True,
        runner=gh,
    )
    with pytest.raises(ToolkitError) as exc:
        toolkit_install(
            "plugin",
            "github:owner/repo/lint",
            root=root,
            home=home,
            scope="user",
            yes=True,
            plan_hash=prev["plan_hash"],
            runner=gh,
        )
    assert exc.value.code == "install_failed"


def test_plugin_install_at_project_scope_is_refused(root: Path, home: Path) -> None:
    with pytest.raises(ToolkitError) as exc:
        toolkit_install(
            "plugin",
            "github:owner/repo/lint",
            root=root,
            home=home,
            scope="project",
            preview=True,
            runner=FakeGh(),
        )
    assert exc.value.code == "unsupported_scope"


def test_preview_output_validates_against_dummyplane_schema(
    root: Path, home: Path
) -> None:
    if schemas_dir() is None:
        pytest.skip("dummyPlane schemas not found; set DUMMYPLANE_SCHEMAS_DIR")
    prev = _preview(_skill_gh(), "skill", "github:owner/repo/skills/demo", root, home)
    validate(prev, load_schema("toolkit-install-preview.json"))


def test_apply_output_validates_against_dummyplane_schema(
    root: Path, home: Path
) -> None:
    if schemas_dir() is None:
        pytest.skip("dummyPlane schemas not found; set DUMMYPLANE_SCHEMAS_DIR")
    gh = _skill_gh()
    prev = _preview(gh, "skill", "github:owner/repo/skills/demo", root, home)
    result = toolkit_install(
        "skill",
        "github:owner/repo/skills/demo",
        root=root,
        home=home,
        scope="project",
        yes=True,
        plan_hash=prev["plan_hash"],
        runner=gh,
    )
    validate(result, load_schema("toolkit-install-result.json"))
