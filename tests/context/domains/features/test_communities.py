"""`features/communities.py` — the community roll-up, pure half.

Identity is the contract: a card's slug comes from what the community
*contains* (dominant feature + top member), never from the partition
integer, because Leiden/Louvain ids renumber between runs and the
artifact is committed and diffed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dummyindex.context.domains.features.communities import (
    COMMUNITIES_SCHEMA_VERSION,
    GraphCommunity,
    rollup_communities,
)

_NODES = {
    "auth_login": {
        "label": "login()",
        "file_type": "code",
        "source_file": "/repo/app/auth.py",
        "source_location": "L1",
    },
    "auth_verify": {
        "label": "verify()",
        "file_type": "code",
        "source_file": "/repo/app/auth.py",
        "source_location": "L20",
    },
    "auth_note": {
        "label": "Why we log in.",
        "file_type": "rationale",
        "source_file": "/repo/app/auth.py",
        "source_location": "L2",
    },
}

_SCORES = {"auth_login": 0.6, "auth_verify": 0.2}


@pytest.mark.unit
def test_slug_comes_from_feature_and_top_member_not_the_partition_int() -> None:
    rolled = rollup_communities(
        _NODES,
        {7: ["auth_login", "auth_verify", "auth_note"]},
        _SCORES,
        owner_of_symbol={"auth_login": "auth", "auth_verify": "auth"},
    )
    (card,) = rolled.communities
    assert card.slug == "auth-login"
    assert "7" not in card.slug


@pytest.mark.unit
def test_rollup_is_identical_across_partition_renumbering() -> None:
    members = ["auth_login", "auth_verify", "auth_note"]
    first = rollup_communities(_NODES, {0: members}, _SCORES)
    second = rollup_communities(_NODES, {12: members}, _SCORES)
    assert first.to_dict() == second.to_dict()


@pytest.mark.unit
def test_rationale_nodes_are_neither_members_nor_size() -> None:
    rolled = rollup_communities(
        _NODES, {0: ["auth_login", "auth_verify", "auth_note"]}, _SCORES
    )
    (card,) = rolled.communities
    assert card.size == 2
    assert [m.id for m in card.members] == ["auth_login", "auth_verify"]


@pytest.mark.unit
def test_members_are_ranked_by_score_and_capped_at_top_k() -> None:
    rolled = rollup_communities(
        _NODES, {0: ["auth_verify", "auth_login"]}, _SCORES, top_k=1
    )
    (card,) = rolled.communities
    assert [m.id for m in card.members] == ["auth_login"]
    assert card.size == 2, "the cap trims the listing, not the community"


@pytest.mark.unit
def test_member_path_cites_repo_relative_file_and_line() -> None:
    rolled = rollup_communities(
        _NODES, {0: ["auth_login"]}, _SCORES, root=Path("/repo")
    )
    (card,) = rolled.communities
    assert card.members[0].path == "app/auth.py:1"


@pytest.mark.unit
def test_summary_quotes_the_best_ranked_member_docstring() -> None:
    rolled = rollup_communities(
        _NODES,
        {0: ["auth_login", "auth_verify"]},
        _SCORES,
        rationale_of={
            "auth_verify": "Verify things.",
            "auth_login": "Log the user in.\nMore detail nobody quotes.",
        },
    )
    (card,) = rolled.communities
    assert card.summary == "Log the user in."


@pytest.mark.unit
def test_colliding_slugs_get_deterministic_ordinals() -> None:
    nodes = {
        "a_login": {"label": "login()", "file_type": "code"},
        "b_login": {"label": "login()", "file_type": "code"},
    }
    rolled = rollup_communities(
        nodes,
        {0: ["a_login"], 1: ["b_login"]},
        {"a_login": 0.5, "b_login": 0.5},
        owner_of_symbol={"a_login": "auth", "b_login": "auth"},
    )
    assert [c.slug for c in rolled.communities] == ["auth-login", "auth-login-2"]


@pytest.mark.unit
def test_dominant_feature_is_the_plurality_owner() -> None:
    nodes = {
        "x": {"label": "x()", "file_type": "code"},
        "y": {"label": "y()", "file_type": "code"},
        "z": {"label": "z()", "file_type": "code"},
    }
    rolled = rollup_communities(
        nodes,
        {0: ["x", "y", "z"]},
        {"x": 0.9},
        owner_of_symbol={"x": "auth", "y": "billing", "z": "billing"},
    )
    (card,) = rolled.communities
    assert card.feature == "billing"
    assert card.slug == "billing-x", "slug pairs the owner with the top member"


@pytest.mark.unit
def test_empty_input_rolls_up_to_an_empty_artifact() -> None:
    assert rollup_communities({}, {}, {}).to_dict() == {
        "schema_version": COMMUNITIES_SCHEMA_VERSION,
        "communities": [],
    }


@pytest.mark.unit
def test_cards_are_frozen_data() -> None:
    card = GraphCommunity(slug="auth-login", size=1, members=())
    with pytest.raises(AttributeError):
        card.slug = "renamed"  # type: ignore[misc]
