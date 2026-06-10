"""Tests for the v0.14 stack-aware author picker (`context dev-pick`)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from dummyindex.cli.dev_pick import run as run_dev_pick
from dummyindex.context.domains.dev_pick import pick_dev


def _fs(*tokens: str) -> frozenset[str]:
    return frozenset(tokens)


# ---------------------------------------------------------------------------
# pick_dev — one assertion per branch of the precedence table
# ---------------------------------------------------------------------------


def test_branch1_fastapi_routes() -> None:
    pick = pick_dev(
        feature_files=("src/app/api/users.py", "src/app/routes/auth.py"),
        dep_tokens=_fs("fastapi", "pydantic"),
    )
    assert pick.persona_id == "dev-backend-fastapi"
    assert pick.subagent_type == "Backend Architect"
    assert pick.framework == "FastAPI"


def test_branch2_django_views() -> None:
    pick = pick_dev(
        feature_files=("app/accounts/views.py",),
        dep_tokens=_fs("django"),
    )
    assert pick.persona_id == "dev-backend-django"
    assert pick.subagent_type == "Backend Architect"
    assert pick.framework == "Django"


def test_branch3_spring_controller() -> None:
    pick = pick_dev(
        feature_files=("src/main/java/com/x/UserController.java",),
        dep_tokens=_fs("spring-boot"),
    )
    assert pick.persona_id == "dev-backend-spring"
    assert pick.subagent_type == "Backend Architect"
    assert pick.framework == "Spring Boot"


def test_branch3_spring_via_springframework_token() -> None:
    pick = pick_dev(
        feature_files=("UserController.java",),
        dep_tokens=_fs("springframework"),
    )
    assert pick.persona_id == "dev-backend-spring"


def test_branch4_node_route() -> None:
    pick = pick_dev(
        feature_files=("app/api/users/route.ts",),
        dep_tokens=_fs("next"),
    )
    assert pick.persona_id == "dev-backend-node"
    assert pick.subagent_type == "Backend Architect"
    assert pick.framework == "Node"


def test_branch4_node_via_express() -> None:
    pick = pick_dev(
        feature_files=("app/api/orders/route.js",),
        dep_tokens=_fs("express"),
    )
    assert pick.persona_id == "dev-backend-node"


def test_branch5_frontend_by_file_ext() -> None:
    pick = pick_dev(
        feature_files=("src/components/Button.tsx",),
        dep_tokens=_fs(),
    )
    assert pick.persona_id == "dev-frontend"
    assert pick.subagent_type == "Frontend Developer"
    # No framework token, .tsx implies React.
    assert pick.framework == "React"


def test_branch5_frontend_by_dep_token_vue() -> None:
    pick = pick_dev(
        feature_files=("src/widget.js",),
        dep_tokens=_fs("vue"),
    )
    assert pick.persona_id == "dev-frontend"
    assert pick.framework == "Vue"


def test_branch5_frontend_svelte_file_no_token() -> None:
    pick = pick_dev(
        feature_files=("src/Card.svelte",),
        dep_tokens=_fs(),
    )
    assert pick.persona_id == "dev-frontend"
    assert pick.framework == "Svelte"


def test_branch6_data_sql() -> None:
    pick = pick_dev(
        feature_files=("db/0001_init.sql",),
        dep_tokens=_fs(),
    )
    assert pick.persona_id == "dev-data"
    assert pick.subagent_type == "Data Engineer"
    assert pick.framework == "Data"


def test_branch6_data_migrations() -> None:
    pick = pick_dev(
        feature_files=("app/migrations/0002_add_col.py",),
        dep_tokens=_fs(),
    )
    assert pick.persona_id == "dev-data"


def test_branch7_ai_dep_token() -> None:
    pick = pick_dev(
        feature_files=("src/serve.py",),
        dep_tokens=_fs("torch"),
    )
    assert pick.persona_id == "dev-ai"
    assert pick.subagent_type == "AI Engineer"
    assert pick.framework == "AI"


def test_branch7_ai_path_marker() -> None:
    pick = pick_dev(
        feature_files=("ml/train_model.py",),
        dep_tokens=_fs(),
    )
    assert pick.persona_id == "dev-ai"


def test_branch7_ai_scikit_learn_hyphenated_token() -> None:
    pick = pick_dev(
        feature_files=("src/classify.py",),
        dep_tokens=_fs("scikit-learn"),
    )
    assert pick.persona_id == "dev-ai"


def test_branch8_fallback_generic() -> None:
    pick = pick_dev(
        feature_files=("src/util.go", "README.md"),
        dep_tokens=_fs("cobra"),
    )
    assert pick.persona_id == "dev-generic-senior"
    assert pick.subagent_type == "Senior Developer"
    assert pick.framework == "generic"


# ---------------------------------------------------------------------------
# Agent-availability fallback chain (PR3)
# ---------------------------------------------------------------------------


def test_specialist_fallback_chain() -> None:
    """A specialist degrades to Senior Developer, then general-purpose."""
    pick = pick_dev(
        feature_files=("src/app/api/users.py",),
        dep_tokens=_fs("fastapi"),
    )
    assert pick.subagent_type == "Backend Architect"
    assert pick.fallbacks == ("Senior Developer", "general-purpose")


def test_senior_fallback_chain_skips_itself() -> None:
    """The generic-senior pick falls straight back to general-purpose."""
    pick = pick_dev(feature_files=("src/util.go",), dep_tokens=_fs())
    assert pick.subagent_type == "Senior Developer"
    assert pick.fallbacks == ("general-purpose",)


def test_fallback_chain_always_ends_at_general_purpose() -> None:
    """Every pick ends at the always-available built-in, so dispatch never
    bottoms out with no agent."""
    for files, deps in (
        (("src/Button.tsx",), _fs()),          # frontend
        (("db/schema.sql",), _fs()),           # data
        (("ml/train.py",), _fs("torch")),      # ai
        (("src/util.go",), _fs()),             # generic-senior
    ):
        pick = pick_dev(feature_files=files, dep_tokens=deps)
        assert pick.fallbacks[-1] == "general-purpose"


# ---------------------------------------------------------------------------
# Precedence
# ---------------------------------------------------------------------------


def test_precedence_fastapi_beats_data() -> None:
    """A feature matching both fastapi-route (#1) and a .sql file (#6)
    resolves to fastapi because #1 precedes #6."""
    pick = pick_dev(
        feature_files=("app/api/users.py", "db/schema.sql"),
        dep_tokens=_fs("fastapi"),
    )
    assert pick.persona_id == "dev-backend-fastapi"


def test_precedence_node_beats_frontend() -> None:
    """app/api/route.ts with a next dep matches #4 before the .tsx
    frontend rule #5 would fire on a sibling file."""
    pick = pick_dev(
        feature_files=("app/api/users/route.ts", "app/page.tsx"),
        dep_tokens=_fs("next", "react"),
    )
    assert pick.persona_id == "dev-backend-node"


def test_to_dict_round_trip_serializes_plain_strings() -> None:
    """Drive a real picker branch, then round-trip through to_dict + json.

    Exercises actual picker output (not a hand-built literal), and proves the
    StrEnum fields serialize to plain wire strings via json.dumps.
    """
    pick = pick_dev(feature_files=("src/serve.py",), dep_tokens=_fs("torch"))
    as_dict = pick.to_dict()
    assert as_dict == {
        "persona_id": "dev-ai",
        "subagent_type": "AI Engineer",
        "framework": "AI",
        "fallbacks": ["Senior Developer", "general-purpose"],
    }
    # json round-trip yields bare strings, not "PersonaId.AI" repr forms.
    assert json.loads(json.dumps(as_dict)) == as_dict
    assert json.dumps(as_dict) == (
        '{"persona_id": "dev-ai", "subagent_type": "AI Engineer", '
        '"framework": "AI", "fallbacks": ["Senior Developer", "general-purpose"]}'
    )


# ---------------------------------------------------------------------------
# Fix #3 — AI-by-path is segment/basename anchored, `pipeline` is not a marker
# ---------------------------------------------------------------------------


def test_pipeline_segment_is_not_ai_without_ml_deps() -> None:
    """This repo's own `pipeline/` must not misclassify as AI."""
    pick = pick_dev(
        feature_files=("dummyindex/pipeline/runner.py",),
        dep_tokens=_fs(),
    )
    assert pick.persona_id == "dev-generic-senior"


def test_ai_training_segment_matches() -> None:
    pick = pick_dev(
        feature_files=("ml/training/run.py",),
        dep_tokens=_fs(),
    )
    assert pick.persona_id == "dev-ai"


def test_constrain_substring_does_not_false_positive_ai() -> None:
    """`train` as an unanchored substring once matched `constrain`."""
    pick = pick_dev(
        feature_files=("src/constrain_solver.py",),
        dep_tokens=_fs(),
    )
    assert pick.persona_id == "dev-generic-senior"


# ---------------------------------------------------------------------------
# Fix #4 — data markers models/schema are segment/basename anchored
# ---------------------------------------------------------------------------


def test_datamodels_and_schemaless_are_not_data() -> None:
    pick = pick_dev(
        feature_files=("app/datamodels.py", "app/schemaless.py"),
        dep_tokens=_fs(),
    )
    assert pick.persona_id == "dev-generic-senior"


def test_models_segment_is_data() -> None:
    pick = pick_dev(feature_files=("app/models/user.py",), dep_tokens=_fs())
    assert pick.persona_id == "dev-data"


def test_schema_sql_is_data() -> None:
    pick = pick_dev(feature_files=("db/schema.sql",), dep_tokens=_fs())
    assert pick.persona_id == "dev-data"


def test_migrations_segment_is_data() -> None:
    pick = pick_dev(feature_files=("migrations/0001.py",), dep_tokens=_fs())
    assert pick.persona_id == "dev-data"


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


def test_cmd_dev_pick_reads_feature_and_manifest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    feature_id = "auth"
    feat_dir = tmp_path / ".context" / "features" / feature_id
    feat_dir.mkdir(parents=True)
    (feat_dir / "feature.json").write_text(
        json.dumps({"files": ["src/app/api/login.py"]}), encoding="utf-8"
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project]\ndependencies = ["fastapi>=0.110", "pydantic"]\n',
        encoding="utf-8",
    )

    rc = run_dev_pick(["--feature", feature_id, str(tmp_path)])
    assert rc == 0

    out = json.loads(capsys.readouterr().out)
    assert out == {
        "persona_id": "dev-backend-fastapi",
        "subagent_type": "Backend Architect",
        "framework": "FastAPI",
        "fallbacks": ["Senior Developer", "general-purpose"],
    }


