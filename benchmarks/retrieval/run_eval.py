"""Real-repo retrieval benchmark for `dummyindex context query`.

Clones pinned public repos (requests, flask, dummyindex itself), builds the
deterministic backbone `.context/` (no council enrichment, no paid APIs), then
scores natural-language questions whose gold answers are source files:

  hit@1 / hit@3 — does a top-k returned feature contain a gold file?
  MRR           — reciprocal rank of the first feature containing a gold file

Questions are split 50/50 into dev (for iterating) and holdout (untouched
while tuning) so improvements can't be silently overfit.

Usage:
    python benchmarks/retrieval/run_eval.py [--workdir PATH] [--split dev|holdout|both]

Baseline vs. current numbers are recorded in RESULTS.md.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

REPOS = {
    "requests": (
        "https://github.com/psf/requests.git",
        "3c7baaa05ab4aa49cc819ce3a819d260de19c157",
    ),
    "flask": (
        "https://github.com/pallets/flask.git",
        "49943b5a94413a530761350f04e896f76e8d620e",
    ),
    "dummyindex-self": (
        "https://github.com/MullaAhmed/dummyIndex.git",
        "38c360258b125d575807596efdcc4df333fc1f20",
    ),
    # Only used by the fresh validation set (questions_holdout3.json): no
    # tuning question touches it, so it measures cross-repo generalization.
    "click": (
        "https://github.com/pallets/click.git",
        "2247b35ea1c47c727d7a06e51fa280e12a863ff6",
    ),
}

QUESTIONS = pathlib.Path(__file__).with_name("questions.json")


def ensure_repo(workdir: pathlib.Path, name: str, url: str, sha: str) -> pathlib.Path:
    dest = workdir / name
    if not (dest / ".git").exists():
        subprocess.run(["git", "clone", "--quiet", url, str(dest)], check=True)
    subprocess.run(["git", "-C", str(dest), "checkout", "--quiet", sha], check=True)
    return dest


def ensure_index(repo_dir: pathlib.Path) -> pathlib.Path:
    """Always build a fresh deterministic backbone index.

    `--force` matters for dummyindex itself: the repo tracks its own
    council-enriched `.context/`, and benchmarking against it would mix
    index states (enriched for one repo, backbone for the others) and
    measure the enrichment, not the retrieval scoring.
    """
    context_dir = repo_dir / ".context"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "dummyindex",
            "context",
            "init",
            ".",
            "--root",
            ".",
            "--no-hooks",
            "--no-default-plugins",
            "--depth",
            "standard",
            "--force",
        ],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )
    return context_dir


def feature_files(context_dir: pathlib.Path) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for d in sorted((context_dir / "features").iterdir()):
        fj = d / "feature.json"
        if not fj.exists():
            continue
        try:
            payload = json.loads(fj.read_text(encoding="utf-8"))
        except Exception:
            continue
        files: set[str] = set()
        for f in payload.get("files") or []:
            if isinstance(f, str):
                files.add(f)
                files.add(f.rsplit("/", 1)[-1])
        out[payload.get("feature_id", d.name)] = files
    return out


def gold_matches(golds: list[str], ffiles: set[str]) -> bool:
    for g in golds:
        if g in ffiles or g.rsplit("/", 1)[-1] in ffiles:
            return True
        if not g.endswith(".py") and any(
            f.startswith(g.rstrip("/") + "/") for f in ffiles
        ):
            return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", default=".bench-repos")
    ap.add_argument(
        "--split", choices=["dev", "holdout", "both", "all"], default="both"
    )
    ap.add_argument(
        "--questions",
        default=None,
        help="Question file to evaluate (default: questions.json next to this script)",
    )
    args = ap.parse_args()

    from dummyindex.context.domains.query import query

    workdir = pathlib.Path(args.workdir)
    workdir.mkdir(exist_ok=True)
    questions_path = pathlib.Path(args.questions) if args.questions else QUESTIONS
    questions = json.loads(questions_path.read_text(encoding="utf-8"))

    if args.split == "all":
        # One unsplit bucket: for fresh validation sets where the dev/holdout
        # alternation is meaningless.
        questions = {
            r: [(q, g, "all") for q, g in items] for r, items in questions.items()
        }
        splits = ["all"]
    else:
        questions = {
            r: [(q, g, None) for q, g in items] for r, items in questions.items()
        }
        splits = ["dev", "holdout"] if args.split == "both" else [args.split]
    ranks: dict[str, list[int | None]] = {s: [] for s in splits}
    for repo, items in questions.items():
        url, sha = REPOS[repo]
        repo_dir = ensure_repo(workdir, repo, url, sha)
        context_dir = ensure_index(repo_dir)
        fmap = feature_files(context_dir)
        for i, (text, golds, forced) in enumerate(items):
            split = forced or ("dev" if i % 2 == 0 else "holdout")
            if split not in ranks:
                continue
            res = query(
                context_dir, text, top_k=10, budget_tokens=100000, max_bytes=65_536
            )
            if res.truncated:
                raise RuntimeError(
                    f"query output truncated for {repo}: {text!r}; "
                    "cannot score top-10 retrieval"
                )
            rank = None
            for r, m in enumerate(res.matches, start=1):
                if gold_matches(golds, fmap.get(m.feature.feature_id, set())):
                    rank = r
                    break
            ranks[split].append(rank)

    for split, rr in ranks.items():
        n = len(rr)
        hit1 = sum(1 for r in rr if r == 1) / n
        hit3 = sum(1 for r in rr if r is not None and r <= 3) / n
        mrr = sum(1.0 / r for r in rr if r) / n
        print(f"{split.upper()}: n={n} hit@1={hit1:.3f} hit@3={hit3:.3f} MRR={mrr:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
