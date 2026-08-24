"""Head-to-head benchmark harness: opencode (raw) vs opencode + `.context/`.

Two arms, one model, identical prompts — only the context backend differs:

- ``Arm.BASELINE`` ("C"): a fresh clone of the target repo at a pinned commit,
  with a minimal neutral ``AGENTS.md``. The agent navigates with its own
  glob/grep tools.
- ``Arm.CONTEXT`` ("A"): the same clone at the same commit, plus a
  deterministic `dummyindex ingest` backbone (`.context/` map + features) and
  the same neutral ``AGENTS.md`` extended with the `.context/` navigation
  section. The agent walks the index instead of grepping.

Suites:

- **RepoQA SNF** (`suites/repoqa.py`) — Searching Needle Function tasks from
  the public RepoQA dataset; graded by the official case-insensitive substring
  rule (`scoring/snf.py`).
- **SWE-bench Lite subset** (`suites/swebench.py`) — end-to-end issue
  resolution; patches are extracted (`scoring/swebench_patch.py`) and graded
  by the official dockerized SWE-bench harness (`scoring/swegrade.sh`).

Everything that spends money is double-gated: the CLI needs both
``--execute`` and ``DUMMYINDEX_BENCH_ALLOW_PAY=1``, mirroring the opt-in
discipline of ``tests/eval/test_behavior_arms.py``. Without them every entry
point is a dry-run planner.

Run ``python -m benchmarks plan`` to see the full matrix without spending
anything.
"""

from __future__ import annotations

BENCHMARKS_VERSION = "0.1.0"

PAY_GATE_ENV = "DUMMYINDEX_BENCH_ALLOW_PAY"
