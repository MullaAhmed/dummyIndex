"""Tests for dummyindex/cache.py."""
import pytest
from pathlib import Path
from dummyindex.pipeline.cache import file_hash, cache_dir, load_cached, save_cached, cached_files, clear_cache, _body_content


@pytest.fixture
def tmp_file(tmp_path):
    f = tmp_path / "sample.txt"
    f.write_text("hello world")
    return f


@pytest.fixture
def cache_root(tmp_path):
    return tmp_path


def test_file_hash_consistent(tmp_file):
    """Same file gives same hash on repeated calls."""
    h1 = file_hash(tmp_file)
    h2 = file_hash(tmp_file)
    assert h1 == h2
    assert isinstance(h1, str)
    assert len(h1) == 64  # SHA256 hex digest length


def test_file_hash_changes(tmp_path):
    """Different file contents give different hashes."""
    f1 = tmp_path / "a.txt"
    f2 = tmp_path / "b.txt"
    f1.write_text("content one")
    f2.write_text("content two")
    assert file_hash(f1) != file_hash(f2)


def test_cache_roundtrip(tmp_file, cache_root):
    """Save then load returns the same result dict."""
    result = {"nodes": [{"id": "n1", "label": "Node1"}], "edges": []}
    save_cached(tmp_file, result, root=cache_root)
    loaded = load_cached(tmp_file, root=cache_root)
    assert loaded == result


def test_cache_miss_on_change(tmp_file, cache_root):
    """After file content changes, load_cached returns None."""
    result = {"nodes": [], "edges": [{"source": "a", "target": "b"}]}
    save_cached(tmp_file, result, root=cache_root)
    # Modify the file
    tmp_file.write_text("completely different content")
    assert load_cached(tmp_file, root=cache_root) is None


def test_cached_files(tmp_path, cache_root):
    """cached_files returns the set of cached hashes."""
    f1 = tmp_path / "file1.py"
    f2 = tmp_path / "file2.py"
    f1.write_text("alpha")
    f2.write_text("beta")

    save_cached(f1, {"nodes": [], "edges": []}, root=cache_root)
    save_cached(f2, {"nodes": [], "edges": []}, root=cache_root)

    hashes = cached_files(cache_root)
    assert file_hash(f1, cache_root) in hashes
    assert file_hash(f2, cache_root) in hashes


def test_clear_cache(tmp_file, cache_root):
    """clear_cache removes all .json files from dummyindex-out/cache/."""
    save_cached(tmp_file, {"nodes": [], "edges": []}, root=cache_root)
    assert len(list((cache_root / "dummyindex-out" / "cache").glob("*.json"))) > 0
    clear_cache(cache_root)
    assert len(list((cache_root / "dummyindex-out" / "cache").glob("*.json"))) == 0


def test_md_frontmatter_only_change_same_hash(tmp_path):
    """Changing only frontmatter fields in a .md file does not change the hash."""
    f = tmp_path / "doc.md"
    f.write_text("---\nreviewed: 2026-01-01\n---\n\n# Title\n\nBody text.")
    h1 = file_hash(f)
    f.write_text("---\nreviewed: 2026-04-09\n---\n\n# Title\n\nBody text.")
    h2 = file_hash(f)
    assert h1 == h2


def test_md_body_change_different_hash(tmp_path):
    """Changing the body of a .md file produces a different hash."""
    f = tmp_path / "doc.md"
    f.write_text("---\nreviewed: 2026-01-01\n---\n\n# Title\n\nOriginal body.")
    h1 = file_hash(f)
    f.write_text("---\nreviewed: 2026-01-01\n---\n\n# Title\n\nChanged body.")
    h2 = file_hash(f)
    assert h1 != h2


def test_md_no_frontmatter_hashed_normally(tmp_path):
    """A .md file with no frontmatter is hashed by its full content."""
    f = tmp_path / "doc.md"
    f.write_text("# Just a heading\n\nNo frontmatter here.")
    h1 = file_hash(f)
    f.write_text("# Just a heading\n\nDifferent content.")
    h2 = file_hash(f)
    assert h1 != h2


def test_non_md_file_hashed_fully(tmp_path):
    """Non-.md files are still hashed by their full content."""
    f = tmp_path / "script.py"
    f.write_text("# comment\nx = 1")
    h1 = file_hash(f)
    f.write_text("# changed comment\nx = 1")
    h2 = file_hash(f)
    assert h1 != h2


def test_body_content_strips_frontmatter():
    """_body_content correctly strips YAML frontmatter."""
    content = b"---\ntitle: Test\n---\n\nActual body."
    assert _body_content(content) == b"\n\nActual body."


def test_body_content_no_frontmatter():
    """_body_content returns content unchanged when no frontmatter present."""
    content = b"No frontmatter here."
    assert _body_content(content) == content


# --- Content-addressable cache (fix for re-run cache misses) ---


def test_file_hash_is_path_independent(tmp_path):
    """Cache key must be content-only so re-runs from different cwds hit."""
    from dummyindex.pipeline.cache import file_hash
    a = tmp_path / "subdir1" / "file.txt"
    b = tmp_path / "subdir2" / "renamed.txt"
    a.parent.mkdir()
    b.parent.mkdir()
    a.write_text("identical content")
    b.write_text("identical content")
    assert file_hash(a, root=tmp_path / "subdir1") == file_hash(b, root=tmp_path / "subdir2")


def test_cache_round_trip_across_paths(tmp_path):
    """A file with identical content found at a different path within the same
    project should hit the cache from the previous run."""
    from dummyindex.pipeline.cache import save_cached, load_cached
    src1 = tmp_path / "subdir" / "original.py"
    src2 = tmp_path / "elsewhere" / "renamed.py"
    src1.parent.mkdir(); src2.parent.mkdir()
    src1.write_text("def foo(): pass")
    src2.write_text("def foo(): pass")
    save_cached(src1, {"nodes": [{"id": "n1"}], "edges": []}, root=tmp_path)
    loaded = load_cached(src2, root=tmp_path)
    assert loaded is not None
    assert loaded["nodes"] == [{"id": "n1"}]


def test_restore_hyperedges_from_disk(tmp_path):
    """Each pipeline step should preserve prior hyperedges in graph.json."""
    import networkx as nx
    from dummyindex.pipeline.export import attach_hyperedges, restore_hyperedges_from_disk

    G = nx.Graph()
    G.add_node("a")
    # Simulate Step 6c written graph.json with one flow
    (tmp_path / "graph.json").write_text(
        '{"nodes":[],"links":[],"hyperedges":[{"id":"flow:1","kind":"flow","label":"x","nodes":["a"]}]}'
    )
    n = restore_hyperedges_from_disk(G, tmp_path / "graph.json")
    assert n == 1
    assert G.graph["hyperedges"][0]["id"] == "flow:1"
    # Now Step 6d adds a feature — both should coexist after attach_hyperedges
    attach_hyperedges(G, [{"id": "feature:1", "kind": "feature", "label": "y", "nodes": ["a"]}])
    ids = [h["id"] for h in G.graph["hyperedges"]]
    assert "flow:1" in ids and "feature:1" in ids


def test_restore_hyperedges_no_op_on_missing_file(tmp_path):
    import networkx as nx
    from dummyindex.pipeline.export import restore_hyperedges_from_disk
    G = nx.Graph()
    n = restore_hyperedges_from_disk(G, tmp_path / "missing.json")
    assert n == 0
