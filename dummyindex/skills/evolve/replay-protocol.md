# Optional runtime replay and learning

The normal workflow needs no evaluation setup. An accepted closeout can include
`learning_reflection` with a verified rule ID, target, body, expected document
hash, source files and existing project tests. Closeout runs one candidate through
the existing exact gate and recoverable promotion. No supported lesson means
`no_entry`; missing checks mean `evaluated/blocked`, not applied.

For actual agent behavior, supply an explicit trusted executor/evaluator:

```sh
dummyindex context evolve experiment --run repair \
  --command '["python","tools/replay.py"]' \
  --case tests/cases/development.json --heldout tests/cases/heldout.json \
  --candidate 0 --model your-model --rubric artifact-check-v1
```

The candidate is already validated/staged by the ordinary evolve workflow. A
specification file additionally supports `general`, `domain` and `composition`
candidate indices, explicit case IDs/splits/required controls, guidance IDs,
`seed`, independent `repetition` and a resource `budget`. Both lenses execute
before a supported composition. Failed compositions leave the incumbent eligible.

The command receives `--request FILE` in an isolated captured project snapshot.
The JSON request includes model/rubric identities, cases, seed/repetition,
remaining `max_tokens`/`max_cost_usd`, and required guidance records with
`id`, `version`, `path`, `sha256`. It must actually invoke the agent, evaluate its
artifacts independently, and return one JSON object on stdout:

```json
{"status":"measured","cases":[{"id":"case-id","status":"pass"}],"tokens":120,"cost_usd":0.01,"loaded":[{"id":"guidance-id","version":"exact-version","sha256":"exact-body-hash"}],"evidence":"Independent artifact check and execution trace locator"}
```

Each requested case must appear exactly once. Failed required controls veto a
candidate regardless of aggregate quality. All required body loads must match
the supplied identities; mere role declarations do not qualify. Available but
unused skills receive no utility attribution. Infrastructure errors return
`status: infra_error`, `reason`, and known `tokens`/`cost_usd`; unknown accounting
stops further execution. Include all paid calls, retries, selectors and reflection
inside the executor's reservation and returned accounting.

Selection uses development/validation cases, then executes both incumbent and
selected candidate on held-out cases. Held-out files are absent from development
snapshots; durable exposure ancestry rejects re-labelled development cases.
The `current` pointer is an experiment recommendation. Applying guidance still
uses the ordinary exact project gate and recoverable promotion.

Defaults are six execution stages, 120 seconds, 20,000 tokens, $2, two
non-improving probes and no infrastructure retries. Stage/retry budgets and
wall-time/output monitoring include every scheduled call. Timeout or output
overflow kills the process tree/group. The trusted runner must reserve token and
cost limits before provider calls; returned spending is checked but provider
billing is outside the controller. Output growth is polled, so short bursts can
exceed the 64 KB receipt limit before termination.

Valid receipts reuse exact baseline/candidate/cases/model/environment/evaluator/
rubric/seed/repetition identities. Changed inputs or deliberate repetitions run
again. Temporary trees expire after execution; compact outcomes and per-version
utility remain. Two failed trials mark a version suspect for repair; low usage
alone never causes deletion. The repository's deterministic process fixtures
verify this protocol and control flow, not measured LLM improvement.
