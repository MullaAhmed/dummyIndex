"""Tests for dummyindex.context.domains.fleetrun — the fleet-run domain.

Covers the checkpoint/mutation contract: init ordering + refusals, frozen
disjointness, priority + parallel cap, gated-skip anti-stall, the budget
breaker (trip + explicit `spend --adjust` resume), lock-serialized
read-modify-write under concurrency, loud corrupt-state failures, and
deterministic merge order.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from dummyindex.context.domains.fleetrun import (
    Budget,
    FleetInitError,
    FleetSlugError,
    FleetStateCorruptError,
    FleetUnit,
    FleetUnitError,
    FleetUnitStatus,
    NextEnvelope,
    UnitSpec,
    add_spend,
    budget_halted,
    checkpoint,
    init_run,
    load_run,
    merge_order,
    next_run_id,
    next_units,
    render_branch,
    units_from_intake,
    units_from_plans,
    validate_unit_specs,
    write_state,
)


def _specs(*slug_paths: tuple[str, tuple[str, ...]]) -> list[UnitSpec]:
    return [UnitSpec(slug, paths=paths) for slug, paths in slug_paths]


def _init(
    tmp_path: Path,
    specs: list[UnitSpec],
    *,
    max_parallel: int = 3,
    budget_usd: float = 100.0,
) -> Path:
    state, _warnings = init_run(
        tmp_path / ".context", specs, budget_usd=budget_usd, max_parallel=max_parallel
    )
    return tmp_path / ".context" / "fleet" / f"run-{state.run_id}"


# ----- init -----------------------------------------------------------------


@pytest.mark.unit
def test_init_writes_manifest_first_and_state_last(tmp_path: Path) -> None:
    run_dir = _init(tmp_path, _specs(("alpha", ("a.py",)), ("bravo", ("b.py",))))
    manifest = run_dir / "RUN-MANIFEST.md"
    assert manifest.is_file()
    text = manifest.read_text(encoding="utf-8")
    assert "## Units (priority order = dispatch order)" in text
    assert "## Commit policy" in text
    assert "Stage ONLY files your unit owns" in text
    state = load_run(run_dir)
    assert [u.slug for u in state.units] == ["alpha", "bravo"]
    assert [u.id for u in state.units] == ["u01", "u02"]
    # state.json is valid JSON with a monotonic revision >= 1.
    import json

    payload = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    assert payload["revision"] >= 1
    assert payload["units"][0]["paths"] == ["a.py"]


@pytest.mark.unit
def test_init_refuses_zero_unit_run(tmp_path: Path) -> None:
    with pytest.raises(FleetInitError, match="zero-unit"):
        init_run(tmp_path / ".context", [], budget_usd=10.0, max_parallel=2)


@pytest.mark.unit
def test_init_refuses_duplicate_slugs(tmp_path: Path) -> None:
    with pytest.raises(FleetInitError, match="duplicate unit slugs: alpha"):
        init_run(
            tmp_path / ".context",
            _specs(("alpha", ("a.py",)), ("alpha", ("b.py",))),
            budget_usd=10.0,
            max_parallel=2,
        )


@pytest.mark.unit
def test_init_refuses_bad_budget_parallel_and_template(tmp_path: Path) -> None:
    specs = _specs(("alpha", ("a.py",)))
    with pytest.raises(FleetInitError, match="--budget-usd must be > 0"):
        init_run(tmp_path / ".context", specs, budget_usd=0, max_parallel=1)
    with pytest.raises(FleetInitError, match="--max-parallel must be >= 1"):
        init_run(tmp_path / ".context", specs, budget_usd=1.0, max_parallel=0)
    with pytest.raises(FleetInitError, match="must contain \\{id\\} and \\{slug\\}"):
        init_run(
            tmp_path / ".context",
            specs,
            budget_usd=1.0,
            max_parallel=1,
            branch_template="no-tokens-here",
        )


@pytest.mark.unit
def test_init_warns_and_serializes_units_without_paths(tmp_path: Path) -> None:
    state, warnings = init_run(
        tmp_path / ".context",
        _specs(("mystery", ()), ("known", ("k.py",))),
        budget_usd=5.0,
        max_parallel=4,
    )
    assert any("no member paths known" in w for w in warnings)
    env = next_units(state)
    # The empty-path unit intersects everything: only it dispatches this round,
    # and every other unit is held back behind its unknown footprint.
    assert [u.id for u in env.units] == ["u01"]
    assert any("intersect" in r for _i, r in env.skipped)


@pytest.mark.unit
def test_branch_rendering_is_token_replacement_not_format(tmp_path: Path) -> None:
    assert render_branch("{run}/{id}-{slug}", "0007", "u02", "fix-thing") == (
        "0007/u02-fix-thing"
    )
    # A caller template may carry stray braces — never str.format.
    assert render_branch("x/{id}/{id}", "r", "u1", "s") == "x/u1/u1"


@pytest.mark.unit
def test_next_run_id_pads_and_increments(tmp_path: Path) -> None:
    ctx = tmp_path / ".context"
    assert next_run_id(ctx) == "0001"
    (ctx / "fleet" / "run-0009").mkdir(parents=True)
    (ctx / "fleet" / "maintain-x").mkdir()  # different prefix is ignored
    assert next_run_id(ctx) == "0010"


@pytest.mark.unit
def test_slug_charset_enforced() -> None:
    with pytest.raises(FleetSlugError):
        validate_unit_specs([UnitSpec("Bad Slug")])
    with pytest.raises(FleetSlugError):
        validate_unit_specs([UnitSpec("-leading")])
    assert validate_unit_specs([UnitSpec("OK-thing_1")])[0].slug == "ok-thing_1"


# ----- intake parsing -------------------------------------------------------


@pytest.mark.unit
def test_units_from_intake_reads_paths_and_ignores_host_metadata() -> None:
    specs = units_from_intake(
        {
            "units": [
                {
                    "ticket": "T-1",
                    "title": "Fix thing",
                    "paths": ["src/a.py", "", "src/a.py"],
                    "repo_hint": "ignored-host-metadata",
                },
                {"title": "No ticket id"},
            ]
        }
    )
    assert specs[0].slug == "T-1"  # verbatim; init_run's validation lowercases
    assert specs[0].paths == ("src/a.py",)  # deduped, blanks dropped
    assert specs[0].ticket == "T-1"
    assert specs[1].slug == "unit-2"
    with pytest.raises(FleetInitError):
        units_from_intake({"nope": True})


@pytest.mark.unit
def test_units_from_plans_reads_member_files_and_warns_when_absent(
    tmp_path: Path,
) -> None:
    ctx = tmp_path / ".context"
    prop = ctx / "proposals" / "with-files"
    prop.mkdir(parents=True)
    (prop / "proposal.json").write_text(
        '{"slug": "with-files", "member_files": ["src/x.py"], "title": "X"}',
        encoding="utf-8",
    )
    bare = ctx / "proposals" / "bare"
    bare.mkdir(parents=True)
    (bare / "proposal.json").write_text('{"slug": "bare"}', encoding="utf-8")

    specs, warnings = units_from_plans(ctx, ["with-files", "bare"])
    assert specs[0].paths == ("src/x.py",)
    assert specs[0].title == "X"
    assert specs[1].paths == ()
    assert len(warnings) == 1 and "bare" in warnings[0]
    with pytest.raises(FleetSlugError, match="not found"):
        units_from_plans(ctx, ["ghost"])


# ----- dispatch frontier ----------------------------------------------------


def _unit(uid: str, slug: str, paths: tuple[str, ...], status: str = "pending"):
    return FleetUnit(
        id=uid, slug=slug, branch=f"{uid}-{slug}", status=status, paths=paths
    )


def _state(units: tuple[FleetUnit, ...], *, max_parallel: int = 4, cap: float = 100.0):
    from dummyindex.context.domains.fleetrun import FleetRunState

    return FleetRunState(
        run_id="0001",
        units=units,
        budget=Budget(cap_usd=cap, spent_est_usd=0.0),
        max_parallel=max_parallel,
        branch_template="{run}/{id}-{slug}",
    )


@pytest.mark.unit
def test_next_respects_priority_cap_and_disjointness() -> None:
    state = _state(
        (
            _unit("u01", "a", ("shared.py",)),
            _unit("u02", "b", ("shared.py",)),
            _unit("u03", "c", ("c.py",)),
            _unit("u04", "d", ("d.py",)),
            _unit("u05", "e", ("e.py",)),
        ),
        max_parallel=2,
    )
    env = next_units(state)
    assert isinstance(env, NextEnvelope) and env.status == "ok"
    assert [u.id for u in env.units] == ["u01", "u03"]
    reasons = dict(env.skipped)
    assert "intersect" in reasons["u02"]
    assert reasons["u04"] == "parallel cap reached this round"


@pytest.mark.unit
def test_next_skips_gated_blocked_and_inflight_with_reasons() -> None:
    state = _state(
        (
            _unit("u01", "a", (), status="gated"),
            _unit("u02", "b", ("b.py",), status="blocked"),
            _unit("u03", "c", ("c.py",), status="building"),
            _unit("u04", "d", ("d.py",)),
        )
    )
    env = next_units(state)
    assert [u.id for u in env.units] == ["u04"]
    reasons = dict(env.skipped)
    assert reasons["u01"].startswith("gated")
    assert reasons["u02"] == "blocked"
    assert "in-flight" in reasons["u03"]


@pytest.mark.unit
def test_gated_unit_stays_skipped_until_answered(tmp_path: Path) -> None:
    run_dir = _init(tmp_path, _specs(("a", ("a.py",)), ("b", ("b.py",))))
    checkpoint(run_dir, "u01", gate="Which migration strategy?")
    env = next_units(load_run(run_dir))
    assert [u.id for u in env.units] == ["u02"]
    # Answering the gate requires --status; the question clears permanently...
    checkpoint(run_dir, "u01", status="pending", note="strategy B chosen")
    env2 = next_units(load_run(run_dir))
    assert [u.id for u in env2.units] == ["u01", "u02"]
    answered = load_run(run_dir).unit("u01")
    assert answered.gate_question is None
    assert answered.status == "pending"
    # ...and an answered unit that moved on (e.g. building) is in-flight, not
    # re-dispatched.
    checkpoint(run_dir, "u01", status="building")
    env3 = next_units(load_run(run_dir))
    assert [u.id for u in env3.units] == ["u02"]
    assert dict(env3.skipped)["u01"].startswith("in-flight")


@pytest.mark.unit
def test_gate_requires_nonempty_question_and_answer_requires_status(
    tmp_path: Path,
) -> None:
    run_dir = _init(tmp_path, _specs(("a", ("a.py",))))
    with pytest.raises(FleetUnitError, match="non-empty"):
        checkpoint(run_dir, "u01", gate="   ")
    checkpoint(run_dir, "u01", gate="real question?")
    with pytest.raises(FleetUnitError, match="gated on"):
        checkpoint(run_dir, "u01")


@pytest.mark.unit
def test_deterministic_sort_key_priority_then_unit_id() -> None:
    # Equal effective priorities still traverse by unit id — stable, ordered.
    state = _state(
        (
            _unit("u09", "i", ("i.py",)),
            _unit("u04", "d", ("d.py",)),
            _unit("u01", "a", ("a.py",)),
        )
    )
    env = next_units(state)
    assert [u.id for u in env.units] == ["u09", "u04", "u01"]
    mo = merge_order(state)
    assert [e.unit.id for e in mo] == ["u09", "u04", "u01"]


# ----- budget breaker -------------------------------------------------------


@pytest.mark.unit
def test_budget_halts_at_cap_with_resume_instructions(tmp_path: Path) -> None:
    run_dir = _init(
        tmp_path, _specs(("a", ("a.py",)), ("b", ("b.py",))), budget_usd=10.0
    )
    add_spend(run_dir, "u01", 6.0)
    add_spend(run_dir, "u02", 4.0)
    state = load_run(run_dir)
    assert budget_halted(state)
    env = next_units(state)
    assert env.status == "BUDGET-HALT"
    assert env.units == ()
    joined = "\n".join(env.resume)
    assert "--adjust" in joined
    assert "$10.00" in joined
    # The breaker latches: even at exactly the cap nothing dispatches.
    add_spend(run_dir, "u02", -4.0, adjust=True)
    env_ok = next_units(load_run(run_dir))
    assert env_ok.status == "ok" and len(env_ok.units) == 2


@pytest.mark.unit
def test_negative_spend_requires_adjust_flag(tmp_path: Path) -> None:
    run_dir = _init(tmp_path, _specs(("a", ("a.py",))), budget_usd=10.0)
    with pytest.raises(FleetUnitError, match="--adjust"):
        add_spend(run_dir, "u01", -1.0)
    with pytest.raises(FleetUnitError, match="negative"):
        add_spend(run_dir, "u01", -99.0, adjust=True)
    add_spend(run_dir, "u01", 5.0)
    budget = add_spend(run_dir, "u01", -1.0, adjust=True).budget
    assert budget.spent_est_usd == 4.0


@pytest.mark.unit
def test_checkpoint_unknown_unit_fails_loud(tmp_path: Path) -> None:
    run_dir = _init(tmp_path, _specs(("a", ("a.py",))))
    with pytest.raises(FleetUnitError, match="unknown unit"):
        checkpoint(run_dir, "ghost")


# ----- RMW concurrency + revision -------------------------------------------


@pytest.mark.unit
def test_concurrent_checkpoint_and_spend_never_lose_increments(
    tmp_path: Path,
) -> None:
    """The lock-serialized read-modify-write contract: N concurrent spend adds
    plus M checkpoints against the same run dir land EVERY increment."""
    run_dir = _init(
        tmp_path, _specs(("a", ("a.py",)), ("b", ("b.py",))), budget_usd=1000.0
    )

    def spend(_i: int) -> None:
        add_spend(run_dir, "u01", 1.0)

    def tick(_i: int) -> None:
        checkpoint(run_dir, "u02", wave=_i % 5)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(spend, range(20)))
        list(pool.map(tick, range(20)))

    state = load_run(run_dir)
    assert state.budget.spent_est_usd == 20.0
    assert state.revision == 41  # started at 1; every mutation bumped once
    assert state.unit("u01").spend_est_usd == 20.0


@pytest.mark.unit
def test_lock_timeout_raises_instead_of_writing_blind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dummyindex.context.domains import fleetrun as fr

    run_dir = _init(tmp_path, _specs(("a", ("a.py",))))
    monkeypatch.setattr(fr, "_LOCK_ATTEMPTS", 2)
    monkeypatch.setattr(fr, "_LOCK_RETRY_SECONDS", 0.0)
    (run_dir / ".lock").write_text("someone-else", encoding="utf-8")
    with pytest.raises(fr.FleetLockError, match="stale"):
        add_spend(run_dir, "u01", 1.0)


# ----- loud failure on corruption -------------------------------------------


@pytest.mark.unit
def test_load_run_fails_loud_with_repair_instructions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deliberate divergence from gc/anchor tolerance: fleet state is the only
    recovery path, so every corruption raises WITH printed repair/re-init
    instructions instead of degrading to a tolerant None."""
    run_dir = _init(tmp_path, _specs(("a", ("a.py",))))

    missing = tmp_path / "nope"
    with pytest.raises(FleetStateCorruptError, match="does not exist"):
        load_run(missing)

    torn = tmp_path / "torn"
    torn.mkdir()
    (torn / "RUN-MANIFEST.md").write_text("# manifest\n", encoding="utf-8")
    with pytest.raises(FleetStateCorruptError, match="never went live"):
        load_run(torn)

    manifestless = tmp_path / "manifestless"
    write_state(manifestless, load_run(run_dir))
    with pytest.raises(FleetStateCorruptError, match="torn init"):
        load_run(manifestless)

    corrupt = tmp_path / "corrupt"
    corrupt.mkdir()
    (corrupt / "RUN-MANIFEST.md").write_text("# m\n", encoding="utf-8")
    (corrupt / "state.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(FleetStateCorruptError, match=r"invalid JSON"):
        load_run(corrupt)

    badshape = tmp_path / "badshape"
    badshape.mkdir()
    (badshape / "RUN-MANIFEST.md").write_text("# m\n", encoding="utf-8")
    (badshape / "state.json").write_text('{"run_id": ""}', encoding="utf-8")
    with pytest.raises(FleetStateCorruptError) as exc:
        load_run(badshape)
    assert "re-init a fresh run" in str(exc.value)


@pytest.mark.unit
def test_state_round_trip_rejects_off_alphabet_status(tmp_path: Path) -> None:
    run_dir = _init(tmp_path, _specs(("a", ("a.py",))))
    state = load_run(run_dir)
    tampered = _state_dict_with(state, unit_overrides={"status": "quantum"})
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "RUN-MANIFEST.md").write_text("# m\n", encoding="utf-8")
    (bad / "state.json").write_text(tampered, encoding="utf-8")
    with pytest.raises(FleetStateCorruptError, match="unknown status 'quantum'"):
        load_run(bad)
    assert FleetUnitStatus("gated").value == "gated"


