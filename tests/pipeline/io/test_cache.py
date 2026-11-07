"""Tests for the hardened per-file extraction cache (``pipeline/io/cache.py``).

Covers the four hardening fixes from the ``outstanding-audit-fixes`` proposal:

- ``cache_dir`` confines the ambient ``DUMMYINDEX_CACHE_DIR`` env var to the
  repo root (silent fallback, never raises), while the trusted in-process
  override (``cache_dir_override`` → ``set_trusted_cache_dir``) still directs
  the cache to its target.
- ``load_cached`` applies an accept-superset schema guard: malformed payloads
  miss, a real round-tripped entry still hits.
- ``_body_content`` anchors the ``.md`` frontmatter fence to a bare ``---``
  line (no truncation at a non-bare ``---hack``).
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from dummyindex.context.build.common import cache_dir_override
from dummyindex.pipeline.io import load_cached, save_cached
from dummyindex.pipeline.io.cache import (
    _body_content,
    build_read_cache,
    cache_dir,
    file_hash,
    read_source_bytes,
    scope_cache_to_version,
    set_trusted_cache_dir,
)


@pytest.fixture(autouse=True)
def _clear_trusted_override() -> None:
    """Ensure no leaked trusted override bleeds across tests."""
    set_trusted_cache_dir(None)
    yield
    set_trusted_cache_dir(None)


# ----- cache_dir confinement + trusted override -----------------------------


@pytest.mark.unit
def test_ambient_out_of_repo_cache_dir_silently_falls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "outside" / "cache"
    monkeypatch.setenv("DUMMYINDEX_CACHE_DIR", str(outside))

    # No raise — the out-of-repo ambient value is ignored.
    result = cache_dir(root)

    assert result == (root / ".context" / "cache").resolve()
    assert not outside.exists(), "out-of-repo cache dir must not be created"


@pytest.mark.unit
def test_ambient_in_repo_cache_dir_is_honored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    inside = root / "custom" / "cache"
    monkeypatch.setenv("DUMMYINDEX_CACHE_DIR", str(inside))

    result = cache_dir(root)

    assert result == inside.resolve()


@pytest.mark.unit
def test_trusted_override_directs_cache_to_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    # An out-of-repo ambient value must NOT win over the trusted override.
    monkeypatch.setenv("DUMMYINDEX_CACHE_DIR", str(tmp_path / "outside"))
    target = root / ".context" / "cache"

    with cache_dir_override(target):
        result = cache_dir(root)

    assert result == target.resolve()
    # The user's env var is never mutated by the override.
    assert os.environ["DUMMYINDEX_CACHE_DIR"] == str(tmp_path / "outside")
    # Override cleared on exit.
    assert cache_dir(root) == (root / ".context" / "cache").resolve()


# ----- load_cached accept-superset schema -----------------------------------


def _write_raw_entry(root: Path, source: Path, payload: object) -> None:
    """Write a raw cache entry (bypassing save_cached's schema) at source's hash."""
    from dummyindex.pipeline.io.cache import cache_dir as _cd
    from dummyindex.pipeline.io.cache import file_hash

    h = file_hash(source, root)
    (_cd(root) / f"{h}.json").write_text(json.dumps(payload), encoding="utf-8")


@pytest.mark.unit
@pytest.mark.parametrize(
    "payload",
    [
        ["not", "a", "dict"],  # non-dict payload
        {"nodes": "x", "edges": []},  # nodes not list-typed
        {"nodes": [], "edges": {}},  # edges not list-typed
        {"nodes": [{"label": "no-id"}], "edges": []},  # node lacks string id
        {"nodes": [{"id": 123}], "edges": []},  # node id not a string
    ],
)
def test_load_cached_misses_on_malformed_payload(
    tmp_path: Path, payload: object
) -> None:
    root = tmp_path
    source = root / "mod.py"
    source.write_text("x = 1\n", encoding="utf-8")
    _write_raw_entry(root, source, payload)

    assert load_cached(source, root) is None


@pytest.mark.unit
def test_load_cached_hits_on_real_round_tripped_entry(tmp_path: Path) -> None:
    root = tmp_path
    source = root / "mod.py"
    source.write_text("x = 1\n", encoding="utf-8")
    result = {
        "nodes": [{"id": "n1", "label": "x"}],
        "edges": [{"source": "n1", "target": "n2"}],
    }

    save_cached(source, result, root)
    hit = load_cached(source, root)

    assert hit == result


@pytest.mark.unit
def test_load_cached_hits_with_unknown_keys(tmp_path: Path) -> None:
    # Unknown top-level keys are ignored (no mass invalidation).
    root = tmp_path
    source = root / "mod.py"
    source.write_text("y = 2\n", encoding="utf-8")
    payload = {"nodes": [{"id": "n1"}], "edges": [], "extra": "ignored"}
    _write_raw_entry(root, source, payload)

    assert load_cached(source, root) == payload


# ----- _body_content line-anchored frontmatter fence ------------------------


@pytest.mark.unit
def test_body_content_returns_body_below_closing_fence() -> None:
    content = (
        b"---\n"
        b"title: Doc\n"
        b"status: draft\n"
        b"---\n"
        b"# Heading\n"
        b"Body text\n"
        b"---\n"  # an in-body horizontal rule
        b"More text\n"
    )

    body = _body_content(content).decode()

    assert "title: Doc" not in body
    assert "# Heading" in body
    assert "More text" in body


@pytest.mark.unit
def test_body_content_non_bare_dash_hack_does_not_truncate() -> None:
    # A non-bare `---hack` line inside the frontmatter must NOT be treated as the
    # closing fence — the loose `find("\n---")` substring used to truncate here.
    content = (
        b"---\n"
        b"title: Doc\n"
        b"---hack\n"  # NOT a bare fence
        b"status: draft\n"
        b"---\n"  # the real closing fence
        b"# Body\n"
        b"Real content\n"
    )

    body = _body_content(content).decode()

    # The hack line did not close the frontmatter; the real body is returned.
    assert "status: draft" not in body
    assert "# Body" in body
    assert "Real content" in body


@pytest.mark.unit
def test_body_content_without_closing_fence_hashes_whole_file() -> None:
    content = b"---\ntitle: Doc\nstill frontmatter, no close\n"

    # No bare closing fence → whole-file fallback (no regression).
    assert _body_content(content) == content


@pytest.mark.unit
def test_body_content_no_frontmatter_returns_whole_file() -> None:
    content = b"# Just a heading\nNo frontmatter here\n"
    assert _body_content(content) == content


# ----- read_source_bytes seam + build-scoped read cache (P2) -----------------


@pytest.mark.unit
def test_read_source_bytes_reads_disk_outside_build_cache(tmp_path, monkeypatch):
    """Outside a build_read_cache block every call hits disk (prior behaviour)."""
    f = tmp_path / "a.py"
    f.write_bytes(b"x = 1\n")

    n = {"reads": 0}
    orig = Path.read_bytes

    def spy(self):
        n["reads"] += 1
        return orig(self)

    monkeypatch.setattr(Path, "read_bytes", spy)
    assert read_source_bytes(f) == b"x = 1\n"
    assert read_source_bytes(f) == b"x = 1\n"
    assert n["reads"] == 2  # no memoization without an open cache


@pytest.mark.unit
def test_build_read_cache_memoizes_one_disk_read_per_path(tmp_path, monkeypatch):
    """Inside build_read_cache, repeated reads of one path hit disk once and
    return identical bytes (the P2 collapse of hash + extractor reads)."""
    f = tmp_path / "a.py"
    f.write_bytes(b"x = 1\n")

    n = {"reads": 0}
    orig = Path.read_bytes

    def spy(self):
        n["reads"] += 1
        return orig(self)

    monkeypatch.setattr(Path, "read_bytes", spy)
    with build_read_cache():
        b1 = read_source_bytes(f)
        # file_hash also routes through the seam → memo hit, no extra disk read.
        _ = file_hash(f)
        b2 = read_source_bytes(f)
    assert b1 == b2 == b"x = 1\n"
    assert n["reads"] == 1


@pytest.mark.unit
def test_build_read_cache_pins_bytes_against_mid_block_mutation(tmp_path):
    """A file changed on disk after its first cached read still yields the
    ORIGINAL bytes for the rest of the block (one consistent byte-state)."""
    f = tmp_path / "a.py"
    f.write_bytes(b"ORIGINAL\n")
    with build_read_cache():
        first = read_source_bytes(f)
        f.write_bytes(b"MUTATED\n")
        second = read_source_bytes(f)
    assert first == second == b"ORIGINAL\n"
    # After the block exits the cache is cleared → a fresh read sees the change.
    assert read_source_bytes(f) == b"MUTATED\n"


@pytest.mark.unit
def test_build_read_cache_cleared_on_exit(tmp_path):
    """The cache does not bleed across builds: a new block re-reads disk."""
    f = tmp_path / "a.py"
    f.write_bytes(b"ONE\n")
    with build_read_cache():
        assert read_source_bytes(f) == b"ONE\n"
    f.write_bytes(b"TWO\n")
    with build_read_cache():
        assert read_source_bytes(f) == b"TWO\n"


# ----- scope_cache_to_version (extraction-cache version scope) --------------

_STAMP = "extraction-version"


def _seed_scoped_cache(
    cache: Path, *, stamp: str | None, entries: int = 3
) -> list[Path]:
    """Create a cache dir with ``entries`` hash entries, a manifest and a stamp."""
    cache.mkdir(parents=True)
    seeded = []
    for i in range(entries):
        entry = cache / f"{i:064x}.json"
        entry.write_text('{"nodes": [], "edges": []}', encoding="utf-8")
        seeded.append(entry)
    (cache / "manifest.json").write_text("{}\n", encoding="utf-8")
    if stamp is not None:
        (cache / _STAMP).write_bytes(f"{stamp}\n".encode())
    return seeded


@pytest.mark.unit
def test_scope_cache_mismatch_wipes_hash_entries_and_restamps(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    entries = _seed_scoped_cache(cache, stamp="0.36.0")
    (cache / "skill-feedback.json").write_text("{}\n", encoding="utf-8")
    (cache / "_enrich_plan.json").write_text("{}\n", encoding="utf-8")
    nested = cache / "sub"
    nested.mkdir()
    nested_entry = nested / f"{9:064x}.json"
    nested_entry.write_text("{}", encoding="utf-8")

    deleted = scope_cache_to_version(cache, "9.9.9")

    assert deleted == 3
    assert not any(e.exists() for e in entries)
    assert (cache / "manifest.json").read_text(encoding="utf-8") == "{}\n"
    assert (cache / "skill-feedback.json").exists()
    assert (cache / "_enrich_plan.json").exists()
    assert nested_entry.exists(), "only direct children are scoped"
    assert (cache / _STAMP).read_bytes() == b"9.9.9\n"
    assert not list(cache.glob("*.tmp")), "no tmp file left behind"


@pytest.mark.unit
def test_scope_cache_same_version_touches_nothing(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    entries = _seed_scoped_cache(cache, stamp="9.9.9")
    stamp_before = (cache / _STAMP).stat().st_mtime_ns

    assert scope_cache_to_version(cache, "9.9.9") == 0

    assert all(e.exists() for e in entries)
    assert (cache / _STAMP).read_bytes() == b"9.9.9\n"
    assert (cache / _STAMP).stat().st_mtime_ns == stamp_before


@pytest.mark.unit
def test_scope_cache_crlf_stamp_counts_as_same_version(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    entries = _seed_scoped_cache(cache, stamp=None)
    (cache / _STAMP).write_bytes(b"9.9.9\r\n")

    assert scope_cache_to_version(cache, "9.9.9") == 0
    assert all(e.exists() for e in entries)


@pytest.mark.unit
def test_scope_cache_missing_stamp_wipes_entries_and_writes_stamp(
    tmp_path: Path,
) -> None:
    cache = tmp_path / "cache"
    entries = _seed_scoped_cache(cache, stamp=None)

    assert scope_cache_to_version(cache, "9.9.9") == 3

    assert not any(e.exists() for e in entries)
    assert (cache / "manifest.json").exists()
    assert (cache / _STAMP).read_bytes() == b"9.9.9\n"


@pytest.mark.unit
def test_scope_cache_skips_symlink_named_like_an_entry(
    tmp_path: Path, real_symlinks: None
) -> None:
    cache = tmp_path / "cache"
    _seed_scoped_cache(cache, stamp="0.36.0", entries=1)
    outside = tmp_path / "outside.json"
    outside.write_bytes(b"outside-bytes")
    link = cache / f"{7:064x}.json"
    link.symlink_to(outside)

    assert scope_cache_to_version(cache, "9.9.9") == 1

    assert link.is_symlink(), "a linked entry is never deleted"
    assert outside.read_bytes() == b"outside-bytes"
    assert (cache / _STAMP).read_bytes() == b"9.9.9\n"


@pytest.mark.unit
def test_scope_cache_skips_reparse_point_named_like_an_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Runs everywhere (no symlink privilege needed): the lstat of one entry
    # reports a reparse point, as a Windows link would.
    cache = tmp_path / "cache"
    entries = _seed_scoped_cache(cache, stamp="0.36.0")
    linked = entries[1]
    real_lstat = os.lstat

    def fake_lstat(path, *args, **kwargs):
        if Path(path).name == linked.name:
            return SimpleNamespace(
                st_mode=stat.S_IFREG | 0o644,
                st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT,
            )
        return real_lstat(path, *args, **kwargs)

    monkeypatch.setattr(os, "lstat", fake_lstat)

    assert scope_cache_to_version(cache, "9.9.9") == 2

    assert linked.exists()
    assert not entries[0].exists() and not entries[2].exists()


@pytest.mark.unit
def test_scope_cache_unlink_failure_withholds_stamp_then_retries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = tmp_path / "cache"
    entries = _seed_scoped_cache(cache, stamp="0.36.0")
    stuck = entries[1]
    real_unlink = os.unlink

    def flaky_unlink(path, *args, **kwargs):
        if Path(path).name == stuck.name:
            raise PermissionError(13, "locked", str(path))
        return real_unlink(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(os, "unlink", flaky_unlink)
        assert scope_cache_to_version(cache, "9.9.9") == 2

    assert stuck.exists()
    assert not entries[0].exists() and not entries[2].exists()
    assert (cache / _STAMP).read_bytes() == b"0.36.0\n", "stamp not advanced"

    # The next run retries the leftover entry and then stamps.
    assert scope_cache_to_version(cache, "9.9.9") == 1
    assert not stuck.exists()
    assert (cache / _STAMP).read_bytes() == b"9.9.9\n"


@pytest.mark.unit
def test_scope_cache_missing_dir_returns_zero_and_does_not_create(
    tmp_path: Path,
) -> None:
    cache = tmp_path / ".context" / "cache"

    assert scope_cache_to_version(cache, "9.9.9") == 0

    assert not cache.exists()
    assert not cache.parent.exists()
