"""Tests for textual cross-reference detection.

``_derive_textual_references`` is the O(F·text) single-pass matcher that replaced
an O(F²·text) per-pair ``str.find`` scan. The optimization is only valid if it is
**byte-faithful** — same chosen reference, same offset, same precedence (full path
over basename). These tests pin that:

- a frozen golden asserting the exact emitted edges on a hand-built stress
  fixture (full-path match, short-basename rejection, basename-collision
  rejection, overlapping/adjacent occurrences);
- a randomized differential test comparing the live matcher against a reference
  implementation of the old per-pair logic.
"""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from dummyindex.pipeline.build.common import _rel_path
from dummyindex.pipeline.build.references import (
    _derive_textual_references,
    _read_text_safely,
)


def _write(root: Path, spec: dict[str, str]) -> list[Path]:
    files: list[Path] = []
    for rel, content in spec.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        files.append(p)
    return files


def _derive(root: Path, spec: dict[str, str]) -> list[dict]:
    files = _write(root, spec)
    file_ids_by_rel = {rel: rel for rel in spec}  # rel doubles as a stable id
    cross: list[dict] = []
    _derive_textual_references(files, root, file_ids_by_rel, cross)
    return sorted(
        cross,
        key=lambda e: (e["source"], e["target"], e["relation"], e["source_location"]),
    )


# ---------------------------------------------------------------------------
# Frozen golden
# ---------------------------------------------------------------------------

# Exercises: full-path match, full-path-that-is-a-short-basename (x.py),
# long unique basename fallback (settings_loader.py), basename collision
# rejection (util.py / config.py), repeated + adjacent occurrences.
_STRESS_SPEC = {
    "app/main.py": (
        "import config\n# see app/util.py and util.py\n"
        "load x.py too\nref to settings_loader.py here\n"
    ),
    "app/util.py": "nothing relevant\n",
    "lib/util.py": "collides with app/util.py basename\n",
    "x.py": "short basename <5? 'x.py' is 4 chars -> rejected unless full path\n",
    "settings_loader.py": "unique long basename\n",
    "config.py": "import config\n",
    "app/config.py": "another config\n",
    "doc.md": (
        "references app/main.py twice: app/main.py and again app/main.py\n"
        "also settings_loader.py\n"
    ),
    "overlap.py": "aaaapp/util.pyapp/util.py edge\n",
}

_GOLDEN_EDGES = [
    ("app/main.py", "app/util.py", "offset:20"),
    ("app/main.py", "settings_loader.py", "offset:65"),
    ("app/main.py", "x.py", "offset:49"),
    ("doc.md", "app/main.py", "offset:11"),
    ("doc.md", "settings_loader.py", "offset:69"),
    ("lib/util.py", "app/util.py", "offset:14"),
    ("overlap.py", "app/util.py", "offset:3"),
]


@pytest.mark.unit
def test_derive_textual_references_matches_golden(tmp_path: Path) -> None:
    edges = _derive(tmp_path / "proj", _STRESS_SPEC)
    got = [(e["source"], e["target"], e["source_location"]) for e in edges]
    assert got == _GOLDEN_EDGES
    # Every edge is the generic INFERRED ``references`` relation.
    assert all(e["relation"] == "references" for e in edges)
    assert all(e["confidence"] == "INFERRED" for e in edges)


@pytest.mark.unit
def test_full_path_wins_over_basename(tmp_path: Path) -> None:
    """When both the full path and a unique basename appear, the recorded
    offset is the full-path occurrence — even if the basename appears earlier."""
    spec = {
        "src/loader.py": "loader.py mentioned first, then src/loader.py later\n",
        "main.py": "",
    }
    # source 'main.py' must reference 'src/loader.py'
    spec["main.py"] = "loader.py then src/loader.py\n"
    edges = _derive(tmp_path / "proj", spec)
    by_pair = {(e["source"], e["target"]): e["source_location"] for e in edges}
    # full path 'src/loader.py' starts at offset 15, not the basename at 0
    assert by_pair[("main.py", "src/loader.py")] == "offset:15"