def test_cmd_dev_pick_missing_feature_returns_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / ".context" / "features").mkdir(parents=True)
    rc = run_dev_pick(["--feature", "nope", str(tmp_path)])
    assert rc == 2
    assert "not found" in capsys.readouterr().err


def _write_feature(tmp_path: Path, feature_id: str, files: list[str]) -> None:
    feat_dir = tmp_path / ".context" / "features" / feature_id
    feat_dir.mkdir(parents=True)
    (feat_dir / "feature.json").write_text(
        json.dumps({"files": files}), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Fix #1 — dotted Maven groupId splits into component tokens -> Spring matches
# ---------------------------------------------------------------------------


def test_cmd_dev_pick_spring_via_dotted_maven_groupid(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_feature(tmp_path, "orders", ["src/main/java/com/x/FooController.java"])
    (tmp_path / "pom.xml").write_text(
        "<project>\n"
        "  <dependencies>\n"
        "    <dependency>\n"
        "      <groupId>org.springframework.boot</groupId>\n"
        "      <artifactId>spring-boot-starter-web</artifactId>\n"
        "    </dependency>\n"
        "  </dependencies>\n"
        "</project>\n",
        encoding="utf-8",
    )

    rc = run_dev_pick(["--feature", "orders", str(tmp_path)])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["persona_id"] == "dev-backend-spring"
    assert out["framework"] == "Spring Boot"


# ---------------------------------------------------------------------------
# Fix #2 — prose in a description key does not inject framework dep tokens
# ---------------------------------------------------------------------------


def test_cmd_dev_pick_prose_description_does_not_misroute(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_feature(tmp_path, "core", ["src/core/util.py"])
    (tmp_path / "pyproject.toml").write_text(
        "[project]\n"
        'name = "core"\n'
        'description = "a django-style toolkit with fastapi-like ergonomics"\n'
        'dependencies = ["click", "rich"]\n',
        encoding="utf-8",
    )

    rc = run_dev_pick(["--feature", "core", str(tmp_path)])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["persona_id"] == "dev-generic-senior"
