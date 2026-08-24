"""CLI tests for `dummyindex context fleet` — wire-only surface over fleetrun.

Full lifecycle on a temp repo seeded from `tests/fixtures/fleetrun/`:
init from fixture proposals, next/checkpoint/spend loop to done, stable
merge-order, the anti-stall empty envelope, BUDGET-HALT exit-0 envelope
with resume via `spend --adjust`, and usage-error mapping.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from dummyindex.cli import dispatch
from tests.paths import FIXTURES_DIR

_FLEET_FIXTURES = FIXTURES_DIR / "fleetrun"
_SLUGS = ("alpha", "bravo", "charlie", "delta")


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """A temp repo with a `.context/` + the four fixture proposals."""
    root = tmp_path / "repo"
    (root / ".context").mkdir(parents=True)
    for slug in _SLUGS:
        dest = root / ".context" / "proposals" / slug
        dest.mkdir(parents=True)
        shutil.copy(_FLEET_FIXTURES / slug / "proposal.json", dest / "proposal.json")
    return root


def _argv(repo: Path, *args: str) -> list[str]:
    return ["fleet", *args, "--root", str(repo)]


def _out(capsys: pytest.CaptureFixture[str]) -> str:
    return capsys.readouterr().out


# ----- init -----------------------------------------------------------------


@pytest.mark.integration
def test_init_from_fixture_proposals_writes_committed_artifacts(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = dispatch(
        _argv(
            repo,
            "init",
            "--plans",
            "delta,charlie,alpha,bravo",
            "--budget-usd",
            "50",
            "--max-parallel",
            "3",
            "--ruling",
            "merge-order=priority",
            "--branch-template",
            "fleet/{id}-{slug}",
        )
    )
    assert code == 0
    out = _out(capsys)
    assert "run-0001" in out
    run_dir = repo / ".context" / "fleet" / "run-0001"
    manifest = (run_dir / "RUN-MANIFEST.md").read_text(encoding="utf-8")
    assert "| 1 | u01 | delta" in manifest
    assert "(none — serialized)" in manifest  # delta has no member_files
    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    assert [u["slug"] for u in state["units"]] == ["delta", "charlie", "alpha", "bravo"]
    assert state["units"][2]["paths"] == ["src/alpha.py", "src/shared.py"]
    assert state["branch_template"] == "fleet/{id}-{slug}"
    assert state["rulings"] == [["merge-order", "priority"]]
    assert any("warning" in line for line in out.splitlines())


@pytest.mark.integration
def test_init_refuses_zero_units_duplicate_slugs_and_both_sources(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    for argv, needle in (
        (_argv(repo, "init", "--plans", "", "--budget-usd", "5"), "--plans"),
        (
            _argv(
                repo,
                "init",
                "--plans",
                "alpha,alpha",
                "--budget-usd",
                "5",
                "--max-parallel",
                "1",
            ),
            "duplicate unit slugs: alpha",
        ),
        (
            _argv(
                repo,
                "init",
                "--plans",
                "alpha",
                "--intake",
                "x.json",
                "--budget-usd",
                "5",
                "--max-parallel",
                "1",
            ),
            "exactly one of --plans",
        ),
        (
            _argv(repo, "init", "--plans", "alpha", "--max-parallel", "1"),
            "--budget-usd",
        ),
    ):
        code = dispatch(argv)
        assert code == 2, argv
        assert needle in capsys.readouterr().err


@pytest.mark.unit
def test_unknown_verb_and_bare_invocation_are_usage_errors(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert dispatch(["fleet"]) == 2
    assert "usage: dummyindex context fleet" in capsys.readouterr().err
    assert dispatch(["fleet", "teleport"]) == 2
    assert "unknown fleet verb 'teleport'" in capsys.readouterr().err


# ----- lifecycle to done ----------------------------------------------------


@pytest.mark.integration
def test_full_lifecycle_init_to_done_with_stable_merge_order(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        dispatch(
            _argv(
                repo,
                "init",
                "--plans",
                "charlie,alpha,bravo",
                "--budget-usd",
                "40",
                "--max-parallel",
                "3",
            )
        )
        == 0
    )
    # Wave 1: charlie + alpha dispatch (disjoint); bravo held (shared.py).
    assert dispatch(_argv(repo, "next")) == 0
    out = _out(capsys)
    assert "DISPATCH u01 charlie" in out
    assert "DISPATCH u02 alpha" in out
    assert "skip u03: member paths intersect" in out

    # Build both to done, metering real spend.
    for uid in ("u01", "u02"):
        assert (
            dispatch(
                _argv(
                    repo,
                    "checkpoint",
                    "--unit",
                    uid,
                    "--status",
                    "building",
                    "--wave",
                    "1",
                )
            )
            == 0
        )
        assert dispatch(_argv(repo, "spend", "--unit", uid, "--est-usd", "3.5")) == 0
        assert (
            dispatch(_argv(repo, "checkpoint", "--unit", uid, "--status", "merging"))
            == 0
        )
        assert (
            dispatch(
                _argv(
                    repo,
                    "checkpoint",
                    "--unit",
                    uid,
                    "--status",
                    "done",
                    "--note",
                    "landed clean",
                )
            )
            == 0
        )
    _out(capsys)

    # Wave 2: bravo finally dispatches.
    assert dispatch(_argv(repo, "next", "--json")) == 0
    payload = json.loads(_out(capsys))
    assert payload["halt"] is False
    assert [u["id"] for u in payload["units"]] == ["u03"]

    # Merge-order is deterministic across repeated calls and cites rationale.
    assert dispatch(_argv(repo, "merge-order")) == 0
    first = _out(capsys)
    assert dispatch(_argv(repo, "merge-order")) == 0
    second = _out(capsys)
    assert first == second
    assert "[landed] u01 charlie — first to land" in first
    assert "lands after u01: shares src/alpha.py" not in first  # disjoint pair
    assert "lands after u02: shares src/shared.py" in first

    # Status reflects the whole board.
    assert dispatch(_argv(repo, "status", "--json")) == 0
    status = json.loads(_out(capsys))
    assert status["budget"]["spent_est_usd"] == 7.0
    by_id = {u["id"]: u for u in status["units"]}
    assert by_id["u01"]["status"] == "done"
    assert by_id["u03"]["status"] == "pending"
    assert status["halt"] is False


@pytest.mark.integration
def test_anti_stall_every_unit_gated_yields_valid_empty_envelope_exit_0(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        dispatch(
            _argv(
                repo,
                "init",
                "--plans",
                "alpha,charlie",
                "--budget-usd",
                "10",
                "--max-parallel",
                "2",
            )
        )
        == 0
    )
    _out(capsys)
    for uid in ("u01", "u02"):
        code = dispatch(
            _argv(repo, "checkpoint", "--unit", uid, "--gate", f"pick one for {uid}?")
        )
        assert code == 0
    _out(capsys)

    # Human output: empty-but-valid envelope, exit 0.
    code = dispatch(_argv(repo, "next"))
    assert code == 0
    human = _out(capsys)
    assert "0 unit(s)" in human and "gated until answered" in human

    # JSON envelope: halt=false, no units, reasons carried.
    code = dispatch(_argv(repo, "next", "--json"))
    assert code == 0
    payload = json.loads(_out(capsys))
    assert payload["halt"] is False and payload["units"] == []
    assert {s["id"] for s in payload["skipped"]} == {"u01", "u02"}
    assert all("gated" in s["reason"] for s in payload["skipped"])

    # Answering one gate re-opens exactly that lane.
    assert (
        dispatch(
            _argv(
                repo,
                "checkpoint",
                "--unit",
                "u01",
                "--status",
                "pending",
                "--note",
                "answered elsewhere",
            )
        )
        == 0
    )
    _out(capsys)
    code = dispatch(_argv(repo, "next", "--json"))
    payload = json.loads(_out(capsys))
    assert [u["id"] for u in payload["units"]] == ["u01"]


# ----- budget breaker over the CLI ------------------------------------------


@pytest.mark.integration
def test_budget_halt_envelope_exits_zero_and_resume_via_spend_adjust(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        dispatch(
            _argv(
                repo,
                "init",
                "--plans",
                "alpha,charlie",
                "--budget-usd",
                "10",
                "--max-parallel",
                "2",
            )
        )
        == 0
    )
    _out(capsys)
    assert dispatch(_argv(repo, "spend", "--unit", "u01", "--est-usd", "7.25")) == 0
    assert "$7.25/$10.00" in _out(capsys)

    # Plain negative spend is refused; the recorded correction is the only way.
    code = dispatch(_argv(repo, "spend", "--unit", "u01", "--est-usd", "-1"))
    assert code == 2
    assert "--adjust" in capsys.readouterr().err

    # Over the cap: next answers with a BUDGET-HALT envelope — exit 0.
    assert dispatch(_argv(repo, "spend", "--unit", "u01", "--est-usd", "3.00")) == 0
    _out(capsys)
    code = dispatch(_argv(repo, "next", "--json"))
    assert code == 0
    payload = json.loads(_out(capsys))
    assert payload["halt"] is True
    assert payload["status"] == "BUDGET-HALT"
    assert payload["units"] == []
    resume = "\n".join(payload["resume"])
    assert "--adjust" in resume and "--est-usd -0.26" in resume

    # The printed resume path is executable as-is and clears the breaker.
    assert (
        dispatch(
            _argv(repo, "spend", "--unit", "u01", "--est-usd", "-0.26", "--adjust")
        )
        == 0
    )
    _out(capsys)
    code = dispatch(_argv(repo, "next", "--json"))
    payload = json.loads(_out(capsys))
    assert payload["halt"] is False and len(payload["units"]) == 2


# ----- run discovery --------------------------------------------------------


@pytest.mark.integration
def test_run_discovery_defaults_to_newest_and_explicit_dir_wins(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    for plans in ("alpha", "charlie"):
        assert (
            dispatch(
                _argv(
                    repo,
                    "init",
                    "--plans",
                    plans,
                    "--budget-usd",
                    "5",
                    "--max-parallel",
                    "1",
                )
            )
            == 0
        )
    _out(capsys)
    # No --run: newest run-* wins (run-0002 holds charlie alone).
    assert dispatch(_argv(repo, "status", "--json")) == 0
    newest = json.loads(_out(capsys))
    assert newest["run"] == "0002"
    assert [u["slug"] for u in newest["units"]] == ["charlie"]
    # Explicit --run targets the older one regardless of recency.
    old = repo / ".context" / "fleet" / "run-0001"
    assert dispatch(["fleet", "status", "--run", str(old), "--root", str(repo)]) == 0
    assert "run 0001" in _out(capsys)


@pytest.mark.integration
def test_missing_context_dir_maps_to_usage_error(tmp_path: Path, capsys) -> None:
    code = dispatch(["fleet", "next", "--root", str(tmp_path)])
    assert code == 2
    assert "not found" in capsys.readouterr().err