def _state_dict_with(state: object, *, unit_overrides: dict) -> str:
    import json

    from dummyindex.context.domains.fleetrun import _state_dict

    payload = _state_dict(state)  # type: ignore[arg-type]
    payload["units"][0].update(unit_overrides)
    return json.dumps(payload)


# ----- merge order ----------------------------------------------------------


@pytest.mark.unit
def test_merge_order_cites_disjointness_rationale_and_is_stable() -> None:
    units = (
        _unit("u01", "a", ("shared.py", "a.py")),
        _unit("u02", "b", ("shared.py", "b.py")),
        _unit("u03", "c", ("c.py",)),
    )
    entries = merge_order(_state(units))
    assert [(e.position, e.unit.id) for e in entries] == [
        (0, "u01"),
        (1, "u02"),
        (2, "u03"),
    ]
    assert entries[0].reason == "first to land"
    assert entries[1].reason.startswith("lands after u01: shares shared.py")
    assert entries[2].reason == "parallel-safe with all above (disjoint paths)"

    done_first = merge_order(
        _state(
            (
                _unit("u01", "a", ("a.py",), status="done"),
                _unit("u02", "b", ("b.py",)),
            )
        )
    )
    assert [e.landed for e in done_first] == [True, False]
    again = merge_order(_state(units))
    assert [e.unit.id for e in again] == [e.unit.id for e in entries]
