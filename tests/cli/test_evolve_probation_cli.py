"""CLI lifecycle for ``evolve attribute`` and ``evolve probation`` (wire-only).

Drives ``dispatch(["evolve", ...])`` over a throwaway repo. Real corrections
come from a Claude transcript imported through ``scan_hosts``, mirroring
``tests/context/domains/test_probation.py``.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from dummyindex.cli import dispatch
from dummyindex.context.domains import evidence
from dummyindex.context.domains.evidence import scan_hosts
from dummyindex.context.domains.observe import corrections, record_exposure, session_key
from dummyindex.context.domains.probation import store
from dummyindex.context.domains.probation.enums import State
from dummyindex.context.domains.probation.models import Item

pytestmark = pytest.mark.unit

SLUG = "proj"
SYNC_NOW = datetime.now(timezone.utc).replace(
    hour=12, minute=0, second=0, microsecond=0
)
CORRECTION = "wrong, do it the other way"
DISABLED = "evolution disabled (DUMMYINDEX_EVOLUTION)"


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(evidence, "encode_project_slug", lambda root: SLUG)
    monkeypatch.setattr(evidence, "project_dir_name", lambda root: SLUG)
    root = tmp_path / "repo"
    context = root / ".context"
    (context / "conventions").mkdir(parents=True)
    (context / "conventions/testing.md").write_text("# Testing\n", encoding="utf-8")
    (root / "cache.py").write_bytes(b"VALUE = 1\n")
    return SimpleNamespace(root=root, context=context, projects=tmp_path / "claude")


def _item(**overrides) -> Item:
    fields = {
        "id": "r1",
        "target": ".context/conventions/testing.md",
        "body": "Use fixtures.\n",
        "applies_when": "writing tests",
        "prediction": "fewer flakes",
        "probe": None,
        "sources": {},
        "tests": ("tests/test_x.py",),
        "evidence": ("ev-1",),
        "origin_session": None,
        "learning_event": "chat:c1",
        "created": SYNC_NOW.isoformat(),
        "state": State.PROBATION,
        "harm": (),
    }
    fields.update(overrides)
    return Item(**fields)


def _human(env, sid: str, n: int, text: str, ts: str) -> dict:
    return {
        "type": "user",
        "userType": "external",
        "cwd": str(env.root),
        "uuid": f"{sid}-h{n}",
        "timestamp": ts,
        "message": {"role": "user", "content": text},
    }


def _tool(sid: str, n: int, ts: str, name: str, payload: dict) -> dict:
    return {
        "type": "assistant",
        "uuid": f"{sid}-a{n}",
        "timestamp": ts,
        "message": {
            "role": "assistant",
            "model": "m",
            "content": [
                {
                    "type": "tool_use",
                    "id": f"{sid}-t{n}",
                    "name": name,
                    "input": payload,
                }
            ],
        },
    }


def _session(
    env, sid: str, *, inject: tuple[str, ...] = ("probation:r1",)
) -> list[str]:
    """Write one Claude transcript (with its injections); return its correction ids."""
    ts = SYNC_NOW.strftime("%Y-%m-%dT%H:%M:%SZ")
    if inject:
        record_exposure(
            env.context,
            session_id=sid,
            turn=0,
            items=[(item, None) for item in inject],
            now=SYNC_NOW - timedelta(seconds=1),
        )
    rows = [
        _human(env, sid, 0, "start", ts),
        _tool(sid, 1, ts, "Bash", {"command": "ls"}),
        _human(env, sid, 2, CORRECTION, ts),
    ]
    path = env.projects / SLUG / f"{sid}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    scan_hosts(env.context, claude_projects=env.projects, now=SYNC_NOW)
    mine = [c for c in corrections(env.context) if c["session"] == session_key(sid)]
    return [c["id"] for c in mine]


def _cli(env, *args: str) -> int:
    return dispatch(["evolve", *args, "--root", str(env.root)])


def test_attribute_next_empty_prints_nothing_to_attribute(env, capsys):
    rc = _cli(env, "attribute", "--next")
    assert rc == 0
    assert "nothing to attribute" in capsys.readouterr().out


def test_attribute_retraction_demotes_at_once(env):
    store.save_item(env.context, _item(id="r1", state=State.PROBATION))
    cids = _session(env, "s1")
    assert cids, "transcript import should produce a correction"

    rc = _cli(
        env,
        "attribute",
        "--event",
        cids[0],
        "--verdict",
        "attributed",
        "--item",
        "probation:r1",
        "--retracts",
    )

    assert rc == 0
    assert store.load_item(env.context, "r1").state is State.DEMOTED


def test_bad_verdict_and_bare_retracts_exit_2(env):
    assert _cli(env, "attribute", "--event", "cid", "--verdict", "maybe") == 2
    assert (
        _cli(env, "attribute", "--event", "cid", "--verdict", "unknown", "--retracts")
        == 2
    )
    assert (
        _cli(
            env, "attribute", "--event", "cid", "--verdict", "attributed", "--retracts"
        )
        == 2
    )


def test_disabled_verbs_print_disabled_line(env, monkeypatch, capsys):
    monkeypatch.setenv("DUMMYINDEX_EVOLUTION", "0")
    store.save_item(env.context, _item(id="r1", state=State.PROBATION))

    for args in (
        ("attribute", "--next"),
        ("probation", "report"),
        ("probation", "promote"),
        ("probation", "demote", "--item", "r1"),
    ):
        capsys.readouterr()
        assert _cli(env, *args) == 0, args
        assert DISABLED in capsys.readouterr().out, args


def test_probation_report_and_unknown_subverb(env):
    assert _cli(env, "probation", "report") == 0
    assert _cli(env, "probation", "bogus") == 2
    assert _cli(env, "probation") == 2
