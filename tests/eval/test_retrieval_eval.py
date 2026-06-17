"""Correctness-gated retrieval eval over the frozen ``SAMPLE_REPO`` index.

This is the spec's improvement #4 (Contract §4, Decision **D5**). It reuses the
deterministic ``query()`` retrieval — **no retrieval-logic change** — and the
``SAMPLE_REPO`` + ``build_all`` fixture that ``tests/context/domains/test_query.py``
uses, giving a stable index with authored ids (``community-0`` = ``app.py``,
``community-1`` = ``web/app.ts``, ``community-2`` = ``helpers.py``). The live
``.context/`` is un-enriched and re-clusters on rebuild, so gating on its ids
would be brittle.

What it does, mirroring ponytail's ``loc.js`` + ``correctness.js``:

- *Recording* (always printed): **MRR**, **hit-rate@3**, **mean tokens-to-answer**.
- *Gate*: ``hit_rate_at_3 >= T_HIT`` **and** ``MRR >= T_MRR``, where the floors
  are set one documented margin below the observed baseline recorded in
  ``BASELINE.md``.
- *Negative control* (permanent): a known-wrong fixture is asserted to score
  0 / rank ∞ — so the gate is non-vacuous.
- *Fixture validation* (Acceptance §4): every positive fixture's question shares
  ≥1 non-stopword token with a file basename or symbol name of its expected
  feature in the built index.

In this frozen index ``features/INDEX.json`` carries no ``files`` key, so a
positive's ``expected_path`` surfaces via a match's **citations**, not a
``files`` field — assertions key on citations (and feature-id rank).
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from tests.paths import SAMPLE_REPO

from dummyindex.context.build.runner import build_all
from dummyindex.context.domains.query import query, tokenize

# ---------------------------------------------------------------------------
# Gate floors — set ONE documented margin below the observed baseline.
# See tests/eval/BASELINE.md for the observed numbers (MRR 1.0, hit@3 1.0,
# mean tokens 40.5) and the rationale for these margins. Do not lower these
# to make a regression pass: a drop below them is a real retrieval regression.
# ---------------------------------------------------------------------------
T_HIT = 0.90   # hit-rate@3 floor (observed 1.0; 0.10 absolute margin)
T_MRR = 0.85   # MRR floor        (observed 1.0; 0.15 absolute margin)

_TOP_K = 3
_FIXTURES_PATH = Path(__file__).resolve().parent / "retrieval_fixtures.json"


# ---------------------------------------------------------------------------
# Fixtures — build the sample index ONCE per module (build_all is the costly
# bit: tree-sitter parse + graph + cluster). Both metrics and validation read
# the same frozen index.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def indexed_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A ``SAMPLE_REPO`` copy that's been through ``build_all`` once."""
    base = tmp_path_factory.mktemp("eval_repo")
    dest = base / "sample_repo"
    shutil.copytree(SAMPLE_REPO, dest)
    build_all(dest, cache_root=base / "cache")
    return dest


def _load_fixtures() -> list[dict]:
    return json.loads(_FIXTURES_PATH.read_text(encoding="utf-8"))


def _positives() -> list[dict]:
    return [f for f in _load_fixtures() if not f.get("negative_control")]


def _negative_control() -> dict:
    negatives = [f for f in _load_fixtures() if f.get("negative_control")]
    assert len(negatives) == 1, "expected exactly one negative_control fixture"
    return negatives[0]


# ---------------------------------------------------------------------------
# Per-fixture evaluation helpers (pure — no I/O beyond the supplied ctx dir).
# ---------------------------------------------------------------------------


def _expected_rank(matches, expected_feature_id: str) -> int | None:
    """1-based rank of the expected feature in ``matches``, or None if absent."""
    for i, m in enumerate(matches):
        if m.feature.feature_id == expected_feature_id:
            return i + 1
    return None


def _path_in_citations(match, expected_path: str) -> bool:
    """Whether ``expected_path`` surfaces in this match's citations.

    The frozen-index INDEX.json carries no ``files`` key, so the stable path
    surfaces via citations (which join feature members → ``map/symbols.json``).
    A citation path is repo-relative (e.g. ``web/app.ts``); match it exactly or
    as a trailing path segment.
    """
    for c in match.citations:
        cpath = c.path
        if cpath == expected_path or cpath.endswith("/" + expected_path):
            return True
    return False


