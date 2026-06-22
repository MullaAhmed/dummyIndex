"""Hardening tests for the extraction walk (plan Task 4).

Covers the three fixes in ``dummyindex/pipeline/extract/__init__.py``:

- (a) symlink containment at ``collect_files`` leaf emission (walk-time),
- (b) ``global_label_to_nid`` collision disambiguation (skip, never last-bind),
- (c) ``id_remap`` immutability (build new dicts, don't mutate cached ones).
"""
from __future__ import annotations

import os
from pathlib import Path

import dummyindex.pipeline.extract as extract_mod
from dummyindex.pipeline.extract import collect_files, extract


# --- (a) symlink containment at collect_files leaf emission -------------------

def test_collect_files_rejects_symlink_escaping_root(tmp_path):
    """A symlink whose realpath is OUTSIDE root is not emitted under
    follow_symlinks=True, so neither read sink (cache-hash / extractor) can
    ever touch the out-of-tree target."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "inside.py").write_text("x = 1\n")

    # An out-of-tree target with distinctive content.
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    secret = outside_dir / "secret.py"
    secret.write_text("LEAKED = 'out-of-root'\n")

    # A symlink inside the repo pointing at the out-of-tree file.
    link = root / "escape.py"
    os.symlink(secret, link)

    files = collect_files(root, follow_symlinks=True, root=root)
    resolved = {os.path.realpath(p) for p in files}

    assert os.path.realpath(root / "inside.py") in resolved
    # The escaping symlink's realpath must not appear among emitted leaves.
    assert os.path.realpath(secret) not in resolved
    assert link.resolve() not in {p.resolve() for p in files}


def test_walk_does_not_read_out_of_tree_symlink_target(tmp_path):
    """End-to-end: extract over a repo containing an escaping symlink yields no
    node/edge carrying the out-of-root file's content."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "inside.py").write_text("def keep():\n    pass\n")

    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    secret = outside_dir / "secret.py"
    secret.write_text("def leaked_symbol():\n    pass\n")

    os.symlink(secret, root / "escape.py")

    files = collect_files(root, follow_symlinks=True, root=root)
    result = extract(files, cache_root=root)

    blob = repr(result["nodes"]) + repr(result["edges"])
    assert "leaked_symbol" not in blob
    # No node's source_file may resolve outside the repo root.
    for n in result["nodes"]:
        sf = n.get("source_file")
        if sf:
            assert os.path.realpath(sf).startswith(os.path.realpath(root))


# --- (b) global_label_to_nid collision disambiguation -------------------------

def _fake_extractor(nodes, raw_calls=()):
    def _inner(_path):
        return {"nodes": list(nodes), "edges": [], "raw_calls": list(raw_calls)}
    return _inner


def test_label_collision_skips_call_resolution(tmp_path, monkeypatch):
    """Two distinct symbols normalize to the same label key — a calls edge to
    that label is skipped, never bound to the last-iterated node."""
    a = tmp_path / "a.py"
    b = tmp_path / "b.py"
    c = tmp_path / "c.py"
    # Distinct bytes per file so the content-hash cache never serves one
    # file's parse for another.
    a.write_text("a = 1\n")
    b.write_text("b = 2\n")
    c.write_text("c = 3\n")

    # a.py and b.py each define a symbol whose normalized label is "helper".
    # c.py has a raw_call to "helper" — ambiguous, must be skipped.
    results = {
        a: {"nodes": [{"id": "a_helper", "label": "helper()",
                       "source_file": str(a)}],
            "edges": [], "raw_calls": []},
        b: {"nodes": [{"id": "b_helper", "label": "helper()",
                       "source_file": str(b)}],
            "edges": [], "raw_calls": []},
        c: {"nodes": [{"id": "c_caller", "label": "caller()",
                       "source_file": str(c)}],
            "edges": [],
            "raw_calls": [{"caller_nid": "c_caller", "callee": "helper",
                           "source_file": str(c)}]},
    }

    def fake(path):
        return results[path]

    monkeypatch.setitem(extract_mod._DISPATCH, ".py", fake)

    out = extract([a, b, c], cache_root=tmp_path)
    calls_targets = {
        e["target"] for e in out["edges"]
        if e.get("relation") == "calls" and e.get("source") == "c_caller"
    }
    # Must NOT have bound to either colliding node (the bug bound to last).
    assert "a_helper" not in calls_targets
    assert "b_helper" not in calls_targets


def test_unambiguous_label_still_resolves(tmp_path, monkeypatch):
    """Control: a unique label key still produces a calls edge (no over-skip)."""
    a = tmp_path / "a.py"
    c = tmp_path / "c.py"
    a.write_text("a = 1\n")
    c.write_text("c = 3\n")

    results = {
        a: {"nodes": [{"id": "a_helper", "label": "helper()",
                       "source_file": str(a)}],
            "edges": [], "raw_calls": []},
        c: {"nodes": [{"id": "c_caller", "label": "caller()",
                       "source_file": str(c)}],
            "edges": [],
            "raw_calls": [{"caller_nid": "c_caller", "callee": "helper",
                           "source_file": str(c)}]},
    }

    monkeypatch.setitem(extract_mod._DISPATCH, ".py", lambda p: results[p])

    out = extract([a, c], cache_root=tmp_path)
    calls = [e for e in out["edges"]
             if e.get("relation") == "calls" and e.get("source") == "c_caller"]
    assert any(e["target"] == "a_helper" for e in calls)


# --- (c) id_remap immutability ------------------------------------------------

def test_id_remap_does_not_mutate_cached_dicts(tmp_path, monkeypatch):
    """Patch load_cached to return a CAPTURED sentinel dict and assert the
    captured object's node id is untouched after extract (the remap pass must
    build new dicts, not mutate the cache-returned aliases)."""
    src = tmp_path / "pkg" / "mod.py"
    src.parent.mkdir(parents=True)
    src.write_text("x = 1\n")

    # With a single path, extract() resolves root = src.parent, so the remap
    # rewrites _make_id(str(src)) -> _make_id("mod.py"): the two differ, so the
    # id_remap pass fires and must build a NEW dict (not mutate the sentinel).
    old_id = extract_mod._make_id(str(src))
    new_id = extract_mod._make_id("mod.py")
    assert old_id != new_id  # guard: the remap genuinely fires

    sentinel_node = {"id": old_id, "label": "mod.py", "source_file": str(src)}
    captured = {"nodes": [sentinel_node], "edges": [], "raw_calls": []}

    def fake_load_cached(path, cache_root):
        return captured

    monkeypatch.setattr(extract_mod, "load_cached", fake_load_cached)
    monkeypatch.setitem(
        extract_mod._DISPATCH, ".py",
        lambda p: {"nodes": [], "edges": [], "raw_calls": []},
    )

    out = extract([src], cache_root=tmp_path)

    # The captured (first-call) object's id must be UNTOUCHED.
    assert sentinel_node["id"] == old_id
    assert captured["nodes"][0]["id"] == old_id
    # The remap ran on a COPY: the returned node carries the new id.
    returned_ids = {n["id"] for n in out["nodes"]}
    assert new_id in returned_ids
    assert old_id not in returned_ids
