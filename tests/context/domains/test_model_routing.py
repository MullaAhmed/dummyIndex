"""Model routing — precedence, closed key set, alias validation.

The domain-level contract of build-dispatch-fanout-fix's routing module:
routing is proposal data validated against the existing ``ModelChoice``
alphabet (reuse, no new enum), with ``build --route`` overriding at run
time. Precedence: invocation > proposal > unset.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dummyindex.context.domains.buildloop import BuildLoopError
from dummyindex.context.domains.buildloop.routing import (
    ROUTING_KEYS,
    parse_route_flags,
    read_proposal_routing,
    resolve_routing,
    validate_routing,
)
from dummyindex.context.domains.config import ModelChoice

pytestmark = pytest.mark.unit


def _write_proposal(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "proposal.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# ----- unset / proposal-only --------------------------------------------------


def test_absent_file_is_unset(tmp_path: Path) -> None:
    assert resolve_routing(tmp_path / "missing.json") == {}


def test_proposal_without_routing_key_is_unset(tmp_path: Path) -> None:
    path = _write_proposal(tmp_path, {"slug": "x"})
    assert resolve_routing(path) == {}


def test_proposal_routing_block_resolved_verbatim(tmp_path: Path) -> None:
    path = _write_proposal(
        tmp_path,
        {
            "slug": "x",
            "routing": {"implementer": "sonnet", "auditor": "opus"},
        },
    )
    assert resolve_routing(path) == {"implementer": "sonnet", "auditor": "opus"}


def test_empty_routing_block_is_unset(tmp_path: Path) -> None:
    path = _write_proposal(tmp_path, {"slug": "x", "routing": {}})
    assert resolve_routing(path) == {}


# ----- precedence: invocation > proposal > unset ------------------------------


def test_override_adds_roles_beyond_the_proposal(tmp_path: Path) -> None:
    path = _write_proposal(
        tmp_path, {"slug": "x", "routing": {"implementer": "sonnet"}}
    )
    resolved = resolve_routing(path, {"decisions": "current"})
    assert resolved == {"implementer": "sonnet", "decisions": "current"}


def test_override_beats_proposal_on_the_same_role(tmp_path: Path) -> None:
    path = _write_proposal(
        tmp_path,
        {"slug": "x", "routing": {"implementer": "sonnet", "auditor": "haiku"}},
    )
    resolved = resolve_routing(path, {"implementer": "opus"})
    assert resolved == {"implementer": "opus", "auditor": "haiku"}


def test_invocation_without_proposal_still_routes(tmp_path: Path) -> None:
    assert resolve_routing(tmp_path / "missing.json", {"implementer": "fable"}) == {
        "implementer": "fable"
    }


# ----- validation: closed keys + ModelChoice aliases --------------------------


def test_every_model_choice_alias_is_legal(tmp_path: Path) -> None:
    for alias in ModelChoice:
        resolved = validate_routing({"implementer": alias.value}, origin="t")
        assert resolved["implementer"] == alias.value
    assert "current" in {m.value for m in ModelChoice}


def test_unknown_key_rejected() -> None:
    with pytest.raises(BuildLoopError) as excinfo:
        validate_routing({"writer": "sonnet"}, origin="t")
    message = str(excinfo.value)
    assert "unknown routing key 'writer'" in message
    for role in ROUTING_KEYS:
        assert role in message


def test_invalid_alias_rejected_and_named() -> None:
    with pytest.raises(BuildLoopError) as excinfo:
        validate_routing({"implementer": "gpt-9"}, origin="t")
    message = str(excinfo.value)
    assert "not one of" in message
    for member in ModelChoice:
        assert member.value in message


def test_non_string_alias_rejected() -> None:
    with pytest.raises(BuildLoopError):
        validate_routing({"implementer": 3}, origin="t")


def test_non_mapping_payload_rejected() -> None:
    with pytest.raises(BuildLoopError):
        validate_routing(["sonnet"], origin="t")  # type: ignore[arg-type]


def test_hand_edited_proposal_fails_loudly_with_its_path(tmp_path: Path) -> None:
    path = _write_proposal(tmp_path, {"slug": "x", "routing": {"implementer": "nope"}})
    with pytest.raises(BuildLoopError) as excinfo:
        read_proposal_routing(path)
    assert str(path) in str(excinfo.value)


def test_malformed_proposal_json_raises_build_loop_error(tmp_path: Path) -> None:
    path = tmp_path / "proposal.json"
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(BuildLoopError):
        read_proposal_routing(path)


# ----- CLI-side token parsing -------------------------------------------------


def test_parse_route_flags_accepts_repeatable_kv_pairs() -> None:
    parsed = parse_route_flags(
        ["implementer=sonnet", "auditor=opus", "decisions=current"]
    )
    assert parsed == {
        "implementer": "sonnet",
        "auditor": "opus",
        "decisions": "current",
    }


def test_parse_route_flags_last_token_wins_per_role() -> None:
    parsed = parse_route_flags(["implementer=opus", "implementer=sonnet"])
    assert parsed == {"implementer": "sonnet"}


@pytest.mark.parametrize("token", ["sonnet", "=sonnet", "implementer=", "", "a=b=c"])
def test_parse_route_flags_rejects_malformed_tokens(token: str) -> None:
    with pytest.raises(BuildLoopError):
        parse_route_flags([token])


def test_parse_route_flags_validates_values_through_the_shared_validator() -> None:
    with pytest.raises(BuildLoopError):
        parse_route_flags(["implementer=bogus"])
