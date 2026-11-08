# Checklist — Trim long code comments repo-wide (dummyindex/ + tests/) to the non-obvious why, no behavior change

## Wave 1 — package units (disjoint dirs)
- [x] U1 trim comments/docstrings in dummyindex/context/domains/{features,debt,preflight,doc_reorg}/
- [x] U2 trim comments/docstrings in dummyindex/context/domains/{equip,proposals,graph_query}/
- [x] U3 trim comments/docstrings in files directly in dummyindex/context/domains/ and {source_docs,audit}/
- [x] U4 trim comments/docstrings in dummyindex/context/domains/{buildloop,memory,gc}/ (miner Apache attribution verbatim)
- [x] U5 trim comments/docstrings in dummyindex/context/domains/{reality_check,docguard}/, context/output/, usage/, analysis/, export/
- [x] U6 trim comments/docstrings in dummyindex/cli/** (onboard keywords, statusline badge semantics kept)
- [x] U7 trim comments/docstrings in dummyindex/context/build/** (upgrade.py renderer literals byte-identical)
- [x] U8 trim comments/docstrings in dummyindex/*.py, dummyindex/context/*.py, context/schemas/, skills/**/*.py

## Wave 2 — installer, pipeline, tests (disjoint dirs)
- [x] U9 trim comments/docstrings in dummyindex/installer/**
- [x] U10 trim comments/docstrings in dummyindex/pipeline/**
- [x] U11 trim comments/docstrings in tests/eval/** and tests/*.py (MIT attribution with holder verbatim)
- [x] U12 trim comments/docstrings in tests/{cli,context,pipeline,analysis,export,usage}/** (canary SCOPE/COUPLING HOLE kept)

## Wave 3 — acceptance (after all units stop)
- [x] Acceptance: ast_equiv.py reports 0 CODE/LOST/NEW/GONE/PARSE, scope check lists only modified non-fixture .py files, license-line grep of removed lines is empty
- [x] Acceptance: ruff check dummyindex tests passes, ruff format --check passes on changed files (minus the 7), full pytest ends exactly 3562 passed, 168 skipped
- [x] Acceptance: comment_scan --doc-min 9 combined <= 2,824 (dummyindex) and <= 740 (tests), bytes cut >= 25% per tree, 0 rows missing from exceptions.md

## Wave 4 — quality review
- [x] Acceptance: sampled review of 24 top-cut files plus every WARN file answers yes to all 4 questions, verdicts in review.md
