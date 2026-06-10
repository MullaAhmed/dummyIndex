"""Lifecycle (status/uninstall) coverage for MARKETPLACE + VENDORED items."""
import json

from dummyindex.context.domains.equip import (
    EquipmentItem,
    EquipmentKind,
    EquipmentManifest,
    EquipmentSource,
    ItemState,
    content_hash,
    stamp_vendored,
    status,
    uninstall,
)


def _manifest(*items):
    return EquipmentManifest(schema_version=3, items=tuple(items))


def _marketplace_item():
    return EquipmentItem(
        kind=EquipmentKind.AGENT,
        name="pg-tuner@official",
        path=".claude/settings.json",
        source=EquipmentSource.MARKETPLACE,
        marketplace="official",
        origin_repo="anthropics/claude-plugins-official",
        mechanism="native",
    )


def _vendored_item(root, *, body="body\n"):
    rel = ".claude/skills/pdf/SKILL.md"
    f = root / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    stamped = stamp_vendored(body)
    f.write_text(stamped)
    item = EquipmentItem(
        kind=EquipmentKind.SKILL,
        name="pdf",
        path=rel,
        source=EquipmentSource.VENDORED,
        mechanism="vendor",
        origin_repo="anthropics/skills",
        origin_hash=content_hash(stamped),
    )
    return item, f


def test_uninstall_removes_marketplace_settings_keys(tmp_path):
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(
        json.dumps(
            {
                "extraKnownMarketplaces": {"official": {"source": {"source": "github", "repo": "anthropics/claude-plugins-official"}}},
                "enabledPlugins": {"pg-tuner@official": True},
            }
        )
    )
    uninstall(tmp_path, _manifest(_marketplace_item()), dry_run=False)
    data = json.loads(settings.read_text())
    assert "pg-tuner@official" not in data.get("enabledPlugins", {})
    assert "official" not in data.get("extraKnownMarketplaces", {})


def test_uninstall_removes_pristine_vendored_file(tmp_path):
    item, f = _vendored_item(tmp_path)
    report = uninstall(tmp_path, _manifest(item), dry_run=False)
    assert not f.exists()
    assert "pdf" in report.removed


def test_uninstall_keeps_user_modified_vendored_file(tmp_path):
    item, f = _vendored_item(tmp_path)
    f.write_text("<!-- dummyindex:installed -->\nI edited this\n")  # hash now differs
    report = uninstall(tmp_path, _manifest(item), dry_run=False)
    assert f.exists()  # never clobber a user-edited copy
    assert "pdf" in report.skipped_user_modified


def test_status_reports_marketplace_and_vendored(tmp_path):
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"enabledPlugins": {"pg-tuner@official": True}}))
    item, _ = _vendored_item(tmp_path)
    report = status(tmp_path, _manifest(_marketplace_item(), item))
    by_name = {n: s for n, s, _v in report.items}
    assert by_name["pg-tuner@official"] == ItemState.PRISTINE  # enabled
    assert by_name["pdf"] == ItemState.PRISTINE  # vendored file hash matches


def test_status_marketplace_missing_when_not_enabled(tmp_path):
    report = status(tmp_path, _manifest(_marketplace_item()))
    by_name = {n: s for n, s, _v in report.items}
    assert by_name["pg-tuner@official"] == ItemState.MISSING