# ---------------------------------------------------------------------------
# The gate — MRR + hit-rate@3 over the positive fixtures.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_retrieval_eval_gate(indexed_repo: Path) -> None:
    """Run every positive fixture through ``query`` and gate on MRR + hit@3.

    Records (and prints) MRR, hit-rate@3, and mean tokens-to-answer; asserts
    the two correctness floors from BASELINE.md. The metrics print via
    ``print`` so pytest surfaces them under ``-s`` and in the report on failure.
    """
    ctx = indexed_repo / ".context"
    positives = _positives()
    assert len(positives) >= 12, "spec requires ≥12 positive fixtures"

    reciprocal_ranks: list[float] = []
    hits: list[int] = []
    token_costs: list[int] = []

    for fx in positives:
        expected_id = fx["expected_feature_id"]
        expected_path = fx["expected_path"]
        result = query(ctx, fx["question"], top_k=_TOP_K)

        rank = _expected_rank(result.matches, expected_id)
        reciprocal_ranks.append(1.0 / rank if rank is not None else 0.0)
        hits.append(1 if rank is not None else 0)
        token_costs.append(result.total_estimated_tokens)

        # When we do hit, the stable expected path must surface in that match's
        # citations (paths survive re-clustering; ids do not).
        if rank is not None:
            assert _path_in_citations(result.matches[rank - 1], expected_path), (
                f"{expected_id}: expected_path {expected_path!r} absent from "
                f"citations {[c.path for c in result.matches[rank - 1].citations]!r} "
                f"for question {fx['question']!r}"
            )

    n = len(positives)
    mrr = sum(reciprocal_ranks) / n
    hit_rate_at_3 = sum(hits) / n
    mean_tokens = sum(token_costs) / n

    # Print so the metrics are visible in test output (pytest -rA / -s).
    print()
    print("=== retrieval eval (frozen SAMPLE_REPO index) ===")
    print(f"positives             : {n}")
    print(f"MRR                   : {mrr:.4f}  (floor T_MRR={T_MRR})")
    print(f"hit-rate@3            : {hit_rate_at_3:.4f}  (floor T_HIT={T_HIT})")
    print(f"mean tokens-to-answer : {mean_tokens:.4f}")

    # --- the gate ---
    assert hit_rate_at_3 >= T_HIT, (
        f"hit-rate@3 {hit_rate_at_3:.4f} below floor {T_HIT} — retrieval "
        f"regression (see tests/eval/BASELINE.md)"
    )
    assert mrr >= T_MRR, (
        f"MRR {mrr:.4f} below floor {T_MRR} — retrieval regression "
        f"(see tests/eval/BASELINE.md)"
    )


# ---------------------------------------------------------------------------
# Negative control — proves the gate is non-vacuous.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_negative_control_scores_zero(indexed_repo: Path) -> None:
    """The negative-control fixture's target must score 0 / rank ∞.

    Its question shares no token with any sample feature, so ``query`` returns
    no matches at all — the wrong target is absent (rank ∞, reciprocal rank 0).
    If this ever started matching, the gate above could pass vacuously.
    """
    ctx = indexed_repo / ".context"
    neg = _negative_control()
    result = query(ctx, neg["question"], top_k=_TOP_K)

    # The known-wrong target is absent from every match → rank ∞.
    matched_ids = [m.feature.feature_id for m in result.matches]
    assert neg["expected_feature_id"] not in matched_ids, (
        f"negative control unexpectedly matched its (wrong) target "
        f"{neg['expected_feature_id']!r}; matches={matched_ids!r}"
    )
    assert _expected_rank(result.matches, neg["expected_feature_id"]) is None

    # In this frozen index the off-topic question matches nothing at all, which
    # is the strongest form of "scores 0": no match has a positive score.
    assert result.matches == (), (
        f"negative control should produce no matches; got "
        f"{[(m.feature.feature_id, m.feature.score) for m in result.matches]!r}"
    )


# ---------------------------------------------------------------------------
# Fixture validation (Acceptance §4) — every positive question shares ≥1
# non-stopword token with a file basename or symbol name of its expected
# feature in the BUILT index.
# ---------------------------------------------------------------------------


def _feature_vocab(ctx: Path, feature_id: str) -> set[str]:
    """Tokens from the expected feature's file basenames + symbol names.

    Reads ``features/<id>/feature.json`` for ``files`` (basenames) and
    ``members``, joining members against ``map/symbols.json`` for symbol names —
    the same name/file signals ``query`` scores against. Tokenized with the
    public ``tokenize`` so the overlap check matches the scorer's vocabulary.
    """
    vocab: set[str] = set()

    feature_json = ctx / "features" / feature_id / "feature.json"
    payload = json.loads(feature_json.read_text(encoding="utf-8"))

    for fp in payload.get("files", []) or []:
        if isinstance(fp, str):
            basename = fp.rsplit("/", 1)[-1]
            vocab.update(tokenize(basename))

    member_ids = {m for m in payload.get("members", []) or [] if isinstance(m, str)}
    if member_ids:
        symbols_json = ctx / "map" / "symbols.json"
        if symbols_json.exists():
            sym_payload = json.loads(symbols_json.read_text(encoding="utf-8"))
            for s in sym_payload.get("symbols", []) or []:
                sid = s.get("symbol_id") or s.get("node_id")
                name = s.get("name")
                if sid in member_ids and isinstance(name, str):
                    vocab.update(tokenize(name))

    return vocab


@pytest.mark.integration
def test_every_positive_fixture_shares_a_token(indexed_repo: Path) -> None:
    """Each positive question overlaps its expected feature's name/file vocab.

    Since ``summary`` is null in the frozen index, the name/path/symbol overlap
    is what makes retrieval possible — this guards the fixtures against drifting
    into questions the deterministic scorer cannot answer.
    """
    ctx = indexed_repo / ".context"
    for fx in _positives():
        vocab = _feature_vocab(ctx, fx["expected_feature_id"])
        question_tokens = set(tokenize(fx["question"]))
        overlap = question_tokens & vocab
        assert overlap, (
            f"question {fx['question']!r} shares no non-stopword token with "
            f"feature {fx['expected_feature_id']!r} vocab {sorted(vocab)!r} "
            f"(question tokens {sorted(question_tokens)!r})"
        )
