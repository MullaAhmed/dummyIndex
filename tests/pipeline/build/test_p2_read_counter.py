"""Each source file is read at most twice per build.

Every read site goes through ``Path.read_bytes``/``read_text``, so the spy is
path-keyed. Pinned: one ``extract`` + ``build_structure`` pass reads each source
file at most twice; a file mutated after its first read yields one consistent
byte-state; the threaded-bytes reference pass is byte-identical to the disk-read
pass.
"""

from __future__ import annotations

import collections
import shutil
from pathlib import Path

import pytest

from dummyindex.pipeline.build import build_structure
from dummyindex.pipeline.extract import collect_files, extract

SAMPLE_REPO = Path(__file__).resolve().parents[2] / "fixtures" / "sample_repo"


def _spy_reads(monkeypatch) -> dict[str, int]:
    """Install a path-keyed counter over both byte/text read primitives.

    The three deduped sites (``generic.py``/``cache.py``/the cross-file
    resolvers) all call ``Path.read_bytes``; ``references.py``'s disk fallback
    uses ``Path.read_text`` — both are counted so a bypass cannot hide.
    """
    counts: dict[str, int] = collections.defaultdict(int)
    orig_rb = Path.read_bytes
    orig_rt = Path.read_text

    def spy_rb(self):
        counts[str(self)] += 1
        return orig_rb(self)

    def spy_rt(self, *a, **k):
        counts[str(self)] += 1
        return orig_rt(self, *a, **k)

    monkeypatch.setattr(Path, "read_bytes", spy_rb)
    monkeypatch.setattr(Path, "read_text", spy_rt)
    return counts


@pytest.mark.integration
def test_each_source_file_read_at_most_twice(tmp_path, monkeypatch):
    """One extract + build_structure pass reads each .py/.java file at most twice."""
    repo = tmp_path / "repo"
    shutil.copytree(SAMPLE_REPO, repo)
    files = collect_files(repo, root=repo)

    counts = _spy_reads(monkeypatch)
    extraction = extract(files, cache_root=repo)
    build_structure(extraction, files, repo, include_extras=False)

    code_counts = {f: c for f, c in counts.items() if f.endswith((".py", ".java"))}
    assert code_counts, "sample repo must contain code files to count"
    for f, c in code_counts.items():
        assert c <= 2, f"{f} read {c} times (> 2): {dict(code_counts)}"


@pytest.mark.integration
def test_extract_returns_threaded_file_bytes(tmp_path):
    """extract() carries the bytes it read, keyed by str(path), for reuse by the
    textual-reference pass."""
    repo = tmp_path / "repo"
    shutil.copytree(SAMPLE_REPO, repo)
    files = collect_files(repo, root=repo)

    extraction = extract(files, cache_root=repo)
    file_bytes = extraction["file_bytes"]
    assert isinstance(file_bytes, dict)
    code = [p for p in files if p.suffix in (".py", ".java")]
    assert code, "sample repo must contain code files"
    for p in code:
        assert str(p) in file_bytes
        assert file_bytes[str(p)] == p.read_bytes()


@pytest.mark.integration
def test_threaded_bytes_reference_pass_is_byte_identical(tmp_path):
    """The threaded-bytes textual-reference pass produces exactly the same
    cross-edges as the disk-read pass (perf change is output-invariant)."""
    repo = tmp_path / "repo"
    shutil.copytree(SAMPLE_REPO, repo)
    files = collect_files(repo, root=repo)

    extraction = extract(files, cache_root=repo)
    threaded = build_structure(extraction, files, repo, include_extras=False)

    # Force the disk path by stripping the threaded bytes.
    disk_extraction = dict(extraction)
    disk_extraction["file_bytes"] = {}
    disk = build_structure(disk_extraction, files, repo, include_extras=False)

    assert threaded["cross_edges"] == disk["cross_edges"]
    assert threaded["nodes"] == disk["nodes"]


@pytest.mark.integration
def test_mid_build_mutation_yields_one_consistent_byte_state(tmp_path, monkeypatch):
    """A file mutated on disk after its first read is seen with one byte-state.

    The build-scoped read cache pins the first-read bytes, so the reference pass
    sees what the hash/extractor saw, not the later mutation."""
    repo = tmp_path / "repo"
    repo.mkdir()
    src = repo / "mod.py"
    src.write_text("def alpha():\n    pass\n# mentions other.py\n")
    other = repo / "other.py"
    other.write_text("def beta():\n    pass\n")
    files = collect_files(repo, root=repo)

    from dummyindex.pipeline.io import cache as cache_mod

    original = cache_mod.read_source_bytes
    mutated_after_first_read: dict[str, bool] = {}

    def mutating_read(path):
        data = original(path)
        # After the FIRST read of mod.py, corrupt it on disk. Any later disk
        # read would observe the mutation; the cache must serve the originals.
        key = str(path)
        if key.endswith("mod.py") and key not in mutated_after_first_read:
            mutated_after_first_read[key] = True
            Path(path).write_bytes(b"GARBAGE_MUTATED_CONTENT\n")
        return data

    monkeypatch.setattr(cache_mod, "read_source_bytes", mutating_read)
    # extract imports the name directly, so patch its binding too.
    import dummyindex.pipeline.extract as extract_mod

    monkeypatch.setattr(extract_mod, "read_source_bytes", mutating_read)

    extraction = extract(files, cache_root=repo)

    # The threaded bytes for mod.py must be the ORIGINAL content, never the
    # garbage written mid-build.
    threaded = extraction["file_bytes"][str(src)]
    assert b"GARBAGE_MUTATED_CONTENT" not in threaded
    assert b"def alpha" in threaded

    # And build_structure (which runs the reference pass on those bytes) must
    # not surface the mutated content either.
    structure = build_structure(extraction, files, repo, include_extras=False)
    blob = repr(structure["nodes"]) + repr(structure["cross_edges"])
    assert "GARBAGE_MUTATED_CONTENT" not in blob