# ---------------------------------------------------------------------------
# Randomized differential test vs the old per-pair implementation
# ---------------------------------------------------------------------------


def _old_find(text: str, tgt_rel: str, basename_to_rels: dict[str, list[str]]) -> int:
    """Reference implementation of the retired per-pair ``_find_reference``."""
    idx = text.find(tgt_rel)
    if idx >= 0:
        return idx
    tgt_name = Path(tgt_rel).name
    if len(tgt_name) < 5:
        return -1
    if len(basename_to_rels.get(tgt_name, [])) != 1:
        return -1
    return text.find(tgt_name)


def _old_derive(
    files: list[Path], root: Path, file_ids_by_rel: dict[str, str]
) -> list[dict]:
    rel_to_id: dict[str, str] = {}
    basename_to_rels: dict[str, list[str]] = {}
    for path in files:
        rel = _rel_path(str(path), root)
        fid = file_ids_by_rel.get(rel)
        if not rel or not fid:
            continue
        rel_to_id[rel] = fid
        basename_to_rels.setdefault(Path(rel).name, []).append(rel)
    keys: set[tuple[str, str, str]] = set()
    edges: list[dict] = []
    for path in files:
        src_rel = _rel_path(str(path), root)
        src_id = rel_to_id.get(src_rel)
        if not src_id:
            continue
        text = _read_text_safely(path)
        if not text:
            continue
        for tgt_rel, tgt_id in rel_to_id.items():
            if tgt_id == src_id:
                continue
            mi = _old_find(text, tgt_rel, basename_to_rels)
            if mi < 0:
                continue
            key = (src_id, tgt_id, "references")
            if key in keys:
                continue
            keys.add(key)
            edges.append(
                {"source": src_id, "target": tgt_id, "source_location": f"offset:{mi}"}
            )
    return sorted(edges, key=lambda e: (e["source"], e["target"], e["source_location"]))


@pytest.mark.unit
def test_matches_old_per_pair_logic_on_random_corpora(tmp_path: Path) -> None:
    """The single-pass matcher is byte-faithful to the old O(F²) scan across a
    fuzzed corpus of paths, basenames, padding, and overlapping occurrences."""
    rng = random.Random(1234)
    vocab = [
        "app",
        "lib",
        "src",
        "util",
        "main",
        "config",
        "x",
        "ab",
        "node",
        "run",
        "io",
        "db",
        "mod",
        "core",
        "test",
    ]
    exts = [".py", ".md", ".js", ".txt"]
    pads = ["", " ", "\n", "xx", "//", "aaa"]

    for trial in range(200):
        root = tmp_path / f"t{trial}"
        root.mkdir()
        rels: set[str] = set()
        for _ in range(rng.randint(2, 8)):
            depth = rng.randint(0, 2)
            parts = [rng.choice(vocab) for _ in range(depth)]
            parts.append(rng.choice(vocab) + rng.choice(exts))
            rels.add("/".join(parts))
        rel_list = list(rels)
        spec: dict[str, str] = {}
        for r in rel_list:
            chunks: list[str] = []
            for _ in range(rng.randint(0, 4)):
                tgt = rng.choice(rel_list)
                chunks.append(tgt if rng.random() < 0.5 else Path(tgt).name)
                chunks.append(rng.choice(pads))
            spec[r] = "".join(chunks)

        files = _write(root, spec)
        file_ids_by_rel = {rel: rel for rel in spec}

        cross: list[dict] = []
        _derive_textual_references(files, root, file_ids_by_rel, cross)
        new = sorted(
            (
                {
                    "source": e["source"],
                    "target": e["target"],
                    "source_location": e["source_location"],
                }
                for e in cross
            ),
            key=lambda e: (e["source"], e["target"], e["source_location"]),
        )
        old = _old_derive(files, root, file_ids_by_rel)
        assert new == old, f"diverged on trial {trial}: spec={spec}"
